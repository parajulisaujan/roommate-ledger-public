import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.cors import CORSMiddleware

from app.ai.receipts import HttpReceiptProvider
from app.api import auth, exports, ledger, receipts
from app.config import Settings
from app.db import engine_for
from app.errors import ApiError
from app.logging import configure as configure_logging
from app.schemas import ErrorOutput
from app.security.ingress import DeploymentIngress
from app.security.session import security
from app.services.accounts import SmtpEmailProvider

logger = logging.getLogger("roommateledger")


class RequestBoundary:
    """Bound actual request bytes, including chunked bodies, before multipart parsing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        reference = str(uuid4())
        scope.setdefault("state", {})["request_id"] = reference
        limit = 9 * 1024 * 1024 if scope["path"] == "/api/receipts/extract" else 1024 * 1024
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > limit:
                raise ApiError(413, "FILE_TOO_LARGE", "Use a receipt image smaller than 8 MB.")
            return message

        async def headers(message):
            if message["type"] == "http.response.start":
                message["headers"] += [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-request-id", reference.encode()),
                ]
            await send(message)

        await self.app(scope, bounded_receive, headers)


def create_app(settings: Settings | None = None, engine=None, email=None, receipt_provider=None):
    config = settings or Settings()
    if config.production:
        configure_logging()
    owned_engine = engine is None
    db_engine = engine or engine_for(config)
    # A separate bounded pool prevents requests holding ledger connections from
    # exhausting the connections needed to commit independent rate-limit attempts.
    rate_engine = engine_for(config, pool_size=2, max_overflow=0)

    @asynccontextmanager
    async def lifespan(app):
        yield
        rate_engine.dispose()
        if owned_engine:
            db_engine.dispose()

    app = FastAPI(
        title="RoommateLedger",
        version="2.0.0",
        lifespan=lifespan,
        description="USD integer-cent ledger. Authenticate using an HttpOnly JSESSIONID cookie. Obtain a synchronizer token from GET /api/auth/csrf and send X-CSRF-TOKEN on every mutation, including login and registration. Receipts are draft data until explicitly confirmed.",
        docs_url=None if config.production else "/docs",
        redoc_url=None,
        openapi_url=None if config.production else "/openapi.json",
    )
    app.state.settings, app.state.engine = config, db_engine
    app.state.rate_engine = rate_engine
    app.state.email = email or SmtpEmailProvider(config)
    app.state.receipts = receipt_provider or HttpReceiptProvider(config)
    app.add_middleware(RequestBoundary)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-TOKEN", "Idempotency-Key"],
        max_age=3600,
    )
    if config.deployment_proxy_required:
        app.add_middleware(DeploymentIngress, key=config.deployment_proxy_key.get_secret_value())

    @app.exception_handler(ApiError)
    async def domain_error(request: Request, error: ApiError):
        headers = {"Retry-After": str(config.rate_window_seconds)} if error.status == 429 else {}
        response = JSONResponse(
            {"code": error.code, "message": str(error)}, status_code=error.status, headers=headers
        )
        if error.status == 401:
            response.delete_cookie(
                "JSESSIONID",
                path="/",
                secure=config.cookie_secure,
                httponly=True,
                samesite=config.cookie_same_site,
            )
        return response

    async def validation_error(request: Request, error):
        return JSONResponse(
            {
                "code": "VALIDATION_ERROR",
                "message": "Check the required fields, dates and amounts.",
            },
            status_code=400,
        )

    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(ValidationError, validation_error)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error):
        return JSONResponse(
            {
                "code": "CONFLICT",
                "message": "This record conflicts with existing data. Refresh and try again.",
            },
            status_code=409,
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error):
        reference = getattr(request.state, "request_id", str(uuid4()))
        logger.error(
            "request_failed reference=%s exception_type=%s", reference, type(error).__name__
        )
        return JSONResponse(
            {
                "code": "INTERNAL_ERROR",
                "message": "Something went wrong. Retry or contact support with reference "
                + reference,
            },
            status_code=500,
            headers={"X-Request-ID": reference, "Cache-Control": "no-store"},
        )

    for router in (auth.router, ledger.router, receipts.router, exports.router):
        app.include_router(
            router,
            prefix="/api",
            dependencies=[Depends(security)],
            responses={
                status: {"model": ErrorOutput}
                for status in (400, 401, 403, 404, 409, 413, 429, 500, 503)
            },
        )

    @app.get("/health", tags=["Health"])
    @app.get("/api/health", tags=["Health"])
    def health():
        return {"status": "ok"}

    @app.get("/actuator/health/liveness", tags=["Health"])
    def liveness():
        return {"status": "UP"}

    @app.get("/actuator/health/readiness", tags=["Health"])
    def readiness():
        try:
            with db_engine.connect() as connection:
                connection.execute(
                    text(
                        "SELECT 1 FROM alembic_version WHERE version_num='0003_request_idempotency'"
                    )
                ).scalar_one()
            return {"status": "UP"}
        except Exception:
            return JSONResponse({"status": "DOWN"}, status_code=503)

    return app


app = create_app()
