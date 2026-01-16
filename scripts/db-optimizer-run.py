#!/usr/bin/env python3
"""
UCM Database Optimizer - Run Script
Must be executed from /opt/ucm/backend directory
"""
import sys
import logging
from datetime import datetime
from flask import Flask
from config.settings import Config
from database import db
from services.db_management_service import DatabaseManagementService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/ucm/db-optimizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def run_optimization():
    try:
        logger.info('='*60)
        logger.info('UCM Database Optimizer - Starting')
        logger.info('='*60)
        
        app = create_app()
        with app.app_context():
            service = DatabaseManagementService()
            stats = service.get_database_stats()
            
            if stats['size_mb'] < 10:
                logger.info('Skipping - DB too small (%.2f MB)' % stats['size_mb'])
                return 0
            
            if stats['fragmentation_pct'] < 5:
                logger.info('Skipping - low fragmentation (%.2f%%)' % stats['fragmentation_pct'])
                return 0
            
            logger.info('Size: %s, Fragmentation: %.2f%%' % (stats['size_formatted'], stats['fragmentation_pct']))
            
            result = service.optimize_database()
            
            if result['success']:
                v = result['vacuum']
                logger.info('✓ VACUUM: %.2f → %.2f MB (saved %s)' % (v['size_before_mb'], v['size_after_mb'], v['space_saved_formatted']))
                logger.info('✓ ANALYZE completed')
                logger.info('='*60)
                return 0
            else:
                logger.error('✗ Failed: %s' % result.get('error', 'Unknown'))
                return 1
                
    except Exception as e:
        logger.error('✗ Fatal error: %s' % str(e), exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(run_optimization())


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/ucm/db-optimizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_app():
    """Create minimal Flask app for DB access"""
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def should_run_vacuum():
    """
    Check if VACUUM should run
    Skip if database is too small (<10MB)
    """
    app = create_app()
    with app.app_context():
        service = DatabaseManagementService()
        stats = service.get_database_stats()
        
        # Skip if DB < 10 MB
        if stats['size_mb'] < 10:
            logger.info(f"Skipping VACUUM - database too small ({stats['size_mb']} MB)")
            return False
        
        # Skip if fragmentation < 5%
        if stats['fragmentation_pct'] < 5:
            logger.info(f"Skipping VACUUM - low fragmentation ({stats['fragmentation_pct']}%)")
            return False
        
        return True


def run_optimization():
    """Run database optimization"""
    try:
        logger.info("=" * 60)
        logger.info("UCM Database Optimizer - Starting")
        logger.info("=" * 60)
        
        if not should_run_vacuum():
            logger.info("Optimization not needed - exiting")
            return 0
        
        app = create_app()
        with app.app_context():
            service = DatabaseManagementService()
            
            # Get stats before
            stats_before = service.get_database_stats()
            logger.info(f"Database size before: {stats_before['size_formatted']}")
            logger.info(f"Fragmentation: {stats_before['fragmentation_pct']}%")
            
            # Run optimization
            result = service.optimize_database()
            
            if result['success']:
                vacuum_result = result['vacuum']
                logger.info(f"✓ VACUUM completed")
                logger.info(f"  Size before: {vacuum_result['size_before_mb']} MB")
                logger.info(f"  Size after:  {vacuum_result['size_after_mb']} MB")
                logger.info(f"  Space saved: {vacuum_result['space_saved_formatted']}")
                
                logger.info(f"✓ ANALYZE completed")
                
                # Optional: Send email notification to admin
                try:
                    from models import User
                    from services.notification_service import NotificationService
                    
                    admin = User.query.filter_by(is_admin=True).first()
                    if admin and admin.email and admin.email_notifications:
                        notif_service = NotificationService()
                        notif_service.send_email(
                            to_email=admin.email,
                            subject="UCM Database Optimization Completed",
                            body=f"""Database optimization completed successfully.

Size before: {vacuum_result['size_before_mb']} MB
Size after: {vacuum_result['size_after_mb']} MB
Space saved: {vacuum_result['space_saved_formatted']}

This is an automated weekly maintenance task.
"""
                        )
                        logger.info(f"Email notification sent to {admin.email}")
                except Exception as e:
                    logger.warning(f"Could not send email notification: {e}")
                
                logger.info("=" * 60)
                logger.info("UCM Database Optimizer - Completed Successfully")
                logger.info("=" * 60)
                return 0
            else:
                logger.error(f"✗ Optimization failed: {result.get('error', 'Unknown error')}")
                return 1
                
    except Exception as e:
        logger.error(f"✗ Fatal error during optimization: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(run_optimization())
