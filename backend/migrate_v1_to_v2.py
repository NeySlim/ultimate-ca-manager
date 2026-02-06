#!/usr/bin/env python3
"""
UCM Full Migration: v1.8.x → v2.0.0

Migrates:
- Database schema and data
- Data directory structure (backend/data → data)
- Configuration files
- Certificate and key files

Usage:
    # Full migration from v1.8.x installation
    python3 migrate_v1_to_v2.py /opt/ucm

    # Dry run (show what would be done)
    python3 migrate_v1_to_v2.py --dry-run /opt/ucm
    
    # Database only (for already-migrated file structure)
    python3 migrate_v1_to_v2.py --db-only /opt/ucm/data/ucm.db
"""

import sqlite3
import sys
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
import argparse

# =============================================================================
# CONFIGURATION
# =============================================================================

# v1.8.x paths (relative to UCM_ROOT)
V1_DATA_DIR = "backend/data"
V1_DB_PATH = "backend/data/ucm.db"
V1_ENV_FILE = ".env"

# v2.0.0 paths (relative to UCM_ROOT)  
V2_DATA_DIR = "data"
V2_DB_PATH = "data/ucm.db"
V2_ENV_FILE = "/etc/ucm/ucm.env"

# Directories to migrate
DATA_SUBDIRS = ['ca', 'certs', 'private', 'crl', 'scep', 'backups']

# New directories in v2
NEW_SUBDIRS = ['sessions']

# =============================================================================
# DATABASE MIGRATIONS
# =============================================================================

COLUMN_MIGRATIONS = {
    'users': [
        ('totp_secret', 'VARCHAR(32)', None),
        ('totp_confirmed', 'BOOLEAN', '0'),
        ('backup_codes', 'TEXT', None),
        ('failed_logins', 'INTEGER', '0'),
        ('locked_until', 'DATETIME', None),
        ('login_count', 'INTEGER', '0'),
    ],
    'certificates': [
        ('archived', 'BOOLEAN', '0'),
        ('source', 'VARCHAR(50)', "'manual'"),
        ('template_id', 'INTEGER', None),
        ('owner_group_id', 'INTEGER', None),
        ('key_algo', 'VARCHAR(50)', None),
        ('subject_cn', 'VARCHAR(255)', None),
    ],
    'certificate_authorities': [
        ('owner_group_id', 'INTEGER', None),
        ('serial_number', 'VARCHAR(64)', None),
    ],
    'audit_logs': [
        ('resource_name', 'VARCHAR(255)', None),
        ('entry_hash', 'VARCHAR(64)', None),
        ('prev_hash', 'VARCHAR(64)', None),
    ],
}

# =============================================================================
# DETECTION FUNCTIONS
# =============================================================================

def detect_installation_version(ucm_root):
    """Detect UCM installation version"""
    ucm_root = Path(ucm_root)
    
    # Check for v1.8.x structure: backend/data/ucm.db
    v1_db = ucm_root / V1_DATA_DIR / "ucm.db"
    v2_db = ucm_root / V2_DATA_DIR / "ucm.db"
    
    if v1_db.exists() and not v2_db.exists():
        return "1.8.x", v1_db
    elif v2_db.exists():
        return "2.0.x", v2_db
    elif v1_db.exists() and v2_db.exists():
        # Both exist - check which is newer
        if v1_db.stat().st_mtime > v2_db.stat().st_mtime:
            return "1.8.x", v1_db
        return "2.0.x", v2_db
    else:
        return "unknown", None


def get_db_version(conn):
    """Detect database schema version"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    
    if '_migrations' in tables or 'user_sessions' in tables:
        return '2.0'
    if 'users' in tables and 'certificates' in tables:
        return '1.8'
    return 'unknown'


# =============================================================================
# FILE MIGRATION
# =============================================================================

def migrate_files(ucm_root, dry_run=False):
    """Migrate files from v1.8.x structure to v2.0.0"""
    ucm_root = Path(ucm_root)
    v1_data = ucm_root / V1_DATA_DIR
    v2_data = ucm_root / V2_DATA_DIR
    
    print(f"\n--- File Migration ---")
    print(f"From: {v1_data}")
    print(f"To:   {v2_data}")
    
    if not v1_data.exists():
        print(f"✗ Source directory not found: {v1_data}")
        return False
    
    # Create v2 data directory
    if not dry_run:
        v2_data.mkdir(exist_ok=True)
        for subdir in NEW_SUBDIRS:
            (v2_data / subdir).mkdir(exist_ok=True)
    print(f"{'[DRY] ' if dry_run else ''}✓ Created {v2_data}")
    
    # Migrate subdirectories
    for subdir in DATA_SUBDIRS:
        src = v1_data / subdir
        dst = v2_data / subdir
        
        if not src.exists():
            continue
            
        if dst.exists() and list(dst.iterdir()):
            print(f"  ⚠ {subdir}/ already has content in destination - skipping")
            continue
        
        # Count files
        files = list(src.glob('*'))
        if not files:
            print(f"  ○ {subdir}/ is empty - skipping")
            continue
        
        if dry_run:
            print(f"  [DRY] Would copy {len(files)} files from {subdir}/")
        else:
            dst.mkdir(exist_ok=True)
            for f in files:
                if f.is_file():
                    shutil.copy2(f, dst / f.name)
            print(f"  ✓ Copied {len(files)} files from {subdir}/")
    
    # Migrate HTTPS certificates
    for cert_file in ['https_cert.pem', 'https_key.pem']:
        src = v1_data / cert_file
        dst = v2_data / cert_file
        if src.exists() and not dst.exists():
            if dry_run:
                print(f"  [DRY] Would copy {cert_file}")
            else:
                shutil.copy2(src, dst)
                print(f"  ✓ Copied {cert_file}")
    
    # Migrate database
    v1_db = v1_data / 'ucm.db'
    v2_db = v2_data / 'ucm.db'
    if v1_db.exists() and not v2_db.exists():
        if dry_run:
            print(f"  [DRY] Would copy ucm.db ({v1_db.stat().st_size / 1024:.1f} KB)")
        else:
            shutil.copy2(v1_db, v2_db)
            print(f"  ✓ Copied ucm.db ({v2_db.stat().st_size / 1024:.1f} KB)")
    
    return True


def migrate_config(ucm_root, dry_run=False):
    """Migrate configuration from .env to /etc/ucm/ucm.env"""
    ucm_root = Path(ucm_root)
    v1_env = ucm_root / V1_ENV_FILE
    v2_env = Path(V2_ENV_FILE)
    
    print(f"\n--- Config Migration ---")
    
    if not v1_env.exists():
        print(f"  ○ No .env file to migrate")
        return True
    
    if v2_env.exists():
        print(f"  ⚠ {v2_env} already exists - skipping")
        return True
    
    if dry_run:
        print(f"  [DRY] Would migrate .env → {v2_env}")
        return True
    
    # Read old config
    old_config = {}
    with open(v1_env, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                old_config[key.strip()] = value.strip()
    
    # Create new config directory
    v2_env.parent.mkdir(parents=True, exist_ok=True)
    
    # Write new config with v2 format
    with open(v2_env, 'w') as f:
        f.write("# UCM Configuration (migrated from v1.8.x)\n")
        f.write(f"# Migrated at: {datetime.now().isoformat()}\n\n")
        
        # Essential keys
        for key in ['SECRET_KEY', 'JWT_SECRET_KEY']:
            if key in old_config:
                f.write(f"{key}={old_config[key]}\n")
        
        # Update paths for v2
        f.write(f"\n# Database (updated path for v2.0)\n")
        f.write(f"DATABASE_PATH=/opt/ucm/data/ucm.db\n")
        
        # Copy other settings
        f.write(f"\n# Other settings\n")
        skip_keys = {'SECRET_KEY', 'JWT_SECRET_KEY', 'DATABASE_PATH', 'DATA_DIR'}
        for key, value in old_config.items():
            if key not in skip_keys:
                f.write(f"{key}={value}\n")
    
    os.chmod(v2_env, 0o600)
    print(f"  ✓ Created {v2_env}")
    return True


# =============================================================================
# DATABASE MIGRATION
# =============================================================================

def add_column_if_missing(conn, table, col_name, col_type, default_value=None):
    """Add a column if it doesn't exist"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    
    if col_name in existing:
        return False
    
    default_clause = f"DEFAULT {default_value}" if default_value else ""
    sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} {default_clause}".strip()
    
    try:
        conn.execute(sql)
        print(f"  ✓ Added {table}.{col_name}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to add {table}.{col_name}: {e}")
        return False


def create_v2_tables(conn):
    """Create new v2.0 tables"""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = {row[0] for row in cursor.fetchall()}
    
    tables_created = []
    
    # user_sessions
    if 'user_sessions' not in existing:
        conn.execute("""
            CREATE TABLE user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id VARCHAR(255) UNIQUE NOT NULL,
                ip_address VARCHAR(45),
                user_agent VARCHAR(500),
                auth_method VARCHAR(50) DEFAULT 'password',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON user_sessions(session_id)")
        tables_created.append('user_sessions')
    
    # groups
    if 'groups' not in existing:
        conn.execute("""
            CREATE TABLE groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(80)
            )
        """)
        tables_created.append('groups')
    
    # group_members
    if 'group_members' not in existing:
        conn.execute("""
            CREATE TABLE group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role VARCHAR(20) DEFAULT 'member',
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                added_by VARCHAR(80),
                FOREIGN KEY (group_id) REFERENCES groups(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (group_id, user_id)
            )
        """)
        tables_created.append('group_members')
    
    # api_keys
    if 'api_keys' not in existing:
        conn.execute("""
            CREATE TABLE api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key_hash VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                permissions TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                last_used_at DATETIME,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
        tables_created.append('api_keys')
    
    # certificate_templates
    if 'certificate_templates' not in existing:
        conn.execute("""
            CREATE TABLE certificate_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                template_type VARCHAR(20) NOT NULL,
                key_type VARCHAR(20) DEFAULT 'RSA',
                key_size INTEGER DEFAULT 2048,
                validity_days INTEGER DEFAULT 365,
                key_usage TEXT,
                extended_key_usage TEXT,
                subject_template TEXT,
                san_template TEXT,
                is_system BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(80)
            )
        """)
        tables_created.append('certificate_templates')
    
    # trusted_certificates  
    if 'trusted_certificates' not in existing:
        conn.execute("""
            CREATE TABLE trusted_certificates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                certificate TEXT NOT NULL,
                fingerprint_sha256 VARCHAR(95) UNIQUE NOT NULL,
                subject VARCHAR(512),
                issuer VARCHAR(512),
                valid_from DATETIME,
                valid_to DATETIME,
                purpose VARCHAR(50),
                is_ca BOOLEAN DEFAULT 0,
                imported_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                imported_by VARCHAR(80)
            )
        """)
        tables_created.append('trusted_certificates')
    
    # _migrations tracking
    if '_migrations' not in existing:
        conn.execute("""
            CREATE TABLE _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) UNIQUE NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Mark all existing migrations as applied
        migrations = ['001_add_api_keys', '004_create_webauthn_table', 
                      '005_create_webauthn_challenges', '006_add_locked_until',
                      '007_add_audit_hash_chain', 'v1_to_v2_migration']
        for m in migrations:
            try:
                conn.execute("INSERT INTO _migrations (name) VALUES (?)", (m,))
            except:
                pass
        tables_created.append('_migrations')
    
    conn.commit()
    
    if tables_created:
        print(f"  ✓ Created tables: {', '.join(tables_created)}")
    return len(tables_created)


def extract_cn_from_subject(subject):
    """Extract CN from X.509 subject string"""
    if not subject:
        return None
    for part in subject.replace('/', ',').split(','):
        part = part.strip()
        if part.upper().startswith('CN='):
            return part[3:].strip()
    return None


def populate_computed_columns(conn):
    """Populate subject_cn and key_algo from existing certificate data"""
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, subject, prv, crt 
        FROM certificates 
        WHERE subject_cn IS NULL OR key_algo IS NULL
    """)
    rows = cursor.fetchall()
    
    if not rows:
        return
    
    updated = 0
    for cert_id, subject, prv, crt in rows:
        cn = extract_cn_from_subject(subject)
        
        # Detect key algorithm
        data = (crt or '') + (prv or '')
        if 'EC PRIVATE' in data or 'BEGIN EC' in data:
            algo = 'ECDSA'
        else:
            algo = 'RSA'
        
        cursor.execute("""
            UPDATE certificates 
            SET subject_cn = COALESCE(subject_cn, ?),
                key_algo = COALESCE(key_algo, ?)
            WHERE id = ?
        """, (cn, algo, cert_id))
        updated += 1
    
    conn.commit()
    if updated:
        print(f"  ✓ Populated computed columns for {updated} certificates")


def migrate_database(db_path, dry_run=False):
    """Migrate database schema from v1.8.x to v2.0.0"""
    print(f"\n--- Database Migration ---")
    print(f"Database: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"✗ Database not found: {db_path}")
        return False
    
    if dry_run:
        print("[DRY] Would migrate database schema")
        return True
    
    # Backup
    backup_path = f"{db_path}.pre_v2_backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"  ✓ Backup: {backup_path}")
    
    conn = sqlite3.connect(db_path)
    
    try:
        version = get_db_version(conn)
        print(f"  Schema version: {version}")
        
        if version == '2.0':
            print("  ✓ Database already at v2.0")
            return True
        
        # Add missing columns
        cols_added = 0
        for table, columns in COLUMN_MIGRATIONS.items():
            for col_name, col_type, default_value in columns:
                if add_column_if_missing(conn, table, col_name, col_type, default_value):
                    cols_added += 1
        conn.commit()
        
        # Create new tables
        tables_created = create_v2_tables(conn)
        
        # Populate computed columns
        populate_computed_columns(conn)
        
        print(f"\n  ✓ Migration complete: {cols_added} columns added, {tables_created} tables created")
        return True
        
    except Exception as e:
        print(f"\n  ✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        conn.close()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Migrate UCM from v1.8.x to v2.0.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('path', help='UCM installation root or database path')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be done without making changes')
    parser.add_argument('--db-only', action='store_true',
                        help='Only migrate database, skip file migration')
    parser.add_argument('--files-only', action='store_true',
                        help='Only migrate files, skip database migration')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("UCM Migration: v1.8.x → v2.0.0")
    print("=" * 60)
    
    if args.dry_run:
        print("** DRY RUN MODE - No changes will be made **\n")
    
    path = Path(args.path)
    
    # Detect what we're dealing with
    if args.db_only or path.suffix == '.db':
        # Database-only migration
        success = migrate_database(str(path), args.dry_run)
    else:
        # Full installation migration
        version, db_path = detect_installation_version(path)
        print(f"Installation: {path}")
        print(f"Detected version: {version}")
        
        if version == 'unknown':
            print("✗ Cannot detect UCM version. Check path is correct.")
            sys.exit(1)
        
        success = True
        
        if not args.db_only:
            if version == '1.8.x':
                success = migrate_files(path, args.dry_run) and success
                success = migrate_config(path, args.dry_run) and success
            else:
                print("\n✓ Files already in v2.0 structure")
        
        if not args.files_only and db_path:
            # If files were migrated, DB is now in v2 location
            if version == '1.8.x' and not args.dry_run:
                new_db = path / V2_DATA_DIR / 'ucm.db'
                if new_db.exists():
                    db_path = new_db
            success = migrate_database(str(db_path), args.dry_run) and success
    
    print("\n" + "=" * 60)
    if success:
        print("✓ Migration completed successfully!")
        if not args.dry_run:
            print("\nNext steps:")
            print("  1. Verify the migration: systemctl restart ucm")
            print("  2. Check logs: journalctl -u ucm -n 50")
            print("  3. Test login and functionality")
            print("  4. If all OK, remove old data: rm -rf /opt/ucm/backend/data")
    else:
        print("✗ Migration failed - check errors above")
    print("=" * 60)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
