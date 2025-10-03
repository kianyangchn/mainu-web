-- Establish persistent storage for shared menu tokens.
CREATE TABLE IF NOT EXISTS share_tokens (
    token TEXT PRIMARY KEY,
    template_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS share_tokens_expires_idx ON share_tokens (expires_at);
CREATE INDEX IF NOT EXISTS share_tokens_created_idx ON share_tokens (created_at);
