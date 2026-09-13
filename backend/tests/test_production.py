import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from conftest import mutate, register
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.config import Settings
from app.logging import JsonFormatter
from app.main import create_app
from app.security.proxy import client_address
from app.services.accounts import SmtpEmailProvider


def test_production_entrypoint_does_not_print_invalid_settings_input():
    # Real subprocess exercises import-time Settings(), before create_app can
    # configure logging. Never inherit provider settings into this reproduction.
    env = {k: v for k, v in os.environ.items() if k.lower() not in Settings.model_fields}
    env.update(
        APP_ENV="production",
        FRONTEND_URL="https://app.example.test",
        COOKIE_SECURE="true",
        EMAIL_VERIFICATION_REQUIRED="true",
        SMTP_HOST="smtp.example.test",
        EMAIL_FROM="sender@example.test",
        SMTP_PORT="PRIVATE_CREDENTIAL_SENTINEL",
        SMTP_STARTTLS="true",
    )
    result = subprocess.run(
        [sys.executable, "-m", "app.serve"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 1
    assert "PRODUCTION STARTUP FAILED" in result.stderr
    assert "PRIVATE_CREDENTIAL_SENTINEL" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


def test_production_server_log_message_and_traceback_are_suppressed():
    from app.serve import ProductionServerFormatter

    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        "",
        0,
        "PRIVATE_PASSWORD %s",
        ("PRIVATE_URL",),
        (RuntimeError, RuntimeError("PRIVATE_TOKEN"), None),
    )
    assert ProductionServerFormatter().format(record) == (
        "PRODUCTION SERVER ERROR; details suppressed"
    )


def test_application_logging_preserves_production_server_redaction():
    script = """
import logging
from unittest.mock import patch
from app.serve import run_server
from app.logging import configure
with patch('app.serve.uvicorn.Server'):
    run_server(production=True)
configure()
logging.getLogger('uvicorn.error').error('PRIVATE_LIFESPAN_TRACEBACK')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    assert result.stderr.strip() == "PRODUCTION SERVER ERROR; details suppressed"
    assert "PRIVATE_LIFESPAN_TRACEBACK" not in result.stdout + result.stderr


def test_production_log_formatter_does_not_append_exception_values():
    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        "",
        0,
        "Exception in ASGI application",
        (),
        (RuntimeError, RuntimeError("private-token"), None),
    )
    result = JsonFormatter().format(record)
    assert "Exception in ASGI application" in result
    assert "private-token" not in result


@pytest.mark.parametrize(
    "values",
    [
        {"app_env": "prodution"},
        {"rate_login": 0},
        {"rate_window_seconds": -1},
        {"smtp_timeout_seconds": 0},
        {"receipt_timeout_seconds": 121},
        {"trusted_proxy_cidrs": "0.0.0.0/0"},
        {"trusted_proxy_cidrs": "*"},
    ],
)
def test_invalid_production_controls(values):
    with pytest.raises(ValidationError):
        Settings(**values)


@pytest.mark.parametrize(
    "peer,forwarded,trusted,expected",
    [
        ("203.0.113.1", "198.51.100.2", "10.0.0.0/24", "203.0.113.1"),
        ("10.0.0.2", "192.0.2.99, 198.51.100.2, 10.0.0.3", "10.0.0.0/24", "198.51.100.2"),
        ("10.0.0.2", "invalid", "10.0.0.0/24", "10.0.0.2"),
        ("::1", "2001:db8::1", "::1/128", "2001:db8::1"),
        ("10.0.0.2", "198.51.100.2", "", "10.0.0.2"),
    ],
)
def test_proxy_identity(peer, forwarded, trusted, expected):
    assert client_address(peer, forwarded, trusted) == expected


def test_request_id_and_safe_unhandled_error(client, app, caplog):
    @app.get("/test-failure")
    def fail():
        raise RuntimeError("private-password-and-financial-data")

    response = client.get("/health", headers={"X-Request-ID": "untrusted"})
    UUID(response.headers["x-request-id"])
    failure = client.get("/test-failure")
    assert failure.status_code == 500
    assert failure.headers["x-request-id"] in failure.json()["message"]
    assert "private-password" not in failure.text + caplog.text
    assert "RuntimeError" in caplog.text


def test_smtp_tls_credentials_sender_and_timeout():
    settings = Settings(
        smtp_host="smtp.example.test",
        email_from="ledger@example.test",
        smtp_username="test-user",
        smtp_password="fictional",
        smtp_timeout_seconds=7,
    )
    with patch("app.services.accounts.smtplib.SMTP") as smtp:
        server = smtp.return_value.__enter__.return_value
        SmtpEmailProvider(settings).send("recipient@example.test", "Verify", "Fictional body")
        smtp.assert_called_once_with("smtp.example.test", 587, timeout=7)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("test-user", "fictional")
        assert server.send_message.call_args.args[0]["From"] == "ledger@example.test"


@pytest.mark.parametrize("error", [TimeoutError("secret"), OSError("secret")])
def test_smtp_failure_revokes_token_and_redacts(client, mailbox, engine, caplog, error):
    user = register(client)
    mailbox.send = MagicMock(side_effect=error)
    known = mutate(client, "POST", "/api/auth/forgot-password", {"email": user["email"]})
    unknown = mutate(client, "POST", "/api/auth/forgot-password", {"email": "absent@example.test"})
    assert known.status_code == 200 and known.json() == unknown.json()
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM account_token WHERE purpose='RESET' AND used=false")
            ).scalar_one()
            == 0
        )
    assert "secret" not in caplog.text


def test_production_subdomain_cors_cookie_csrf(settings, engine, clean, mailbox):
    config = Settings(
        **(
            settings.model_dump()
            | {
                "app_env": "production",
                "frontend_url": "https://app.example.test",
                "cors_allowed_origins": "https://app.example.test",
                "cookie_secure": True,
                "smtp_host": "smtp.example.test",
                "email_from": "ledger@example.test",
                "email_verification_required": True,
            }
        )
    )
    with TestClient(
        create_app(config, engine=engine, email=mailbox), base_url="https://api.example.test"
    ) as client:
        response = client.get("/api/auth/csrf", headers={"Origin": config.frontend_url})
        cookie = response.headers["set-cookie"].lower()
        assert all(value in cookie for value in ("httponly", "secure", "samesite=lax", "path=/"))
        assert "domain=" not in cookie
        assert response.headers["access-control-allow-origin"] == config.frontend_url
        assert response.headers["access-control-allow-credentials"] == "true"
        assert client.post("/api/auth/login", json={}).status_code == 403
        assert client.get("/openapi.json").status_code == 404
        register(client)
        assert mutate(client, "POST", "/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401
