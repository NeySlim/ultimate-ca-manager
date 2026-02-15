"""
Migration 030: Fix schema mismatches between models and database

Adds missing columns:
- user_sessions.auth_method (model has it, DB doesn't)
- approval_requests.certificate_id, policy_id, requester_comment, 
  approvals, required_approvals, expires_at, resolved_at
- certificate_policies.policy_type, ca_id, template_id, rules,
  requires_approval, approval_group_id, min_approvers,
  notify_on_violation, notification_emails, priority, enabled

Renames:
- user_sessions.last_active → last_activity (add alias column)
"""


def upgrade(conn):
    cursor = conn.cursor()
    
    # --- user_sessions: add auth_method, last_activity ---
    try:
        cursor.execute("ALTER TABLE user_sessions ADD COLUMN auth_method VARCHAR(50) DEFAULT 'password'")
    except Exception:
        pass  # column already exists
    
    try:
        cursor.execute("ALTER TABLE user_sessions ADD COLUMN last_activity DATETIME")
        # Copy data from last_active to last_activity
        cursor.execute("UPDATE user_sessions SET last_activity = last_active WHERE last_activity IS NULL")
    except Exception:
        pass

    # --- approval_requests: add missing columns ---
    for col_sql in [
        "ALTER TABLE approval_requests ADD COLUMN certificate_id INTEGER REFERENCES certificates(id)",
        "ALTER TABLE approval_requests ADD COLUMN policy_id INTEGER REFERENCES certificate_policies(id)",
        "ALTER TABLE approval_requests ADD COLUMN requester_comment TEXT",
        "ALTER TABLE approval_requests ADD COLUMN approvals TEXT DEFAULT '[]'",
        "ALTER TABLE approval_requests ADD COLUMN required_approvals INTEGER DEFAULT 1",
        "ALTER TABLE approval_requests ADD COLUMN expires_at DATETIME",
        "ALTER TABLE approval_requests ADD COLUMN resolved_at DATETIME",
    ]:
        try:
            cursor.execute(col_sql)
        except Exception:
            pass

    # --- certificate_policies: add missing columns ---
    for col_sql in [
        "ALTER TABLE certificate_policies ADD COLUMN policy_type VARCHAR(50) DEFAULT 'issuance'",
        "ALTER TABLE certificate_policies ADD COLUMN ca_id INTEGER REFERENCES certificate_authorities(id)",
        "ALTER TABLE certificate_policies ADD COLUMN template_id INTEGER REFERENCES certificate_templates(id)",
        "ALTER TABLE certificate_policies ADD COLUMN rules TEXT DEFAULT '{}'",
        "ALTER TABLE certificate_policies ADD COLUMN requires_approval BOOLEAN DEFAULT 0",
        "ALTER TABLE certificate_policies ADD COLUMN approval_group_id INTEGER REFERENCES groups(id)",
        "ALTER TABLE certificate_policies ADD COLUMN min_approvers INTEGER DEFAULT 1",
        "ALTER TABLE certificate_policies ADD COLUMN notify_on_violation BOOLEAN DEFAULT 1",
        "ALTER TABLE certificate_policies ADD COLUMN notification_emails TEXT",
        "ALTER TABLE certificate_policies ADD COLUMN priority INTEGER DEFAULT 0",
        "ALTER TABLE certificate_policies ADD COLUMN enabled BOOLEAN DEFAULT 1",
        "ALTER TABLE certificate_policies ADD COLUMN is_active BOOLEAN DEFAULT 1",
        "ALTER TABLE certificate_policies ADD COLUMN created_by VARCHAR(80)",
        "ALTER TABLE certificate_policies ADD COLUMN updated_at DATETIME",
    ]:
        try:
            cursor.execute(col_sql)
        except Exception:
            pass
    
    # Sync is_active from enabled if is_active was just added
    try:
        cursor.execute("UPDATE certificate_policies SET is_active = enabled WHERE is_active IS NULL AND enabled IS NOT NULL")
    except Exception:
        pass

    conn.commit()


def downgrade(conn):
    # SQLite doesn't support DROP COLUMN easily, skip
    pass
