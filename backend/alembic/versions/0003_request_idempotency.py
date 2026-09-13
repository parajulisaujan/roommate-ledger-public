"""Transactional financial request receipts; no financial data rewrite."""

from alembic import op

revision = "0003_request_idempotency"
down_revision = "0002_decimal_sessions"


def upgrade():
    op.execute("""CREATE TABLE request_idempotency (
        user_id UUID NOT NULL REFERENCES app_user(id),
        operation VARCHAR(40) NOT NULL, key_hash VARCHAR(64) NOT NULL,
        request_hash VARCHAR(64) NOT NULL, response JSONB,
        expires_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP + INTERVAL '30 days',
        PRIMARY KEY(user_id, operation, key_hash))""")
    op.execute(
        "CREATE INDEX request_idempotency_expiry ON request_idempotency(expires_at) WHERE response IS NOT NULL"
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or isolated restore.")
