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
import bcrypt

def init_database():
    """Initialize database with tables and default user"""
    app = create_app()
    
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✓ Database tables created")
        
        # Check if admin user exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            # Create default admin user
            hashed_password = bcrypt.hashpw('changeme123'.encode('utf-8'), bcrypt.gensalt())
            admin = User(
                username='admin',
                email='admin@ucm.local',
                password_hash=hashed_password.decode('utf-8'),
                role='admin',
                is_active=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✓ Default admin user created (username: admin, password: changeme123)")
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
