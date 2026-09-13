from decimal import Decimal
from uuid import UUID

import pytest

from app.errors import ApiError
from app.services.money import cents, proportional, split

IDS = [UUID(int=i) for i in range(1, 5)]


@pytest.mark.parametrize(
    ("amount", "count", "expected"),
    [
        (10000, 4, [2500] * 4),
        (10000, 3, [3334, 3333, 3333]),
        (9000, 3, [3000] * 3),
        (4000, 1, [4000]),
    ],
)
def test_equal(amount, count, expected):
    result = split(amount, "EQUAL", IDS[:count])
    assert list(result.values()) == [Decimal(v) for v in expected]
    assert all(isinstance(v, Decimal) for v in result.values())


def test_signed_java_uuid_order_is_preserved():
    negative = UUID("80000000-0000-0000-0000-000000000000")
    positive = UUID("00000000-0000-0000-0000-000000000001")
    assert split(1, "EQUAL", [positive, negative]) == {
        negative: Decimal("1"),
        positive: Decimal("0"),
    }


@pytest.mark.parametrize(
    "method,values", [("FIXED", [5000, 3000, 2000]), ("PERCENTAGE", [5000, 3000, 2000])]
)
def test_custom(method, values):
    assert (
        list(split(10000, method, IDS[:3], dict(zip(IDS[:3], values, strict=True))).values())
        == values
    )


@pytest.mark.parametrize(
    "method,values",
    [
        ("FIXED", [5000, 3000, 1000]),
        ("PERCENTAGE", [5000, 3000, 1000]),
        ("PERCENTAGE", [-1, 5000, 5001]),
        ("UNKNOWN", [5000, 3000, 2000]),
    ],
)
def test_invalid_custom(method, values):
    with pytest.raises(ApiError):
        split(10000, method, IDS[:3], dict(zip(IDS[:3], values, strict=True)))


@pytest.mark.parametrize(
    "value", [0, -1, 100000000001, 1.1, True, "100", Decimal("NaN"), Decimal("0.1")]
)
def test_invalid_money(value):
    with pytest.raises(ApiError):
        split(value, "EQUAL", IDS)


@pytest.mark.parametrize("participants", [[], [IDS[0], IDS[0]], [None], None])
def test_invalid_participants(participants):
    with pytest.raises(ApiError):
        split(100, "EQUAL", participants)


def test_conservation_many_values_and_maximum():
    for amount in list(range(1, 1001)) + [100000000000]:
        for method, values in [
            ("EQUAL", None),
            ("PERCENTAGE", dict(zip(IDS[:3], [3333, 3333, 3334], strict=True))),
        ]:
            shares = split(amount, method, IDS[:3], values)
            assert sum(shares.values()) == cents(amount)
            assert shares == split(amount, method, list(reversed(IDS[:3])), values)


def test_receipt_proportional_adjustments():
    shares = proportional(Decimal("1001"), [Decimal("333"), Decimal("333"), Decimal("334")])
    assert shares == [333, 333, 335]
    assert sum(shares) == 1001
