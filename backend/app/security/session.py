import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.db import Store, database
from app.errors import ApiError, forbidden
from app.security.proxy import client_address
from app.services.households import token_hash

Database = Annotated[Store, Depends(database, scope="function")]
PUBLIC = {
    "/api/auth/csrf",
    "/api/auth/register",
    "/api/auth/login",
    "/api/health",
    "/api/auth/capabilities",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-email",
    "/actuator/health/liveness",
    "/actuator/health/readiness",
}


def set_cookie(request: Request, response: Response, token: str):
    config = request.app.state.settings
    response.set_cookie(
        "JSESSIONID",
        token,
        httponly=True,
        secure=config.cookie_secure,
        samesite=config.cookie_same_site,
        path="/",
    )


def new_session(request: Request, response: Response, db: Store, user: UUID | None = None):
    config = request.app.state.settings
    if user is None:
        # Reuse needs no new allocation. New sessions share a peer budget behind staging.
        consume_rate(request, None, ("session_creation", config.rate_session_creation))
        db.execute("SELECT pg_advisory_xact_lock(731924, 2)")
    db.execute("DELETE FROM web_session WHERE expires_at<CURRENT_TIMESTAMP")
    if (
        user is None
        and db.one("SELECT COUNT(*) AS n FROM web_session WHERE user_id IS NULL")["n"]
        >= config.anonymous_session_limit
    ):
        raise ApiError(429, "RATE_LIMITED", "Session capacity reached. Please try again later.")
    old = getattr(request.state, "session", None)
    csrf = old["csrf_token"] if old else secrets.token_urlsafe(32)
    if old:
        db.execute("DELETE FROM web_session WHERE token_hash=:token", token=old["token_hash"])
    token = secrets.token_urlsafe(32)
    version = (
        db.one("SELECT session_version FROM app_user WHERE id=:u", u=user)["session_version"]
        if user
        else 0
    )
    row = dict(
        token_hash=token_hash(token),
        csrf_token=csrf,
        user_id=user,
        session_version=version,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=request.app.state.settings.session_timeout_seconds),
    )
    db.execute(
        "INSERT INTO web_session(token_hash,csrf_token,user_id,session_version,expires_at) VALUES(:token_hash,:csrf_token,:user_id,:session_version,:expires_at)",
        **row,
    )
    request.state.session = row
    set_cookie(request, response, token)
    return row


def sign_out(request: Request, response: Response, db: Store):
    if request.state.session:
        db.execute(
            "DELETE FROM web_session WHERE token_hash=:token",
            token=request.state.session["token_hash"],
        )
    response.delete_cookie(
        "JSESSIONID",
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite=request.app.state.settings.cookie_same_site,
    )


def rate_limit(request: Request, user: UUID | None):
    path, config = request.url.path, request.app.state.settings
    if request.method != "POST":
        return
    actions = {
        "/api/auth/login": ("login", config.rate_login),
        "/api/auth/register": ("registration", config.rate_registration),
        "/api/auth/forgot-password": ("password_reset", config.rate_password_reset),
        "/api/auth/reset-password": ("reset_confirm", config.rate_reset_confirm),
        "/api/auth/verify-email": ("verification", config.rate_verification),
        "/api/account/resend-verification": ("verification", config.rate_verification),
        "/api/receipts/extract": ("extraction", config.rate_extraction),
        "/api/account/password": ("account", config.rate_account),
        "/api/account/deactivate": ("account", config.rate_account),
    }
    action = actions.get(path)
    if path.endswith(("/invitations", "/invitations/email")):
        action = ("invitations", config.rate_invitations)
    if user:
        consume_rate(request, user, ("writes", config.rate_writes))
    if action:
        consume_rate(request, user, action)


def consume_rate(request: Request, user: UUID | None, action: tuple[str, int]):
    config = request.app.state.settings
    peer = request.client.host if request.client else "unknown"
    subject = token_hash(
        str(user)
        if user
        else client_address(
            peer, request.headers.get("x-forwarded-for", ""), config.trusted_proxy_cidrs
        )
    )
    # Independent commit records failed attempts; PostgreSQL synchronizes all workers.
    with Session(request.app.state.rate_engine) as session, session.begin():
        db = Store(session)
        db.execute("DELETE FROM abuse_window WHERE expires_at<CURRENT_TIMESTAMP")
        row = db.one(
            """INSERT INTO abuse_window(subject_hash,action,expires_at,attempts)
            VALUES(:subject,:action,:expiry,1)
            ON CONFLICT(subject_hash,action) DO UPDATE SET attempts=abuse_window.attempts+1
            RETURNING attempts""",
            subject=subject,
            action=action[0],
            expiry=datetime.now(timezone.utc) + timedelta(seconds=config.rate_window_seconds),
        )
    if row["attempts"] > action[1]:
        raise ApiError(429, "RATE_LIMITED", "Too many attempts. Please try again later.")


def security(request: Request, db: Database):
    config = request.app.state.settings
    raw = request.cookies.get("JSESSIONID", "")
    rows = (
        db.all(
            "SELECT * FROM web_session WHERE token_hash=:token AND expires_at>CURRENT_TIMESTAMP",
            token=token_hash(raw),
        )
        if raw
        else []
    )
    row = rows[0] if rows else None
    request.state.session = row
    user = row["user_id"] if row else None
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-TOKEN", "")
        if row is None or not secrets.compare_digest(csrf, row["csrf_token"]):
            raise forbidden()
    if user:
        account = db.one(
            "SELECT deactivated,session_version,email_verified FROM app_user WHERE id=:u", u=user
        )
        if account["deactivated"] or account["session_version"] != row["session_version"]:
            raise ApiError(401, "UNAUTHORIZED", "Please sign in.")
        if (
            config.email_verification_required
            and not account["email_verified"]
            and not request.url.path.startswith(("/api/auth/", "/api/account/"))
            and request.url.path != "/api/profile"
        ):
            raise ApiError(403, "EMAIL_UNVERIFIED", "Verify your email before using your ledger.")
    elif request.url.path not in PUBLIC:
        raise ApiError(401, "UNAUTHORIZED", "Please sign in.")
    rate_limit(request, user)
    if row:
        db.execute(
            "UPDATE web_session SET expires_at=:expiry WHERE token_hash=:token",
            expiry=datetime.now(timezone.utc) + timedelta(seconds=config.session_timeout_seconds),
            token=row["token_hash"],
        )
    request.state.user = user


def identity(request: Request) -> UUID:
    user = request.state.user
    if not user:
        raise ApiError(401, "UNAUTHORIZED", "Please sign in.")
    return user


User = Annotated[UUID, Depends(identity)]
