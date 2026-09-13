import logging
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Protocol
from uuid import UUID, uuid4

import bcrypt

from app.config import Settings
from app.db import Store
from app.errors import invalid
from app.services.households import token_hash
from app.services.write_guard import write_guard

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    def available(self) -> bool: ...
    def send(self, recipient: str, subject: str, body: str) -> None: ...


class SmtpEmailProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def available(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.email_from)

    def send(self, recipient: str, subject: str, body: str) -> None:
        config = self.settings
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = config.email_from, recipient, subject
        message.set_content(body)
        with smtplib.SMTP(
            config.smtp_host, config.smtp_port, timeout=config.smtp_timeout_seconds
        ) as server:
            if config.smtp_starttls:
                server.starttls(context=ssl.create_default_context())
            if config.smtp_username:
                server.login(config.smtp_username, config.smtp_password)
            server.send_message(message)


def password_hash(password: str) -> str:
    if len(password) < 12 or len(password.encode()) > 72:
        raise invalid(
            "Use at least 12 characters and no more than 72 UTF-8 bytes for your password."
        )
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def password_matches(password: str, encoded: str) -> bool:
    if len(password.encode()) > 72:
        return False
    try:
        return bcrypt.checkpw(password.encode(), encoded.encode())
    except ValueError:
        return False


class Accounts:
    def __init__(self, db: Store, settings: Settings, email: EmailProvider):
        self.db, self.settings, self.email = db, settings, email

    def capabilities(self):
        return {
            "emailDeliveryAvailable": self.email.available(),
            "verificationRequired": self.settings.email_verification_required,
        }

    def issue(self, user: UUID, purpose: str):
        account = self.db.one(
            "SELECT email,email_verified,deactivated FROM app_user WHERE id=:id FOR UPDATE", id=user
        )
        if (
            not self.email.available()
            or account["deactivated"]
            or (purpose == "VERIFY" and account["email_verified"])
        ):
            return
        self.db.execute("DELETE FROM account_token WHERE expires_at<CURRENT_TIMESTAMP")
        self.db.execute(
            "UPDATE account_token SET used=true WHERE user_id=:u AND purpose=:purpose",
            u=user,
            purpose=purpose,
        )
        token, id = secrets.token_urlsafe(32), uuid4()
        self.db.execute(
            "INSERT INTO account_token(id,user_id,token_hash,purpose,expires_at) VALUES(:id,:u,:token,:purpose,:expiry)",
            id=id,
            u=user,
            token=token_hash(token),
            purpose=purpose,
            expiry=datetime.now(timezone.utc)
            + timedelta(minutes=30 if purpose == "RESET" else 1440),
        )
        action = "reset" if purpose == "RESET" else "verify"
        try:
            self.email.send(
                account["email"],
                "Reset your RoommateLedger password"
                if purpose == "RESET"
                else "Verify your RoommateLedger email",
                f"Open this link to continue: {self.settings.frontend_url}/#{action}={token}\nThis link expires and can be used once. If you did not request it, ignore this email.",
            )
        except Exception:
            self.db.execute("UPDATE account_token SET used=true WHERE id=:id", id=id)
            logger.warning("account_email_delivery_failed purpose=%s", purpose)

    def request_reset(self, email: str):
        users = self.db.all(
            "SELECT id FROM app_user WHERE email=:email AND deactivated=false",
            email=email.strip().lower(),
        )
        if users:
            self.issue(users[0]["id"], "RESET")

    def consume(self, token: str, purpose: str) -> UUID:
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise invalid("This link is invalid or expired. Request a new email.")
        rows = self.db.all(
            "SELECT id,user_id FROM account_token WHERE token_hash=:token AND purpose=:purpose AND used=false AND expires_at>CURRENT_TIMESTAMP FOR UPDATE",
            token=token_hash(token),
            purpose=purpose,
        )
        if not rows:
            raise invalid("This link is invalid or expired. Request a new email.")
        self.db.execute("UPDATE account_token SET used=true WHERE id=:id", id=rows[0]["id"])
        return rows[0]["user_id"]

    def reset(self, token: str, password: str):
        encoded = password_hash(password)
        user = self.consume(token, "RESET")
        self.db.execute(
            "UPDATE app_user SET password_hash=:password,session_version=session_version+1 WHERE id=:u AND deactivated=false",
            password=encoded,
            u=user,
        )
        self.db.execute(
            "UPDATE account_token SET used=true WHERE user_id=:u AND purpose='RESET'", u=user
        )

    def verify(self, token: str):
        user = self.consume(token, "VERIFY")
        self.db.execute(
            "UPDATE app_user SET email_verified=true WHERE id=:u AND deactivated=false", u=user
        )

    def check_password(self, user: UUID, password: str):
        account = self.db.one(
            "SELECT password_hash,deactivated FROM app_user WHERE id=:u FOR UPDATE", u=user
        )
        if account["deactivated"] or not password_matches(password, account["password_hash"]):
            raise invalid("Current password is incorrect.")

    def change_password(self, user: UUID, current: str, replacement: str):
        encoded = password_hash(replacement)
        self.check_password(user, current)
        self.db.execute(
            "UPDATE app_user SET password_hash=:password,session_version=session_version+1 WHERE id=:u",
            password=encoded,
            u=user,
        )
        self.db.execute("UPDATE account_token SET used=true WHERE user_id=:u", u=user)

    def deactivate(self, user: UUID, password: str):
        write_guard(self.db, user, membership_change=True)
        self.check_password(user, password)
        if self.db.exists(
            "SELECT m.id FROM membership m WHERE m.user_id=:u AND m.role='OWNER' AND m.left_at IS NULL AND EXISTS(SELECT 1 FROM membership other WHERE other.household_id=m.household_id AND other.user_id<>:u AND other.left_at IS NULL)",
            u=user,
        ):
            raise invalid(
                "Remove active roommates from households you own before deactivating. Historical records and balances will remain."
            )
        self.db.execute(
            "UPDATE app_user SET deactivated=true,session_version=session_version+1 WHERE id=:u",
            u=user,
        )
        self.db.execute(
            "UPDATE membership SET left_at=CURRENT_DATE WHERE user_id=:u AND left_at IS NULL",
            u=user,
        )
        self.db.execute("UPDATE account_token SET used=true WHERE user_id=:u", u=user)
        self.db.execute("UPDATE recurring_template SET active=false WHERE owner_id=:u", u=user)
        self.db.execute(
            "UPDATE invitation SET expires_at=CURRENT_TIMESTAMP WHERE household_id IN (SELECT household_id FROM membership WHERE user_id=:u AND role='OWNER')",
            u=user,
        )
