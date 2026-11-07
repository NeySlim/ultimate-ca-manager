"""Multipart uploads spooled under DATA_DIR/tmp rather than the system temp dir.

The system temp dir may be a small or memory-backed tmpfs; DATA_DIR is the
persistent volume every install already writes to.
"""
import logging
import os
import tempfile
from pathlib import Path

from flask import Request, current_app

logger = logging.getLogger(__name__)

# Werkzeug's own threshold: smaller files stay in memory.
SPOOL_IN_MEMORY_BYTES = 500 * 1024


def prepare_spool_dir(data_dir):
    """Create `DATA_DIR/tmp` (0700) and return it, or None (logged) if it is unusable."""
    path = Path(data_dir) / 'tmp'
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as exc:
        logger.warning("Uploads spool to the system temp dir: %s is not usable (%s)",
                       path, exc)
        return None
    return os.path.realpath(path)


class SpoolingRequest(Request):
    """Spools each uploaded file above 500 KiB to an anonymous file in the configured directory."""

    def _get_file_stream(self, total_content_length, content_type,
                         filename=None, content_length=None):
        spool = current_app.config.get('UPLOAD_SPOOL_DIR')
        if spool:
            # Recreated if removed while running; this request falls back otherwise
            try:
                os.makedirs(spool, 0o700, exist_ok=True)
            except OSError:
                spool = None
        return tempfile.SpooledTemporaryFile(
            max_size=SPOOL_IN_MEMORY_BYTES, mode='rb+', dir=spool)
