-- PostgreSQL initial schema, equivalent to SQLAlchemy metadata. Run on a fresh DB only.
BEGIN;
CREATE TABLE IF NOT EXISTS users (
 id VARCHAR PRIMARY KEY, email VARCHAR NOT NULL UNIQUE,
 password VARCHAR NOT NULL, token_hash VARCHAR, token_expires DOUBLE PRECISION NOT NULL,
 consents JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
 id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id),
 kind VARCHAR NOT NULL, data JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_records_user_id ON records(user_id);
CREATE INDEX IF NOT EXISTS ix_records_kind ON records(kind);
COMMIT;
