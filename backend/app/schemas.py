from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_serializer, field_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, revalidate_instances="always")


class Credentials(Schema):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=12, max_length=72)]
    name: Annotated[str | None, Field(max_length=80)] = None

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        from email_validator import validate_email

        return validate_email(
            value, check_deliverability=False, test_environment=True
        ).normalized.lower()

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password exceeds BCrypt's 72-byte limit.")
        return value


class ProfileInput(Schema):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    diet: Annotated[str, Field(min_length=1, max_length=32)]
    timezone: Annotated[str, Field(min_length=1, max_length=60)]
    notifications: bool = False

    @field_validator("name", "diet")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required field.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Unknown timezone.") from error
        return value


class Profile(ProfileInput):
    id: UUID
    email: str
    currency: Literal["USD"]
    email_verified: bool
    verification_required: bool


class Name(Schema):
    name: Annotated[str, Field(min_length=1, max_length=80)]


class ExpenseInput(Schema):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    merchant: Annotated[str | None, Field(max_length=120)] = None
    amount: StrictInt
    category: Annotated[str, Field(min_length=1, max_length=40)]
    scope: Literal["PERSONAL", "HOUSEHOLD", "SELECTED_MEMBERS"]
    householdId: UUID | None = None
    payerId: UUID | None = None
    date: Date
    splitMethod: Literal["EQUAL", "FIXED", "PERCENTAGE"]
    participants: Annotated[list[UUID] | None, Field(max_length=100)] = None
    values: dict[UUID, StrictInt] | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None
    version: StrictInt | None = None

    @field_validator("title", "category")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required field.")
        return value


class SettlementInput(Schema):
    fromUser: UUID
    toUser: UUID
    amount: StrictInt
    method: Annotated[str, Field(min_length=1, max_length=40)]
    date: Date


class RecurringInput(Schema):
    expense: ExpenseInput
    nextDue: Date
    frequency: Literal["MONTHLY", "WEEKLY", "YEARLY"]
    active: bool = False


class ReceiptItem(Schema):
    description: Annotated[str, Field(min_length=1, max_length=120)]
    rawDescription: Annotated[str | None, Field(max_length=500)] = None
    quantity: Annotated[Decimal, Field(gt=Decimal("0"), le=Decimal("10000"))]
    unitPrice: Annotated[StrictInt | None, Field(ge=0, le=100000000000)] = None
    amount: Annotated[StrictInt, Field(gt=0, le=100000000000)]
    category: Annotated[str, Field(min_length=1, max_length=40)]
    confidence: Annotated[Decimal | None, Field(ge=Decimal("0"), le=Decimal("1"))] = None
    scope: str | None = None
    participants: list[UUID] | None = None

    @field_serializer("quantity", "confidence", when_used="json")
    def display_decimal(self, value: Decimal | None):
        # These are display metadata, never authoritative money or allocation weights.
        return (
            None
            if value is None
            else int(value)
            if value == value.to_integral_value()
            else float(value)
        )

    @field_validator("description", "category")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required field.")
        return value


Total = Annotated[StrictInt, Field(ge=0, le=100000000000)]


class ReceiptDraft(Schema):
    merchant: Annotated[str, Field(max_length=120)]
    date: Date
    currency: Literal["USD"]
    householdId: UUID | None = None
    payerId: UUID | None = None
    items: Annotated[list[ReceiptItem], Field(max_length=100)]
    subtotal: Total
    discounts: Total
    tax: Total
    fees: Total
    total: Total


class Address(Schema):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    _email = field_validator("email")(Credentials.email_address.__func__)


class Token(Schema):
    token: Annotated[str, Field(min_length=1, max_length=100)]


class Password(Schema):
    password: Annotated[str, Field(min_length=1, max_length=72)]


class Reset(Token, Password):
    pass


class Passwords(Password):
    currentPassword: Annotated[str, Field(min_length=1, max_length=72)]


class ExpenseRow(Schema):
    id: UUID
    owner_id: UUID
    household_id: UUID | None
    payer_id: UUID
    payer_name: str
    title: str
    merchant: str | None
    amount: int
    currency: Literal["USD"]
    category: str
    scope: Literal["PERSONAL", "HOUSEHOLD", "SELECTED_MEMBERS"]
    split_method: Literal["EQUAL", "FIXED", "PERCENTAGE"]
    expense_date: Date
    notes: str | None
    receipt_id: UUID | None
    template_id: UUID | None
    deleted: bool
    version: int
    created_at: datetime


class AllocationOutput(Schema):
    user_id: UUID
    amount: int
    name: str


class ExpenseOutput(ExpenseRow):
    allocations: list[AllocationOutput]


class ExpensePage(Schema):
    items: list[ExpenseRow]
    total: int
    page: int
    pageSize: int


class ReceiptOutput(Schema):
    id: UUID
    owner_id: UUID
    status: Literal["UPLOADED", "PROCESSING", "NEEDS_REVIEW", "CONFIRMED", "FAILED"]
    fingerprint: str | None
    draft: ReceiptDraft
    error: str | None
    created_at: datetime


class UploadOutput(ReceiptOutput):
    duplicate: bool


class BalanceOutput(Schema):
    id: UUID
    name: str
    balance: int


class ErrorOutput(Schema):
    code: str
    message: str
