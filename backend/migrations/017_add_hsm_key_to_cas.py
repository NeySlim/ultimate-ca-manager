"""
Migration 017: Add HSM key reference to Certificate Authorities

Adds hsm_key_id foreign key to certificate_authorities table,
allowing CAs to use HSM-backed private keys for signing.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_migration(db_path: str) -> bool:
    """
    Add hsm_key_id column to certificate_authorities table
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        True if migration succeeded
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(certificate_authorities)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'hsm_key_id' not in columns:
            logger.info("Adding hsm_key_id column to certificate_authorities...")
            
            # Add column - SQLite doesn't support ADD CONSTRAINT with FK inline
            # but the FK will be enforced via SQLAlchemy
            cursor.execute("""
                ALTER TABLE certificate_authorities
                ADD COLUMN hsm_key_id INTEGER REFERENCES hsm_keys(id)
            """)
            
            conn.commit()
            logger.info("Migration 017 completed: hsm_key_id added to certificate_authorities")
        else:
            logger.info("Migration 017 skipped: hsm_key_id already exists")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Migration 017 failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/ucm/backend/ucm.db"
    success = run_migration(db_path)
    sys.exit(0 if success else 1)
