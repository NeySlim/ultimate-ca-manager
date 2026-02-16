"""
Migration 032: Seed default report schedule settings

Enables the expiry report (daily) by default so admins get certificate
expiration warnings out of the box. Compliance report is disabled by default.
"""


def upgrade(conn):
    cursor = conn.cursor()

    defaults = [
        ('report_expiry_enabled', 'true'),
        ('report_compliance_enabled', 'false'),
        ('report_expiry_recipients', '[]'),
        ('report_compliance_recipients', '[]'),
    ]

    for key, value in defaults:
        cursor.execute('SELECT id FROM system_config WHERE key = ?', (key,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO system_config (key, value) VALUES (?, ?)', (key, value))

    conn.commit()


def downgrade(conn):
    cursor = conn.cursor()
    for key in ['report_expiry_enabled', 'report_compliance_enabled',
                'report_expiry_recipients', 'report_compliance_recipients']:
        cursor.execute("DELETE FROM system_config WHERE key = ?", (key,))
    conn.commit()
