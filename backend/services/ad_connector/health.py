"""
Active health probing for the Active Directory Connector's domain controllers.

``services/ad_connector/lookup.py``'s ``_connect`` walks the configured DCs
in order and returns the first that binds. On its own that means a dead DC
is discovered only when a client needs it: a refused connection fails in
milliseconds, but a *black-holed* DC (packets dropped rather than rejected,
the usual shape of a host being patched or a firewall rule landing) costs
``_LDAP_CONNECT_TIMEOUT_SECONDS`` on every single lookup before failover
gets a turn. A WSTEP enrollment would sit there wearing that delay, and
nothing anywhere would say why.

So the same bind this connector actually uses is run on a schedule instead,
and the verdict is written to the config row. ``_connect`` then skips a DC
already known to be down, and an operator learns about it from the log and
the settings page rather than from a slow enrollment.

Three deliberate choices:

1. **The probe is a full bind**, not a TCP connect. The failure this
   connector was built for -- a DC certificate whose SAN names only its own
   host -- passes a TCP check and fails a TLS handshake, so a shallower
   probe would report a DC healthy that cannot actually serve a lookup.

2. **Only transitions are logged.** A DC that has been down for an hour
   would otherwise write the same warning every probe and bury everything
   else. Going down logs a warning (high severity when it was the last one
   standing), coming back logs the recovery, and steady state is silent.

3. **The state is advisory and expires.** ``_connect`` ignores it once it
   is older than ``stale_after(interval)`` and never lets it rule out
   every DC: if the probe stopped running, or its verdict is simply wrong,
   the connector must still try rather than refuse enrollment on the word
   of a stale record. Health can only ever reorder and thin the candidate
   list, never empty it.
"""
import json
import logging

from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)

# The floor under how long a verdict is trusted by _connect. The window
# itself is derived from the connector's own probe interval (stale_after):
# a fixed 15 minutes would expire every verdict long before the next probe
# on any interval above it, leaving _connect permanently without an opinion
# on the installations that probe least often.
_HEALTH_STALE_FLOOR_SECONDS = 900

DEFAULT_PROBE_INTERVAL_SECONDS = 120
# The scheduler's own loop wakes once a minute, so anything below that is
# honoured as "every wake" rather than literally -- the floor says so
# instead of accepting a number the scheduler cannot deliver.
MIN_PROBE_INTERVAL_SECONDS = 60
MAX_PROBE_INTERVAL_SECONDS = 86400

STATE_UP = 'up'
STATE_DEGRADED = 'degraded'
STATE_DOWN = 'down'
STATE_UNKNOWN = 'unknown'


def parse_health(raw):
    """The stored ``health`` JSON -> dict, or ``{}`` for anything unusable.

    Never raises: this column is read on the enrollment path, and a row
    hand-edited into invalid JSON must degrade to "no health information"
    rather than break every lookup.
    """
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning('AD Connector: health column is not valid JSON, ignoring it')
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _age_seconds(iso_value):
    """Seconds since an ISO timestamp, or ``None`` if it can't be read."""
    if not iso_value:
        return None
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat(str(iso_value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds()


def state_of(raw_health):
    """``'up'``/``'degraded'``/``'down'``/``'unknown'`` for a stored blob."""
    health = parse_health(raw_health)
    state = health.get('state')
    return state if state in (STATE_UP, STATE_DEGRADED, STATE_DOWN) else STATE_UNKNOWN


def servers_health(raw_health):
    """``{host: {'healthy': bool, 'message': str, 'since': iso, ...}}``."""
    health = parse_health(raw_health)
    servers = health.get('servers')
    return servers if isinstance(servers, dict) else {}


def stale_after(interval=None):
    """How long a verdict stays actionable, for a connector probing every
    ``interval`` seconds.

    Two probe periods, never less than ``_HEALTH_STALE_FLOOR_SECONDS``:
    generous enough that an interval change, a slow probe or a scheduler
    that missed a tick doesn't make the connector start ignoring good data,
    and tied to the interval so a daily probe's verdict isn't expired for
    all but the first fifteen minutes of its own cycle. ``to_dict`` applies
    this same window to the stored verdict (``health_fresh``, next to
    ``health_stale_after``) so the settings badge can't disagree with what
    ``_connect`` is acting on, or with a browser clock.
    """
    try:
        interval = int(interval or DEFAULT_PROBE_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        interval = DEFAULT_PROBE_INTERVAL_SECONDS
    return max(_HEALTH_STALE_FLOOR_SECONDS, 2 * interval)


def is_fresh(raw_health, interval=None):
    """Whether the stored verdict is recent enough for ``_connect`` to act on."""
    age = _age_seconds(parse_health(raw_health).get('checked_at'))
    return age is not None and age <= stale_after(interval)


def prioritise(servers, raw_health, interval=None):
    """The configured DCs, reordered so the ones known to be up come first
    and the ones known to be down are dropped.

    Falls back to ``servers`` untouched when the stored verdict is stale,
    absent or would eliminate every candidate -- see the module docstring:
    this may thin and reorder the list, never empty it. A DC the probe has
    no opinion on (just added, never yet probed) keeps its place ahead of
    the known-bad ones rather than being treated as either.
    """
    if not servers or not is_fresh(raw_health, interval):
        return servers
    known = servers_health(raw_health)
    healthy, unknown, unhealthy = [], [], []
    for host in servers:
        entry = known.get(host)
        if entry is None or not isinstance(entry, dict) or 'healthy' not in entry:
            unknown.append(host)
        elif entry.get('healthy'):
            healthy.append(host)
        else:
            unhealthy.append(host)
    candidates = healthy + unknown
    # Every DC is currently marked down. Trusting that would turn a probe
    # failure (a UCM-side DNS blip, say) into a total enrollment outage, so
    # the original list wins and the bind decides.
    return candidates if candidates else servers


def _build_state(results, previous):
    """Probe results -> the blob to store, carrying each DC's ``since``
    forward so a DC that has been down for an hour still reports when it
    went down rather than when it was last checked."""
    now = utc_isoformat(utc_now())
    previous_servers = servers_health(previous)
    servers = {}
    for host, ok, message in results:
        was = previous_servers.get(host) or {}
        changed = was.get('healthy') is not ok
        servers[host] = {
            'healthy': ok,
            'message': message,
            'checked_at': now,
            'since': now if changed or not was.get('since') else was.get('since'),
        }
    healthy_count = sum(1 for _host, ok, _msg in results if ok)
    if not results:
        state = STATE_UNKNOWN
    elif healthy_count == len(results):
        state = STATE_UP
    elif healthy_count:
        state = STATE_DEGRADED
    else:
        state = STATE_DOWN
    return {
        'state': state,
        'checked_at': now,
        'healthy': healthy_count,
        'total': len(results),
        'servers': servers,
    }


def _log_transitions(results, previous, previous_state, new_state):
    """Warn on what changed, stay quiet on what didn't."""
    previous_servers = servers_health(previous)
    for host, ok, message in results:
        was = previous_servers.get(host) or {}
        if was.get('healthy') is ok:
            continue
        if ok:
            logger.warning('AD Connector: domain controller %s is reachable again', host)
        else:
            logger.warning(
                'AD Connector: domain controller %s is unreachable and will be '
                'skipped until it recovers: %s', host, message)
    if new_state == STATE_DOWN and previous_state != STATE_DOWN:
        # The connector as a whole is out. Error, not warning: no naked-CSR
        # subject can be derived and no Enroll ACL can be evaluated while
        # this holds, so GPO autoenrollment is failing for every client.
        logger.error(
            'AD Connector: every configured domain controller is unreachable '
            '(%s). Active Directory lookups and Kerberos autoenrollment will '
            'fail until one recovers.',
            ', '.join(host for host, _ok, _msg in results) or 'none configured')
    elif previous_state == STATE_DOWN and new_state in (STATE_UP, STATE_DEGRADED):
        logger.warning('AD Connector: recovered, at least one domain controller is reachable again')


def record(config, results):
    """Store ``[(host, ok, message), ...]`` on ``config`` as the current
    verdict, logging whatever changed. The caller commits.

    Shared by the scheduled probe and the settings page's Test Connection,
    which performs exactly the same per-DC bind: a manual test that left the
    stored health untouched would leave the badge contradicting the result
    the operator is looking at.
    """
    previous = config.health
    previous_state = state_of(previous)
    new = _build_state(results, previous)
    _log_transitions(results, previous, previous_state, new['state'])
    config.health = new
    return new


def probe(config):
    """Bind to each configured DC in turn and return
    ``[(host, ok, message), ...]``.

    ``None`` when the probe could not run at all, which is not the same as
    the empty list: ``[]`` is "there was nothing to probe", ``None`` is "the
    probe could not run, so nothing here is a verdict". The caller must keep
    ``None`` out of ``record``, or a verdict about nothing would replace the
    real one.

    Never raises: this runs on the scheduler's thread, where anything
    escaping is a failed run on every wake whatever the interval.
    """
    from services.ad_connector import lookup

    servers = lookup.config_servers(config)
    if not servers:
        return []
    # The same rule the lookups and the save apply: an anonymous bind is
    # not a connection this connector makes, so nothing is probed either.
    if not lookup.has_bind_credentials(config):
        logger.warning('AD Connector: %s', lookup.BIND_CREDENTIAL_MISSING)
        return None

    try:
        tls, cleanup = lookup._build_tls(config)
    except Exception as e:
        logger.warning('AD Connector: could not prepare the health probe: %s', e)
        return None

    results = []
    try:
        for host in servers:
            try:
                conn = lookup._connect_to(config, host, tls)
            except Exception as e:
                results.append((host, False, str(e)))
                continue
            results.append((host, True, 'Connected and bound successfully'))
            try:
                conn.unbind()
            except Exception:
                pass
    finally:
        cleanup()
    return results


def _is_due(config, previous):
    """Whether the configured period has elapsed since the last probe.

    The scheduler registers this task at its own wake cadence and the real
    period is enforced here, from the row, rather than by the interval
    passed to ``register_task``. Two reasons: only the worker holding the
    scheduler's singleton lock runs the loop, so re-registering from
    whichever web worker handled the settings save would update a copy that
    never fires; and reading the row means an interval change takes effect
    on the next wake with no restart.
    """
    interval = config.health_probe_interval or DEFAULT_PROBE_INTERVAL_SECONDS
    age = _age_seconds(parse_health(previous).get('checked_at'))
    return age is None or age >= interval


def run_health_probe():
    """The scheduled task. Probes the connector's DCs, logs what changed and
    stores the verdict.

    Returns the scheduler's outcome contract -- ``{'status': 'ok' |
    'skipped' | 'failed', 'reason': ...}``, as ``services/backup/
    schedule.py`` does (see ``scheduler_service._outcome_of``). The task is
    registered at the scheduler's own one-minute cadence and does nothing on
    most wakes, so reporting that as a successful run would fill the admin
    view with green runs that never touched a domain controller, and would
    count a probe that failed among them.

    Never raises -- a probe that blows up must not take the scheduler's
    whole loop with it, and must not leave a stale verdict looking fresh.
    """
    from models import ADConnectorConfig
    from services.ad_connector import lookup
    from utils.db_transaction import safe_commit

    config = ADConnectorConfig.get_singleton()
    if config is None or not config.enabled or not config.server:
        return {'status': 'skipped', 'reason': 'not configured or disabled'}
    # A skip, not a warning: the scheduler wakes every minute, and the fix
    # for this is in the settings dialog, not in the log.
    if not lookup.has_bind_credentials(config):
        return {'status': 'skipped', 'reason': 'bind credentials missing'}

    previous = config.health
    previous_state = state_of(previous)

    if not _is_due(config, previous):
        return {'status': 'skipped', 'reason': 'not due yet', 'state': previous_state}

    try:
        results = probe(config)
    except Exception as e:
        # Not logged here: the scheduler logs a failed run, and probe has
        # already said whatever it could not do.
        return {'status': 'failed', 'reason': str(e)}
    if results is None:
        # The probe could not run. Recording that would store a verdict about
        # nothing over the real one, losing every DC's `since` with it, and
        # would count a green run that never touched a domain controller.
        return {'status': 'failed', 'reason': 'the probe could not run'}

    new = record(config, results)
    ok, _err = safe_commit(logger, 'Failed to store AD Connector health')
    if not ok:
        # safe_commit has already rolled back, so nothing was stored: the
        # verdict in hand is not the one _connect will read, and reporting
        # it as this run's result would claim a probe that did not land.
        return {'status': 'failed', 'reason': 'could not store the health verdict'}
    return {
        'status': 'ok',
        'state': new['state'],
        'healthy': new['healthy'],
        'total': new['total'],
    }
