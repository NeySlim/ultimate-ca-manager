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
            # Create default admin user with the same properties as the
            # canonical bootstrap paths in app.py / database_health.py.
            # NOTE: the User column is `active` — `is_active=True` made this
            # constructor raise TypeError whenever the block was reached.
            from auth.password_change_gate import DEFAULT_INITIAL_PASSWORD, initial_password_needs_change
            initial_password = app.config.get("INITIAL_ADMIN_PASSWORD", DEFAULT_INITIAL_PASSWORD)
            admin = User(
                username=admin_username,
                email=app.config.get("INITIAL_ADMIN_EMAIL", "admin@localhost"),
                role='admin',
                active=True,
                # The default password is public knowledge, so it must be
                # rotated at first login rather than silently remaining valid.
                force_password_change=initial_password_needs_change(initial_password),
                # Exempt the bootstrap admin from forced 2FA enrolment (#141)
                # so enabling global enforcement can never lock out this
                # account — same as the other bootstrap paths.
                totp_exempt=True
            )
            admin.set_password(initial_password)
            db.session.add(admin)
            db.session.commit()
            print(f"✓ Default admin user created (username: {admin_username}, "
                  "password: INITIAL_ADMIN_PASSWORD, default changeme123)")
            print("  ⚠️  CHANGE THIS PASSWORD IMMEDIATELY!")
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
