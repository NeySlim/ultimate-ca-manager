"""
Migration 042: Add SAN fields, SNI hostname to discovered_certificates.
- san_dns_names: JSON array of DNS SANs from the certificate
- san_ip_addresses: JSON array of IP SANs from the certificate
- sni_hostname: TLS SNI hostname used for this probe (empty = default/no SNI)
- Update unique constraint to (target, port, sni_hostname)
"""


def upgrade(conn):
    cursor = conn.execute("PRAGMA table_info(discovered_certificates)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'san_dns_names' in columns:
        return  # Already migrated

    # Recreate table with new columns and updated unique constraint
    conn.execute("""
        CREATE TABLE discovered_certificates_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_profile_id INTEGER REFERENCES discovery_scan_profiles(id) ON DELETE SET NULL,
            target VARCHAR(1024) NOT NULL,
            port INTEGER NOT NULL DEFAULT 443,
            sni_hostname VARCHAR(1024) NOT NULL DEFAULT '',
            subject TEXT,
            issuer TEXT,
            serial_number VARCHAR(100),
            not_before DATETIME,
            not_after DATETIME,
            fingerprint_sha256 VARCHAR(64),
            pem_certificate TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'unmanaged',
            ucm_certificate_id INTEGER REFERENCES certificates(id) ON DELETE SET NULL,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_changed_at DATETIME,
            previous_fingerprint VARCHAR(64),
            dns_hostname VARCHAR(1024),
            san_dns_names TEXT NOT NULL DEFAULT '[]',
            san_ip_addresses TEXT NOT NULL DEFAULT '[]',
            scan_error TEXT,
            UNIQUE(target, port, sni_hostname)
        )
    """)

    conn.execute("""
        INSERT INTO discovered_certificates_new (
            id, scan_profile_id, target, port, sni_hostname,
            subject, issuer, serial_number, not_before, not_after,
            fingerprint_sha256, pem_certificate, status,
            ucm_certificate_id, first_seen, last_seen, last_changed_at,
            previous_fingerprint, dns_hostname, san_dns_names, san_ip_addresses, scan_error
        )
        SELECT
            id, scan_profile_id, target, port, '',
            subject, issuer, serial_number, not_before, not_after,
            fingerprint_sha256, pem_certificate, status,
            ucm_certificate_id, first_seen, last_seen, last_changed_at,
            previous_fingerprint, dns_hostname, '[]', '[]', scan_error
        FROM discovered_certificates
    """)

    conn.execute("DROP TABLE discovered_certificates")
    conn.execute("ALTER TABLE discovered_certificates_new RENAME TO discovered_certificates")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_disc_cert_fp ON discovered_certificates(fingerprint_sha256)")
    conn.commit()


def downgrade(conn):
    conn.execute("""
        CREATE TABLE discovered_certificates_old (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_profile_id INTEGER REFERENCES discovery_scan_profiles(id) ON DELETE SET NULL,
            target VARCHAR(1024) NOT NULL,
            port INTEGER NOT NULL DEFAULT 443,
            subject TEXT,
            issuer TEXT,
            serial_number VARCHAR(100),
            not_before DATETIME,
            not_after DATETIME,
            fingerprint_sha256 VARCHAR(64),
            pem_certificate TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'unmanaged',
            ucm_certificate_id INTEGER REFERENCES certificates(id) ON DELETE SET NULL,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_changed_at DATETIME,
            previous_fingerprint VARCHAR(64),
            dns_hostname VARCHAR(1024),
            scan_error TEXT,
            UNIQUE(target, port)
        )
    """)
    conn.execute("""
        INSERT INTO discovered_certificates_old (
            id, scan_profile_id, target, port,
            subject, issuer, serial_number, not_before, not_after,
            fingerprint_sha256, pem_certificate, status,
            ucm_certificate_id, first_seen, last_seen, last_changed_at,
            previous_fingerprint, dns_hostname, scan_error
        )
        SELECT
            id, scan_profile_id, target, port,
            subject, issuer, serial_number, not_before, not_after,
            fingerprint_sha256, pem_certificate, status,
            ucm_certificate_id, first_seen, last_seen, last_changed_at,
            previous_fingerprint, dns_hostname, scan_error
        FROM discovered_certificates
        WHERE sni_hostname = ''
    """)
    conn.execute("DROP TABLE discovered_certificates")
    conn.execute("ALTER TABLE discovered_certificates_old RENAME TO discovered_certificates")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_disc_cert_fp ON discovered_certificates(fingerprint_sha256)")
    conn.commit()
