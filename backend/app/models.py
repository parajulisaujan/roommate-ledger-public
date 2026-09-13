"""SQLAlchemy mappings retain the established PostgreSQL schema and cent units."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    diet: Mapped[str] = mapped_column(String(32))
    timezone: Mapped[str] = mapped_column(String(60))
    currency: Mapped[str] = mapped_column(String(3))
    notifications: Mapped[bool]
    email_verified: Mapped[bool]
    deactivated: Mapped[bool]
    session_version: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Household(Base):
    __tablename__ = "household"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Membership(Base):
    __tablename__ = "membership"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("household.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    role: Mapped[str] = mapped_column(String(10))
    joined_at: Mapped[date]
    left_at: Mapped[date | None]


class Invitation(Base):
    __tablename__ = "invitation"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("household.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"))


class Receipt(Base):
    __tablename__ = "receipt"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    status: Mapped[str] = mapped_column(String(20))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    draft: Mapped[str] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecurringTemplate(Base):
    __tablename__ = "recurring_template"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    household_id: Mapped[UUID | None] = mapped_column(ForeignKey("household.id"))
    draft: Mapped[str] = mapped_column(Text)
    next_due: Mapped[date]
    frequency: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool]


class Expense(Base):
    __tablename__ = "expense"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    household_id: Mapped[UUID | None] = mapped_column(ForeignKey("household.id"))
    payer_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    title: Mapped[str] = mapped_column(String(120))
    merchant: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    currency: Mapped[str] = mapped_column(String(3))
    category: Mapped[str] = mapped_column(String(40))
    scope: Mapped[str] = mapped_column(String(20))
    split_method: Mapped[str] = mapped_column(String(12))
    expense_date: Mapped[date]
    notes: Mapped[str | None] = mapped_column(String(2000))
    receipt_id: Mapped[UUID | None] = mapped_column(ForeignKey("receipt.id"))
    template_id: Mapped[UUID | None] = mapped_column(ForeignKey("recurring_template.id"))
    deleted: Mapped[bool]
    version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Allocation(Base):
    __tablename__ = "allocation"
    expense_id: Mapped[UUID] = mapped_column(ForeignKey("expense.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 0))


class Settlement(Base):
    __tablename__ = "settlement"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID] = mapped_column(ForeignKey("household.id"))
    from_user: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    to_user: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 0))
    method: Mapped[str] = mapped_column(String(40))
    payment_date: Mapped[date]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    household_id: Mapped[UUID | None] = mapped_column(ForeignKey("household.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    action: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountToken(Base):
    __tablename__ = "account_token"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(12))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool]


class WebSession(Base):
    __tablename__ = "web_session"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("app_user.id"))
    session_version: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
