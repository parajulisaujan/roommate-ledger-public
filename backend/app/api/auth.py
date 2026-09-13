from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response

from app.errors import ApiError, invalid
from app.schemas import (
    Address,
    Credentials,
    Password,
    Passwords,
    Profile,
    ProfileInput,
    Reset,
    Token,
)
from app.security.session import Database, User, new_session, sign_out
from app.services.accounts import Accounts, password_hash, password_matches

router = APIRouter(tags=["Authentication and account"])


def accounts(request: Request, db: Database) -> Accounts:
    return Accounts(db, request.app.state.settings, request.app.state.email)


def profile(request: Request, db: Database, user: UUID):
    row = db.one(
        "SELECT id,name,email,diet,timezone,currency,notifications,email_verified FROM app_user WHERE id=:u",
        u=user,
    )
    row["verification_required"] = request.app.state.settings.email_verification_required
    return row


@router.get("/auth/csrf")
def csrf(request: Request, response: Response, db: Database):
    row = request.state.session or new_session(request, response, db)
    return {"token": row["csrf_token"], "headerName": "X-CSRF-TOKEN"}


@router.post("/auth/register", response_model=Profile)
def register(data: Credentials, request: Request, response: Response, db: Database):
    if not data.name or not data.name.strip():
        raise invalid("Enter your name.")
    user = uuid4()
    db.execute(
        "INSERT INTO app_user(id,name,email,password_hash) VALUES(:id,:name,:email,:password)",
        id=user,
        name=data.name.strip(),
        email=data.email,
        password=password_hash(data.password),
    )
    new_session(request, response, db, user)
    accounts(request, db).issue(user, "VERIFY")
    return profile(request, db, user)


@router.post("/auth/login", response_model=Profile)
def login(data: Credentials, request: Request, response: Response, db: Database):
    rows = db.all(
        "SELECT id,password_hash FROM app_user WHERE email=:email AND deactivated=false",
        email=data.email,
    )
    encoded = (
        rows[0]["password_hash"]
        if rows
        else "$2a$12$abcdefghijklmnopqrstuuCqM0mb.YBBn8x00oAoTPNKaCZLH6bhS"
    )
    if not password_matches(data.password, encoded) or not rows:
        raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    user = rows[0]["id"]
    new_session(request, response, db, user)
    return profile(request, db, user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Database):
    sign_out(request, response, db)


@router.get("/auth/me", response_model=Profile)
def me(request: Request, db: Database, user: User):
    return profile(request, db, user)


@router.patch("/profile", response_model=Profile)
def update_profile(data: ProfileInput, request: Request, db: Database, user: User):
    db.execute(
        "UPDATE app_user SET name=:name,diet=:diet,timezone=:timezone,notifications=:notifications WHERE id=:id",
        id=user,
        **data.model_dump(),
    )
    return profile(request, db, user)


@router.get("/auth/capabilities")
def capabilities(request: Request, db: Database):
    return accounts(request, db).capabilities()


@router.post("/auth/forgot-password")
def forgot(data: Address, request: Request, db: Database):
    accounts(request, db).request_reset(data.email)
    return {
        "message": "If this address has an active account and email delivery is available, a reset link will be sent."
    }


@router.post("/auth/reset-password")
def reset(data: Reset, request: Request, db: Database):
    accounts(request, db).reset(data.token, data.password)
    return {"message": "Password reset. Sign in with your new password."}


@router.post("/auth/verify-email")
def verify(data: Token, request: Request, db: Database):
    accounts(request, db).verify(data.token)
    return {"message": "Email verified. You can continue to your ledger."}


@router.post("/account/resend-verification")
def resend(request: Request, db: Database, user: User):
    accounts(request, db).issue(user, "VERIFY")
    return {
        "message": "If verification is needed and email delivery is available, a new link will be sent."
    }


@router.post("/account/password")
def change_password(
    data: Passwords, request: Request, response: Response, db: Database, user: User
):
    accounts(request, db).change_password(user, data.currentPassword, data.password)
    sign_out(request, response, db)


@router.post("/account/deactivate")
def deactivate(data: Password, request: Request, response: Response, db: Database, user: User):
    accounts(request, db).deactivate(user, data.password)
    sign_out(request, response, db)
