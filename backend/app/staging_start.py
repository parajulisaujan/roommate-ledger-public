"""Guarded startup migrations for the Render Free / Neon / Mailtrap sandbox recipe."""

import logging
import ssl
import sys
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import text

from alembic import command
from app.config import Settings
from app.db import engine_for

# Exact allowlist of model-validator messages owned by config.py. Never use
# substring matches: library errors may interpolate rejected values.
MODEL_VALIDATION_CODES = {
    "Protected ingress requires a deployment proxy key of at least 32 characters.": "deployment_proxy_key_invalid",
    "Trust specific proxy networks, never all addresses.": "trusted_proxy_invalid",
    "Rate limits and window must be between 1 and 86400.": "rate_limit_invalid",
    "CORS requires exact HTTP(S) origins without paths or wildcards.": "cors_invalid",
    "Invalid cookie SameSite.": "cookie_same_site_invalid",
    "SameSite=None requires Secure cookies.": "cookie_secure_invalid",
    "Session timeout must be between 60 and 86400 seconds.": "session_timeout_invalid",
    "Production CORS origins require HTTPS.": "cors_invalid",
    "Production requires an exact public HTTPS FRONTEND_URL.": "frontend_url_invalid",
    "Production requires COOKIE_SECURE=true.": "cookie_secure_invalid",
    "Production requires SMTP delivery with STARTTLS.": "smtp_configuration_invalid",
    "Production requires SMTP_HOST.": "smtp_host_missing",
    "Production requires EMAIL_FROM.": "email_from_missing",
    "Production requires SMTP_STARTTLS=true.": "smtp_starttls_disabled",
    "Production requires email verification.": "email_verification_invalid",
    "Unknown receipt provider.": "receipt_provider_invalid",
    "Receipt adapter requires HTTPS without embedded credentials.": "receipt_provider_invalid",
}
FIELD_VALIDATION_CODES = {
    "deployment_proxy_key": "deployment_proxy_key_invalid",
    "frontend_url": "frontend_url_invalid",
    "cookie_secure": "cookie_secure_invalid",
    "cookie_same_site": "cookie_same_site_invalid",
    "email_verification_required": "email_verification_invalid",
    "cors_allowed_origins": "cors_invalid",
    "trusted_proxy_cidrs": "trusted_proxy_invalid",
    "app_env": "app_env_invalid",
    "session_timeout_seconds": "session_timeout_invalid",
    "smtp_host": "smtp_configuration_invalid",
    "smtp_port": "smtp_port_invalid",
    "smtp_username": "smtp_username_invalid",
    "smtp_password": "smtp_password_invalid",
    "smtp_starttls": "smtp_starttls_invalid",
    "smtp_timeout_seconds": "smtp_timeout_invalid",
    "email_from": "smtp_configuration_invalid",
    **{
        name: "receipt_provider_invalid"
        for name in (
            "receipt_provider",
            "receipt_provider_url",
            "receipt_provider_api_key",
            "receipt_timeout_seconds",
            "openai_api_key",
            "openai_receipt_model",
        )
    },
    **{name: "rate_limit_invalid" for name in Settings.model_fields if name.startswith("rate_")},
}
FIELD_TYPE_ERRORS = frozenset(
    {
        "bool_parsing",
        "bool_type",
        "int_parsing",
        "int_type",
        "int_from_float",
        "float_parsing",
        "float_type",
        "string_type",
        "string_unicode",
    }
)
SETTINGS_FIELDS = frozenset(Settings.model_fields)


def settings_validation_codes(error: ValidationError) -> list[str]:
    codes = set()
    for detail in error.errors(include_input=False, include_context=False, include_url=False):
        location = detail["loc"]
        if not location:
            # Pydantic prefixes ValueError messages; compare the entire message.
            codes.add(
                next(
                    (
                        code
                        for message, code in MODEL_VALIDATION_CODES.items()
                        if detail["msg"] == "Value error, " + message
                    ),
                    "settings_validation_unknown",
                )
            )
        elif len(location) == 1 and location[0] in SETTINGS_FIELDS:
            codes.add(FIELD_VALIDATION_CODES.get(location[0], "field_type_invalid"))
            if detail["type"] in FIELD_TYPE_ERRORS:
                codes.add("field_type_invalid")
        else:
            codes.add("settings_validation_unknown")
    return sorted(codes or {"settings_validation_unknown"})


@contextmanager
def stage(name):
    """Only caller-owned labels cross the diagnostic boundary, never exception text."""
    print(f"STAGING START {name}", flush=True)
    try:
        yield
    except BaseException:
        print(f"STAGING FAIL {name}", file=sys.stderr, flush=True)
        raise
    print(f"STAGING PASS {name}", flush=True)


def validate_staging(settings: Settings):
    url = settings.sqlalchemy_url
    if not (
        settings.app_env == "staging"
        and settings.deployment_proxy_required
        and url.database == "roommateledger_staging"
        and url.host
        and url.host.endswith(".neon.tech")
        and url.query.get("sslmode") == "verify-full"
        and url.query.get("sslrootcert") == "/etc/ssl/certs/ca-certificates.crt"
        and settings.smtp_host == "sandbox.smtp.mailtrap.io"
        and settings.smtp_port == 2525
        and settings.smtp_starttls
        and settings.smtp_username
        and settings.smtp_password
        and not settings.openai_api_key
        and not settings.receipt_provider_api_key
    ):
        raise RuntimeError("Free staging configuration rejected; check the staging runbook.")
    with stage("ca_bundle"):
        path = Path("/etc/ssl/certs/ca-certificates.crt")
        if not path.is_file():
            raise RuntimeError("CA bundle missing.")
        ssl.create_default_context(cafile=str(path))


def prepare(settings: Settings):
    with stage("staging_configuration"):
        validate_staging(settings)
    with stage("database_connection"):
        engine = engine_for(settings, migration=True)
    try:
        with stage("database_connection"):
            try:
                connection = engine.connect()
            except Exception as exc:
                # libpq does not supply SQLSTATE for TLS handshake failures. Inspect
                # known markers internally, but never emit any part of the message.
                if any(
                    marker in str(exc).lower()
                    for marker in (
                        "certificate verify failed",
                        "root certificate",
                        "ssl certificate",
                        "does not match host name",
                        "server does not support ssl",
                    )
                ):
                    print("STAGING FAIL database_tls_handshake", file=sys.stderr, flush=True)
                raise
        with connection:
            with stage("database_identity"):
                if (
                    connection.execute(text("SELECT current_database()")).scalar_one()
                    != "roommateledger_staging"
                ):
                    raise RuntimeError("Unexpected staging database.")
            with stage("database_tls"):
                # SQLAlchemy's public driver_connection exposes psycopg.Connection.
                # PGconn.ssl_in_use wraps libpq PQsslInUse (a boolean). Inspect the
                # client socket: pg_stat_ssl describes the server-side proxy hop.
                # Missing/unsupported inspection raises inside the sanitized stage.
                if connection.connection.driver_connection.pgconn.ssl_in_use is not True:
                    raise RuntimeError("Staging database TLS is required.")
            with stage("alembic_migration"):
                # End preflight's transaction before Alembic owns the DDL transaction.
                connection.rollback()
                config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
    finally:
        engine.dispose()
    print("PASS staging database identity, TLS and Alembic upgrade", flush=True)


def main():
    # Third-party startup logs may include SQL or provider exception text.
    # Restore logging before serving; startup diagnostics use only fixed labels.
    previous = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with stage("settings_validation"):
            try:
                settings = Settings()
            except ValidationError as exc:
                for code in settings_validation_codes(exc):
                    print(f"STAGING SETTINGS {code}", file=sys.stderr, flush=True)
                raise
            except Exception:
                print("STAGING SETTINGS settings_validation_unknown", file=sys.stderr, flush=True)
                raise
        prepare(settings)
        with stage("application_startup"):
            from app.serve import main as serve

            logging.disable(previous)
            serve(sanitized=True)
    except (Exception, SystemExit):
        # Provider/SQL exceptions can contain credential-bearing connection details.
        print(
            "STAGING STOP startup_failed; consult the preceding STAGING FAIL code.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1) from None
    finally:
        logging.disable(previous)


if __name__ == "__main__":
    main()
