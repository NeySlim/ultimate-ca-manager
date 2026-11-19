"""Who may read and cancel the restore job while its SQLite transaction holds the database.

No request can read the database then, so the worker answers from what it checked earlier:
each credential that passed require_auth against the database while this restore's gate was up
(the session or API key, its permissions, the host it came on). Writes are refused from the
moment this worker saw the gate, so no revocation can commit after that check and before the
restore commits; a check made before the gate went up is never used. Anything else, unchecked
or unknown, answers 503 with Retry-After; a request with no credential at all, 401.
"""
import hashlib
import threading
import types

from flask import g, request, session

MAX_ENTRIES = 4096
# One account's checks push out its own oldest ones first, never another account's
MAX_PER_USER = 32
# The restore job's own routes, served from its local state while the database is held
HELD_ENDPOINTS = frozenset({'system_v2.get_job', 'system_v2.cancel_job'})
_FINGERPRINT = ('user_id', 'session_version', 'restore_epoch', 'account_created', 'login_time')

_lock = threading.Lock()
_entries = {}
_gate = [None]


def _gate_key(view):
    state = getattr(view, 'local_state', None) if view is not None else None
    if not state or not view.active():
        return None
    return state.get('job_id'), state.get('started_at')


def _credential():
    """('api_key', hash) for a presented key, ('session', id) for a signed-in session, else None."""
    from auth.unified import presented_api_key
    key = presented_api_key(request)
    if key:
        return 'api_key', hashlib.sha256(key.encode()).hexdigest()
    sid = getattr(session, 'sid', None)
    if sid and session.get('user_id'):
        return 'session', sid
    return None


def _fingerprint():
    return tuple(session.get(name) for name in _FINGERPRINT)


def _current_view():
    from services import cluster_maintenance
    view = cluster_maintenance.current(refresh=False)
    if view is None or (view.row or {}).get('reason') != cluster_maintenance.LOCAL_REASON:
        return None
    return view


def _entries_for(gate):
    if _gate[0] != gate:
        _entries.clear()
        _gate[0] = gate
    return _entries


def remember(auth_result):
    """require_auth, once every check passed against the database during this restore's gate."""
    from utils.sqlite_wait import window
    if window() != 'gate' or not request.path.startswith('/api/'):
        return
    gate, key = _gate_key(_current_view()), _credential()
    if gate is None or key is None:
        return
    entry = {'gate': gate, 'host': request.host, 'user_id': auth_result['user_id'],
             'username': getattr(auth_result.get('user'), 'username', None),
             'force_password_change': bool(getattr(auth_result.get('user'),
                                                   'force_password_change', False)),
             'auth_method': auth_result['auth_method'],
             'permissions': list(auth_result['permissions'] or []),
             'api_key_id': auth_result.get('api_key_id'),
             'expires_at': auth_result.get('api_key_expires_at')}
    if key[0] == 'session':
        from auth.unified import AuthManager
        entry['fingerprint'] = _fingerprint()
        entry['limits'] = AuthManager.session_limits()
    with _lock:
        entries = _entries_for(gate)
        entries.pop(key, None)
        _make_room(entries, entry['user_id'])
        entries[key] = entry


def _make_room(entries, user_id):
    """Under _lock: the account's oldest check past its share; when full, the oldest check of
    the account holding the most."""
    own = [k for k, e in entries.items() if e['user_id'] == user_id]
    if len(own) >= MAX_PER_USER:
        entries.pop(own[0])
    elif len(entries) >= MAX_ENTRIES:
        counts = {}
        for e in entries.values():
            counts[e['user_id']] = counts.get(e['user_id'], 0) + 1
        largest = max(counts, key=counts.get)
        entries.pop(next(k for k, e in entries.items() if e['user_id'] == largest))


def forget():
    """A credential the database refused during the gate is never answered from memory."""
    key = _credential()
    if key is None:
        return
    with _lock:
        _entries.pop(key, None)


def _checked(view):
    """The credential's earlier check for this gate: an entry, None (no credential) or False."""
    key = _credential()
    if key is None:
        return None
    gate = _gate_key(view)
    with _lock:
        entry = _entries_for(gate).get(key)
    # Only a check made during this very gate counts, the memory emptied or not
    if entry is None or entry['gate'] != gate or entry['host'] != request.host:
        return False
    # A key that expired since its check is refused as the database would refuse it
    if entry['expires_at'] is not None:
        from utils.datetime_utils import utc_now
        if entry['expires_at'] < utc_now():
            return None
    if key[0] == 'session':
        if entry['fingerprint'] != _fingerprint():
            return False
        from auth.unified import AuthManager
        from utils.datetime_utils import utc_now
        now = utc_now()
        if AuthManager.session_ended(session, now, limits=entry['limits'], log=False):
            session.clear()
            return None
        session['last_activity'] = now.isoformat()
    return entry


def _serve_job(view):
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    from services import cluster_maintenance
    from utils.response import AUTHENTICATION_REQUIRED_PROBLEM, error_response
    from middleware.public_host_middleware import untrusted_forwarded_host_refusal
    refused = untrusted_forwarded_host_refusal()
    if refused is not None:
        return refused
    entry = _checked(view)
    if entry is None:
        return error_response('Authentication required', 401,
                              problem_type=AUTHENTICATION_REQUIRED_PROBLEM)
    if entry is False or entry['force_password_change'] or session.get(ENROLL_SESSION_KEY):
        return cluster_maintenance.refusal(view, message=cluster_maintenance.HELD_MESSAGE)
    g.current_user = types.SimpleNamespace(id=entry['user_id'], username=entry['username'])
    g.auth_method = entry['auth_method']
    g.permissions = entry['permissions']
    g.user_id = entry['user_id']
    g.api_key_id = entry['api_key_id']
    from api.v2.system import jobs as routes
    job_id = (request.view_args or {}).get('job_id')
    if request.endpoint == 'system_v2.cancel_job':
        if entry['auth_method'] == 'session':
            from security.csrf import check_request
            refused = check_request()
            if refused is not None:
                return refused
        return routes.held_cancel(job_id, view)
    return routes.held_read(job_id, view)


def answer_without_database():
    """The restore job's read or cancellation when the database stayed locked before the
    transaction was marked as holding it (the restore's own writes): as while it holds it."""
    from flask import has_request_context
    if not has_request_context() or request.endpoint not in HELD_ENDPOINTS:
        return None
    view = _current_view()
    return None if view is None else _serve_job(view)


def before_request():
    """While the restore's transaction holds the SQLite database: health and the restore job
    are answered without it, OCSP says tryLater (RFC 6960 §2.3), anything else 503 at once."""
    from utils.ha import ha_enabled
    if ha_enabled():
        return None
    from services import cluster_maintenance
    from utils.public_endpoints import PROBE_PATHS, is_public_protocol_path
    view = cluster_maintenance.current(refresh=True)
    if view is None or not cluster_maintenance.held_locally(view):
        return None
    if request.path in PROBE_PATHS or request.blueprint in cluster_maintenance.OPEN_BLUEPRINTS:
        return None
    if request.endpoint in HELD_ENDPOINTS:
        return _serve_job(view)
    if request.blueprint in cluster_maintenance.READ_BLUEPRINTS:
        from api.ocsp_routes import try_later_response
        return try_later_response()
    if not request.path.startswith('/api/') and not is_public_protocol_path(request.path):
        return None  # the interface's files; a hook that reads the database answers 503 itself
    return cluster_maintenance.refusal(view, message=cluster_maintenance.HELD_MESSAGE)
