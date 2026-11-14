"""Which database an archive was taken from, so its row numbers are compared only there.

A random id in `system_config`, never exported as a setting nor overwritten by a restore.
"""
import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from models import db

from security.master_key_bootstrap import OPT_OUT_KEY
from security.session_key import ALL_KEYS as SESSION_KEY_SETTINGS
from services.scheduler_service import STATE_KEY as SCHEDULER_STATE_KEY
from auth.initial_admin import MARKER_KEY as INITIAL_PASSWORD_MARKER_KEY
from utils.serial_duplicates import PENDING_KEY

from .errors import BackupExportError

logger = logging.getLogger(__name__)

CONFIG_KEY = 'backup_installation_id'
METADATA_KEY = 'installation_id'
# Settings about this installation or cluster itself (scheduler state, the pending
# serial index of the upgrade from 2.254, the scheduled backup's reservation and conclusion,
# services/backup/schedule.py, the expiry webhooks mark, the scheduled passes' leases, the
# session key that signs this installation's tokens, the node holding the generated
# initial password): never exported, never restored
LOCAL_SETTINGS = frozenset((CONFIG_KEY, OPT_OUT_KEY, SCHEDULER_STATE_KEY, PENDING_KEY,
                            'backup.last_run', 'backup.concluded_run',
                            'expiry_alerts.webhooks_mark', 'expiry_alerts.lease',
                            INITIAL_PASSWORD_MARKER_KEY)
                           + SESSION_KEY_SETTINGS)
LOCAL_SETTING_PREFIXES = ('crl_schedule_lease_',)


def is_local_setting(key) -> bool:
    return key in LOCAL_SETTINGS or str(key).startswith(LOCAL_SETTING_PREFIXES)


def installation_id(create: bool = False) -> Optional[str]:
    """This database's id; created on first use when `create` is set."""
    from models import SystemConfig

    row = SystemConfig.query.filter_by(key=CONFIG_KEY).first()
    if row is not None and row.value:
        return row.value
    if not create:
        return None
    value = uuid.uuid4().hex
    try:
        if row is None:
            db.session.add(SystemConfig(key=CONFIG_KEY, value=value,
                                        description='Identifies this database in its backups'))
        else:
            row.value = value
        db.session.commit()
    except IntegrityError:
        # Another export created it first: that one is the id
        db.session.rollback()
        row = SystemConfig.query.filter_by(key=CONFIG_KEY).first()
        return row.value if row is not None else None
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error("Could not store the backup installation id: %s", type(exc).__name__)
        raise BackupExportError(
            "Could not record this installation's identifier, which every archive "
            "carries; check that the database accepts writes") from exc
    return value


def same_installation(backup_data: Dict[str, Any]) -> bool:
    """Whether the archive was taken from this very database."""
    metadata = backup_data.get('metadata')
    carried = metadata.get(METADATA_KEY) if isinstance(metadata, dict) else None
    if not isinstance(carried, str) or not carried:
        return False
    return carried == installation_id()
