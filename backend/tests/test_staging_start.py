from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.config import Settings
from app.staging_start import main, prepare, validate_staging


def sandbox_settings(**changes):
    values = dict(
        app_env="staging",
        database_url="postgresql://fictional@ep-test.neon.tech/roommateledger_staging?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt",
        frontend_url="https://preview.example.test",
        cookie_secure=True,
        email_verification_required=True,
        deployment_proxy_required=True,
        deployment_proxy_key="fictional-origin-key-" * 3,
        smtp_host="sandbox.smtp.mailtrap.io",
        smtp_port=2525,
        smtp_username="fictional-test-user",
        smtp_password="fictional-test-password",
        email_from="ledger-staging@example.test",
    )
    return Settings(**(values | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"database_url": "postgresql://localhost/roommateledger_staging"},
        {"database_url": "postgresql://ep-test.neon.tech/development?sslmode=verify-full"},
        {"database_url": "postgresql://ep-test.neon.tech/roommateledger_staging?sslmode=require"},
        {"deployment_proxy_required": False},
        {"smtp_port": 587},
        {"smtp_host": "smtp.real-provider.example"},
        {"smtp_password": ""},
        {"openai_api_key": "fictional-live-key"},
        {"receipt_provider_api_key": "fictional-live-key"},
    ],
)
def test_rejects_unsafe_configuration_before_connecting(changes):
    with (
        patch("app.staging_start.Path.is_file", return_value=True),
        patch("app.staging_start.ssl.create_default_context"),
        patch("app.staging_start.engine_for") as engine,
    ):
        with pytest.raises(RuntimeError):
            prepare(sandbox_settings(**changes))
        engine.assert_not_called()


def test_requires_ca_bundle():
    with patch("app.staging_start.Path.is_file", return_value=False):
        with pytest.raises(RuntimeError):
            validate_staging(sandbox_settings())


def test_migrates_same_verified_connection_then_disposes():
    engine = MagicMock()
    connection = engine.connect.return_value
    connection.execute.return_value.scalar_one.side_effect = ["roommateledger_staging"]
    connection.connection.driver_connection.pgconn.ssl_in_use = True
    with (
        patch("app.staging_start.Path.is_file", return_value=True),
        patch("app.staging_start.ssl.create_default_context"),
        patch("app.staging_start.engine_for", return_value=engine),
        patch("app.staging_start.command.upgrade") as upgrade,
    ):
        prepare(sandbox_settings())
    assert upgrade.call_args.args[0].attributes["connection"] is connection
    assert upgrade.call_args.args[1] == "head"
    connection.rollback.assert_called_once()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize(
    "failure,code",
    [
        ("settings", "settings_validation"),
        ("configuration", "staging_configuration"),
        ("ca", "ca_bundle"),
        ("connection", "database_connection"),
        ("handshake", "database_tls_handshake"),
        ("identity", "database_identity"),
        ("tls", "database_tls"),
        ("migration", "alembic_migration"),
        ("application", "application_startup"),
    ],
)
def test_failure_codes_never_expose_provider_details(failure, code, capsys):
    secret = "postgresql://PRIVATE_USER:PRIVATE_PASSWORD@PRIVATE_HOST/db?key=PRIVATE_KEY"
    engine = MagicMock()
    connection = engine.connect.return_value
    connection.execute.return_value.scalar_one.side_effect = [
        "wrong" if failure == "identity" else "roommateledger_staging",
    ]
    connection.connection.driver_connection.pgconn.ssl_in_use = failure != "tls"
    with (
        patch("app.staging_start.Settings", return_value=sandbox_settings()) as settings,
        patch("app.staging_start.Path.is_file", return_value=failure != "ca"),
        patch("app.staging_start.ssl.create_default_context"),
        patch("app.staging_start.engine_for", return_value=engine),
        patch("app.staging_start.command.upgrade") as upgrade,
        patch("app.serve.main") as serve,
    ):
        if failure == "settings":
            settings.side_effect = ValueError(secret)
        if failure == "configuration":
            settings.return_value = sandbox_settings(smtp_port=587)
        if failure in {"connection", "handshake"}:
            engine.connect.side_effect = RuntimeError(
                ("certificate verify failed " if failure == "handshake" else "") + secret
            )
        if failure == "migration":
            upgrade.side_effect = RuntimeError(secret)
        if failure == "application":
            serve.side_effect = RuntimeError(secret)
        with pytest.raises(SystemExit) as stopped:
            main()
        assert stopped.value.code == 1
        if failure != "application":
            serve.assert_not_called()
        if failure not in {"migration", "application"}:
            upgrade.assert_not_called()
    captured = capsys.readouterr()
    assert f"STAGING FAIL {code}" in captured.err
    assert "PRIVATE_" not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err


def test_server_traceback_messages_are_sanitized():
    import logging

    from app.serve import StagingServerFormatter

    record = logging.LogRecord(
        "uvicorn.error", logging.ERROR, "", 0, "Traceback PRIVATE_PASSWORD", (), None
    )
    assert StagingServerFormatter().format(record) == (
        "STAGING FAIL application_startup_or_runtime; server details suppressed"
    )


def test_server_not_started_is_a_failure():
    from app.serve import main as serve

    with patch("app.serve.uvicorn.Server") as server:
        server.return_value.started = False
        with pytest.raises(RuntimeError, match="Application startup failed"):
            serve(sanitized=True)


@pytest.mark.parametrize("database,tls", [("development", True), ("roommateledger_staging", False)])
def test_live_identity_and_tls_must_pass_before_migration(database, tls):
    engine = MagicMock()
    connection = engine.connect.return_value
    connection.execute.return_value.scalar_one.side_effect = [database]
    connection.connection.driver_connection.pgconn.ssl_in_use = tls
    with (
        patch("app.staging_start.Path.is_file", return_value=True),
        patch("app.staging_start.ssl.create_default_context"),
        patch("app.staging_start.engine_for", return_value=engine),
        patch("app.staging_start.command.upgrade") as upgrade,
    ):
        with pytest.raises(RuntimeError):
            prepare(sandbox_settings())
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"deployment_proxy_key": "SECRET_SHORT"}, "deployment_proxy_key_invalid"),
        (
            {"frontend_url": "https://SECRET_USER:SECRET_PASSWORD@example.test/path"},
            "frontend_url_invalid",
        ),
        ({"cookie_secure": False}, "cookie_secure_invalid"),
        ({"cookie_same_site": "SECRET_INPUT"}, "cookie_same_site_invalid"),
        ({"smtp_starttls": False}, "smtp_starttls_disabled"),
        ({"smtp_host": ""}, "smtp_host_missing"),
        ({"email_from": ""}, "email_from_missing"),
        ({"smtp_port": "SECRET_PORT"}, "smtp_port_invalid"),
        ({"smtp_starttls": "SECRET_BOOLEAN"}, "smtp_starttls_invalid"),
        ({"smtp_username": {"SECRET_USER": "SECRET_VALUE"}}, "smtp_username_invalid"),
        ({"smtp_password": ["SECRET_PASSWORD"]}, "smtp_password_invalid"),
        ({"smtp_timeout_seconds": "SECRET_TIMEOUT"}, "smtp_timeout_invalid"),
        ({"smtp_timeout_seconds": 0}, "smtp_timeout_invalid"),
        ({"smtp_timeout_seconds": 31}, "smtp_timeout_invalid"),
        ({"smtp_host": ["SECRET_HOST"]}, "smtp_configuration_invalid"),
        ({"email_from": ["SECRET_SENDER"]}, "smtp_configuration_invalid"),
        ({"email_verification_required": False}, "email_verification_invalid"),
        (
            {"cors_allowed_origins": "https://SECRET_USER:SECRET_PASSWORD@example.test"},
            "cors_invalid",
        ),
        ({"trusted_proxy_cidrs": "0.0.0.0/0"}, "trusted_proxy_invalid"),
        ({"app_env": "SECRET_INPUT"}, "app_env_invalid"),
        ({"receipt_provider": "SECRET_INPUT"}, "receipt_provider_invalid"),
        ({"rate_login": 0}, "rate_limit_invalid"),
        ({"session_timeout_seconds": 1}, "session_timeout_invalid"),
        ({"smtp_port": "SECRET_INPUT"}, "field_type_invalid"),
        ({"trusted_proxy_cidrs": "SECRET_INVALID_CIDR"}, "settings_validation_unknown"),
        ({"cookie_same_site": "none", "cookie_secure": False}, "cookie_secure_invalid"),
        ({"cors_allowed_origins": "http://example.test"}, "cors_invalid"),
        (
            {
                "receipt_provider_url": "http://SECRET_USER:SECRET_PASSWORD@example.test",
                "receipt_provider_api_key": "SECRET_KEY",
            },
            "receipt_provider_invalid",
        ),
        ({"frontend_url": "https://[SECRET_BAD_IPV6"}, "settings_validation_unknown"),
        ({"cookie_secure": "SECRET_BOOL"}, "cookie_secure_invalid"),
        ({"smtp_port": "SECRET_PORT", "rate_login": "SECRET_RATE"}, "rate_limit_invalid"),
    ],
)
def test_actual_settings_validation_diagnostics(changes, expected, capsys):
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as error:
        sandbox_settings(
            **(
                dict(
                    database_password="SECRET_DATABASE_PASSWORD",
                    smtp_password="SECRET_SMTP_PASSWORD",
                    smtp_username="SECRET_SMTP_USER",
                )
                | changes
            )
        )
    with (
        patch("app.staging_start.Settings", side_effect=error.value),
        patch("app.staging_start.prepare") as preflight,
    ):
        with pytest.raises(SystemExit) as stopped:
            main()
        assert stopped.value.code == 1
        preflight.assert_not_called()
    captured = capsys.readouterr()
    assert f"STAGING SETTINGS {expected}" in captured.err
    # Assert the entire output consists of static diagnostics, not just sentinel absence.
    from app.staging_start import FIELD_VALIDATION_CODES, MODEL_VALIDATION_CODES

    allowed = set(FIELD_VALIDATION_CODES.values()) | set(MODEL_VALIDATION_CODES.values())
    allowed |= {"field_type_invalid", "settings_validation_unknown"}
    for line in captured.err.splitlines():
        assert line in {
            "STAGING FAIL settings_validation",
            "STAGING STOP startup_failed; consult the preceding STAGING FAIL code.",
            *("STAGING SETTINGS " + code for code in allowed),
        }
    assert captured.out == "STAGING START settings_validation\n"
    assert "SECRET" not in captured.out + captured.err


def test_unknown_model_message_cannot_spoof_known_reason():
    from pydantic import ValidationError

    from app.staging_start import settings_validation_codes

    error = ValidationError.from_exception_data(
        "Settings",
        [
            {
                "type": "value_error",
                "loc": (),
                "input": {"password": "SECRET"},
                "ctx": {"error": ValueError("Production requires COOKIE_SECURE=true. SECRET")},
            }
        ],
    )
    assert settings_validation_codes(error) == ["settings_validation_unknown"]


def test_unrecognized_location_never_appears_in_codes():
    from pydantic import ValidationError

    from app.staging_start import settings_validation_codes

    error = ValidationError.from_exception_data(
        "Settings",
        [
            {
                "type": "string_type",
                "loc": ("SECRET_FIELD",),
                "input": "SECRET_VALUE",
            }
        ],
    )
    assert settings_validation_codes(error) == ["settings_validation_unknown"]


@pytest.mark.parametrize("state", [False, None, "true", 1, "missing", "raises"])
def test_client_tls_unverified_blocks_migrations_without_leaking(state, capsys):
    engine = MagicMock()
    connection = engine.connect.return_value
    connection.execute.return_value.scalar_one.side_effect = ["roommateledger_staging"]
    pgconn = MagicMock()
    if state == "missing":
        pgconn = SimpleNamespace()
    elif state == "raises":
        type(pgconn).ssl_in_use = PropertyMock(
            side_effect=RuntimeError("postgresql://SECRET_USER:SECRET_PASSWORD@SECRET_HOST/db")
        )
    else:
        pgconn.ssl_in_use = state
    connection.connection.driver_connection.pgconn = pgconn
    with (
        patch("app.staging_start.Settings", return_value=sandbox_settings()),
        patch("app.staging_start.Path.is_file", return_value=True),
        patch("app.staging_start.ssl.create_default_context"),
        patch("app.staging_start.engine_for", return_value=engine),
        patch("app.staging_start.command.upgrade") as upgrade,
        patch("app.serve.main") as serve,
    ):
        with pytest.raises(SystemExit) as stopped:
            main()
        assert stopped.value.code == 1
    upgrade.assert_not_called()
    serve.assert_not_called()
    engine.dispose.assert_called_once()
    connection.execute.assert_called_once()
    output = capsys.readouterr()
    assert "STAGING FAIL database_tls" in output.err
    assert "SECRET" not in output.out + output.err
    assert "Traceback" not in output.out + output.err
