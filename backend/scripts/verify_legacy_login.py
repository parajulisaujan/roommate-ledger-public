"""Verify a preserved fictional Java test account can sign in through FastAPI."""

import httpx
from sqlalchemy import text

from app.config import Settings
from app.db import engine_for
from app.services.accounts import password_matches


def main():
    config = Settings()
    if not config.sqlalchemy_url.database.startswith("ledger_adoption_"):
        raise RuntimeError("Use the isolated restored-copy database.")
    engine = engine_for(config)
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT id,email,password_hash FROM app_user WHERE password_hash LIKE '$2a$%' AND email LIKE '%@example.test' AND deactivated=false"
                )
            )
            .mappings()
            .all()
        )
    engine.dispose()
    account = next(
        (row for row in rows if password_matches("fictional-api-password", row["password_hash"])),
        None,
    )
    if account is None:
        raise RuntimeError("No preserved Java privacy-test account found.")
    with httpx.Client(base_url="http://127.0.0.1:8080", timeout=10) as client:
        csrf = client.get("/api/auth/csrf").json()
        response = client.post(
            "/api/auth/login",
            headers={csrf["headerName"]: csrf["token"]},
            json={"email": account["email"], "password": "fictional-api-password"},
        )
        response.raise_for_status()
        assert response.json()["id"] == str(account["id"])
    print(
        "PASS: original Java BCrypt account authenticated through FastAPI with its unchanged hash and identity."
    )


if __name__ == "__main__":
    main()
