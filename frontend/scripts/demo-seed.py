"""Fictional portfolio data; invoked only inside the disposable demo container."""

import os
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import Store, engine_for
from app.schemas import ExpenseInput, SettlementInput
from app.services.accounts import password_hash
from app.services.expenses import Expenses
from app.services.finance import Finance, add_months
from app.services.households import Households
from sqlalchemy.orm import Session

settings = Settings()
demo_database = os.environ.get("DEMO_DATABASE", "")
if (
    settings.app_env != "development"
    or not demo_database.startswith("ledger_demo_")
    or not settings.database_url.endswith("/" + demo_database)
):
    raise RuntimeError("This fixture requires the disposable local demo database.")
engine = engine_for(settings)
with Session(engine) as session, session.begin():
    db = Store(session)
    if db.exists("SELECT id FROM app_user LIMIT 1"):
        raise RuntimeError("This fixture requires an empty database.")
    names = ["Saujan Parajuli", "Sejal Khadka", "Bikash Gurung", "Binod Tiwari"]
    users = [uuid4() for _ in names]
    encoded = password_hash(os.environ["DEMO_PASSWORD"])
    for user, name in zip(users, names):
        db.execute(
            "INSERT INTO app_user(id,name,email,password_hash,diet,email_verified) "
            "VALUES(:id,:name,:email,:password,:diet,true)",
            id=user,
            name=name,
            email=name.split()[0].lower() + ".roommateledger@example.test",
            password=encoded,
            diet="No restriction",
        )
    owner = users[0]
    households, expenses = Households(db), Expenses(db)
    house = households.create(owner, "Irving Apartment")["id"]
    for user in users[1:]:
        households.accept(user, households.invite(owner, house)["token"])
    db.execute(
        "UPDATE membership SET joined_at=:day WHERE household_id=:house",
        day=add_months(datetime.now(ZoneInfo("America/Chicago")).date(), -3).replace(
            day=1
        ),
        house=house,
    )
    for month in [2, 1, 0]:
        for title, amount, category, merchant, payer in [
            ("Walmart groceries", 8640, "Groceries", "Walmart", owner),
            ("Electric bill", 12475, "Utilities", "Electric utility", users[1]),
            ("Costco household supplies", 4218, "Shopping", "Costco", users[2]),
            ("Dinner", 6400, "Dining", "Neighborhood restaurant", users[3]),
        ]:
            expenses.create(
                owner,
                ExpenseInput(
                    title=title,
                    amount=amount + month * 125,
                    category=category,
                    merchant=merchant,
                    scope="HOUSEHOLD",
                    householdId=house,
                    payerId=payer,
                    date=add_months(
                        datetime.now(ZoneInfo("America/Chicago")).date(), -month
                    ).replace(day=1),
                    splitMethod="EQUAL",
                ),
            )
    Finance(db).settle(
        users[2],
        house,
        SettlementInput(
            fromUser=users[2],
            toUser=users[1],
            amount=2500,
            method="Cash",
            date=datetime.now(ZoneInfo("America/Chicago")).date(),
        ),
    )
engine.dispose()
