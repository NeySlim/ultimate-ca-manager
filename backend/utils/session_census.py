"""How many live server-side sessions an account holds at one session version.

Reads the store the application uses (files, SQL table or Redis); None when the
store cannot be listed, so a caller never reports a count it did not see.
"""
import logging
from datetime import datetime, timezone

from flask import current_app

logger = logging.getLogger(__name__)


def count_sessions(user_id, version):
    """Sessions of ``user_id`` (signed in or waiting on a second factor) still at ``version``,
    and not already ended by the application's lifetime or inactivity limits."""
    from auth.unified import AuthManager
    from utils.datetime_utils import utc_now
    iface = current_app.session_interface
    serializer = getattr(iface, 'serializer', None)
    if serializer is None:
        return None
    try:
        blobs = _stored_blobs(iface)
        if blobs is None:
            return None
        count = 0
        now, limits = utc_now(), AuthManager.session_limits()
        for blob in blobs:
            try:
                # The file store keeps the dict itself, the others its encoding
                data = blob if isinstance(blob, dict) else serializer.decode(blob)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            owner = data.get('user_id', data.get('pending_2fa_user_id'))
            if (owner == user_id and (data.get('session_version') or 0) == version
                    and not AuthManager.session_ended(data, now, limits=limits, log=False)):
                count += 1
        return count
    except Exception as exc:
        logger.warning("Could not count the sessions of user %s: %s", user_id, exc)
        return None


def _stored_blobs(iface):
    """Every live entry as the store keeps it, or None for a store not listed here."""
    prefix = getattr(iface, 'key_prefix', '')
    model = getattr(iface, 'sql_session_model', None)
    if model is not None:
        store = iface._store() if hasattr(iface, '_store') else None
        session = store if store is not None else iface.client.session
        now = datetime.now(timezone.utc).replace(tzinfo=None)  # the store's naive UTC
        try:
            rows = session.query(model.data).filter(
                model.session_id.startswith(prefix), model.expiry > now).all()
        finally:
            if store is not None:
                store.close()
        return [bytes(row.data) for row in rows if row.data is not None]
    from cachelib.file import FileSystemCache
    cache = getattr(iface, 'cache', None) or getattr(iface, 'client', None)
    if isinstance(cache, FileSystemCache):
        return list(_file_entries(cache))
    redis_scan = getattr(cache, 'scan_iter', None)
    if redis_scan is not None:
        return [blob for blob in (cache.get(key) for key in redis_scan(match=f'{prefix}*'))
                if blob]
    return None


def _file_entries(cache):
    """Each unexpired value of a cachelib file cache, read as its own get() reads it."""
    import struct
    import time
    now = time.time()
    for name in cache._list_dir():
        try:
            with open(name, 'rb') as f:
                expires = struct.unpack('I', f.read(4))[0]
                if expires != 0 and expires < now:
                    continue
                yield cache.serializer.load(f)
        except (OSError, EOFError, struct.error):
            continue
