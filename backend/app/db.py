from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import missing


def engine_for(
    settings: Settings, *, pool_size: int = 5, max_overflow: int = 5, migration: bool = False
) -> Engine:
    url = settings.sqlalchemy_url
    # Supported libpq parameters. Explicit operator URL options take precedence.
    defaults = {
        "connect_timeout": "5",
        "options": "-c statement_timeout=300000 -c lock_timeout=10000"
        if migration
        else "-c statement_timeout=15000 -c lock_timeout=5000",
    }
    url = url.update_query_dict(
        {key: value for key, value in defaults.items() if key not in url.query}
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=5,
        hide_parameters=True,
    )


class Store:
    """Parameterized SQL projections within the request's SQLAlchemy transaction."""

    def __init__(self, session: Session):
        self.session = session

    def execute(self, sql: str, **params: Any):
        return self.session.execute(text(sql), params)

    def all(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in self.execute(sql, **params).mappings()]

    def one(self, sql: str, **params: Any) -> dict[str, Any]:
        row = self.execute(sql, **params).mappings().first()
        if row is None:
            raise missing()
        return dict(row)

    def exists(self, sql: str, **params: Any) -> bool:
        return self.execute(sql, **params).first() is not None

    def audit(self, actor: UUID, household: UUID | None, action: str, entity: UUID) -> None:
        self.execute(
            "INSERT INTO audit_event(id,household_id,actor_id,action,entity_id) "
            "VALUES(:id,:household,:actor,:action,:entity)",
            id=uuid4(),
            household=household,
            actor=actor,
            action=action,
            entity=entity,
        )


def database(request: Request) -> Iterator[Store]:
    # function scope commits before the response leaves the endpoint, including commit errors.
    with Session(request.app.state.engine) as session, session.begin():
        yield Store(session)
