"""The integration secrets under the database key (utils.encryption): which ones a key
cannot open, and their re-encryption from one key to another.

The columns are the backup manifest's secrets, the authority services/database_admin/
verify.py also reads, plus every setting row. Only Fernet tokens of that layer are
touched: a value under the key-encryption key ('ENC:') or in the clear is left as it is.
Nothing here logs or returns a value, encrypted or not: only labels and counts.
"""
import importlib
import json
import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class RewrapRefused(Exception):
    """Secrets neither key opens; nothing was written. Carries their labels."""

    def __init__(self, labels):
        self.labels = list(labels)
        super().__init__('these secrets open under neither key, nothing was re-encrypted: '
                         + ', '.join(self.labels))


@dataclass
class StoredSecret:
    label: str
    table: object       # sqlalchemy Table
    pk: object          # primary key Column
    row_id: object
    column: object      # the stored Column
    stored: str
    fields: bool        # a JSON object whose sensitive values are each a token


def _columns():
    """(section label, table, primary key, column, fields) for every column of a secret
    the manifest does not name as under the key-encryption key."""
    from sqlalchemy import inspect
    from services.backup.manifest import SECTIONS
    for name, section in SECTIONS.items():
        if not section.secrets:
            continue
        module, _, cls = section.model.partition(':')
        table = inspect(getattr(importlib.import_module(module), cls)).local_table
        pk = list(table.primary_key.columns)[0]
        for secret in section.secrets:
            layer = section.stored.get(secret)
            if layer == 'master':
                continue
            column = table.c.get(secret)
            column = column if column is not None else table.c.get(f'_{secret}')
            if column is None:
                raise RuntimeError(f'{name}.{secret} is not a column of {table.name}')
            yield name, table, pk, column, layer == 'fields'
    from models import SystemConfig
    table = SystemConfig.__table__
    yield 'system_config', table, table.c.key, table.c.value, False


def secret_values() -> List[StoredSecret]:
    """Every stored value of those columns that holds at least one database-key token."""
    from models import db
    from utils.encryption import is_encrypted
    found = []
    for name, table, pk, column, fields in _columns():
        rows = db.session.execute(
            db.select(pk, column).where(column.isnot(None), column != '')).all()
        for row_id, stored in rows:
            if not isinstance(stored, str):
                continue
            if fields:
                if not _field_tokens(stored):
                    continue
            elif not is_encrypted(stored):
                continue
            found.append(StoredSecret(f'{name} {row_id} {column.name}', table, pk, row_id,
                                      column, stored, fields))
    return found


def _field_tokens(stored: str) -> dict:
    from models.hsm import _is_sensitive_key
    from utils.encryption import is_encrypted
    try:
        parsed = json.loads(stored)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {k: v for k, v in parsed.items()
            if _is_sensitive_key(k) and isinstance(v, str) and is_encrypted(v)}


def _tokens(secret: StoredSecret) -> List[str]:
    return list(_field_tokens(secret.stored).values()) if secret.fields else [secret.stored]


def _opens(fernet: Fernet, token: str) -> bool:
    try:
        fernet.decrypt(token.encode())
        return True
    except InvalidToken:
        return False


def unreadable_secrets(key: Optional[bytes] = None) -> List[str]:
    """Labels of the secrets `key` (default: this node's key) does not open."""
    from utils.encryption import get_cipher
    fernet = Fernet(key) if key else get_cipher()
    return [s.label for s in secret_values() if not all(_opens(fernet, t) for t in _tokens(s))]


def _reencrypt(token: str, target: Fernet, sources: List[Fernet]) -> Optional[str]:
    """The token under `target`; itself when already there; None when no key opens it."""
    if _opens(target, token):
        return token
    for source in sources:
        try:
            plain = source.decrypt(token.encode())
        except InvalidToken:
            continue
        return target.encrypt(plain).decode()
    return None


def rewrap(source_keys: Iterable[bytes], target_key: bytes, dry_run: bool = False) -> dict:
    """Every database-key secret re-encrypted under `target_key`, from one of `source_keys`.

    Idempotent: a value already under the target is skipped. A value no key opens stops
    the run before anything is written, naming it. One transaction; each UPDATE matches the
    value read, so a value changed meanwhile is never overwritten (the run is refused).
    """
    from models import db
    target = Fernet(target_key)
    sources = [Fernet(k) for k in source_keys]
    planned, unreadable, already = [], [], 0
    for secret in secret_values():
        if secret.fields:
            fields = json.loads(secret.stored)
            changed = False
            for name, token in _field_tokens(secret.stored).items():
                new = _reencrypt(token, target, sources)
                if new is None:
                    unreadable.append(f'{secret.label}.{name}')
                elif new != token:
                    fields[name], changed = new, True
            new_value = json.dumps(fields) if changed else secret.stored
        else:
            new_value = _reencrypt(secret.stored, target, sources)
            if new_value is None:
                unreadable.append(secret.label)
                continue
        if new_value == secret.stored:
            already += 1
        else:
            planned.append((secret, new_value))
    if unreadable:
        db.session.rollback()
        raise RewrapRefused(unreadable)
    if dry_run:
        db.session.rollback()
        return {'rewritten': 0, 'to_rewrite': len(planned), 'already': already}
    try:
        for secret, new_value in planned:
            result = db.session.execute(
                secret.table.update().where(secret.pk == secret.row_id)
                .where(secret.column == secret.stored).values({secret.column.name: new_value}))
            if result.rowcount != 1:
                raise RuntimeError(f'{secret.label} changed during the run, run it again')
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    logger.info('Database key: %d integration secret(s) re-encrypted, %d already under the key',
                len(planned), already)
    return {'rewritten': len(planned), 'to_rewrite': 0, 'already': already}


def report_unreadable_at_start() -> List[str]:
    """HA start: the secrets the shared key does not open, logged by label. Never raises."""
    try:
        labels = unreadable_secrets()
    except Exception as e:
        from models import db
        db.session.rollback()
        logger.error(f'Integration secrets not checked at start: {type(e).__name__}: {e}')
        return []
    if labels:
        logger.error(
            '%d integration secret(s) do not decrypt with UCM_DB_ENCRYPTION_KEY and their '
            'integrations will fail until they are re-encrypted (python -m scripts.rewrap_db_key, '
            'see docs/HA.md) or entered again: %s', len(labels), ', '.join(labels))
    return labels
