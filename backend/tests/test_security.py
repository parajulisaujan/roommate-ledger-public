import re

import pytest
from conftest import csrf, mutate, register
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from test_ledger import expense

from app.config import Settings
from app.main import create_app


def test_auth_csrf_session_rotation_logout(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/register", json={}).status_code == 403
    csrf(client)
    old = client.cookies["JSESSIONID"]
    user = register(client)
    assert client.cookies["JSESSIONID"] != old
    assert client.get("/api/auth/me").json()["id"] == user["id"]
    cookie = client.get("/api/auth/csrf")
    assert cookie.status_code == 200
    assert mutate(client, "POST", "/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert (
        mutate(
            client,
            "POST",
            "/api/auth/login",
            {"email": user["email"], "password": "wrong password value"},
        ).status_code
        == 401
    )
    assert (
        mutate(
            client,
            "POST",
            "/api/auth/login",
            {"email": user["email"], "password": user["password"]},
        ).status_code
        == 200
    )


def test_secure_cookie_and_expiration(settings, engine, clean, mailbox):
    app = create_app(
        settings.model_copy(update={"cookie_secure": True}), engine=engine, email=mailbox
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/auth/csrf")
        cookie = response.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
        register(client)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE web_session SET expires_at=CURRENT_TIMESTAMP - INTERVAL '1 hour'")
            )
        assert client.get("/api/auth/me").status_code == 401


def token(mailbox, action):
    return re.search(r"#" + action + r"=([A-Za-z0-9_-]{43})", mailbox.messages[-1][2]).group(1)


def test_reset_one_use_hash_and_all_session_revocation(client, app, mailbox, engine):
    user = register(client)
    with TestClient(app) as other:
        assert (
            mutate(
                other,
                "POST",
                "/api/auth/login",
                {"email": user["email"], "password": user["password"]},
            ).status_code
            == 200
        )
        assert (
            mutate(
                client, "POST", "/api/auth/forgot-password", {"email": user["email"]}
            ).status_code
            == 200
        )
        reset = token(mailbox, "reset")
        with engine.connect() as connection:
            assert reset not in str(connection.execute(text("SELECT * FROM account_token")).all())
        response = mutate(
            client,
            "POST",
            "/api/auth/reset-password",
            {"token": reset, "password": "new correct password"},
        )
        assert response.status_code == 200, response.text
        assert client.get("/api/auth/me").status_code == 401
        assert other.get("/api/auth/me").status_code == 401
    with TestClient(app) as fresh:
        assert (
            mutate(
                fresh,
                "POST",
                "/api/auth/reset-password",
                {"token": reset, "password": "another password"},
            ).status_code
            == 400
        )
        assert (
            mutate(
                fresh,
                "POST",
                "/api/auth/login",
                {"email": user["email"], "password": "new correct password"},
            ).status_code
            == 200
        )


def test_expired_superseded_tokens_and_generic_reset(client, mailbox, engine):
    user = register(client)
    mutate(client, "POST", "/api/auth/forgot-password", {"email": user["email"]})
    old = token(mailbox, "reset")
    mutate(client, "POST", "/api/auth/forgot-password", {"email": user["email"]})
    current = token(mailbox, "reset")
    assert (
        mutate(
            client,
            "POST",
            "/api/auth/reset-password",
            {"token": old, "password": "replacement password"},
        ).status_code
        == 400
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE account_token SET expires_at=CURRENT_TIMESTAMP-INTERVAL '1 day'")
        )
    assert (
        mutate(
            client,
            "POST",
            "/api/auth/reset-password",
            {"token": current, "password": "replacement password"},
        ).status_code
        == 400
    )
    mailbox.enabled = False
    a = mutate(client, "POST", "/api/auth/forgot-password", {"email": user["email"]})
    b = mutate(client, "POST", "/api/auth/forgot-password", {"email": "unknown@example.test"})
    assert a.json() == b.json()


def test_verification_gate(settings, engine, clean, mailbox):
    app = create_app(
        settings.model_copy(update={"email_verification_required": True}),
        engine=engine,
        email=mailbox,
    )
    with TestClient(app) as client:
        user = register(client)
        assert user["verification_required"] and not user["email_verified"]
        assert client.get("/api/households").status_code == 403
        assert client.get("/api/auth/me").status_code == 200
        assert (
            mutate(
                client, "POST", "/api/auth/verify-email", {"token": token(mailbox, "verify")}
            ).status_code
            == 200
        )
        assert client.get("/api/households").status_code == 200


def test_password_change_and_deactivation_preserve_records(client, app, engine):
    user = register(client)
    created = mutate(client, "POST", "/api/expenses", expense(user)).json()
    assert (
        mutate(
            client,
            "POST",
            "/api/account/password",
            {"currentPassword": "wrong", "password": "replacement password"},
        ).status_code
        == 400
    )
    assert (
        mutate(
            client,
            "POST",
            "/api/account/password",
            {"currentPassword": user["password"], "password": "replacement password"},
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").status_code == 401
    with TestClient(app) as other:
        assert (
            mutate(
                other,
                "POST",
                "/api/auth/login",
                {"email": user["email"], "password": "replacement password"},
            ).status_code
            == 200
        )
        assert (
            mutate(
                other, "POST", "/api/account/deactivate", {"password": "replacement password"}
            ).status_code
            == 200
        )
        assert other.get("/api/auth/me").status_code == 401
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT amount FROM expense WHERE id=:id"), {"id": created["id"]}
            ).scalar_one()
            == 10000
        )
    with TestClient(app) as fresh:
        assert (
            mutate(
                fresh,
                "POST",
                "/api/auth/login",
                {"email": user["email"], "password": "replacement password"},
            ).status_code
            == 401
        )


def test_owner_cannot_abandon_roommates(household):
    clients, users, _ = household
    assert (
        mutate(
            clients[0], "POST", "/api/account/deactivate", {"password": users[0]["password"]}
        ).status_code
        == 400
    )


def test_rate_limit_failed_attempts_and_worker_sharing(settings, engine, clean, mailbox):
    limited = settings.model_copy(update={"rate_login": 2})
    for index in range(3):
        with TestClient(create_app(limited, engine=engine, email=mailbox)) as client:
            response = mutate(
                client,
                "POST",
                "/api/auth/login",
                {"email": "unknown@example.test", "password": "wrong password value"},
            )
            assert response.status_code == (401 if index < 2 else 429)
    assert response.headers["retry-after"] == "900"


def test_cors_exact_origin_csrf_and_auth(settings, engine, clean, mailbox):
    app = create_app(
        settings.model_copy(update={"cors_allowed_origins": "https://ledger.example"}),
        engine=engine,
        email=mailbox,
    )
    with TestClient(app) as client:
        headers = {
            "Origin": "https://ledger.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-CSRF-TOKEN,Content-Type",
        }
        response = client.options("/api/expenses", headers=headers)
        assert (
            response.status_code == 200
            and response.headers["access-control-allow-origin"] == "https://ledger.example"
        )
        assert (
            client.options(
                "/api/expenses", headers=headers | {"Origin": "https://evil.example"}
            ).status_code
            == 400
        )
        assert (
            client.get("/api/auth/me", headers={"Origin": "https://ledger.example"}).status_code
            == 401
        )
        assert (
            client.post(
                "/api/expenses", headers={"Origin": "https://ledger.example"}, json={}
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "config",
    [
        {"cors_allowed_origins": "*"},
        {"cors_allowed_origins": "https://host/path"},
        {"cookie_same_site": "none"},
        {"app_env": "production"},
        {"receipt_provider_url": "http://provider.test", "receipt_provider_api_key": "test"},
    ],
)
def test_invalid_configuration_fails_closed(config):
    with pytest.raises(ValidationError):
        Settings(**config)


def test_export_privacy_and_formula_defense(household):
    clients, users, house = household
    assert (
        mutate(
            clients[0],
            "POST",
            "/api/expenses",
            expense(users[0], house, title="=CMD()", merchant="@SUM(1)"),
        ).status_code
        == 200
    )
    assert (
        mutate(
            clients[0], "POST", "/api/expenses", expense(users[0], title="PRIVATE_SECRET")
        ).status_code
        == 200
    )
    response = clients[1].get(f"/api/export/expenses?householdId={house}")
    assert (
        response.status_code == 200 and "'=CMD()" in response.text and "'@SUM(1)" in response.text
    )
    assert "PRIVATE_SECRET" not in response.text
    assert "PRIVATE_SECRET" not in clients[1].get("/api/export/expenses").text


def test_health_openapi_and_safe_validation(client):
    assert client.get("/actuator/health/liveness").json() == {"status": "UP"}
    assert client.get("/actuator/health/readiness").json() == {"status": "UP"}
    assert client.get("/actuator/env").status_code in {401, 404}
    schema = client.get("/openapi.json").json()
    assert "/api/expenses" in schema["paths"] and "ExpenseInput" in schema["components"]["schemas"]
    register(client)
    response = client.get("/api/expenses/not-a-uuid")
    assert response.status_code == 400 and "traceback" not in response.text.lower()
