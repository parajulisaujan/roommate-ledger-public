from datetime import date, timedelta
from uuid import UUID, uuid4

from app.db import Store
from app.errors import forbidden, invalid
from app.schemas import ExpenseInput, RecurringInput
from app.services.expenses import Expenses
from app.services.finance import add_months
from app.services.write_guard import write_guard


class Recurring:
    def __init__(self, db: Store):
        self.db = db
        self.expenses = Expenses(db)

    def list(self, user: UUID, household: UUID | None):
        if household:
            self.expenses.households.member(user, household)
            rows = self.db.all(
                "SELECT * FROM recurring_template WHERE household_id=:h ORDER BY next_due",
                h=household,
            )
        else:
            rows = self.db.all(
                "SELECT * FROM recurring_template WHERE owner_id=:u AND household_id IS NULL ORDER BY next_due",
                u=user,
            )
        for row in rows:
            row["expense"] = ExpenseInput.model_validate_json(row.pop("draft")).model_dump(
                mode="json"
            )
        return rows

    def save(self, user: UUID, id: UUID | None, data: RecurringInput):
        self.expenses.validate(user, data.expense.model_copy(update={"date": date.today()}))
        params = dict(
            u=user,
            h=data.expense.householdId,
            draft=data.expense.model_dump_json(),
            due=data.nextDue,
            frequency=data.frequency,
            active=data.active,
        )
        if id is None:
            id = uuid4()
            self.db.execute(
                "INSERT INTO recurring_template(id,owner_id,household_id,draft,next_due,frequency,active) VALUES(:id,:u,:h,:draft,:due,:frequency,:active)",
                id=id,
                **params,
            )
        else:
            old = self.db.one("SELECT * FROM recurring_template WHERE id=:id FOR UPDATE", id=id)
            if old["owner_id"] != user:
                raise forbidden()
            self.db.execute(
                "UPDATE recurring_template SET household_id=:h,draft=:draft,next_due=:due,frequency=:frequency,active=:active WHERE id=:id",
                id=id,
                **params,
            )
        return {"id": id}

    def record(self, user: UUID, id: UUID):
        write_guard(self.db, user)
        row = self.db.one("SELECT * FROM recurring_template WHERE id=:id FOR UPDATE", id=id)
        if row["owner_id"] != user:
            raise forbidden()
        if not row["active"]:
            raise invalid("This recurring bill is paused.")
        due = row["next_due"]
        if due > date.today():
            raise invalid("This bill is not due yet.")
        data = ExpenseInput.model_validate_json(row["draft"]).model_copy(
            update={"date": due, "version": None}
        )
        result = self.expenses.create(user, data, template=id)
        next_due = (
            due + timedelta(weeks=1)
            if row["frequency"] == "WEEKLY"
            else add_months(due, 12 if row["frequency"] == "YEARLY" else 1)
        )
        self.db.execute(
            "UPDATE recurring_template SET next_due=:due WHERE id=:id", due=next_due, id=id
        )
        return result
