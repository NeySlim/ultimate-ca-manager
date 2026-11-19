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
# gevent patches threading under gunicorn: a greenlet waits here, it does not block the hub
_LOCK = threading.RLock()


@contextmanager
def client_keytab(path):
    """KRB5_CLIENT_KTNAME is ``path`` inside the block and what it was before outside it."""
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
