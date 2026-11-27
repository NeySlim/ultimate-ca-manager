"""Per-name lock around the read-merge-write of a DNS-01 TXT record."""
import hashlib
import logging
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

from config.settings import Config
from utils.process_lock import LockBusyError, process_lock

logger = logging.getLogger(__name__)

LOCK_WAIT_SECONDS = 120
_ADVISORY_NAMESPACE = b'ucm-acme-dns-txt:'


def advisory_key(record_name) -> int:
    """The PostgreSQL advisory lock key of a TXT name, the same on every node."""
    digest = hashlib.sha256(_ADVISORY_NAMESPACE + record_name.lower().encode()).digest()
    return int.from_bytes(digest[:8], 'big', signed=True)


def _cluster_wide():
    from models import db
    from utils.ha import ha_enabled
    return ha_enabled() and db.engine.dialect.name == 'postgresql'


@contextmanager
def _advisory_lock(record_name):
    """A session advisory lock on a connection outside the pool, polled up to the wait.
    The session ends with the lock, and the server drops it within a minute if this node vanishes."""
    from sqlalchemy import text
    from services.scheduler_leader import _SERVER_TIMEOUTS_SQL, _dedicated_engine, application_url
    key = advisory_key(record_name)
    engine = _dedicated_engine(application_url())
    conn = engine.connect().execution_options(isolation_level='AUTOCOMMIT')
    held = False
    try:
        conn.execute(_SERVER_TIMEOUTS_SQL)
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while not held:
            held = bool(conn.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': key}).scalar())
            if held or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        if not held:
            logger.warning("DNS TXT %s still locked by another node after %ss, writing without the lock",
                           record_name, LOCK_WAIT_SECONDS)
        yield
    finally:
        if held:
            try:
                conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})
            except Exception:
                pass  # closing this session, outside any pool, frees it
        conn.close()
        engine.dispose()


@contextmanager
def txt_record_lock(record_name):
    """Serialise writes to one TXT name across workers, and across nodes in HA;
    past the wait, go on unprotected rather than abandon the challenge."""
    if _cluster_wide():
        # DATA_DIR is per node in HA: only the shared database serialises two nodes
        with _advisory_lock(record_name):
            yield
        return
    digest = hashlib.sha256(record_name.lower().encode()).hexdigest()[:16]
    with ExitStack() as stack:
        try:
            stack.enter_context(process_lock(
                Path(Config.DATA_DIR) / f'.acme_dns_txt-{digest}.lock', timeout=LOCK_WAIT_SECONDS,
                purpose='publishing a dns-01 TXT record', subject='DNS TXT update'))
        except LockBusyError:
            logger.warning("DNS TXT %s still locked after %ss, writing without the lock",
                           record_name, LOCK_WAIT_SECONDS)
        yield
