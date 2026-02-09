"""
Migration 016: Create HSM tables
Hardware Security Module provider and key storage.
Supports PKCS#11, Azure Key Vault, Google Cloud KMS, AWS CloudHSM.
"""


def upgrade(conn):
    """Create HSM tables"""
    
    # HSM Providers table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hsm_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL UNIQUE,
            type VARCHAR(50) NOT NULL,
            config TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'unknown',
            last_tested_at DATETIME,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER REFERENCES users(id)
        )
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hsm_providers_type 
        ON hsm_providers(type)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hsm_providers_status 
        ON hsm_providers(status)
    """)
    
    print("  ✓ Created hsm_providers table")
    
    # HSM Keys table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hsm_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL REFERENCES hsm_providers(id) ON DELETE CASCADE,
            key_identifier VARCHAR(255) NOT NULL,
            label VARCHAR(255) NOT NULL,
            algorithm VARCHAR(50) NOT NULL,
            key_type VARCHAR(20) NOT NULL,
            purpose VARCHAR(50) NOT NULL,
            public_key_pem TEXT,
            is_extractable BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            extra_data TEXT,
            UNIQUE(provider_id, key_identifier)
        )
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hsm_keys_provider 
        ON hsm_keys(provider_id)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hsm_keys_algorithm 
        ON hsm_keys(algorithm)
    """)
    
    print("  ✓ Created hsm_keys table")
    
    conn.commit()


def downgrade(conn):
    """Drop HSM tables"""
    conn.execute("DROP TABLE IF EXISTS hsm_keys")
    conn.execute("DROP TABLE IF EXISTS hsm_providers")
    conn.commit()
    print("  ✓ Dropped HSM tables")
