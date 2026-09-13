import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from app.config import Settings
from app.db import Store, engine_for
from app.main import create_app


class Mailbox:
    enabled = True

    def __init__(self):
        self.messages = []

    def available(self):
        return self.enabled

    def send(self, recipient, subject, body):
        self.messages.append((recipient, subject, body))


@pytest.fixture(scope="session")
def settings():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL must name an isolated PostgreSQL database (ledger_pytest_*)."
        )
    settings = Settings(
        database_url=url,
        database_user=os.environ.get("TEST_DATABASE_USER", "ledger"),
        database_password=os.environ.get("TEST_DATABASE_PASSWORD", ""),
        rate_login=1000,
        rate_registration=1000,
        rate_password_reset=1000,
        rate_verification=1000,
        rate_reset_confirm=1000,
        rate_invitations=1000,
        rate_extraction=1000,
        rate_account=1000,
        email_verification_required=False,
        smtp_host="",
        email_from="",
        receipt_provider_url="",
        receipt_provider_api_key="",
        openai_api_key="",
        openai_receipt_model="",
        app_env="development",
    )
    if not settings.sqlalchemy_url.database.startswith("ledger_pytest_"):
        pytest.fail(
            "Integration tests refuse to clear a database without the ledger_pytest_ prefix."
        )
    return settings


@pytest.fixture(scope="session")
def engine(settings):
    old = {
        key: os.environ.get(key) for key in ("DATABASE_URL", "DATABASE_USER", "DATABASE_PASSWORD")
    }
    os.environ.update(
        DATABASE_URL=settings.database_url,
        DATABASE_USER=settings.database_user,
        DATABASE_PASSWORD=settings.database_password,
    )
    try:
        command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    engine = engine_for(settings)
    yield engine
    engine.dispose()


@pytest.fixture
def clean(engine):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE app_user,abuse_window CASCADE"))


@pytest.fixture
def mailbox():
    return Mailbox()


@pytest.fixture
def app(settings, engine, clean, mailbox):
    return create_app(settings, engine=engine, email=mailbox)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def db(engine, clean):
    with Session(engine) as session, session.begin():
        yield Store(session)


def csrf(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200, response.text
    return {response.json()["headerName"]: response.json()["token"]}


def mutate(client, method, path, data=None, **kwargs):
    headers = csrf(client)
    if data is not None:
        kwargs["json"] = data
    return client.request(method, path, headers=headers, **kwargs)


def register(client, name="Test user"):
    data = {
        "name": name,
        "email": str(uuid4()) + "@example.test",
        "password": "correct horse battery",
    }
    response = mutate(client, "POST", "/api/auth/register", data)
    assert response.status_code == 200, response.text
    return response.json() | {"password": data["password"]}


@pytest.fixture
def household(app, client):
    clients = [client] + [TestClient(app, raise_server_exceptions=False) for _ in range(3)]
    users = [register(c, f"Roommate {i}") for i, c in enumerate(clients)]
    response = mutate(client, "POST", "/api/households", {"name": "Fictional household"})
    assert response.status_code == 200, response.text
    house = response.json()["id"]
    for other in clients[1:]:
        invitation = mutate(client, "POST", f"/api/households/{house}/invitations").json()
        response = mutate(other, "POST", "/api/invitations/accept", {"token": invitation["token"]})
        assert response.status_code == 200, response.text
    yield clients, users, house
    for other in clients[1:]:
        other.close()
