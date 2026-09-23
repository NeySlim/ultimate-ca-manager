"""
Active Directory Connector settings routes
/api/v2/ad-connector/* -- single stored LDAP connection UCM uses to query
Active Directory directly, kept deliberately separate from SSO's own LDAP
provider config (see models/ad_connector.py's module docstring for why).
"""
import logging

from flask import Blueprint, request

from auth.unified import require_auth
from models import db, ADConnectorConfig
from services.ad_connector import health, lookup
from services.ad_connector.health import (
    MAX_PROBE_INTERVAL_SECONDS as MAX_PROBE_INTERVAL,
    MIN_PROBE_INTERVAL_SECONDS as MIN_PROBE_INTERVAL,
)
from services.audit_service import AuditService
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response

logger = logging.getLogger(__name__)

bp = Blueprint('ad_connector_v2', __name__)

MAX_SERVER_LEN = 500
MAX_DN_LEN = 500
# Every configured DC is bound to in turn by the health probe, which runs on
# the scheduler's single thread and waits out _LDAP_CONNECT_TIMEOUT_SECONDS
# on each black-holed one. A long list would delay CRL generation, backups
# and discovery behind it every cycle, so the list is capped at more DCs
# than a domain realistically fails over between.
MAX_SERVERS = 8


def _parse_servers(data):
    """The submitted domain controller list -> ``(joined, error)``.

    Accepts ``servers`` (the list the settings form sends) or the older
    single ``server`` string, so an API client written against the
    one-server shape keeps working. Exactly one of the two returned values
    is ever meaningful.
    """
    raw = data['servers'] if 'servers' in data else data.get('server')
    if raw is not None and not isinstance(raw, (str, list, tuple)):
        return None, error_response('servers must be a hostname or a list of hostnames', 400)
    if isinstance(raw, (list, tuple)) and not all(isinstance(entry, str) for entry in raw):
        # split_servers skips these rather than raising (it also reads a
        # column that could have been hand-edited), so the shape has to be
        # refused here or a client would get a silent 200 having stored
        # fewer servers than it sent.
        return None, error_response('each server must be a hostname string', 400)
    servers = lookup.split_servers(raw)
    for host in servers:
        if len(host) > MAX_SERVER_LEN:
            return None, error_response('server is too long', 400)
    if len(servers) > MAX_SERVERS:
        return None, error_response(f'at most {MAX_SERVERS} servers are supported', 400)
    joined = lookup.join_servers(servers)
    if len(joined) > MAX_SERVER_LEN:
        return None, error_response('too many servers', 400)
    return joined, None


def _get_or_create():
    config = ADConnectorConfig.get_singleton()
    if config is None:
        config = ADConnectorConfig()
        db.session.add(config)
    return config


@bp.route('/api/v2/ad-connector', methods=['GET'])
@require_auth(['read:ad_connector'])
def get_config():
    """Get the Active Directory Connector configuration."""
    config = ADConnectorConfig.get_singleton()
    if config is None:
        return success_response(data=ADConnectorConfig().to_dict())
    return success_response(data=config.to_dict())


@bp.route('/api/v2/ad-connector', methods=['PUT'])
@require_auth(['write:ad_connector'])
def update_config():
    """Update the Active Directory Connector configuration (upsert)."""
    data = request.json or {}

    config = _get_or_create()

    if 'servers' in data or 'server' in data:
        joined, err = _parse_servers(data)
        if err:
            return err
        if joined != (config.server or ''):
            # The health blob is keyed by hostname, so a verdict about a DC
            # that is no longer listed (or a renamed one) must not linger and
            # get applied to the new list. Clearing it means the next probe
            # decides, and until then _connect simply has no opinion.
            config.health = None
        config.server = joined or None
    if 'port' in data:
        try:
            config.port = int(data['port']) if data['port'] not in (None, '') else 389
        except (TypeError, ValueError):
            return error_response('port must be an integer', 400)
    if 'health_probe_interval' in data:
        try:
            interval = int(data['health_probe_interval'])
        except (TypeError, ValueError):
            return error_response('health_probe_interval must be an integer', 400)
        if not (MIN_PROBE_INTERVAL <= interval <= MAX_PROBE_INTERVAL):
            return error_response(
                f'health_probe_interval must be between {MIN_PROBE_INTERVAL} '
                f'and {MAX_PROBE_INTERVAL} seconds', 400)
        config.health_probe_interval = interval
    if 'use_ssl' in data:
        config.use_ssl = bool(data['use_ssl'])
    if 'verify_ssl' in data:
        config.verify_ssl = bool(data['verify_ssl'])
    if 'ca_bundle' in data:
        config.ca_bundle = (data['ca_bundle'] or '').strip() or None
    if 'base_dn' in data:
        base_dn = (data['base_dn'] or '').strip()
        if len(base_dn) > MAX_DN_LEN:
            return error_response('base_dn is too long', 400)
        config.base_dn = base_dn or None
    if 'bind_dn' in data:
        bind_dn = (data['bind_dn'] or '').strip()
        if len(bind_dn) > MAX_DN_LEN:
            return error_response('bind_dn is too long', 400)
        config.bind_dn = bind_dn or None
    if 'bind_password' in data and data['bind_password'] != '***':
        config.bind_password = data['bind_password'] or None
    if 'enabled' in data:
        config.enabled = bool(data['enabled'])

    # An enabled connector must never bind anonymously, which is what ldap3
    # does whenever either half is missing. Only while enabled: switching a
    # connector off, or filling it in field by field, binds nothing.
    if config.enabled and not config.bind_dn:
        db.session.rollback()
        return error_response('bind_dn is required while the connector is enabled', 400)
    if config.enabled and not config.bind_password:
        db.session.rollback()
        return error_response('bind_password is required while the connector is enabled', 400)

    config.updated_at = utc_now()

    try:
        ok, err = safe_commit(logger, 'Failed to update AD Connector configuration')
        if not ok:
            return err
    except Exception as e:
        # bind_password's setter raises if encryption is unavailable --
        # fail closed, never silently persist plaintext.
        db.session.rollback()
        logger.error('Failed to update AD Connector configuration: %s', e)
        return error_response('Failed to save configuration (encryption unavailable?)', 500)

    AuditService.log_action(
        action='ad_connector_config_update',
        resource_type='ad_connector',
        resource_name='AD Connector Configuration',
        details='Updated AD Connector configuration',
        success=True,
    )

    return success_response(data=config.to_dict(), message='AD Connector configuration saved')


@bp.route('/api/v2/ad-connector/test', methods=['POST'])
@require_auth(['write:ad_connector'])
def test_connection_inline():
    """Test connectivity using unsaved form data (before save)."""
    from types import SimpleNamespace

    data = request.json or {}
    joined, err = _parse_servers(data)
    if err:
        return err
    if not joined:
        return error_response('server is required', 400)

    # Blank password means "unchanged" (form never re-sends the saved one),
    # not "use an empty password".
    if not (data.get('bind_dn') or '').strip():
        return error_response('bind_dn is required', 400)

    bind_password = data.get('bind_password')
    if not bind_password:
        saved = ADConnectorConfig.get_singleton()
        if saved and saved.bind_password:
            bind_password = saved.bind_password
    if not bind_password:
        # Same rule as the save: an anonymous bind is not a connection this
        # connector is allowed to make, so testing one would report a
        # success it will never be configured to repeat.
        return error_response('bind_password is required', 400)

    cfg = SimpleNamespace(
        server=joined,
        port=int(data['port']) if data.get('port') else 389,
        use_ssl=bool(data.get('use_ssl')),
        verify_ssl=data.get('verify_ssl', True),
        ca_bundle=data.get('ca_bundle') or None,
        bind_dn=data.get('bind_dn'),
        bind_password=bind_password,
    )
    result = lookup.test_connection(cfg)
    if result.get('success'):
        return success_response(data=result, message=result.get('message'))
    # The per-server breakdown rides along on the failure too: with several
    # DCs configured, "which ones failed and why" is the whole point of the
    # test, and a flat message string can't be rendered per row.
    return error_response(result.get('message', 'Connection test failed'), 400,
                          details={'servers': result.get('servers', [])})


@bp.route('/api/v2/ad-connector/test-saved', methods=['POST'])
@require_auth(['write:ad_connector'])
def test_connection_saved():
    """Test connectivity using the saved configuration."""
    config = ADConnectorConfig.get_singleton()
    if config is None or not config.server:
        return error_response('AD Connector is not configured', 400)

    result = lookup.test_connection(config)
    # The badge reflects the test just run, which is the same per-DC bind the
    # probe performs. Only for an enabled connector (a disabled one serves no
    # lookup), and only when DCs were tried: a refused bind reached none.
    if config.enabled and result.get('servers'):
        health.record(config, [
            (s['server'], s['success'], s['message']) for s in result.get('servers', [])
        ])
    config.last_test_at = utc_now()
    # last_test_result is a String(500) and a multi-DC failure detail can
    # run far past that -- store the verdict, the full per-server breakdown
    # goes back in the response for the settings page to render.
    if result.get('success'):
        config.last_test_result = 'partial' if result.get('partial') else 'success'
    else:
        config.last_test_result = f"failed: {result.get('message')}"[:500]
    safe_commit(logger, 'Failed to record AD Connector test result')

    if result.get('success'):
        return success_response(data=result, message=result.get('message'))
    # The per-server breakdown rides along on the failure too: with several
    # DCs configured, "which ones failed and why" is the whole point of the
    # test, and a flat message string can't be rendered per row.
    return error_response(result.get('message', 'Connection test failed'), 400,
                          details={'servers': result.get('servers', [])})
