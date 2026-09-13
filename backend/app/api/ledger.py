from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from app.errors import ApiError, invalid
from app.schemas import (
    Address,
    BalanceOutput,
    ExpenseInput,
    ExpenseOutput,
    ExpensePage,
    Name,
    RecurringInput,
    SettlementInput,
    Token,
)
from app.security.session import Database, User
from app.services.expenses import Expenses
from app.services.finance import Finance
from app.services.households import Households
from app.services.idempotency import replayable
from app.services.recurring import Recurring
from app.services.write_guard import write_guard

router = APIRouter(tags=["Households and ledger"])


@router.get("/households")
def households(db: Database, user: User):
    return Households(db).list(user)


@router.post("/households")
def create_household(data: Name, db: Database, user: User):
    return Households(db).create(user, data.name)


@router.patch("/households/{id}")
def rename_household(id: UUID, data: Name, db: Database, user: User):
    Households(db).rename(user, id, data.name)


@router.get("/households/{id}/members")
def members(id: UUID, db: Database, user: User):
    return Households(db).members(user, id)


@router.delete("/households/{id}/members/{membership}")
def remove_member(id: UUID, membership: UUID, db: Database, user: User):
    Households(db).leave(user, id, membership)


@router.get("/households/{id}/activity")
def activity(id: UUID, db: Database, user: User):
    return Households(db).activity(user, id)


@router.post("/households/{id}/invitations")
def invite(id: UUID, db: Database, user: User):
    return Households(db).invite(user, id)


@router.post("/households/{id}/invitations/email")
def email_invite(id: UUID, data: Address, request: Request, db: Database, user: User):
    if not request.app.state.email.available():
        raise ApiError(
            503,
            "EMAIL_UNAVAILABLE",
            "Email delivery is unavailable. Share an invitation code instead.",
        )
    invitation = Households(db).invite(user, id)
    try:
        request.app.state.email.send(
            data.email,
            "RoommateLedger household invitation",
            f"Sign in or create your account at {request.app.state.settings.frontend_url}. Open Household and enter this single-use code: {invitation['token']}\nThe code expires in 7 days.",
        )
    except Exception as error:
        raise ApiError(
            503,
            "EMAIL_UNAVAILABLE",
            "The email could not be delivered. Retry or share an invitation code.",
        ) from error


@router.post("/invitations/accept")
def accept_body(data: Token, db: Database, user: User):
    return Households(db).accept(user, data.token)


@router.post("/invitations/{token}/accept", deprecated=True)
def accept(token: str, db: Database, user: User):
    return Households(db).accept(user, token)


@router.get("/expenses", response_model=ExpensePage)
def expenses(
    db: Database,
    user: User,
    householdId: UUID | None = None,
    scope: str | None = None,
    search: str | None = None,
    category: str | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    payer: UUID | None = None,
    participant: UUID | None = None,
    minimum: Annotated[int | None, Query(alias="min")] = None,
    maximum: Annotated[int | None, Query(alias="max")] = None,
    page: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    return Expenses(db).list(
        user,
        householdId,
        page,
        scope=scope,
        search=search,
        category=category,
        from_date=from_date,
        to_date=to_date,
        payer=payer,
        participant=participant,
        minimum=minimum,
        maximum=maximum,
    )


@router.post("/expenses", response_model=ExpenseOutput)
def create_expense(
    data: ExpenseInput,
    db: Database,
    user: User,
    request: Request,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    if request.app.state.settings.app_env == "production" and idempotency_key is None:
        raise invalid("Idempotency-Key is required for financial creation.")
    write_guard(db, user)
    if data.householdId is not None:
        Households(db).member(user, data.householdId)
    return replayable(
        db,
        user,
        "expense.create",
        idempotency_key,
        data.model_dump(mode="json"),
        lambda: Expenses(db).create(user, data),
    )


@router.get("/expenses/{id}", response_model=ExpenseOutput)
def expense(id: UUID, db: Database, user: User):
    return Expenses(db).get(user, id)


@router.patch("/expenses/{id}", response_model=ExpenseOutput)
def edit_expense(id: UUID, data: ExpenseInput, db: Database, user: User):
    return Expenses(db).edit(user, id, data)


@router.delete("/expenses/{id}")
def delete_expense(id: UUID, db: Database, user: User):
    Expenses(db).delete(user, id)


@router.get("/households/{id}/balances", response_model=list[BalanceOutput])
def balances(id: UUID, db: Database, user: User):
    return Finance(db).balances(user, id)


@router.get("/households/{id}/settlements")
def settlements(id: UUID, db: Database, user: User):
    return Finance(db).settlements(user, id)


@router.post("/households/{id}/settlements")
def settle(
    id: UUID,
    data: SettlementInput,
    db: Database,
    user: User,
    request: Request,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    if request.app.state.settings.app_env == "production" and idempotency_key is None:
        raise invalid("Idempotency-Key is required for financial creation.")
    write_guard(db, user)
    Households(db).member(user, id)
    return replayable(
        db,
        user,
        "settlement.create",
        idempotency_key,
        {"householdId": str(id), **data.model_dump(mode="json")},
        lambda: Finance(db).settle(user, id, data),
    )


@router.get("/analytics/personal")
def personal_analytics(db: Database, user: User, month: str | None = None):
    return Finance(db).analytics(user, None, month)


@router.get("/households/{id}/analytics")
def household_analytics(id: UUID, db: Database, user: User, month: str | None = None):
    return Finance(db).analytics(user, id, month)


@router.get("/recurring")
def recurring(db: Database, user: User, householdId: UUID | None = None):
    return Recurring(db).list(user, householdId)


@router.post("/recurring")
def create_recurring(data: RecurringInput, db: Database, user: User):
    return Recurring(db).save(user, None, data)


@router.patch("/recurring/{id}")
def edit_recurring(id: UUID, data: RecurringInput, db: Database, user: User):
    return Recurring(db).save(user, id, data)


@router.post("/recurring/{id}/record", response_model=ExpenseOutput)
def record_recurring(id: UUID, db: Database, user: User):
    return Recurring(db).record(user, id)
