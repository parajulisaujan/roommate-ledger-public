import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.main import create_app

KEY = "test-only-origin-key-" * 3


def test_required_ingress_fails_closed_without_key():
    with pytest.raises(ValidationError):
        Settings(deployment_proxy_required=True)


def test_origin_gate_keeps_auth_csrf_and_health(settings, engine, clean, mailbox):
    configured = settings.model_copy(
        update={"deployment_proxy_required": True, "deployment_proxy_key": SecretStr(KEY)}
    )
    app = create_app(configured, engine=engine, email=mailbox)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/actuator/health/readiness").status_code == 200
    assert client.get("/api/auth/csrf").status_code == 404
    assert client.get("/api/auth/csrf", headers={"x-ledger-proxy-key": "wrong"}).status_code == 404
    assert (
        client.get(
            "/api/auth/csrf", headers=[("x-ledger-proxy-key", KEY), ("x-ledger-proxy-key", KEY)]
        ).status_code
        == 404
    )
    assert client.get("/api/auth/csrf", headers={"x-ledger-proxy-key": KEY}).status_code == 200
    assert (
        client.post("/api/auth/login", json={}, headers={"x-ledger-proxy-key": KEY}).status_code
        == 403
    )
    client.close()


def test_configured_gate_applies_to_application_routes(settings, engine, clean, mailbox):
    configured = settings.model_copy(
        update={"deployment_proxy_required": True, "deployment_proxy_key": SecretStr(KEY)}
    )
    protected = create_app(configured, engine=engine, email=mailbox)
    with TestClient(protected) as client:
        assert client.get("/api/households").status_code == 404
        response = client.get("/api/households", headers={"x-ledger-proxy-key": KEY})
        assert response.status_code == 401
        assert KEY not in response.text
        assert "x-ledger-proxy-key" not in response.headers
