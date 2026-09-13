"""Exact Decimal cents and persistent revocable server sessions."""

from alembic import op

revision = "0002_decimal_sessions"
down_revision = "0001_baseline"


def upgrade():
    for table in ("expense", "allocation", "settlement"):
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN amount TYPE NUMERIC(14,0) USING amount::NUMERIC(14,0)"
        )
    op.execute("""CREATE TABLE web_session (
        token_hash VARCHAR(64) PRIMARY KEY, csrf_token VARCHAR(64) NOT NULL,
        user_id UUID REFERENCES app_user(id), session_version BIGINT NOT NULL DEFAULT 0,
        expires_at TIMESTAMPTZ NOT NULL)""")
    op.execute("CREATE INDEX ix_web_session_expires_at ON web_session(expires_at)")
    op.execute("CREATE INDEX web_session_user ON web_session(user_id)")
    op.execute("""CREATE TABLE abuse_window (
        subject_hash VARCHAR(64) NOT NULL, action VARCHAR(40) NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL, attempts INTEGER NOT NULL,
        PRIMARY KEY(subject_hash,action))""")
    op.execute("CREATE INDEX abuse_window_expiry ON abuse_window(expires_at)")


def downgrade():
    raise RuntimeError(
        "Use a reviewed forward migration or verified backup; never silently drop sessions/data."
    )
