"""
SSH CAs package — shared Blueprint and logger.
"""

import logging
from flask import Blueprint

bp = Blueprint('ssh_cas_v2', __name__)
logger = logging.getLogger(__name__)
