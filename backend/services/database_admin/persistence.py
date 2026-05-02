"""
Database Admin — persist DATABASE_URL to /etc/ucm/ucm.env.
"""

import os
import logging
from typing import Optional, Tuple

from config.settings import is_docker

from .helpers import UCM_ENV_PATH

logger = logging.getLogger(__name__)


def persist_database_url(database_url: Optional[str]) -> Tuple[bool, str]:
    """
    Write DATABASE_URL to /etc/ucm/ucm.env (set/update/remove).
    Pass None or empty string to remove (= use SQLite default).
    Refuses in Docker (caller must check first).
    """
    if is_docker():
        return False, "Cannot modify ucm.env in Docker. Set DATABASE_URL env var instead."

    try:
        UCM_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = UCM_ENV_PATH.read_text() if UCM_ENV_PATH.exists() else ""

        lines = [ln for ln in existing.splitlines() if not ln.startswith("DATABASE_URL=") and not ln.startswith("#DATABASE_URL=")]

        if database_url:
            lines.append(f"DATABASE_URL={database_url}")

        new_content = "\n".join(lines).rstrip() + "\n"
        UCM_ENV_PATH.write_text(new_content)
        os.chmod(UCM_ENV_PATH, 0o640)
        return True, "DATABASE_URL persisted"
    except PermissionError as e:
        return False, f"Permission denied writing {UCM_ENV_PATH}: {e}"
    except Exception as e:
        logger.error(f"persist_database_url failed: {e}")
        return False, f"Failed to persist DATABASE_URL: {e}"
