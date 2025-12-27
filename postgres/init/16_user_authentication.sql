-- User authentication and authorization tables
-- Created for GCP deployment with Flask-Login integration

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_login_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create index on email for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Security audit log table
CREATE TABLE IF NOT EXISTS security_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_type VARCHAR(50) NOT NULL,  -- login_success, login_failed, rate_limit_exceeded, logout, etc.
    ip_address VARCHAR(45),  -- IPv6 support
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,  -- Additional context (attempted username, error details, etc.)
    success BOOLEAN DEFAULT FALSE NOT NULL
);

-- Indexes for audit queries
CREATE INDEX IF NOT EXISTS idx_security_audit_user_id ON security_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_security_audit_event_type ON security_audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_security_audit_timestamp ON security_audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_security_audit_ip ON security_audit_log(ip_address);

-- Session management table (optional - can use Redis instead)
CREATE TABLE IF NOT EXISTS user_sessions (
    id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Index for session cleanup
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);

-- Grant permissions (if using separate roles)
-- GRANT SELECT, INSERT, UPDATE ON users TO spending_user;
-- GRANT SELECT, INSERT ON security_audit_log TO spending_user;
-- GRANT SELECT, INSERT, DELETE ON user_sessions TO spending_user;

-- Note: Password hashes should use pbkdf2:sha256:600000 via Werkzeug
-- Example hash format: pbkdf2:sha256:600000$<salt>$<hash>

COMMENT ON TABLE users IS 'User accounts for authentication';
COMMENT ON TABLE security_audit_log IS 'Audit trail for security events (login attempts, rate limiting, etc.)';
COMMENT ON TABLE user_sessions IS 'User session tracking (alternative to Redis-only sessions)';
COMMENT ON COLUMN security_audit_log.metadata IS 'JSONB field for flexible audit data (attempted_username, blocked_reason, etc.)';
