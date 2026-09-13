"""Authoritative money is Decimal cents. JSON exposes only exact integer cents."""

from decimal import Decimal
from uuid import UUID

from app.errors import invalid

MAX = Decimal("100000000000")
ZERO = Decimal("0")
ONE = Decimal("1")


def cents(value: int | Decimal) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise invalid("Money must be integer cents.")
    amount = Decimal(value) if isinstance(value, int) else value
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise invalid("Money must be integer cents.")
    return amount


def positive(value: int | Decimal) -> Decimal:
    amount = cents(value)
    if not ZERO < amount <= MAX:
        raise invalid("Amount must be positive and at most $1 billion.")
    return amount


def java_uuid_order(value: UUID) -> tuple[int, int]:
    def signed(n: int) -> int:
        return n - (1 << 64) if n & (1 << 63) else n

    return signed(value.int >> 64), signed(value.int & ((1 << 64) - 1))


def proportional(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    denominator = sum(weights, ZERO)
    if denominator <= ZERO:
        raise invalid("Allocation weights must have a positive total.")
    # Integer Decimal quotient/remainder avoids precision-dependent recurring division.
    products = [total * weight for weight in weights]
    shares = [product // denominator for product in products]
    order = sorted(range(len(weights)), key=lambda i: (-(products[i] % denominator), i))
    for i in order[: int(total - sum(shares, ZERO))]:
        shares[i] += ONE
    return shares


def split(
    total: int | Decimal,
    method: str,
    participants: list[UUID] | None,
    values: dict[UUID, int] | None = None,
) -> dict[UUID, Decimal]:
    amount = positive(total)
    if (
        not participants
        or len(participants) > 100
        or None in participants
        or len(set(participants)) != len(participants)
    ):
        raise invalid("Choose between 1 and 100 unique participants.")
    ids = sorted(participants, key=java_uuid_order)
    if method == "EQUAL":
        return dict(zip(ids, proportional(amount, [ONE] * len(ids)), strict=True))
    if values is None or set(values) != set(ids):
        raise invalid("Provide one nonnegative value for every participant.")
    weights = [cents(values[id]) for id in ids]
    if any(v < ZERO or v > MAX for v in weights):
        raise invalid("Provide one nonnegative value for every participant.")
    if method == "FIXED":
        if sum(weights, ZERO) != amount:
            raise invalid("Fixed shares must equal the total.")
        return dict(zip(ids, weights, strict=True))
    if method == "PERCENTAGE":
        if sum(weights, ZERO) != Decimal("10000"):
            raise invalid("Percentages must total exactly 100.00%.")
        return dict(zip(ids, proportional(amount, weights), strict=True))
    raise invalid("Unknown split method.")
