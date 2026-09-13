from ipaddress import ip_network
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://localhost:5432/roommateledger"
    database_user: str = "roommateledger"
    database_password: str = ""
    app_env: Literal["development", "staging", "production"] = "development"
    trusted_proxy_cidrs: str = ""
    deployment_proxy_required: bool = False
    deployment_proxy_key: SecretStr = SecretStr("")
    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    cookie_same_site: str = "lax"
    session_timeout_seconds: int = 1800
    cors_allowed_origins: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = Field(default=5, ge=1, le=30)
    receipt_timeout_seconds: float = Field(default=45, ge=1, le=120)
    email_from: str = ""
    email_verification_required: bool = False
    receipt_provider: str = "adapter"
    receipt_provider_url: str = ""
    receipt_provider_api_key: str = ""
    openai_api_key: str = ""
    openai_receipt_model: str = ""
    rate_window_seconds: int = 900
    rate_login: int = 20
    rate_registration: int = 20
    rate_password_reset: int = 5
    rate_reset_confirm: int = 10
    rate_verification: int = 5
    rate_invitations: int = 10
    rate_extraction: int = 10
    rate_account: int = 5
    rate_session_creation: int = 120
    rate_writes: int = 300
    anonymous_session_limit: int = Field(default=10000, ge=1, le=100000)

    @property
    def production(self) -> bool:
        return self.app_env in {"staging", "production"}

    @property
    def origins(self) -> list[str]:
        return [s.strip() for s in self.cors_allowed_origins.split(",") if s.strip()]

    @property
    def sqlalchemy_url(self) -> URL:
        raw = self.database_url.removeprefix("jdbc:")
        url = make_url(raw).set(drivername="postgresql+psycopg")
        return url.set(
            username=url.username or self.database_user,
            password=url.password or self.database_password,
        )

    @model_validator(mode="after")
    def validate_deployment(self):
        if (
            self.deployment_proxy_required
            and len(self.deployment_proxy_key.get_secret_value()) < 32
        ):
            raise ValueError(
                "Protected ingress requires a deployment proxy key of at least 32 characters."
            )
        for cidr in self.trusted_proxy_cidrs.split(","):
            if cidr.strip():
                if ip_network(cidr.strip()).prefixlen == 0:
                    raise ValueError("Trust specific proxy networks, never all addresses.")
        for name in type(self).model_fields:
            if name.startswith("rate_") and not 1 <= getattr(self, name) <= 86400:
                raise ValueError("Rate limits and window must be between 1 and 86400.")
        for origin in self.origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("CORS requires exact HTTP(S) origins without paths or wildcards.")
        if self.cookie_same_site not in {"lax", "strict", "none"}:
            raise ValueError("Invalid cookie SameSite.")
        if self.cookie_same_site == "none" and not self.cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies.")
        if not 60 <= self.session_timeout_seconds <= 86400:
            raise ValueError("Session timeout must be between 60 and 86400 seconds.")
        if self.production:
            if any(urlsplit(origin).scheme != "https" for origin in self.origins):
                raise ValueError("Production CORS origins require HTTPS.")
            origin = urlsplit(self.frontend_url)
            if (
                origin.scheme != "https"
                or not origin.hostname
                or origin.hostname in {"localhost", "127.0.0.1", "::1"}
                or origin.path
                or origin.query
                or origin.fragment
                or origin.username
            ):
                raise ValueError("Production requires an exact public HTTPS FRONTEND_URL.")
            if not self.cookie_secure:
                raise ValueError("Production requires COOKIE_SECURE=true.")
            if not self.smtp_host:
                raise ValueError("Production requires SMTP_HOST.")
            if not self.email_from:
                raise ValueError("Production requires EMAIL_FROM.")
            if not self.smtp_starttls:
                raise ValueError("Production requires SMTP_STARTTLS=true.")
            if not self.email_verification_required:
                raise ValueError("Production requires email verification.")
        if self.receipt_provider not in {"adapter", "openai"}:
            raise ValueError("Unknown receipt provider.")
        if self.receipt_provider_url and self.receipt_provider_api_key:
            endpoint = urlsplit(self.receipt_provider_url)
            if (
                endpoint.scheme != "https"
                or not endpoint.hostname
                or endpoint.username
                or endpoint.fragment
            ):
                raise ValueError("Receipt adapter requires HTTPS without embedded credentials.")
        return self
