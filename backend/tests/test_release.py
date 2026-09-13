from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from test_staging_start import sandbox_settings

from app.release import main, prepare
from app.start import main as start


def settings():
    return sandbox_settings(
        app_env="production",
        database_url="postgresql://db.example.test/ledger_release_test?sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt",
    )


@pytest.mark.parametrize("apply", [False, True])
def test_release_check_is_read_only_and_apply_explicit(apply):
    engine, conn = MagicMock(), MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    conn.execute.return_value.scalar_one.return_value = "ledger_release_test"
    conn.connection.driver_connection.pgconn.ssl_in_use = True
    with (
        patch("app.release.engine_for", return_value=engine),
        patch("app.release.ssl.create_default_context"),
        patch("app.release.command.upgrade") as upgrade,
    ):
        prepare(settings(), "ledger_release_test", apply=apply)
    assert upgrade.call_count == int(apply)
    engine.dispose.assert_called_once()
    conn.rollback.assert_called_once()


@pytest.mark.parametrize("tls", [False, None, "true", 1])
def test_release_tls_fails_closed(tls):
    engine, conn = MagicMock(), MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    conn.execute.return_value.scalar_one.return_value = "ledger_release_test"
    conn.connection.driver_connection.pgconn = SimpleNamespace(ssl_in_use=tls)
    with (
        patch("app.release.engine_for", return_value=engine),
        patch("app.release.ssl.create_default_context"),
        patch("app.release.command.upgrade") as upgrade,
        pytest.raises(RuntimeError),
    ):
        prepare(settings(), "ledger_release_test", apply=True)
    upgrade.assert_not_called()
    engine.dispose.assert_called_once()


def test_release_wrong_target_and_staging_fail_before_connection():
    with patch("app.release.engine_for") as engine:
        for config, name in [(settings(), "wrong"), (sandbox_settings(), "roommateledger_staging")]:
            with pytest.raises(RuntimeError):
                prepare(config, name, apply=True)
        engine.assert_not_called()


@pytest.mark.parametrize("source", ["settings", "migration"])
def test_release_redacts_exceptions_and_third_party_output(source, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["release", "--expected-database", "ledger_release_test", "--apply"]
    )

    def fail(*args, **kwargs):
        print("fictional-provider-secret")
        raise RuntimeError("fictional-provider-secret")

    with (
        patch("app.release.Settings", side_effect=fail if source == "settings" else settings),
        patch("app.release.prepare", side_effect=fail),
    ):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "RELEASE FAIL preflight_or_migration\n"


def test_production_start_does_not_migrate(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with patch("alembic.command.upgrade") as migrate, patch("app.serve.main") as serve:
        start()
    migrate.assert_not_called()
    serve.assert_called_once_with()


def test_staging_start_retains_guard(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    with patch("app.staging_start.main") as staging, patch("app.serve.main") as serve:
        start()
    staging.assert_called_once_with()
    serve.assert_not_called()


def test_release_argument_errors_do_not_echo_inputs(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["release", "fictional-secret-input"])
    with pytest.raises(SystemExit):
        main()
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "RELEASE FAIL arguments\n"
