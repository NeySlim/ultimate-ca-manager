"""
Database health check and repair
Ensures all required tables and initial data exist
"""
import logging
from models import db, SystemConfig, User
from sqlalchemy import inspect

logger = logging.getLogger(__name__)


def check_and_repair_database(app):
    """
    Check database health and repair if needed
    Called on every application startup
    """
    with app.app_context():
        try:
            # 1. Check if all tables exist
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            expected_tables = db.Model.metadata.tables.keys()
            missing_tables = [table for table in expected_tables if table not in existing_tables]
            
            if missing_tables:
                logger.warning(f"Missing tables detected: {missing_tables}")
                logger.info("Creating missing tables...")
                try:
                    db.create_all()
                    logger.info("Missing tables created")
                except Exception as e:
                    logger.warning(f"Error creating tables (may already exist): {e}")
            
            # 2. Verify system_config table has basic entries
            ensure_system_config_defaults(app)
            
            # 3. Verify admin user exists
            ensure_admin_user(app)
            
            logger.info("Database health check completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


def ensure_system_config_defaults(app):
    """Ensure default system config entries exist - handles race conditions"""
    from sqlalchemy.exc import IntegrityError
    from config.settings import Config
    
    defaults = [
        ('app.initialized', 'true', 'Application initialized'),
        ('app.version', Config.APP_VERSION, 'Application version'),
        ('https.enabled', 'true', 'HTTPS enforcement enabled'),
    ]
    
    for key, value, description in defaults:
        # Check if config already exists (read-only check first)
        config = SystemConfig.query.filter_by(key=key).first()
        if config:
            # Always sync app.version from VERSION file
            if key == 'app.version' and config.value != value:
                config.value = value
                db.session.commit()
            continue  # Already exists, skip
            
        # Try to create it in isolated transaction
        try:
            config = SystemConfig(key=key, value=value, description=description)
            db.session.add(config)
            db.session.flush()  # Force write immediately to catch IntegrityError before commit
            db.session.commit()
        except IntegrityError:
            # Another worker won the race - expected with multiple workers
            db.session.rollback()
            logger.debug(f"System config {key} already exists (created by another worker)")
        except Exception as e:
            logger.error(f"Error creating system config {key}: {e}")
            db.session.rollback()


def ensure_admin_user(app):
    """Ensure admin user exists - prevents race conditions with atomic check"""
    from sqlalchemy.exc import IntegrityError
    
    # Quick read-only check first (no lock needed)
    admin_exists = User.query.filter_by(username=app.config.get("INITIAL_ADMIN_USERNAME", "admin")).first()
    if admin_exists:
        return  # Admin already exists, skip
    
    # Only one worker should reach here on first startup
    # Use try/except to handle the case where another worker wins the race
    try:
        # Double-check user count inside transaction
        user_count = User.query.count()
        if user_count > 0:
            # Another worker already created a user
            return
        
        # Create admin user
        logger.info("No users found, creating admin user")
        admin = User(
            username=app.config.get("INITIAL_ADMIN_USERNAME", "admin"),
            email=app.config.get("INITIAL_ADMIN_EMAIL", "admin@example.com"),
            role="admin",
            active=True
        )
        admin.set_password(app.config.get("INITIAL_ADMIN_PASSWORD", "changeme123"))
        admin.force_password_change = True
        db.session.add(admin)
        db.session.commit()
        logger.info(f"✓ Admin user created: {admin.username}")
        
    except IntegrityError:
        # Another worker won the race and created the admin user first
        # This is normal with multiple Gunicorn workers starting simultaneously
        db.session.rollback()
        # Silent - this is expected behavior, not an error
        
    except Exception as e:
        logger.error(f"Unexpected error ensuring admin user: {e}")
        db.session.rollback()
