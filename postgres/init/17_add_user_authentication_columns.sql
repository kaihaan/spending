-- Add authentication columns to existing users table
-- Migrates simple users table to full authentication support

-- Add authentication columns if they don't exist
DO $$
BEGIN
    -- Add username column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='users' AND column_name='username') THEN
        ALTER TABLE users ADD COLUMN username VARCHAR(100);
    END IF;

    -- Add password_hash column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='users' AND column_name='password_hash') THEN
        ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
    END IF;

    -- Add is_admin column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='users' AND column_name='is_admin') THEN
        ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE NOT NULL;
    END IF;

    -- Add is_active column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='users' AND column_name='is_active') THEN
        ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL;
    END IF;

    -- Add last_login_at column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='users' AND column_name='last_login_at') THEN
        ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP;
    END IF;
END $$;

-- Create unique constraint on username if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_username_key') THEN
        ALTER TABLE users ADD CONSTRAINT users_username_key UNIQUE (username);
    END IF;
END $$;

-- Create index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Update comment on users table
COMMENT ON TABLE users IS 'User accounts for authentication and data access control';
COMMENT ON COLUMN users.username IS 'Unique username for login';
COMMENT ON COLUMN users.password_hash IS 'Hashed password using pbkdf2:sha256:600000';
COMMENT ON COLUMN users.is_admin IS 'Admin users have full system access';
COMMENT ON COLUMN users.is_active IS 'Inactive users cannot log in';
COMMENT ON COLUMN users.last_login_at IS 'Timestamp of last successful login';
