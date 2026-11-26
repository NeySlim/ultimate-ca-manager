"""What a fleet console reads of one instance (GET /api/v2/system/instance, #403).

Schema 1, documented in docs/API_REFERENCE.md: a field is only ever added, a removal or a change of
meaning takes schema 2. Nothing here is a secret: the database is named by its engine, never located.
"""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func

import fips_mode
from config.settings import Config
from models import db, CA, SystemConfig
from services.backup import installation
from utils.datetime_utils import utc_isoformat, utc_now

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _database():
    engine = db.engine.dialect.name
    info = getattr(db.engine.dialect, 'server_version_info', None)
    if engine == 'sqlite':
        version = sqlite3.sqlite_version
    else:
        version = '.'.join(str(part) for part in info) if info else None
    return {'engine': engine, 'server_version': version}


def _mode(database_ok):
    if not Config.HA_MODE:
        return {'ha': False, 'node_id': None, 'nodes': None}
    nodes = None
    if not database_ok:
        return {'ha': True, 'node_id': Config.NODE_ID, 'nodes': None}
    try:
        from services.scheduler_leader import cluster_nodes_detail
        from services.scheduler_service import get_scheduler
        nodes = [{k: n[k] for k in ('node_id', 'leader', 'stopped', 'stale', 'version', 'heartbeat_at',
                                    'package_family')}
                 for n in cluster_nodes_detail(get_scheduler().wake_interval)]
    except Exception as exc:
        db.session.rollback()
        logger.warning("Instance state: cluster registry not readable: %s", type(exc).__name__)
    return {'ha': True, 'node_id': Config.NODE_ID, 'nodes': nodes}


def _health():
    """The checks of /health/ready (database, filesystem, Redis when configured, cluster in HA),
    and what the instance refuses to do now."""
    from flask import current_app
    from api import health_routes
    checks = {'database': health_routes._check_database(), 'filesystem': health_routes._check_filesystem()}
    database_ok = checks['database']['status'] == 'ok'
    redis_url = health_routes.config_redis_url()
    if redis_url:
        checks['redis'] = health_routes._check_redis(redis_url)
    if Config.HA_MODE:
        checks['cluster'] = health_routes._check_cluster() if database_ok else {
            'status': 'error', 'message': 'Cluster registry not read: the database does not answer'}
    maintenance = health_routes._maintenance(refresh=database_ok) if Config.HA_MODE else None
    if current_app.config.get('SAFE_MODE'):
        status = 'safe_mode'
    elif maintenance is not None:
        status = 'maintenance'
    elif all(c.get('status') in ('ok', 'skipped') for c in checks.values()):
        status = 'ok'
    else:
        status = 'degraded'
    return {'status': status, 'checks': checks, 'maintenance': maintenance}


def _cas(now):
    from services.dashboard_aggregates import CA_EXPIRY_CRITICAL_DAYS, CA_EXPIRY_WARNING_DAYS, _active_ca
    active = _active_ca(now)

    def count(*conditions):
        return db.session.query(func.count(CA.id)).filter(*conditions).scalar() or 0

    expiring = lambda days: count(active, CA.valid_to.isnot(None), CA.valid_to < now + timedelta(days=days))  # noqa: E731
    next_expiry = db.session.query(func.min(CA.valid_to)).filter(active, CA.valid_to.isnot(None)).scalar()
    return {
        'total': count(),
        'active': count(active),
        'expired': count(and_(CA.valid_to.isnot(None), CA.valid_to <= now)),
        'expiring_90_days': expiring(CA_EXPIRY_CRITICAL_DAYS),
        'expiring_365_days': expiring(CA_EXPIRY_WARNING_DAYS),
        'next_expiry': utc_isoformat(next_expiry),
    }


def _update():
    """The last scheduled check's verdict, read from the database: no request leaves for GitHub."""
    from services import updates

    def setting(key):
        row = SystemConfig.query.filter_by(key=key).first()
        return row.value if row and row.value else None

    checked = setting(updates._LAST_CHECK_TS_KEY)
    try:
        checked_at = (utc_isoformat(datetime.fromtimestamp(float(checked), timezone.utc))
                      if checked and float(checked) > 0 else None)
    except (TypeError, ValueError):
        checked_at = None
    latest = setting(updates._NOTIFIED_VERSION_KEY)
    if checked_at is None:
        return {'available': None, 'latest_version': None, 'checked_at': None}
    available = bool(latest) and updates.compare_versions(latest, updates.get_current_version()) > 0
    return {'available': available, 'latest_version': latest if available else None, 'checked_at': checked_at}


def _backup():
    from services.backup.schedule import get_schedule
    schedule = get_schedule()
    age = schedule.get('last_archive_age_seconds')
    last = utc_isoformat(utc_now() - timedelta(seconds=age)) if isinstance(age, int) else None
    return {'scheduled': bool(schedule.get('enabled')), 'last_archive_at': last,
            'last_outcome': schedule.get('last_outcome'), 'last_outcome_at': schedule.get('last_outcome_at')}


def instance_state() -> dict:
    """Health first: when the database does not answer, what it holds is null instead of a 500."""
    from services.updates import get_update_settings, package_family
    now = utc_now()
    fips = fips_mode.status()
    health = _health()
    database_ok = health['checks']['database']['status'] == 'ok'
    stored = lambda read: read() if database_ok else None  # noqa: E731
    return {
        'schema_version': SCHEMA_VERSION,
        'instance_id': stored(lambda: installation.installation_id(create=True)),
        'generated_at': utc_isoformat(now),
        'version': Config.APP_VERSION,
        'update_channel': stored(lambda: get_update_settings()['channel']),
        'install': {'family': package_family()},
        'mode': _mode(database_ok),
        'database': _database(),
        'health': health,
        'cas': stored(lambda: _cas(now)),
        'update': stored(_update),
        'backup': stored(_backup),
        'fips': {'requested': bool(fips['fips_requested']), 'active': bool(fips['fips_active'])},
    }
