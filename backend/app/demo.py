"""Explicit opt-in fictional data for a local demonstration database."""

import os
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Store, engine_for
from app.schemas import ExpenseInput, RecurringInput, SettlementInput
from app.services.accounts import password_hash
from app.services.expenses import Expenses
from app.services.finance import Finance, add_months
from app.services.households import Households
from app.services.recurring import Recurring


def seed(db: Store, password: str) -> None:
    encoded = password_hash(password)
    if db.exists("SELECT id FROM app_user WHERE email='demo@example.test'"):
        return
    users = [uuid4() for _ in range(4)]
    for index, name in enumerate(["Demo User", "Alex", "David", "Sam"]):
        db.execute(
            "INSERT INTO app_user(id,name,email,password_hash,diet,email_verified) VALUES(:id,:name,:email,:password,:diet,true)",
            id=users[index],
            name=name,
            email="demo@example.test" if index == 0 else name.lower() + "@example.test",
            password=encoded,
            diet="Vegan" if index == 1 else "No restriction",
        )
    households, expenses = Households(db), Expenses(db)
    owner = users[0]
    house = households.create(owner, "Apartment 204 · Fictional demo")["id"]
    for user in users[1:]:
        households.accept(user, households.invite(owner, house)["token"])
    db.execute(
        "UPDATE membership SET joined_at=:day WHERE household_id=:h",
        day=add_months(date.today(), -7).replace(day=1),
        h=house,
    )
    for index in range(5, -1, -1):
        day = add_months(date.today(), -index).replace(day=1)
        records = [
            ("Rent", 240000, "Rent", "HOUSEHOLD", owner),
            ("Internet", 7500, "Utilities", "HOUSEHOLD", users[1]),
            ("Electricity", 14800 + index * 420, "Utilities", "HOUSEHOLD", owner),
            ("Common groceries", 31700 + index * 310, "Groceries", "HOUSEHOLD", owner),
            ("Chicken & fish", 4800 + index * 180, "Groceries", "SELECTED_MEMBERS", users[2]),
            ("Car insurance", 16500, "Insurance", "PERSONAL", owner),
            ("Coffee & dining", 14300 + index * 730, "Dining", "PERSONAL", owner),
            ("Phone", 5500, "Phone", "PERSONAL", owner),
            ("Transportation", 8200 + index * 670, "Transportation", "PERSONAL", owner),
        ]
        for title, amount, category, scope, payer in records:
            expenses.create(
                owner,
                ExpenseInput(
                    title=title,
                    merchant="Fictional demo",
                    amount=amount,
                    category=category,
                    scope=scope,
                    householdId=None if scope == "PERSONAL" else house,
                    payerId=payer,
                    date=day,
                    splitMethod="EQUAL",
                    participants=[owner, users[2]],
                    notes="Fictional development data",
                ),
            )
    Finance(db).settle(
        users[1],
        house,
        SettlementInput(
            fromUser=users[1], toUser=owner, amount=60000, method="Cash", date=date.today()
        ),
    )
    for title, amount, category, scope, due in [
        ("Phone", 5500, "Phone", "PERSONAL", 10),
        ("Internet", 7500, "Utilities", "HOUSEHOLD", 5),
    ]:
        Recurring(db).save(
            owner,
            None,
            RecurringInput(
                expense=ExpenseInput(
                    title=title,
                    amount=amount,
                    category=category,
                    scope=scope,
                    householdId=None if scope == "PERSONAL" else house,
                    payerId=owner,
                    date=date.today(),
                    splitMethod="EQUAL",
                ),
                nextDue=date.today() + timedelta(days=due),
                frequency="MONTHLY",
                active=True,
            ),
        )


def main():
    settings = Settings()
    if settings.production:
        raise RuntimeError("Demo seeding is disabled in production and staging.")
    password = os.environ.get("DEMO_PASSWORD", "")
    engine = engine_for(settings)
    with Session(engine) as session, session.begin():
        seed(Store(session), password)
    engine.dispose()
    print("Fictional demo data is ready. Existing demo data was preserved.")


if __name__ == "__main__":
    main()
