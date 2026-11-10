"""
Session Cleanup Task: removes expired sessions from the file or SQL store.
Runs every 15 minutes; Redis expires its own keys.
"""
import os
import time
import logging

logger = logging.getLogger(__name__)


class SessionCleanupTask:
    """Clean up expired sessions from the filesystem or database store"""

    @staticmethod
    def _purge_database_sessions(app):
        """Delete the rows whose expiry has passed, in one statement."""
        from datetime import datetime
        from sqlalchemy import text
        from models import db

        table = app.config.get('SESSION_SQLALCHEMY_TABLE', 'flask_sessions')
        try:
            # Flask-Session stores naive UTC expiries
            result = db.session.execute(
                text(f'DELETE FROM "{table}" WHERE expiry < :now'), {'now': datetime.utcnow()})
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        logger.info(f"Session cleanup: removed {result.rowcount} expired database sessions")

    @staticmethod
    def execute():
        """Remove session files older than the max session lifetime"""
        try:
            from flask import current_app
            store = current_app.config.get('SESSION_TYPE')
            if store == 'sqlalchemy':
                SessionCleanupTask._purge_database_sessions(current_app)
                return
            if store == 'redis':
                return
            data_dir = current_app.config.get('SESSION_FILE_DIR')
            if not data_dir or not os.path.isdir(data_dir):
                data_dir = os.path.join(
                    current_app.config.get('DATA_DIR', '/opt/ucm/data'),
                    'sessions'
                )
            if not os.path.isdir(data_dir):
                return

            # Get max lifetime from DB (default 24h)
            max_lifetime = 86400
            try:
                from models import SystemConfig
                config = SystemConfig.query.filter_by(key='session_max_lifetime').first()
                if config and config.value:
                    max_lifetime = int(config.value)
            except Exception:
                pass

            # Add 1h buffer to avoid cleaning sessions that are still borderline valid
            cutoff = time.time() - max_lifetime - 3600
            cleaned = 0

            for filename in os.listdir(data_dir):
                filepath = os.path.join(data_dir, filename)
                if not os.path.isfile(filepath):
                    continue
                try:
                    mtime = os.path.getmtime(filepath)
                    if mtime < cutoff:
                        os.unlink(filepath)
                        cleaned += 1
                except OSError:
                    pass

            if cleaned > 0:
                logger.info(f"Session cleanup: removed {cleaned} expired session files")

        except Exception as e:
            logger.error(f"Session cleanup error: {e}")
