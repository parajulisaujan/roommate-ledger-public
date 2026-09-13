ALTER TABLE app_user ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE app_user ADD COLUMN deactivated BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE app_user ADD COLUMN session_version BIGINT NOT NULL DEFAULT 0;
CREATE TABLE account_token (
 id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES app_user(id),
 token_hash VARCHAR(64) NOT NULL UNIQUE,
 purpose VARCHAR(12) NOT NULL CHECK(purpose IN ('RESET','VERIFY')),
 expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
 used BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX account_token_user ON account_token(user_id,purpose,used);
CREATE INDEX account_token_expiry ON account_token(expires_at);
