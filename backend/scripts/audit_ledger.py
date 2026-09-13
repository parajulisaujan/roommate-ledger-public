"""Read-only financial conservation audit; output contains counts, never private records."""

import json

from sqlalchemy import text

from app.config import Settings
from app.db import engine_for


def main():
    engine = engine_for(Settings())
    with engine.connect() as connection:
        mismatches = connection.execute(
            text(
                "SELECT COUNT(*) FROM (SELECT e.id FROM expense e LEFT JOIN allocation a ON a.expense_id=e.id GROUP BY e.id,e.amount HAVING e.amount<>COALESCE(SUM(a.amount),0)) invalid"
            )
        ).scalar_one()
        count = connection.execute(text("SELECT COUNT(*) FROM expense")).scalar_one()
        unconfirmed = connection.execute(
            text(
                "SELECT COUNT(*) FROM expense e JOIN receipt r ON r.id=e.receipt_id WHERE r.status<>'CONFIRMED'"
            )
        ).scalar_one()
    engine.dispose()
    print(
        json.dumps(
            {
                "expenses_checked": count,
                "allocation_mismatches": mismatches,
                "expenses_from_unconfirmed_receipts": unconfirmed,
            }
        )
    )
    if mismatches or unconfirmed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
