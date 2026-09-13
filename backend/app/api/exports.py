import csv
import io
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.errors import invalid
from app.security.session import Database, User
from app.services.households import Households

router = APIRouter(prefix="/export", tags=["Private CSV exports"])


def safe_cell(value) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r")):
        return "'" + text
    return text


def csv_response(rows: list[dict], columns: list[str], name: str) -> Response:
    if len(rows) > 10000:
        raise invalid("Export exceeds 10,000 rows. Choose a smaller date range.")
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["amount_cents" if field == "amount" else field for field in columns])
    for row in rows:
        writer.writerow([safe_cell(row[field]) for field in columns])
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/expenses")
def expenses(
    db: Database,
    user: User,
    householdId: UUID | None = None,
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
):
    if householdId:
        Households(db).member(user, householdId)
        where = "household_id=:subject AND scope<>'PERSONAL'"
    else:
        where = "owner_id=:subject AND scope='PERSONAL'"
    params = {"subject": householdId or user}
    if from_date:
        where += " AND expense_date>=:start"
        params["start"] = from_date
    if to_date:
        where += " AND expense_date<=:end"
        params["end"] = to_date
    columns = [
        "id",
        "title",
        "merchant",
        "expense_date",
        "category",
        "scope",
        "amount",
        "currency",
        "payer_id",
    ]
    rows = db.all(
        "SELECT "
        + ",".join(columns)
        + " FROM expense WHERE deleted=false AND "
        + where
        + " ORDER BY expense_date,id LIMIT 10001",
        **params,
    )
    return csv_response(rows, columns, "expenses")


@router.get("/settlements")
def settlements(householdId: UUID, db: Database, user: User):
    Households(db).member(user, householdId)
    columns = ["id", "from_user", "to_user", "amount", "method", "payment_date"]
    rows = db.all(
        "SELECT "
        + ",".join(columns)
        + " FROM settlement WHERE household_id=:h ORDER BY payment_date,id LIMIT 10001",
        h=householdId,
    )
    return csv_response(rows, columns, "settlements")
