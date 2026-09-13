"""Prove native API restart persistence on an explicitly isolated PostgreSQL test database."""

import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx

from app.config import Settings


def start(environment):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8082",
            "--no-access-log",
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Test API failed to start.")
        try:
            if (
                httpx.get("http://127.0.0.1:8082/actuator/health/readiness", timeout=1).status_code
                == 200
            ):
                return process
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError("Test API readiness deadline exceeded.")


def main():
    if not Settings().sqlalchemy_url.database.startswith("ledger_pytest_"):
        raise RuntimeError("Runtime smoke requires a ledger_pytest_* database.")
    environment = os.environ | {
        "EMAIL_VERIFICATION_REQUIRED": "false",
        "SMTP_HOST": "",
        "EMAIL_FROM": "",
        "APP_ENV": "development",
    }
    process = start(environment)
    try:
        with httpx.Client(base_url="http://127.0.0.1:8082", timeout=10) as client:
            csrf = client.get("/api/auth/csrf").json()
            headers = {csrf["headerName"]: csrf["token"]}
            account = client.post(
                "/api/auth/register",
                headers=headers,
                json={
                    "name": "Restart test",
                    "email": str(uuid4()) + "@example.test",
                    "password": "restart test password",
                },
            )
            account.raise_for_status()
            user = account.json()["id"]
            expense = client.post(
                "/api/expenses",
                headers=headers,
                json={
                    "title": "Restart persistence",
                    "amount": 10001,
                    "category": "Other",
                    "scope": "PERSONAL",
                    "date": date.today().isoformat(),
                    "splitMethod": "EQUAL",
                },
            )
            expense.raise_for_status()
            id = expense.json()["id"]
            process.terminate()
            process.wait(timeout=10)
            process = start(environment)
            assert client.get("/api/auth/me").json()["id"] == user
            restored = client.get("/api/expenses/" + id)
            restored.raise_for_status()
            assert restored.json()["amount"] == 10001
            assert sum(a["amount"] for a in restored.json()["allocations"]) == 10001
            assert client.post("/api/auth/logout", headers=headers).status_code == 204
            assert client.get("/api/auth/me").status_code == 401
        print(
            "PASS: API restart retained the authenticated session, expense and exact allocation; logout revoked access."
        )
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
