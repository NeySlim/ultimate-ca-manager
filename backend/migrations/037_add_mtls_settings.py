"""Add mTLS system_config entries for new installs."""


def upgrade(conn):
    settings = [
        ('mtls_enabled', 'false', 'Enable mTLS client certificate authentication'),
        ('mtls_required', 'false', 'Require client certificate for all connections'),
        ('mtls_trusted_ca_id', '', 'Trusted CA refid for client certificate verification'),
    ]
    for key, value, desc in settings:
        existing = conn.execute(
            "SELECT id FROM system_config WHERE key = ?", (key,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO system_config (key, value, description) VALUES (?, ?, ?)",
                (key, value, desc),
            )
    conn.commit()


def downgrade(conn):
    conn.execute(
        "DELETE FROM system_config WHERE key IN "
        "('mtls_enabled', 'mtls_required', 'mtls_trusted_ca_id')"
    )
    conn.commit()
