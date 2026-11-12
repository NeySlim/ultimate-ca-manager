#!/usr/bin/env python3
"""
Database initialization script for UCM
Creates all tables and default admin user
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Skip secret validation during package installation
os.environ["UCM_SKIP_SECRET_VALIDATION"] = "1"

from app import create_app
from models import db, User

def init_database():
    """Initialize database with tables and default user"""
    app = create_app()

    with app.app_context():
        # Create all tables
        db.create_all()
        print("✓ Database tables created")

        # create_app() already seeds the configured admin (app.py /
        # database_health.py), so this block is a fallback for the case where
        # that seeding was skipped or swallowed. Look up the CONFIGURED
        # username — a hard-coded 'admin' missed any INITIAL_ADMIN_USERNAME
        # override and then tried (and, before this fix, failed) to seed a
        # duplicate.
        admin_username = app.config.get("INITIAL_ADMIN_USERNAME", "admin")
        admin = User.query.filter_by(username=admin_username).first()
        if not admin:
            # The same account as the start-up path: provided or generated, never a default
            from auth.initial_admin import password_file, read_command, seed_admin
            admin = seed_admin(app.config)
            db.session.commit()
            if admin.force_password_change:
                path = password_file(app.config)
                print(f"✓ Admin user created ({admin_username}); generated password in {path}, "
                      f"read it with: {read_command(path)}")
            else:
                print(f"✓ Admin user created ({admin_username}) with the password provided")
        else:
            print("✓ Admin user already exists")
        
        print("\n✅ Database initialization complete")
        print(f"   Database location: {app.config.get('SQLALCHEMY_DATABASE_URI')}")

if __name__ == '__main__':
    try:
        init_database()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Database initialization failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
