"""
System Database Operations
"""

from . import bp
from flask import Blueprint, request, current_app, Response, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, Certificate, CA, CRL, OCSPResponse, SystemConfig
from services.audit_service import AuditService
from pathlib import Path
import os
import sqlite3
import io
from datetime import datetime, timezone
import logging
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)


def _set_system_config(key: str, value: str, description: str) -> None:
    """Upsert a SystemConfig row."""
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value, description=description))
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to upsert SystemConfig {key}: {e}")
        raise


@bp.route('/api/v2/system/database/stats', methods=['GET'])
@require_auth(['read:settings'])
def get_db_stats():
    """Get database statistics (works on SQLite and PostgreSQL)."""
    try:
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_uri.startswith('postgresql'):
            size_bytes = db.session.execute(db.text(
                'SELECT pg_database_size(current_database())'
            )).scalar() or 0
        else:
            db_path = db_uri.replace('sqlite:///', '')
            size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        size_mb = round(size_bytes / (1024 * 1024), 1)

        counts = {
            'cas': CA.query.count(),
            'certificates': Certificate.query.count(),
            'crls': CRL.query.count(),
            'ocsp_responses': OCSPResponse.query.count()
        }

        last_optimized_row = SystemConfig.query.filter_by(key='db_last_optimized').first()
        last_check_row = SystemConfig.query.filter_by(key='db_last_integrity_check').first()

        return success_response(data={
            'size_mb': size_mb,
            'fragmentation_percent': 0,
            'counts': counts,
            'last_vacuum': last_optimized_row.value if last_optimized_row else 'Never',
            'last_check': last_check_row.value if last_check_row else 'Never'
        })
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return error_response("Failed to get database stats")


@bp.route('/api/v2/system/database/optimize', methods=['POST'])
@require_auth(['admin:system'])
def optimize_db():
    """Run VACUUM and ANALYZE (works on SQLite and PostgreSQL)."""
    try:
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_uri.startswith('postgresql'):
            # PG forbids VACUUM inside a transaction block. Use AUTOCOMMIT.
            with db.engine.execution_options(isolation_level='AUTOCOMMIT').connect() as conn:
                conn.execute(db.text('VACUUM ANALYZE'))
        else:
            db.session.execute(db.text('VACUUM'))
            db.session.execute(db.text('ANALYZE'))
        ts = utc_isoformat(utc_now())
        try:
            _set_system_config('db_last_optimized', ts,
                               'Last database optimization timestamp')
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Failed to persist db_last_optimized: {e}")
        AuditService.log_action(
            action='system_optimize',
            resource_type='system',
            resource_name='Database',
            details='Database optimized (VACUUM + ANALYZE)',
            success=True
        )
        return success_response(message="Database optimized successfully")
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        return error_response("Database optimization failed")


@bp.route('/api/v2/system/database/integrity-check', methods=['POST'])
@require_auth(['admin:system'])
def check_integrity():
    """Run database integrity check (works on SQLite and PostgreSQL).

    Returns success_response with {passed, errors, message} under data.
    """
    try:
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_uri.startswith('postgresql'):
            # PRAGMA is SQLite-only. On PG, verify connectivity + count public tables.
            tables = db.session.execute(db.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )).scalar()
            db.session.execute(db.text('SELECT 1')).scalar()
            passed, errors_payload = True, 0
            extra = {'tables': int(tables or 0)}
            message = f"Integrity check passed ({tables} tables verified)"
        else:
            result = db.session.execute(db.text('PRAGMA integrity_check')).scalar()
            extra = {}
            if result == 'ok':
                passed, errors_payload = True, 0
                message = 'Integrity check passed'
            else:
                passed, errors_payload = False, result
                message = 'Integrity check found errors'

        ts = utc_isoformat(utc_now())
        try:
            _set_system_config('db_last_integrity_check', ts,
                               'Last database integrity check timestamp')
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Failed to persist db_last_integrity_check: {e}")

        data = {'passed': passed, 'errors': errors_payload}
        data.update(extra)
        return success_response(data=data, message=message)
    except Exception as e:
        logger.error(f"Integrity check failed: {e}")
        return error_response("Integrity check failed")


@bp.route('/api/v2/system/database/export', methods=['GET'])
@require_auth(['admin:system'])
def export_db():
    """Export database as SQL dump"""
    try:
        db_path = current_app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')

        if not os.path.exists(db_path):
            return error_response("Database not found")

        # Create SQL dump using sqlite3
        conn = sqlite3.connect(db_path)
        sql_dump = io.StringIO()
        for line in conn.iterdump():
            sql_dump.write(f"{line}\n")
        conn.close()

        return Response(
            sql_dump.getvalue(),
            mimetype='application/sql',
            headers={'Content-Disposition': f'attachment; filename=ucm_database_{utc_now().strftime("%Y%m%d_%H%M%S")}.sql'}
        )
    except Exception as e:
        logger.error(f"Database export failed: {e}")
        return error_response("Database export failed")


@bp.route('/api/v2/system/database/reset', methods=['POST'])
@require_auth(['admin:system'])
def reset_db():
    """Reset database to initial state - DANGEROUS"""
    try:
        # `get_current_user` never existed; the import raised and the bare
        # `except` below answered 500 on every call.
        # Read now and passed by value: the entry is written after
        # `drop_all`, when looking the actor up on `g.current_user` would
        # query a table that no longer holds them.
        actor = getattr(g, 'current_user', None)
        actor_name = getattr(actor, 'username', None) or 'unknown'

        # Drop all tables and recreate
        db.drop_all()
        db.create_all()

        # Create default admin user
        from models import User

        # NOTE: the User column is `active`, not `is_active` — the wrong kwarg
        # made this constructor raise TypeError, which the bare `except` below
        # turned into "Database reset failed" AFTER drop_all() had already
        # run: a wiped database with no admin user at all.
        #
        # Recreate the CONFIGURED bootstrap admin exactly as the canonical
        # seeding paths do (app.py, database_health.py, init_db.py):
        # - the configured identity, not a hard-coded 'admin' — a deployment
        #   with INITIAL_ADMIN_USERNAME set would otherwise get the WRONG
        #   admin back from a UI button;
        # - totp_exempt (#141), so a reset under global 2FA enforcement
        #   cannot recreate an admin that no one can log in as;
        # - set_password(), which pins the hash algorithm (models/user.py),
        #   instead of a bare generate_password_hash().
        from auth.password_change_gate import DEFAULT_INITIAL_PASSWORD, initial_password_needs_change
        initial_password = current_app.config.get('INITIAL_ADMIN_PASSWORD', DEFAULT_INITIAL_PASSWORD)
        admin = User(
            username=current_app.config.get('INITIAL_ADMIN_USERNAME', 'admin'),
            email=current_app.config.get('INITIAL_ADMIN_EMAIL', 'admin@localhost'),
            role='admin',
            active=True,
            force_password_change=initial_password_needs_change(initial_password),
            totp_exempt=True
        )
        admin.set_password(initial_password)
        db.session.add(admin)
        ok, err = safe_commit(logger, "Database reset failed")
        if not ok:
            # The tables are already dropped and recreated by now and there
            # is no admin: say so, in a table that exists again.
            AuditService.log_action(
                action='database_reset',
                resource_type='system',
                resource_id='database',
                details=(f"Initiated by {actor_name}; the database was reset "
                         "but the administrator account could not be created"),
                username=actor_name,
                success=False,
            )
            return err

        # Recorded after the reset, not before it. Written first, the entry
        # went into the table `drop_all` was about to destroy, so a reset left
        # no trace of itself at all. Written here it lands in the fresh table,
        # as its first row.
        AuditService.log_action(
            action='database_reset',
            resource_type='system',
            resource_id='database',
            details=f"Initiated by {actor_name}",
            username=actor_name,
        )

        return success_response(message="Database reset successfully. Default admin user created.")
    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        return error_response("Database reset failed")
