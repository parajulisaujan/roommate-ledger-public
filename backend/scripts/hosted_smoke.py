"""Health-only by default. Explicitly authorized mutations use newly created accounts only."""

import getpass
import mimetypes
import os
import re
import secrets
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


def origin(name):
    value = os.environ[name].rstrip("/")
    parsed = urlsplit(value)
    if (
        (
            parsed.scheme != "https"
            and not (
                parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
        or not parsed.hostname
        or parsed.username
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} requires an exact HTTPS origin (HTTP only on loopback).")
    return value


class Actor:
    def __init__(self, base, domain):
        self.client = httpx.Client(
            base_url=base, timeout=150, follow_redirects=False, trust_env=False
        )
        self.email = f"ledger-smoke-{uuid4().hex}@{domain}"
        self.password = secrets.token_urlsafe(32)
        self.user = None

    def call(self, path, data=None, *, method=None, expected=200, **kwargs):
        headers = {}
        if data is not None or method:
            csrf = self.client.get("/api/auth/csrf")
            if csrf.status_code != 200:
                raise RuntimeError("CSRF bootstrap failed")
            headers[csrf.json()["headerName"]] = csrf.json()["token"]
            # Each smoke call is a new operation; the script never automatically retries writes.
            headers["Idempotency-Key"] = str(uuid4())
        response = self.client.request(
            method or ("POST" if data is not None else "GET"),
            "/api" + path,
            headers=headers,
            **({"json": data} if data is not None else {}),
            **kwargs,
        )
        if response.status_code != expected:
            # Never include response bodies, credentials, receipt content or invitation paths.
            raise RuntimeError(
                f"Smoke request failed: expected {expected}, received {response.status_code}"
            )
        return response.json() if response.content else None

    def register(self):
        self.user = self.call(
            "/auth/register",
            {"email": self.email, "password": self.password, "name": "Disposable release smoke"},
        )
        if self.user["verification_required"]:
            mailbox = os.environ.get("SMOKE_LOCAL_MAILBOX_URL")
            if mailbox:
                if urlsplit(self.client.base_url.__str__()).hostname not in {
                    "localhost",
                    "127.0.0.1",
                    "::1",
                }:
                    raise ValueError("Local test mailbox cannot verify a hosted deployment")
                mailbox = origin("SMOKE_LOCAL_MAILBOX_URL")
                if urlsplit(mailbox).hostname not in {"localhost", "127.0.0.1", "::1"}:
                    raise ValueError("Test mailbox must be loopback")
                token = None
                for _ in range(20):
                    with httpx.Client(trust_env=False, timeout=5) as inbox:
                        messages = inbox.get(mailbox, params={"recipient": self.email}).json()
                    for message in messages:
                        match = re.search(r"#verify=([A-Za-z0-9_-]{43})", message["text"])
                        if match:
                            token = match[1]
                    if token:
                        break
                    time.sleep(1)
                if not token:
                    raise RuntimeError("Verification email not received")
            else:
                token = getpass.getpass(f"Verification token from email to {self.email}: ")
            self.call("/auth/verify-email", {"token": token.strip()})
        self.call("/auth/logout", {}, expected=204)
        self.login()

    def login(self):
        self.call("/auth/login", {"email": self.email, "password": self.password})


def main():
    base, backend = origin("SMOKE_FRONTEND_URL"), origin("SMOKE_BACKEND_URL")
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        for url, expected in (
            (base + "/api/health", "ok"),
            (backend + "/health", "ok"),
            (backend + "/actuator/health/readiness", "UP"),
        ):
            response = client.get(url)
            if response.status_code != 200 or response.json() != {"status": expected}:
                raise RuntimeError("Health/readiness failed")
    print("PASS frontend/API health and database readiness")
    if os.environ.get("SMOKE_ALLOW_MUTATIONS") != "true":
        return
    domain = os.environ["SMOKE_EMAIL_DOMAIN"]
    if not re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", domain):
        raise ValueError("Set a smoke-only catch-all email domain you control")
    actors = [Actor(base, domain), Actor(base, domain)]
    a, b = actors
    failures = []
    try:
        for actor in actors:
            actor.register()
        house = a.call("/households", {"name": "Disposable release smoke"})["id"]
        invite = a.call(f"/households/{house}/invitations", {})
        b.call("/invitations/accept", {"token": invite["token"]})
        data = dict(
            title="Disposable smoke",
            merchant="",
            amount=10000,
            category="Other",
            scope="HOUSEHOLD",
            householdId=house,
            payerId=a.user["id"],
            date=date.today().isoformat(),
            splitMethod="EQUAL",
            participants=[],
            values={},
            notes="",
        )
        expense = a.call("/expenses", data)
        detail = a.call(f"/expenses/{expense['id']}")
        if sorted(row["amount"] for row in detail["allocations"]) != [5000, 5000]:
            raise RuntimeError("Exact allocation failed")
        private = a.call(
            "/expenses", data | {"scope": "PERSONAL", "householdId": None, "amount": 4000}
        )
        b.call(f"/expenses/{private['id']}", expected=403)
        b.call(
            f"/households/{house}/settlements",
            {
                "fromUser": b.user["id"],
                "toUser": a.user["id"],
                "amount": 5000,
                "method": "Smoke test only",
                "date": date.today().isoformat(),
            },
        )
        if any(row["balance"] != 0 for row in a.call(f"/households/{house}/balances")):
            raise RuntimeError("Settlement conservation failed")
        if os.environ.get("SMOKE_LIVE_AI") == "true":
            if not a.call("/receipts/capabilities")["automatedExtraction"]:
                raise RuntimeError("Backend provider credentials/model are not configured")
            path = Path(os.environ["LIVE_RECEIPT_FILE"])
            if not 0 < path.stat().st_size <= 8 * 1024 * 1024:
                raise ValueError("Receipt must be at most 8 MiB")
            with path.open("rb") as file:
                receipt = a.call(
                    "/receipts/extract",
                    method="POST",
                    files={
                        "file": (
                            "smoke-receipt",
                            file,
                            mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                        )
                    },
                )
            if receipt["status"] != "NEEDS_REVIEW":
                raise RuntimeError("Live extraction did not produce a reviewable draft")
            print(
                "PASS live provider returned a draft; visual accuracy still requires human review"
            )
        for actor in actors:
            actor.call("/auth/logout", {}, expected=204)
            actor.call("/auth/me", expected=401)
        print(
            "PASS disposable accounts, verification, login, exact split, privacy, settlement and logout"
        )
    finally:
        # Member first so the owner has no active roommates. Only accounts created by this run.
        for actor in reversed(actors):
            try:
                if actor.user:
                    actor.login()
                    actor.call("/account/deactivate", {"password": actor.password})
            except Exception:
                failures.append(actor.email)
            finally:
                actor.client.close()
        if failures:
            raise RuntimeError(
                "Deactivate these disposable smoke accounts via operator support: "
                + ", ".join(failures)
            )
        print("PASS smoke accounts deactivated; fictional financial history retained")


if __name__ == "__main__":
    main()
