"""
Migration: Add hash chain columns to audit_logs for tamper detection
"""
from models import db
from sqlalchemy import text

def upgrade():
    """Add prev_hash and entry_hash columns to audit_logs"""
    try:
        db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN prev_hash VARCHAR(64)"))
        db.session.commit()
        print("✓ Added prev_hash column")
    except Exception as e:
        if "duplicate" in str(e).lower():
            print("✓ prev_hash already exists")
        else:
            print(f"Note: {e}")
        db.session.rollback()
    
    try:
        db.session.execute(text("ALTER TABLE audit_logs ADD COLUMN entry_hash VARCHAR(64)"))
        db.session.commit()
        print("✓ Added entry_hash column")
    except Exception as e:
        if "duplicate" in str(e).lower():
            print("✓ entry_hash already exists")
        else:
            print(f"Note: {e}")
        db.session.rollback()
    
    return True

def downgrade():
    print("Note: SQLite doesn't support DROP COLUMN. Columns will remain.")
    return True

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        upgrade()
