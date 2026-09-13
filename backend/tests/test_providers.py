import json
from datetime import date

import anyio
import httpx
import pytest

from app.ai.receipts import HttpReceiptProvider, parse_draft
from app.config import Settings
from app.errors import ApiError


def data():
    return {
        "merchant": "Fictional Store",
        "date": date.today().isoformat(),
        "currency": "USD",
        "items": [
            {
                "description": "Rice",
                "rawDescription": "RCE",
                "category": "Groceries",
                "quantity": 1,
                "confidence": 0.9,
                "unitPrice": 1000,
                "amount": 1000,
            }
        ],
        "subtotal": 1000,
        "discounts": 0,
        "tax": 0,
        "fees": 0,
        "total": 1000,
    }


def provider(handler, openai=False, timeout=1):
    config = Settings(
        receipt_provider="openai" if openai else "adapter",
        receipt_provider_url="https://provider.example/extract",
        receipt_provider_api_key="test-key",
        openai_api_key="test-key",
        openai_receipt_model="test-model",
    )
    return HttpReceiptProvider(config, httpx.MockTransport(handler), timeout=timeout)


@pytest.mark.parametrize("openai", [False, True])
def test_valid_response_only_draft_no_responsibility(openai):
    payload = data()
    if not openai:
        payload["householdId"] = "00000000-0000-0000-0000-000000000001"
        payload["payerId"] = "00000000-0000-0000-0000-000000000002"
        payload["items"][0].update(scope="HOUSEHOLD", participants=[payload["payerId"]])

    def handler(request):
        assert request.headers["authorization"] == "Bearer test-key"
        if openai:
            sent = json.loads(request.content)
            assert sent["store"] is False and sent["text"]["format"]["strict"] is True
            assert sent["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}],
                },
            )
        assert request.content == b"image"
        return httpx.Response(200, json=payload)

    draft = provider(handler, openai).extract(b"image", "image/png")
    assert draft.total == 1000 and draft.householdId is None and draft.payerId is None
    assert draft.items[0].scope == "PERSONAL" and draft.items[0].participants == []


@pytest.mark.parametrize("openai", [False, True])
def test_missing_credentials_no_network(openai):
    provider = HttpReceiptProvider(
        Settings(
            receipt_provider="openai" if openai else "adapter",
            openai_api_key="",
            receipt_provider_api_key="",
        )
    )
    assert not provider.available()
    with pytest.raises(ApiError, match="not configured"):
        provider.extract(b"image", "image/png")


@pytest.mark.parametrize(
    "change",
    [
        {"total": 1.5},
        {"total": "1000"},
        {"total": None},
        {"total": True},
        {"currency": "EUR"},
        {"unknown": 1},
    ],
)
@pytest.mark.parametrize("openai", [False, True])
def test_strict_provider_money_and_fields(change, openai):
    with pytest.raises((ValueError, TypeError)):
        parse_draft(json.dumps(data() | change), openai)


@pytest.mark.parametrize(
    "body", ["not json", '{"total":1,"total":2}', "{}", json.dumps(data()) + "{}"]
)
def test_malformed_missing_duplicate_and_trailing_json(body):
    with pytest.raises((ValueError, TypeError)):
        parse_draft(body, True)


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_provider_errors_do_not_expose_body(status):
    with pytest.raises(ApiError) as error:
        provider(lambda _: httpx.Response(status, text="SECRET UPSTREAM ERROR")).extract(
            b"image", "image/png"
        )
    assert "SECRET" not in str(error.value)


def test_bounded_provider_body():
    with pytest.raises(ApiError):
        provider(lambda _: httpx.Response(200, content=b" " * 262145)).extract(
            b"image", "image/png"
        )


def test_overall_timeout_includes_stalled_body():
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{"
            await anyio.sleep(10)
            yield b"}"

    with pytest.raises(ApiError):
        provider(lambda _: httpx.Response(200, stream=SlowBody()), timeout=0.01).extract(
            b"image", "image/png"
        )


@pytest.mark.parametrize(
    "status,content",
    [
        ("incomplete", []),
        ("completed", [{"type": "refusal"}]),
        ("completed", []),
        ("completed", [{"type": "output_text", "text": "{}"}] * 2),
    ],
)
def test_openai_incomplete_refusal_and_ambiguous_output(status, content):
    with pytest.raises(ApiError):
        provider(
            lambda _: httpx.Response(
                200, json={"status": status, "output": [{"content": content}]}
            ),
            True,
        ).extract(b"image", "image/png")
