from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import csrf, mutate, register
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_ledger import balances

FIXTURES = Path(__file__).parent / "fixtures"


def draft(user, house=None, items=None, **overrides):
    items = items or [item("Rice", 1000, "PERSONAL", [user["id"]])]
    total = sum(i["amount"] for i in items)
    return {
        "merchant": "Fictional Store",
        "date": date.today().isoformat(),
        "currency": "USD",
        "householdId": house,
        "payerId": user["id"],
        "items": items,
        "subtotal": total,
        "discounts": 0,
        "tax": 0,
        "fees": 0,
        "total": total,
    } | overrides


def item(name, amount, scope, participants):
    return {
        "description": name,
        "rawDescription": name,
        "amount": amount,
        "unitPrice": amount,
        "quantity": 1,
        "category": "Groceries",
        "confidence": None,
        "scope": scope,
        "participants": participants,
    }


def manual(client, data):
    response = mutate(client, "POST", "/api/receipts")
    assert response.status_code == 200, response.text
    id = response.json()["id"]
    response = mutate(client, "PUT", "/api/receipts/" + id, data)
    assert response.status_code == 200, response.text
    return id


def test_mixed_confirmation_private_exact_and_immutable(household):
    clients, users, house = household
    data = draft(
        users[0],
        house,
        [
            item("Rice", 2000, "HOUSEHOLD", []),
            item("Chicken", 1800, "SELECTED_MEMBERS", [u["id"] for u in users[:2]]),
            item("Soap", 1200, "HOUSEHOLD", []),
            item("Shampoo", 1000, "PERSONAL", [users[0]["id"]]),
        ],
    )
    id = manual(clients[0], data)
    assert all(v == 0 for v in balances(clients[0], house).values())
    assert mutate(clients[0], "POST", f"/api/receipts/{id}/confirm").status_code == 200
    assert list(balances(clients[0], house).values()) == [3300, -1700, -800, -800]
    assert clients[1].get(f"/api/receipts/{id}").status_code == 403
    assert mutate(clients[0], "POST", f"/api/receipts/{id}/confirm").status_code == 409
    assert mutate(clients[0], "PUT", f"/api/receipts/{id}", data).status_code == 409
    personal = clients[0].get("/api/expenses").json()["items"][0]
    assert mutate(clients[0], "DELETE", "/api/expenses/" + personal["id"]).status_code == 400
    assert clients[0].get(f"/api/households/{house}/analytics").json()["total"] == 5000
    assert clients[0].get("/api/analytics/personal").json()["personal"] == 1000
    assert "RECEIPT_CONFIRMED" not in [
        r["action"] for r in clients[1].get(f"/api/households/{house}/activity").json()
    ]


def test_failed_second_item_rolls_back_all_writes(household, engine):
    clients, users, house = household
    data = draft(
        users[0],
        house,
        [
            item("Valid", 1000, "PERSONAL", []),
            item("Invalid", 1000, "SELECTED_MEMBERS", [str(uuid4())]),
        ],
    )
    id = manual(clients[0], data)
    assert mutate(clients[0], "POST", f"/api/receipts/{id}/confirm").status_code == 400
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM expense WHERE receipt_id=:id"), {"id": id}
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM audit_event WHERE action='EXPENSE_CREATED'")
            ).scalar_one()
            == 0
        )
    assert clients[0].get(f"/api/receipts/{id}").json()["status"] == "NEEDS_REVIEW"


def test_reconciliation_and_adjustments(client):
    user = register(client)
    data = draft(
        user,
        items=[
            item("One", 333, "PERSONAL", []),
            item("Two", 333, "PERSONAL", []),
            item("Three", 334, "PERSONAL", []),
        ],
        discounts=100,
        tax=80,
        fees=21,
        total=1000,
    )
    id = manual(client, data)
    response = mutate(client, "POST", f"/api/receipts/{id}/confirm")
    assert response.status_code == 400 and response.json()["code"] == "INVALID_RECEIPT_TOTAL"
    assert mutate(client, "PUT", f"/api/receipts/{id}", data | {"total": 1001}).status_code == 200
    assert mutate(client, "POST", f"/api/receipts/{id}/confirm").status_code == 200
    amounts = [r["amount"] for r in client.get("/api/expenses").json()["items"]]
    assert sorted(amounts) == [333, 333, 335]


@pytest.mark.parametrize("kind", ["png", "jpeg", "webp"])
def test_actual_images_private_and_missing_ai_safe(client, kind):
    user = register(client)
    file = (FIXTURES / ("pixel." + kind)).read_bytes()
    response = mutate(
        client,
        "POST",
        "/api/receipts/extract",
        files={"file": ("../../fake.exe", file, "image/" + kind)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "FAILED" and "not configured" in response.json()["error"]
    assert response.json()["owner_id"] == user["id"]
    duplicate = mutate(
        client, "POST", "/api/receipts/extract", files={"file": ("fake", file, "image/" + kind)}
    )
    assert duplicate.json()["duplicate"] is True
    assert client.get("/api/analytics/personal").json()["total"] == 0
    assert (
        mutate(client, "PUT", "/api/receipts/" + response.json()["id"], draft(user)).status_code
        == 200
    )


@pytest.mark.parametrize("kind", ["png", "jpeg", "webp"])
def test_truncated_image_rejected(client, kind):
    register(client)
    data = (FIXTURES / ("pixel." + kind)).read_bytes()[:16]
    response = mutate(
        client, "POST", "/api/receipts/extract", files={"file": ("fake", data, "image/" + kind)}
    )
    assert response.status_code == 400, response.text
    assert client.get("/api/receipts").json() == []


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"", "image/png"),
        (b"not an image", "image/png"),
        (b"x" * (8 * 1024 * 1024 + 1), "image/png"),
        ((FIXTURES / "pixel.png").read_bytes(), "image/jpeg"),
    ],
    ids=["empty", "fake", "oversized", "spoofed-mime"],
)
def test_invalid_uploads(client, data, mime):
    register(client)
    response = mutate(
        client, "POST", "/api/receipts/extract", files={"file": ("fake.png", data, mime)}
    )
    assert response.status_code in {400, 413}, response.text


def test_processing_blocks_edits(client, engine):
    user = register(client)
    id = manual(client, draft(user))
    with engine.begin() as connection:
        connection.execute(text("UPDATE receipt SET status='PROCESSING' WHERE id=:id"), {"id": id})
    assert mutate(client, "PUT", f"/api/receipts/{id}", draft(user)).status_code == 409
    assert mutate(client, "POST", f"/api/receipts/{id}/confirm").status_code == 409


def test_concurrent_confirmation_generates_once(client, app):
    user = register(client)
    id = manual(client, draft(user))
    headers = csrf(client)
    cookies = dict(client.cookies)

    def confirm():
        with TestClient(app, raise_server_exceptions=False) as other:
            other.cookies.update(cookies)
            return other.post(f"/api/receipts/{id}/confirm", headers=headers).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm(), range(2)))
    assert sorted(results) == [200, 409]
    assert client.get("/api/analytics/personal").json()["total"] == 1000
