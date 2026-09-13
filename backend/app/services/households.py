import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.db import Store
from app.errors import forbidden, invalid
from app.services.write_guard import write_guard


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Households:
    def __init__(self, db: Store):
        self.db = db

    def member(self, user: UUID, household: UUID | None) -> None:
        if household is None or not self.db.exists(
            "SELECT id FROM membership WHERE user_id=:u AND household_id=:h AND left_at IS NULL",
            u=user,
            h=household,
        ):
            raise forbidden()

    def owner(self, user: UUID, household: UUID) -> None:
        if not self.db.exists(
            "SELECT id FROM membership WHERE user_id=:u AND household_id=:h AND left_at IS NULL AND role='OWNER'",
            u=user,
            h=household,
        ):
            raise forbidden()

    def applicable(self, household: UUID, day: date) -> list[UUID]:
        return [
            r["user_id"]
            for r in self.db.all(
                "SELECT DISTINCT user_id FROM membership WHERE household_id=:h AND joined_at<=:d AND (left_at IS NULL OR left_at>=:d)",
                h=household,
                d=day,
            )
        ]

    def list(self, user: UUID):
        return self.db.all(
            "SELECT DISTINCT h.* FROM household h JOIN membership m ON m.household_id=h.id WHERE m.user_id=:u AND m.left_at IS NULL",
            u=user,
        )

    def create(self, user: UUID, name: str):
        write_guard(self.db, user, membership_change=True)
        if not name.strip() or len(name) > 80:
            raise invalid("Enter a household name up to 80 characters.")
        id = uuid4()
        self.db.execute(
            "INSERT INTO household(id,name,created_by) VALUES(:id,:name,:u)",
            id=id,
            name=name.strip(),
            u=user,
        )
        self.db.execute(
            "INSERT INTO membership(id,household_id,user_id,role,joined_at) VALUES(:id,:h,:u,'OWNER',:d)",
            id=uuid4(),
            h=id,
            u=user,
            d=date.today(),
        )
        self.db.audit(user, id, "HOUSEHOLD_CREATED", id)
        return self.db.one("SELECT * FROM household WHERE id=:id", id=id)

    def members(self, user: UUID, household: UUID):
        self.member(user, household)
        return self.db.all(
            "SELECT m.*,u.name,u.diet FROM membership m JOIN app_user u ON u.id=m.user_id WHERE m.household_id=:h ORDER BY m.joined_at,u.name",
            h=household,
        )

    def invite(self, user: UUID, household: UUID):
        write_guard(self.db, user)
        self.owner(user, household)
        token = secrets.token_urlsafe(32)
        self.db.execute(
            "INSERT INTO invitation(id,household_id,token_hash,expires_at) VALUES(:id,:h,:token,:expiry)",
            id=uuid4(),
            h=household,
            token=token_hash(token),
            expiry=datetime.now(timezone.utc) + timedelta(days=7),
        )
        return {"token": token, "expiresIn": "7 days"}

    def accept(self, user: UUID, token: str):
        write_guard(self.db, user, membership_change=True)
        invite = self.db.one(
            "SELECT * FROM invitation WHERE token_hash=:token AND accepted_by IS NULL AND expires_at>CURRENT_TIMESTAMP FOR UPDATE",
            token=token_hash(token),
        )
        household = invite["household_id"]
        self.db.one("SELECT id FROM household WHERE id=:h FOR UPDATE", h=household)
        if self.db.exists(
            "SELECT id FROM membership WHERE user_id=:u AND household_id=:h AND left_at IS NULL",
            u=user,
            h=household,
        ):
            raise invalid("You already belong to this household.")
        self.db.execute(
            "INSERT INTO membership(id,household_id,user_id,role,joined_at) VALUES(:id,:h,:u,'MEMBER',:d)",
            id=uuid4(),
            h=household,
            u=user,
            d=date.today(),
        )
        self.db.execute(
            "UPDATE invitation SET accepted_by=:u WHERE id=:id", u=user, id=invite["id"]
        )
        self.db.audit(user, household, "MEMBER_JOINED", user)
        return self.db.one("SELECT * FROM household WHERE id=:h", h=household)

    def leave(self, user: UUID, household: UUID, membership: UUID):
        write_guard(self.db, user, membership_change=True)
        self.owner(user, household)
        row = self.db.one(
            "SELECT * FROM membership WHERE id=:id AND household_id=:h FOR UPDATE",
            id=membership,
            h=household,
        )
        if row["role"] == "OWNER":
            raise invalid("The owner cannot be removed. Transfer ownership in a future release.")
        if row["left_at"] is not None:
            raise invalid("This membership has already ended.")
        self.db.execute(
            "UPDATE membership SET left_at=:d WHERE id=:id", d=date.today(), id=membership
        )
        self.db.audit(user, household, "MEMBER_LEFT", row["user_id"])

    def rename(self, user: UUID, household: UUID, name: str):
        self.owner(user, household)
        if not name.strip() or len(name) > 80:
            raise invalid("Enter a name up to 80 characters.")
        self.db.execute(
            "UPDATE household SET name=:name WHERE id=:id", name=name.strip(), id=household
        )
        self.db.audit(user, household, "HOUSEHOLD_RENAMED", household)

    def activity(self, user: UUID, household: UUID):
        self.member(user, household)
        return self.db.all(
            "SELECT a.action,a.entity_id,a.created_at,u.name FROM audit_event a JOIN app_user u ON a.actor_id=u.id WHERE a.household_id=:h ORDER BY a.created_at DESC LIMIT 50",
            h=household,
        )
