from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.db import Store
from app.errors import conflict, forbidden, invalid
from app.schemas import ExpenseInput
from app.services.households import Households
from app.services.money import cents, split
from app.services.write_guard import write_guard


class Expenses:
    def __init__(self, db: Store):
        self.db = db
        self.households = Households(db)

    def validate(self, user: UUID, data: ExpenseInput) -> dict[UUID, Decimal]:
        write_guard(self.db, user)
        if not date(1900, 1, 1) <= data.date <= date.today():
            raise invalid(
                "Check title, category and date. Future expenses belong in recurring bills."
            )
        if data.scope == "PERSONAL":
            if data.householdId is not None or data.payerId not in {None, user}:
                raise invalid("Personal expenses must belong to and be paid by you.")
            return split(data.amount, "EQUAL", [user])
        self.households.member(user, data.householdId)
        applicable = self.households.applicable(data.householdId, data.date)
        if user not in applicable or data.payerId not in applicable:
            raise invalid(
                "Creator and payer must have belonged to the household on the expense date."
            )
        participants = applicable if data.scope == "HOUSEHOLD" else data.participants
        if participants is None or not set(participants) <= set(applicable):
            raise invalid("Participants must have belonged to the household on this date.")
        return split(data.amount, data.splitMethod, participants, data.values)

    def get(self, user: UUID, id: UUID):
        row = self.db.one(
            "SELECT e.*,u.name AS payer_name FROM expense e JOIN app_user u ON u.id=e.payer_id WHERE e.id=:id AND e.deleted=false",
            id=id,
        )
        if row["scope"] == "PERSONAL":
            if row["owner_id"] != user:
                raise forbidden()
        else:
            self.households.member(user, row["household_id"])
        row["allocations"] = self.db.all(
            "SELECT a.user_id,a.amount,u.name FROM allocation a JOIN app_user u ON u.id=a.user_id WHERE a.expense_id=:id ORDER BY u.name",
            id=id,
        )
        return row

    def _params(self, user: UUID, data: ExpenseInput):
        personal = data.scope == "PERSONAL"
        return dict(
            u=user,
            h=data.householdId,
            payer=user if personal else data.payerId,
            title=data.title,
            merchant=data.merchant,
            amount=cents(data.amount),
            category=data.category,
            scope=data.scope,
            method="EQUAL" if personal else data.splitMethod,
            day=data.date,
            notes=data.notes,
        )

    def _allocations(self, id: UUID, shares: dict[UUID, Decimal]):
        for user, amount in shares.items():
            self.db.execute(
                "INSERT INTO allocation(expense_id,user_id,amount) VALUES(:id,:u,:amount)",
                id=id,
                u=user,
                amount=amount,
            )

    def create(
        self,
        user: UUID,
        data: ExpenseInput,
        receipt: UUID | None = None,
        template: UUID | None = None,
    ):
        shares = self.validate(user, data)
        id = uuid4()
        self.db.execute(
            "INSERT INTO expense(id,owner_id,household_id,payer_id,title,merchant,amount,category,scope,split_method,expense_date,notes,receipt_id,template_id) VALUES(:id,:u,:h,:payer,:title,:merchant,:amount,:category,:scope,:method,:day,:notes,:receipt,:template)",
            id=id,
            receipt=receipt,
            template=template,
            **self._params(user, data),
        )
        self._allocations(id, shares)
        self.db.audit(user, data.householdId, "EXPENSE_CREATED", id)
        return self.get(user, id)

    def _editable(self, user: UUID, id: UUID):
        write_guard(self.db, user)
        self.db.one("SELECT id FROM expense WHERE id=:id FOR UPDATE", id=id)
        row = self.get(user, id)
        if row["owner_id"] != user:
            raise forbidden()
        if row["receipt_id"] is not None:
            raise invalid("Confirmed receipt items are immutable. Record a correction separately.")
        return row

    def edit(self, user: UUID, id: UUID, data: ExpenseInput):
        row = self._editable(user, id)
        if data.version is None or data.version != row["version"]:
            raise conflict("Expense changed. Refresh before editing.")
        if data.householdId != row["household_id"] or data.scope != row["scope"]:
            raise invalid("Keep the original expense scope and household.")
        shares = self.validate(user, data)
        self.db.execute(
            "UPDATE expense SET title=:title,merchant=:merchant,amount=:amount,category=:category,payer_id=:payer,split_method=:method,expense_date=:day,notes=:notes,version=version+1 WHERE id=:id",
            id=id,
            **self._params(user, data),
        )
        self.db.execute("DELETE FROM allocation WHERE expense_id=:id", id=id)
        self._allocations(id, shares)
        self.db.audit(user, data.householdId, "EXPENSE_EDITED", id)
        return self.get(user, id)

    def delete(self, user: UUID, id: UUID):
        row = self._editable(user, id)
        self.db.execute("UPDATE expense SET deleted=true,version=version+1 WHERE id=:id", id=id)
        self.db.audit(user, row["household_id"], "EXPENSE_DELETED", id)

    def list(self, user: UUID, household: UUID | None = None, page: int = 0, **filters):
        params = {"subject": household or user}
        if household:
            self.households.member(user, household)
            where = "e.deleted=false AND e.household_id=:subject AND e.scope<>'PERSONAL'"
        else:
            where = "e.deleted=false AND e.owner_id=:subject AND e.scope='PERSONAL'"
        conditions = {
            "scope": "e.scope=:scope",
            "category": "e.category=:category",
            "from_date": "e.expense_date>=:from_date",
            "to_date": "e.expense_date<=:to_date",
            "payer": "e.payer_id=:payer",
            "minimum": "e.amount>=:minimum",
            "maximum": "e.amount<=:maximum",
            "participant": "EXISTS(SELECT 1 FROM allocation a WHERE a.expense_id=e.id AND a.user_id=:participant)",
        }
        for key, condition in conditions.items():
            value = filters.get(key)
            if value is not None and value != "":
                where += " AND " + condition
                params[key] = value
        if filters.get("search", ""):
            where += (
                " AND (LOWER(e.title) LIKE :search OR LOWER(COALESCE(e.merchant,'')) LIKE :search)"
            )
            params["search"] = "%" + filters["search"].lower() + "%"
        total = self.db.one("SELECT COUNT(*) AS n FROM expense e WHERE " + where, **params)["n"]
        items = self.db.all(
            "SELECT e.*,u.name AS payer_name FROM expense e JOIN app_user u ON u.id=e.payer_id WHERE "
            + where
            + " ORDER BY e.expense_date DESC,e.created_at DESC LIMIT 25 OFFSET :offset",
            offset=page * 25,
            **params,
        )
        return {"items": items, "total": total, "page": page, "pageSize": 25}
