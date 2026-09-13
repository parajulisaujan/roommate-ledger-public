import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from app.db import Store
from app.errors import invalid
from app.schemas import SettlementInput
from app.services.households import Households
from app.services.money import positive
from app.services.write_guard import write_guard


def add_months(day: date, count: int) -> date:
    index = day.year * 12 + day.month - 1 + count
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


class Finance:
    def __init__(self, db: Store):
        self.db = db
        self.households = Households(db)

    def balances(self, user: UUID, household: UUID):
        self.households.member(user, household)
        return self.db.all(
            """SELECT u.id,u.name,
          COALESCE((SELECT SUM(e.amount) FROM expense e WHERE e.household_id=:h AND e.payer_id=u.id AND e.deleted=false),0)
          - COALESCE((SELECT SUM(a.amount) FROM allocation a JOIN expense e ON e.id=a.expense_id WHERE e.household_id=:h AND a.user_id=u.id AND e.deleted=false),0)
          + COALESCE((SELECT SUM(s.amount) FROM settlement s WHERE s.household_id=:h AND s.from_user=u.id),0)
          - COALESCE((SELECT SUM(s.amount) FROM settlement s WHERE s.household_id=:h AND s.to_user=u.id),0) AS balance
        FROM app_user u WHERE EXISTS(SELECT 1 FROM membership m WHERE m.user_id=u.id AND m.household_id=:h) ORDER BY u.name""",
            h=household,
        )

    def settle(self, user: UUID, household: UUID, data: SettlementInput):
        write_guard(self.db, user)
        self.households.member(user, household)
        amount = positive(data.amount)
        if (
            user != data.fromUser
            or user == data.toUser
            or data.date > date.today()
            or not data.method.strip()
        ):
            raise invalid("Record a payment you made, with a valid recipient, date and method.")
        if not self.db.exists(
            "SELECT id FROM membership WHERE household_id=:h AND user_id=:u",
            h=household,
            u=data.toUser,
        ):
            raise invalid("Recipient must belong to household history.")
        id = uuid4()
        self.db.execute(
            "INSERT INTO settlement(id,household_id,from_user,to_user,amount,method,payment_date,created_by) VALUES(:id,:h,:u,:recipient,:amount,:method,:day,:u)",
            id=id,
            h=household,
            u=user,
            recipient=data.toUser,
            amount=amount,
            method=data.method,
            day=data.date,
        )
        self.db.audit(user, household, "SETTLEMENT_RECORDED", id)

    def settlements(self, user: UUID, household: UUID):
        self.households.member(user, household)
        return self.db.all(
            "SELECT s.*,f.name AS from_name,t.name AS to_name FROM settlement s JOIN app_user f ON f.id=s.from_user JOIN app_user t ON t.id=s.to_user WHERE household_id=:h ORDER BY s.payment_date DESC LIMIT 100",
            h=household,
        )

    def analytics(self, user: UUID, household: UUID | None, month: str | None):
        try:
            day = date.fromisoformat((month or date.today().strftime("%Y-%m")) + "-01")
            # Bound all six trend months and the next month to Python's supported date range.
            add_months(day, -5)
            add_months(day, 1)
        except ValueError as error:
            raise invalid("Enter a valid reporting month.") from error
        if household:
            self.households.member(user, household)
            source = " FROM expense e WHERE e.deleted=false AND e.household_id=:subject AND e.scope<>'PERSONAL'"
            amount = "e.amount"
        else:
            source = " FROM expense e JOIN allocation a ON a.expense_id=e.id WHERE e.deleted=false AND a.user_id=:subject"
            amount = "a.amount"
        source += " AND e.expense_date>=:start AND e.expense_date<:end"

        def aggregate(start: date):
            return self.db.one(
                f"SELECT COALESCE(SUM({amount}),0) AS total,COALESCE(SUM(CASE WHEN e.scope='PERSONAL' THEN {amount} ELSE 0 END),0) AS personal,COALESCE(SUM(CASE WHEN e.scope<>'PERSONAL' THEN {amount} ELSE 0 END),0) AS shared"
                + source,
                subject=household or user,
                start=start,
                end=add_months(start, 1),
            )

        def categories(start: date):
            return self.db.all(
                f"SELECT e.category,SUM({amount}) AS total"
                + source
                + " GROUP BY e.category ORDER BY total DESC",
                subject=household or user,
                start=start,
                end=add_months(start, 1),
            )

        current = aggregate(day)
        previous = aggregate(add_months(day, -1))["total"]
        difference = current["total"] - previous
        current.update(
            month=day.strftime("%Y-%m"),
            previousTotal=previous,
            difference=difference,
            percentChange=None
            if previous == 0
            else (difference * Decimal("100") / previous).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            ),
            categories=categories(day),
            previousCategories=categories(add_months(day, -1)),
            trend=[
                dict(aggregate(add_months(day, -i)), month=add_months(day, -i).strftime("%Y-%m"))
                for i in range(5, -1, -1)
            ],
        )
        return current
