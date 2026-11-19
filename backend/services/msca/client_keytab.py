"""The client keytab of a Kerberos Microsoft CA connection.

MIT krb5 reads KRB5_CLIENT_KTNAME when the initiator credential is acquired:
inside requests-kerberos ``generate_request_header`` (``spnego.client`` then
``ctx.step``), during the HTTP exchange. The variable is process-wide, so it
names one connection's keytab only while that connection holds the lock.
"""
import os
import threading
from contextlib import contextmanager

ENV = 'KRB5_CLIENT_KTNAME'
_FILE_TYPES = ('FILE', 'WRFILE')
# gevent patches threading under gunicorn: a greenlet waits here, it does not block the hub
_LOCK = threading.RLock()


def managed_keytab_error(path):
    """Why ``path`` cannot be a client keytab, or None.
    A file of UCM's data folder (the acceptor keytab among them) is never one."""
    if not path or not str(path).strip():
        return None
    value = str(path).strip()
    kind, sep, rest = value.partition(':')
    if sep and kind.upper() in _FILE_TYPES:
        value = rest
    elif sep and not os.path.isabs(value):
        return 'kerberos_keytab_path must be a keytab file path'
    from config.settings import DATA_DIR
    resolved = os.path.realpath(value)
    data_dir = os.path.realpath(str(DATA_DIR))
    if os.path.commonpath([resolved, data_dir]) == data_dir:
        return 'kerberos_keytab_path must not point inside the UCM data folder'
    return None


@contextmanager
def client_keytab(path):
    """KRB5_CLIENT_KTNAME is ``path`` inside the block and what it was before outside it."""
    error = managed_keytab_error(path)
    if error:
        raise ValueError(error)
    with _LOCK:
        before = os.environ.get(ENV)
        if path:
            os.environ[ENV] = path
        try:
            yield
        finally:
            if before is None:
                os.environ.pop(ENV, None)
            else:
                os.environ[ENV] = before
