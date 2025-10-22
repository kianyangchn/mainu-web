-- Persist upload sessions for retryable menu processing.
CREATE TABLE IF NOT EXISTS upload_sessions (
    token VARCHAR(96) PRIMARY KEY,
    file_ids JSONB NOT NULL,
    filenames JSONB NOT NULL,
    content_types JSONB NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS upload_sessions_expires_idx
    ON upload_sessions (expires_at);

CREATE INDEX IF NOT EXISTS upload_sessions_created_idx
    ON upload_sessions (created_at);
