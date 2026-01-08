#!/usr/bin/env python3
"""
Migration script for UCM v1.7.0 - mTLS and WebAuthn Authentication
Adds tables and columns for certificate and MFA authentication
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from models import db
from app import create_app

def migrate():
    """Run migration"""
    print("=" * 60)
    print("UCM v1.7.0 Migration - mTLS & WebAuthn Authentication")
    print("=" * 60)
    
    app = create_app()
    
    with app.app_context():
        # Get database connection
        connection = db.engine.raw_connection()
        cursor = connection.cursor()
        
        try:
            print("\n1. Adding columns to users table...")
            
            # Check if full_name column exists
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'full_name' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)")
                print("   ✓ Added full_name column")
            else:
                print("   - full_name column already exists")
            
            if 'mfa_enabled' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT 0")
                print("   ✓ Added mfa_enabled column")
            else:
                print("   - mfa_enabled column already exists")
            
            connection.commit()
            
            print("\n2. Creating auth_certificates table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_certificates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cert_serial VARCHAR(128) UNIQUE NOT NULL,
                    cert_subject TEXT NOT NULL,
                    cert_issuer TEXT,
                    cert_fingerprint VARCHAR(128),
                    name VARCHAR(128),
                    enabled BOOLEAN DEFAULT 1 NOT NULL,
                    valid_from DATETIME,
                    valid_until DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            print("   ✓ Created auth_certificates table")
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_cert_serial ON auth_certificates(cert_serial)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_cert_fingerprint ON auth_certificates(cert_fingerprint)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_cert_user ON auth_certificates(user_id)")
            print("   ✓ Created indexes")
            
            connection.commit()
            
            print("\n3. Creating webauthn_credentials table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webauthn_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    credential_id BLOB UNIQUE NOT NULL,
                    public_key BLOB NOT NULL,
                    sign_count INTEGER DEFAULT 0 NOT NULL,
                    name VARCHAR(128),
                    aaguid VARCHAR(36),
                    transports TEXT,
                    is_backup_eligible BOOLEAN DEFAULT 0,
                    is_backup_device BOOLEAN DEFAULT 0,
                    user_verified BOOLEAN DEFAULT 0,
                    enabled BOOLEAN DEFAULT 1 NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            print("   ✓ Created webauthn_credentials table")
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_credential_id ON webauthn_credentials(credential_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_user ON webauthn_credentials(user_id)")
            print("   ✓ Created indexes")
            
            connection.commit()
            
            print("\n4. Creating webauthn_challenges table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webauthn_challenges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    challenge VARCHAR(128) UNIQUE NOT NULL,
                    challenge_type VARCHAR(20) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    used BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            print("   ✓ Created webauthn_challenges table")
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_challenge ON webauthn_challenges(challenge)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_challenge_user ON webauthn_challenges(user_id)")
            print("   ✓ Created indexes")
            
            connection.commit()
            
            print("\n5. Creating system_config entries...")
            cursor.execute("""
                INSERT OR IGNORE INTO system_config (key, value, description)
                VALUES ('cert_auth_enabled', '0', 'Enable certificate-based authentication')
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO system_config (key, value, description)
                VALUES ('cert_auth_required', '0', 'Require certificate authentication (no password fallback)')
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO system_config (key, value, description)
                VALUES ('mfa_required_for_admins', '0', 'Require MFA for admin users')
            """)
            cursor.execute("""
                INSERT OR IGNORE INTO system_config (key, value, description)
                VALUES ('webauthn_enabled', '1', 'Enable WebAuthn/FIDO2 passwordless authentication')
            """)
            print("   ✓ Added configuration entries")
            
            connection.commit()
            
            print("\n" + "=" * 60)
            print("✅ Migration completed successfully!")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Restart UCM: systemctl restart ucm (or docker restart)")
            print("2. Configure certificate auth in Settings")
            print("3. Users can enroll certificates/security keys in Profile")
            print("\nNew features available:")
            print("- mTLS certificate authentication")
            print("- WebAuthn/FIDO2 passwordless login")
            print("- Multi-factor authentication (MFA)")
            
        except Exception as e:
            connection.rollback()
            print(f"\n❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        finally:
            cursor.close()
            connection.close()

if __name__ == '__main__':
    migrate()
