"""
Migration: Add locked_until column to users table for persistent account lockout
"""
from models import db
from sqlalchemy import text

def upgrade():
    """Add locked_until column to users table"""
    try:
        db.session.execute(text("""
            ALTER TABLE users ADD COLUMN locked_until DATETIME
        """))
        db.session.commit()
        print("✓ Added locked_until column to users table")
        return True
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("✓ Column locked_until already exists")
            return True
        print(f"✗ Failed to add locked_until column: {e}")
        db.session.rollback()
        return False

def downgrade():
    """Remove locked_until column (SQLite doesn't support DROP COLUMN easily)"""
    print("Note: SQLite doesn't support DROP COLUMN. Column will remain but be unused.")
    return True

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        upgrade()
