#!/usr/bin/env python3
"""
UCM Database Migration Runner
Applies migrations in order, tracks which have been applied.
"""
import os
import sys
import sqlite3
import importlib.util
from pathlib import Path
from datetime import datetime

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db_path():
    """Get database path from environment or default"""
    return os.environ.get('DATABASE_PATH', '/opt/ucm/data/ucm.db')


def ensure_migration_table(conn):
    """Create migration tracking table if not exists"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def get_applied_migrations(conn):
    """Get list of already applied migrations"""
    cursor = conn.execute("SELECT name FROM _migrations ORDER BY name")
    return {row[0] for row in cursor.fetchall()}


def get_pending_migrations(applied):
    """Get list of migration files that haven't been applied"""
    if not MIGRATIONS_DIR.exists():
        return []
    
    pending = []
    for f in sorted(MIGRATIONS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        name = f.stem  # e.g., "001_add_api_keys"
        if name not in applied:
            pending.append(f)
    return pending


def load_migration(path):
    """Load a migration module"""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migration(conn, path, db_path, dry_run=False):
    """Run a single migration"""
    name = path.stem
    module = load_migration(path)
    
    print(f"  → {name}...", end=" ", flush=True)
    
    if dry_run:
        print("(dry run - skipped)")
        return True
    
    try:
        # Check if migration has upgrade function
        if hasattr(module, 'upgrade'):
            # Check signature to determine how to call it
            import inspect
            sig = inspect.signature(module.upgrade)
            param_count = len(sig.parameters)
            
            if param_count == 0:
                # No args: uses SQLAlchemy db.session internally
                module.upgrade()
            elif param_count == 1:
                first_param = list(sig.parameters.keys())[0]
                if 'conn' in first_param.lower():
                    module.upgrade(conn)
                else:
                    # Assumes db_path
                    module.upgrade(db_path)
            else:
                module.upgrade(conn)
                
        elif hasattr(module, 'MIGRATION_SQL'):
            # Legacy format: raw SQL with CREATE TABLE IF NOT EXISTS
            # This is safe to run even if tables already exist
            conn.executescript(module.MIGRATION_SQL)
        else:
            print("SKIP (no upgrade function)")
            return False
        
        # Mark as applied
        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
        print("✓")
        return True
        
    except sqlite3.IntegrityError as e:
        # Already applied (duplicate in _migrations) - skip silently
        conn.rollback()
        print("(already applied)")
        return True
        
    except Exception as e:
        conn.rollback()
        # If error is about table/index already existing, mark as applied anyway
        err_str = str(e).lower()
        if "already exists" in err_str or "duplicate" in err_str:
            conn.execute("INSERT OR IGNORE INTO _migrations (name) VALUES (?)", (name,))
            conn.commit()
            print("✓ (table existed)")
            return True
        print(f"✗ ERROR: {e}")
        return False


def run_all_migrations(dry_run=False, verbose=False):
    """Run all pending migrations"""
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        print("Run init_db.py first to create the database.")
        return False
    
    conn = sqlite3.connect(db_path)
    
    try:
        ensure_migration_table(conn)
        applied = get_applied_migrations(conn)
        pending = get_pending_migrations(applied)
        
        if not pending:
            print("✓ Database is up to date (no pending migrations)")
            return True
        
        print(f"Found {len(pending)} pending migration(s):")
        
        success = True
        for path in pending:
            if not run_migration(conn, path, db_path, dry_run):
                success = False
                break  # Stop on first failure
        
        if success:
            print(f"\n✓ All migrations applied successfully")
        else:
            print(f"\n✗ Migration failed - database may be in inconsistent state")
            print("  Review the error above and fix manually if needed")
        
        return success
        
    finally:
        conn.close()


def show_status():
    """Show migration status"""
    db_path = get_db_path()
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    
    try:
        ensure_migration_table(conn)
        applied = get_applied_migrations(conn)
        pending = get_pending_migrations(applied)
        
        print("=== Migration Status ===")
        print(f"Database: {db_path}")
        print(f"Applied: {len(applied)}")
        print(f"Pending: {len(pending)}")
        
        if applied:
            print("\nApplied migrations:")
            for name in sorted(applied):
                print(f"  ✓ {name}")
        
        if pending:
            print("\nPending migrations:")
            for path in pending:
                print(f"  ○ {path.stem}")
        
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="UCM Database Migration Runner")
    parser.add_argument("command", choices=["run", "status", "dry-run"], 
                        default="status", nargs="?",
                        help="Command to execute")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose output")
    
    args = parser.parse_args()
    
    if args.command == "status":
        show_status()
    elif args.command == "dry-run":
        run_all_migrations(dry_run=True, verbose=args.verbose)
    elif args.command == "run":
        success = run_all_migrations(dry_run=False, verbose=args.verbose)
        sys.exit(0 if success else 1)
