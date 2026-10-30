"""Per-name lock around the read-merge-write of a DNS-01 TXT record."""
import hashlib
import logging
from contextlib import ExitStack, contextmanager
from pathlib import Path

from config.settings import Config
from utils.process_lock import LockBusyError, process_lock

logger = logging.getLogger(__name__)


@contextmanager
def txt_record_lock(record_name):
    """Serialise writes to one TXT name across workers; past the wait, go on
    unprotected rather than abandon the challenge."""
    digest = hashlib.sha256(record_name.lower().encode()).hexdigest()[:16]
    with ExitStack() as stack:
        try:
            stack.enter_context(process_lock(
                Path(Config.DATA_DIR) / f'.acme_dns_txt-{digest}.lock', timeout=120,
                purpose='publishing a dns-01 TXT record', subject='DNS TXT update'))
        except LockBusyError:
            logger.warning("DNS TXT %s still locked after 120s, writing without the lock", record_name)
        yield
