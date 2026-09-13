import hashlib
import io
import warnings
from datetime import date
from uuid import UUID, uuid4

from PIL import Image

from app.ai.receipts import ReceiptProvider
from app.db import Store
from app.errors import ApiError, conflict, forbidden, invalid
from app.schemas import ExpenseInput, ReceiptDraft
from app.services.expenses import Expenses
from app.services.money import ZERO, cents, positive, proportional

MAX_BYTES = 8 * 1024 * 1024


def validate_image(data: bytes, declared: str | None) -> str:
    if not data or len(data) > MAX_BYTES:
        raise invalid("Upload an image between 1 byte and 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(
                    image.format
                )
                if (
                    mime is None
                    or image.width * image.height > 24_000_000
                    or max(image.size) > 12000
                ):
                    raise ValueError("Unsupported image")
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except Exception as error:
        raise invalid("Upload a real JPEG, PNG or WebP image up to 24 megapixels.") from error
    if declared not in {None, mime, "application/octet-stream"}:
        raise invalid("The declared content type does not match the image.")
    return mime


class Receipts:
    def __init__(self, db: Store, provider: ReceiptProvider):
        self.db, self.provider = db, provider
        self.expenses = Expenses(db)

    def get(self, user: UUID, id: UUID):
        row = self.db.one("SELECT * FROM receipt WHERE id=:id", id=id)
        if row["owner_id"] != user:
            raise forbidden()
        row["draft"] = ReceiptDraft.model_validate_json(row["draft"])
        return row

    def list(self, user: UUID):
        return self.db.all(
            "SELECT id,status,error,created_at FROM receipt WHERE owner_id=:u ORDER BY created_at DESC LIMIT 50",
            u=user,
        )

    def manual(self, user: UUID, status: str = "NEEDS_REVIEW"):
        id = uuid4()
        draft = ReceiptDraft(
            merchant="",
            date=date.today(),
            currency="USD",
            payerId=user,
            items=[],
            subtotal=0,
            discounts=0,
            tax=0,
            fees=0,
            total=0,
        )
        self.db.execute(
            "INSERT INTO receipt(id,owner_id,status,draft) VALUES(:id,:u,:status,:draft)",
            id=id,
            u=user,
            status=status,
            draft=draft.model_dump_json(),
        )
        return id

    def upload(self, user: UUID, data: bytes, declared: str | None):
        mime = validate_image(data, declared)
        fingerprint = hashlib.sha256(data).hexdigest()
        duplicate = self.db.exists(
            "SELECT id FROM receipt WHERE owner_id=:u AND fingerprint=:fingerprint",
            u=user,
            fingerprint=fingerprint,
        )
        id = self.manual(user, "UPLOADED")
        self.db.execute(
            "UPDATE receipt SET fingerprint=:fingerprint,status='PROCESSING' WHERE id=:id",
            fingerprint=fingerprint,
            id=id,
        )
        try:
            draft = ReceiptDraft.model_validate(self.provider.extract(data, mime))
            self.db.execute(
                "UPDATE receipt SET draft=:draft,status='NEEDS_REVIEW' WHERE id=:id AND status='PROCESSING'",
                draft=draft.model_dump_json(),
                id=id,
            )
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, ApiError)
                else "Extraction failed. Retry the upload or enter receipt items manually."
            )
            self.db.execute(
                "UPDATE receipt SET status='FAILED',error=:error WHERE id=:id AND status='PROCESSING'",
                error=message[:300],
                id=id,
            )
        return dict(self.get(user, id), duplicate=duplicate)

    def save(self, user: UUID, id: UUID, draft: ReceiptDraft):
        self.db.one("SELECT id FROM receipt WHERE id=:id FOR UPDATE", id=id)
        row = self.get(user, id)
        if row["status"] not in {"NEEDS_REVIEW", "FAILED"}:
            raise conflict(
                "Only a reviewable or failed receipt can be edited. Processing receipts must finish first."
            )
        self.db.execute(
            "UPDATE receipt SET draft=:draft,status='NEEDS_REVIEW',error=NULL WHERE id=:id",
            draft=draft.model_dump_json(),
            id=id,
        )
        return self.get(user, id)

    def confirm(self, user: UUID, id: UUID):
        self.db.one("SELECT id FROM receipt WHERE id=:id FOR UPDATE", id=id)
        row = self.get(user, id)
        if row["status"] != "NEEDS_REVIEW":
            raise conflict(
                "Save and review this receipt before confirmation. Confirmed receipts cannot be confirmed again."
            )
        draft = row["draft"]
        if not draft.items:
            raise invalid("Add at least one item.")
        weights = [cents(item.amount) for item in draft.items]
        subtotal = sum(weights, ZERO)
        if subtotal != cents(draft.subtotal) or subtotal - cents(draft.discounts) + cents(
            draft.tax
        ) + cents(draft.fees) != cents(draft.total):
            raise ApiError(
                400,
                "INVALID_RECEIPT_TOTAL",
                "Items, discounts, tax and fees must reconcile exactly with the receipt total.",
            )
        amounts = proportional(positive(draft.total), weights)
        for item, amount in zip(draft.items, amounts, strict=True):
            personal = item.scope == "PERSONAL"
            if amount == ZERO:
                raise invalid(
                    "Adjustments reduce an item to zero. Combine or remove zero-value items before confirming."
                )
            if personal and draft.payerId not in {None, user}:
                raise invalid(
                    "For items paid by another roommate, choose selected members instead of private personal scope."
                )
            data = ExpenseInput(
                title=item.description,
                merchant=draft.merchant,
                amount=int(amount),
                category=item.category,
                scope=item.scope,
                householdId=None if personal else draft.householdId,
                payerId=user if personal else draft.payerId,
                date=draft.date,
                splitMethod="EQUAL",
                participants=item.participants,
                notes="Receipt item; tax, fees and discounts allocated proportionally.",
            )
            self.expenses.create(user, data, receipt=id)
        self.db.execute("UPDATE receipt SET status='CONFIRMED' WHERE id=:id", id=id)
        self.db.audit(user, None, "RECEIPT_CONFIRMED", id)
        return self.get(user, id)
