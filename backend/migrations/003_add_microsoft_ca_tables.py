"""
Migration 003: Add Microsoft AD CS integration tables

Creates microsoft_cas table for CA connections and msca_requests table
for tracking CSR signing requests submitted to Microsoft AD CS.
"""
import logging

logger = logging.getLogger(__name__)


def upgrade(conn):
    """Create Microsoft CA tables"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS microsoft_cas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE,
            server VARCHAR(500) NOT NULL,
            ca_name VARCHAR(200),
            auth_method VARCHAR(20) NOT NULL DEFAULT 'certificate',
            
            -- Basic auth credentials (encrypted)
            username VARCHAR(500),
            password VARCHAR(500),
            
            -- Client certificate auth (encrypted)
            client_cert_pem TEXT,
            client_key_pem TEXT,
            
            -- Kerberos auth
            kerberos_principal VARCHAR(500),
            kerberos_keytab_path VARCHAR(500),
            
            -- SSL/TLS settings
            use_ssl BOOLEAN DEFAULT 1,
            verify_ssl BOOLEAN DEFAULT 1,
            ca_bundle TEXT,
            
            -- Default settings
            default_template VARCHAR(200) DEFAULT 'WebServer',
            
            -- Status
            enabled BOOLEAN DEFAULT 1,
            last_test_at DATETIME,
            last_test_result VARCHAR(500),
            
            -- Timestamps
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by VARCHAR(80)
        );

        CREATE TABLE IF NOT EXISTS msca_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msca_id INTEGER NOT NULL REFERENCES microsoft_cas(id) ON DELETE CASCADE,
            csr_id INTEGER REFERENCES csrs(id),
            cert_id INTEGER REFERENCES certificates(id),
            request_id INTEGER,
            disposition_message TEXT,
            template VARCHAR(200) NOT NULL,
            status VARCHAR(20) DEFAULT 'submitted',
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            issued_at DATETIME,
            error_message TEXT,
            cert_pem TEXT,
            submitted_by VARCHAR(80)
        );

        CREATE INDEX IF NOT EXISTS idx_msca_requests_msca_id ON msca_requests(msca_id);
        CREATE INDEX IF NOT EXISTS idx_msca_requests_status ON msca_requests(status);
        CREATE INDEX IF NOT EXISTS idx_msca_requests_csr_id ON msca_requests(csr_id);
    """)
    conn.commit()
    logger.info("Migration 003 complete: Microsoft CA tables created")


def downgrade(conn):
    """Remove Microsoft CA tables"""
    conn.execute("DROP TABLE IF EXISTS msca_requests")
    conn.execute("DROP TABLE IF EXISTS microsoft_cas")
    conn.commit()
    logger.info("Migration 003 downgrade: Microsoft CA tables removed")
