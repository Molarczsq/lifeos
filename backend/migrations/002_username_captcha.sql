-- PostgreSQL upgrade. The application performs the same idempotent migration at startup.
-- Preserve old email values as legacy usernames and retain all user IDs/records.
BEGIN;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'email')
 AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'username') THEN
  ALTER TABLE users RENAME COLUMN email TO username;
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS captcha_challenges (
 id VARCHAR PRIMARY KEY,
 answer_hash VARCHAR NOT NULL,
 binding_hash VARCHAR NOT NULL,
 expires_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_captcha_challenges_binding_hash ON captcha_challenges(binding_hash);
CREATE INDEX IF NOT EXISTS ix_captcha_challenges_expires_at ON captcha_challenges(expires_at);
COMMIT;
