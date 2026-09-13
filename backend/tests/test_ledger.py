from datetime import date, timedelta
from uuid import uuid4

import pytest
from conftest import mutate, register
from fastapi.testclient import TestClient
from sqlalchemy import text


def expense(user, house=None, amount=10000, scope=None, **overrides):
    return {
        "title": "Test groceries",
        "merchant": "Store",
        "amount": amount,
        "category": "Groceries",
        "scope": scope or ("HOUSEHOLD" if house else "PERSONAL"),
        "householdId": house,
        "payerId": user["id"],
        "date": date.today().isoformat(),
        "splitMethod": "EQUAL",
        "participants": [],
        "values": {},
        "notes": "",
    } | overrides


def balances(client, house):
    response = client.get(f"/api/households/{house}/balances")
    assert response.status_code == 200, response.text
    return {r["id"]: r["balance"] for r in response.json()}


def test_shared_balance_and_settlement(household):
    clients, users, house = household
    response = mutate(clients[0], "POST", "/api/expenses", expense(users[0], house, 16000))
    assert response.status_code == 200, response.text
    assert [r["amount"] for r in response.json()["allocations"]] == [4000] * 4
    assert balances(clients[0], house)[users[0]["id"]] == 12000
    payment = {
        "fromUser": users[1]["id"],
        "toUser": users[0]["id"],
        "amount": 4000,
        "method": "Cash",
        "date": date.today().isoformat(),
    }
    assert (
        mutate(clients[1], "POST", f"/api/households/{house}/settlements", payment).status_code
        == 200
    )
    result = balances(clients[0], house)
    assert result[users[1]["id"]] == 0 and result[users[0]["id"]] == 8000
    assert sum(result.values()) == 0


def test_private_expenses_and_analytics_never_leak(household, app):
    clients, users, house = household
    for creator, other in [(0, 1), (1, 0)]:
        response = mutate(
            clients[creator], "POST", "/api/expenses", expense(users[creator], amount=4000)
        )
        assert response.status_code == 200, response.text
        assert clients[other].get("/api/expenses/" + response.json()["id"]).status_code == 403
    assert clients[0].get(f"/api/households/{house}/analytics").json()["total"] == 0
    assert clients[2].get("/api/analytics/personal").json()["total"] == 0
    with TestClient(app) as outsider:
        register(outsider)
        for suffix in ["members", "balances", "settlements", "analytics", "activity"]:
            assert outsider.get(f"/api/households/{house}/{suffix}").status_code == 403
        for path in ["expenses", "recurring", "export/expenses", "export/settlements"]:
            assert outsider.get(f"/api/{path}?householdId={house}").status_code == 403


@pytest.mark.parametrize(
    "method,values,expected",
    [
        ("EQUAL", {}, [3000] * 3),
        ("FIXED", {0: 4500, 1: 2700, 2: 1800}, [4500, 2700, 1800]),
        ("PERCENTAGE", {0: 5000, 1: 3000, 2: 2000}, [4500, 2700, 1800]),
    ],
)
def test_selected_splits(household, method, values, expected):
    clients, users, house = household
    data = expense(
        users[0],
        house,
        9000,
        "SELECTED_MEMBERS",
        participants=[u["id"] for u in users[:3]],
        splitMethod=method,
        values={users[i]["id"]: value for i, value in values.items()},
    )
    response = mutate(clients[0], "POST", "/api/expenses", data)
    assert response.status_code == 200, response.text
    assert [r["amount"] for r in response.json()["allocations"]] == expected
    assert balances(clients[0], house)[users[3]["id"]] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"amount": 10.5},
        {"amount": "100"},
        {"amount": True},
        {"date": "bad"},
        {"date": "2999-01-01"},
        {"payerId": str(uuid4())},
        {"scope": "SELECTED_MEMBERS", "participants": [str(uuid4())]},
        {"splitMethod": "PERCENTAGE", "values": {}},
    ],
)
def test_invalid_expense_is_atomic(household, change):
    clients, users, house = household
    response = mutate(clients[0], "POST", "/api/expenses", expense(users[0], house, **change))
    assert response.status_code == 400, response.text
    assert sum(abs(v) for v in balances(clients[0], house).values()) == 0


def test_edit_optimistic_lock_and_owner_only(household):
    clients, users, house = household
    data = expense(users[0], house)
    original = mutate(clients[0], "POST", "/api/expenses", data).json()
    path = "/api/expenses/" + original["id"]
    assert mutate(clients[1], "PATCH", path, data | {"version": 0}).status_code == 403
    assert (
        mutate(clients[0], "PATCH", path, data | {"version": 0, "amount": 20000}).status_code == 200
    )
    assert mutate(clients[0], "PATCH", path, data | {"version": 0}).status_code == 409
    assert mutate(clients[1], "DELETE", path).status_code == 403
    assert mutate(clients[0], "DELETE", path).status_code == 200
    assert clients[0].get(path).status_code == 404
    assert sum(abs(v) for v in balances(clients[0], house).values()) == 0


def test_membership_history_and_finalized_shares(household, engine):
    clients, users, house = household
    today = date.today()
    boundary = today.replace(day=1)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE membership SET joined_at=:d WHERE household_id=:h"),
            {"d": boundary - timedelta(days=100), "h": house},
        )
        connection.execute(
            text("UPDATE membership SET joined_at=:d WHERE user_id=:u"),
            {"d": boundary, "u": users[3]["id"]},
        )
        connection.execute(
            text("UPDATE membership SET left_at=:d WHERE user_id=:u"),
            {"d": boundary - timedelta(days=1), "u": users[1]["id"]},
        )
    prior = mutate(
        clients[0],
        "POST",
        "/api/expenses",
        expense(users[0], house, 9000, date=(boundary - timedelta(days=10)).isoformat()),
    ).json()
    assert {r["user_id"] for r in prior["allocations"]} == {u["id"] for u in users[:3]}
    current = mutate(clients[0], "POST", "/api/expenses", expense(users[0], house, 9000)).json()
    assert {r["user_id"] for r in current["allocations"]} == {users[i]["id"] for i in (0, 2, 3)}
    assert clients[1].get(f"/api/households/{house}/balances").status_code == 403
    assert balances(clients[0], house)[users[1]["id"]] == -3000
    assert (
        clients[0].get("/api/expenses/" + prior["id"]).json()["allocations"] == prior["allocations"]
    )


def test_recurring_history_and_duplicate_due_date(client):
    user = register(client)
    data = {
        "expense": expense(user, amount=5500),
        "nextDue": date.today().isoformat(),
        "frequency": "MONTHLY",
        "active": True,
    }
    template = mutate(client, "POST", "/api/recurring", data).json()["id"]
    assert client.get("/api/analytics/personal").json()["total"] == 0
    recorded = mutate(client, "POST", f"/api/recurring/{template}/record")
    assert recorded.status_code == 200, recorded.text
    assert mutate(client, "POST", f"/api/recurring/{template}/record").status_code == 400
    assert (
        mutate(
            client,
            "PATCH",
            f"/api/recurring/{template}",
            data | {"expense": expense(user, amount=9900)},
        ).status_code
        == 200
    )
    assert mutate(client, "POST", f"/api/recurring/{template}/record").status_code == 409
    assert client.get("/api/analytics/personal").json()["total"] == 5500


def test_analytics_months_categories_no_baseline(client):
    user = register(client)
    assert client.get("/api/analytics/personal").json()["percentChange"] is None
    prior = date.today().replace(day=1) - timedelta(days=1)
    assert (
        mutate(
            client, "POST", "/api/expenses", expense(user, amount=10000, date=prior.isoformat())
        ).status_code
        == 200
    )
    assert mutate(client, "POST", "/api/expenses", expense(user, amount=8000)).status_code == 200
    report = client.get("/api/analytics/personal").json()
    assert (
        report["total"],
        report["previousTotal"],
        report["difference"],
        report["percentChange"],
    ) == (8000, 10000, -2000, -20)
    assert report["categories"] == [{"category": "Groceries", "total": 8000}]
    assert len(report["trend"]) == 6


def test_invitation_single_use_and_owner_permissions(household, app):
    clients, users, house = household
    assert mutate(clients[1], "POST", f"/api/households/{house}/invitations").status_code == 403
    token = mutate(clients[0], "POST", f"/api/households/{house}/invitations").json()["token"]
    with TestClient(app) as other:
        register(other)
        assert mutate(other, "POST", "/api/invitations/accept", {"token": token}).status_code == 200
        assert mutate(other, "POST", "/api/invitations/accept", {"token": token}).status_code == 404
