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
                    db.create_all(checkfirst=True)
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
    """Ensure default system config entries exist"""
    defaults = [
        ('app.initialized', 'true', 'Application initialized'),
        ('app.version', app.config.get('APP_VERSION', '1.8.0'), 'Application version'),
        ('https.enabled', 'true', 'HTTPS enforcement enabled'),
    ]
    
    for key, value, description in defaults:
        config = SystemConfig.query.filter_by(key=key).first()
        if not config:
            logger.info(f"Creating missing system config: {key}")
            config = SystemConfig(key=key, value=value, description=description)
            db.session.add(config)
    
    try:
        db.session.commit()
    except Exception as e:
        logger.error(f"Error creating system config defaults: {e}")
        db.session.rollback()


def ensure_admin_user(app):
    """Ensure admin user exists"""
    try:
        # Check if admin already exists
        admin_exists = User.query.filter_by(username=app.config.get("INITIAL_ADMIN_USERNAME", "admin")).first()
        if admin_exists:
            return  # Admin already exists, skip
        
        if User.query.count() == 0:
            logger.info("No users found, creating admin user")
            admin = User(
                username=app.config.get("INITIAL_ADMIN_USERNAME", "admin"),
                email=app.config.get("INITIAL_ADMIN_EMAIL", "admin@example.com"),
                role="admin",
                active=True
            )
            admin.set_password(app.config.get("INITIAL_ADMIN_PASSWORD", "changeme123"))
            db.session.add(admin)
            db.session.commit()
            logger.info(f"Admin user created: {admin.username}")
    except Exception as e:
        logger.error(f"Error ensuring admin user: {e}")
        db.session.rollback()
