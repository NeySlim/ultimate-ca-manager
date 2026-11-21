"""
SSH CAs package — shared Blueprint and logger.
"""

import logging
import re
from flask import Blueprint

bp = Blueprint('ssh_cas_v2', __name__)
logger = logging.getLogger(__name__)


def ssh_download_stem(descr):
    """*descr* with ASCII punctuation and spaces as '_'; non-ASCII is kept for content_disposition()."""
    return re.sub(r'[^\w.\-\x80-\U0010FFFF]', '_', descr or '')
