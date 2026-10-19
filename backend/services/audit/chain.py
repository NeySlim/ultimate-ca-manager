"""Audit hash chain: sealing and verification.

Entries are sealed with HMAC-SHA256 under a key derived from the master key,
so rewriting the ledger takes that key and not only the database. Without a
master key they are sealed with SHA-256, which anyone can recompute, and the
verification says so.
"""
import hmac as _hmac
import json
import logging
import os
import tempfile

from sqlalchemy import event, func, text
from sqlalchemy.orm import Session

from models import db, AuditLog
from security import encryption as _encryption
from security.encryption import key_encryption

logger = logging.getLogger(__name__)

GENESIS = '0' * 64
SHA256_CHAIN = 1
KEYED_CHAIN = 2
_KEY_LABEL = b'ucm audit chain v2'
_APPEND_LOCK = 0x75636D61756469  # PostgreSQL advisory lock id for appends
_ERROR_LIST_CAP = 1000
KEYRING_NAME = 'audit-chain.keys'
_PENDING_KEYRING = 'ucm_audit_keyring'


def chain_key():
    """(key, key id) sealing the chain, or None without a master key."""
    key = key_encryption.derive_key(_KEY_LABEL)
    if key is None:
        return None
    return key, _hmac.digest(key, b'ucm audit chain key id', 'sha256').hex()[:16]


def keyring_path():
    """The ids of the keys this instance sealed with, kept beside the master key, outside the database."""
    return _encryption.MASTER_KEY_PATH.parent / KEYRING_NAME


def read_keyring():
    """{'current': key id, 'history': [key ids]}, or None when there is none."""
    path = keyring_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and isinstance(data.get('history'), list):
            return data
    except (OSError, ValueError) as e:
        logger.error(f"Unreadable {path}: {e}")
        return None
    logger.error(f"Malformed {path}; key rotations are not attested until it is rewritten")
    return None


def _write_keyring(data):
    path = keyring_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # A file of its own (mkstemp: 0600), on disk before it replaces the old one
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.audit-chain.', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(data, handle)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                import pwd
                ucm = pwd.getpwnam('ucm')
                os.chown(tmp, ucm.pw_uid, ucm.pw_gid)
            except (KeyError, OSError):
                pass
            os.replace(tmp, path)
        except OSError:
            os.unlink(tmp)
            raise
    except OSError as e:
        logger.error(f"Could not write {path}: {e}; the next key change will not be attested")


@event.listens_for(Session, 'after_commit')
def _keyring_after_commit(session):
    # Written once the entry that relies on it is committed, never before
    data = session.info.pop(_PENDING_KEYRING, None)
    if data is not None:
        _write_keyring(data)


@event.listens_for(Session, 'after_rollback')
def _keyring_after_rollback(session):
    session.info.pop(_PENDING_KEYRING, None)


def _reconcile_keyring(session, ring, key_id):
    """Make `key_id` the current key of the history once this transaction commits.

    Also run on an entry that is not the first under its key: a history that
    is missing or names another key (older build, recreated volume, file
    restored) is brought up to date, the previous current key kept in it.
    """
    if ring is not None and ring.get('current') == key_id:
        return
    history = list((ring or {}).get('history', []))
    current = (ring or {}).get('current')
    if current and current not in history:
        history.append(current)
    history = [k for k in history if k != key_id] + [key_id]
    session.info[_PENDING_KEYRING] = {'current': key_id, 'history': history}


def _rotation(session, entry, key_id, ring):
    """What the first entry under `key_id` says about the other keys in the ledger.

    A rotation is attested only when the key history outside the database
    shows the key changed, and only for keys in that history. Without a
    history (new host, restored elsewhere) the other keys are listed as not
    attested, which the verification reports.
    """
    in_ledger = dict(session.query(AuditLog.hash_key_id, func.max(AuditLog.id))
                     .filter(AuditLog.hash_version == KEYED_CHAIN,
                             AuditLog.hash_key_id != key_id, AuditLog.id < entry.id)
                     .group_by(AuditLog.hash_key_id).all())
    if ring is None:
        rotation = {'attested': False, 'keys': in_ledger} if in_ledger else None
    elif ring.get('current') != key_id:
        known = set(ring['history'])
        keys = {k: last for k, last in in_ledger.items() if k in known}
        rotation = {'attested': True, 'keys': keys} if keys else None
    else:
        rotation = None     # same key as before: nothing was rotated
    return json.dumps(rotation, sort_keys=True) if rotation else None


def append_entry(entry, session=None, purge_from=None):
    """Add `entry` to the chain and seal it. The caller commits.

    `purge_from` marks a purge record: it names the first id kept from there.
    """
    session = session or db.session
    # Two writers reading the same predecessor would fork the chain. SQLite
    # serialises writers already; PostgreSQL holds this until the commit.
    if session.get_bind().dialect.name == 'postgresql':
        session.scalar(text('SELECT pg_advisory_xact_lock(:k)'), {'k': _APPEND_LOCK})
    session.add(entry)
    session.flush()

    previous = (session.query(AuditLog).filter(AuditLog.id < entry.id)
                .order_by(AuditLog.id.desc()).first())
    prev_hash = previous.entry_hash if previous and previous.entry_hash else GENESIS
    entry.prev_hash = prev_hash
    if purge_from is not None:
        entry.chain_start = session.query(func.min(AuditLog.id)).filter(
            AuditLog.id >= purge_from).scalar()

    key = chain_key()
    if key is None:
        entry.hash_version = SHA256_CHAIN
        entry.hash_key_id = None
        entry.entry_hash = entry.compute_hash(prev_hash)
        return entry

    entry.hash_version = KEYED_CHAIN
    entry.hash_key_id = key[1]
    ring = read_keyring()
    if not (previous is not None and previous.hash_version == KEYED_CHAIN
            and previous.hash_key_id == key[1]):
        # First entry under this key: it records where the ledger starts and
        # what it attests of the other keys in it.
        if entry.chain_start is None:
            entry.chain_start = session.query(func.min(AuditLog.id)).scalar()
        entry.retired_keys = _rotation(session, entry, key[1], ring)
    _reconcile_keyring(session, ring, key[1])
    entry.entry_hash = entry.compute_hash(prev_hash, key[0])
    return entry


class _Walk:
    """State of one verification pass, fed one entry at a time."""

    def __init__(self, key):
        self.key_bytes, self.key_id = key if key else (None, None)
        self.errors, self.error_count, self.first_error = [], 0, None
        self.unsealed = []
        self.checked = 0
        self.first = None
        self.prev_hash = None
        self.first_keyed = None
        self.rotation, self.rotation_attested = {}, False   # from the first keyed entry
        self.errors_at_first_keyed = 0
        self.run_start, self.run_index = None, 0
        self.protected_from, self.not_attested = None, 0
        self.retired = {}           # key id -> [first id, last id] before the first keyed entry
        self.retired_count = 0
        self.keyed_start = None     # chain_start of entries verified under the key
        self.keyed_min_start = None
        self.any_start = None

    def error(self, entry_id, code, message, **extra):
        self.error_count += 1
        if self.first_error is None or entry_id < self.first_error[0]:
            self.first_error = (entry_id, code)
        if len(self.errors) < _ERROR_LIST_CAP:
            self.errors.append({'id': entry_id, 'code': code, 'error': message, **extra})

    def feed(self, log):
        index = self.checked
        self.checked += 1
        if self.first is None:
            self.first = (log.id, log.hash_version, log.prev_hash or GENESIS)
            self.prev_hash = log.prev_hash or GENESIS
        after_key = self.first_keyed is not None

        if not log.entry_hash:
            self.unsealed.append(log.id)
            self.prev_hash = GENESIS
            if after_key:
                self.error(log.id, 'not_sealed_by_key', 'entry not sealed by the master key')
            self.run_start = None
            return

        errors_before = self.error_count
        if log.prev_hash and log.prev_hash != self.prev_hash:
            self.error(log.id, 'link', 'prev_hash mismatch',
                       expected=self.prev_hash, actual=log.prev_hash)

        version = log.hash_version or SHA256_CHAIN
        keyed_ok = recomputable = False
        if version == SHA256_CHAIN:
            computed = log.compute_hash(log.prev_hash)
            if _hmac.compare_digest(computed, log.entry_hash):
                recomputable = True
            else:
                self.error(log.id, 'tampered', 'entry_hash mismatch (tampered)',
                           expected=computed, actual=log.entry_hash)
        elif version == KEYED_CHAIN:
            if self.key_id is not None and log.hash_key_id == self.key_id:
                computed = log.compute_hash(log.prev_hash, self.key_bytes)
                if _hmac.compare_digest(computed, log.entry_hash):
                    keyed_ok = True
                else:
                    # The expected seal is not returned: it is a valid MAC.
                    self.error(log.id, 'tampered', 'entry_hash mismatch (tampered)')
            else:
                self.retired_count += 1
                if self.key_id is not None and not after_key:
                    span = self.retired.setdefault(log.hash_key_id, [log.id, log.id])
                    span[1] = log.id
        else:
            self.error(log.id, 'unknown_version', f'unknown hash version {version}')
        self.prev_hash = log.entry_hash

        if log.chain_start is not None and self.error_count == errors_before:
            self.any_start = max(self.any_start or log.chain_start, log.chain_start)
            if keyed_ok:
                self.keyed_start = max(self.keyed_start or log.chain_start, log.chain_start)
                self.keyed_min_start = min(self.keyed_min_start or log.chain_start,
                                           log.chain_start)

        if after_key:
            if not keyed_ok and self.error_count == errors_before:
                self.error(log.id, 'not_sealed_by_key', 'entry not sealed by the master key')
            return
        if keyed_ok:
            # Recomputable entries just before the first keyed one are bound by it
            self.first_keyed = log.id
            if self.run_start is None:
                self.run_start, self.run_index = log.id, index
            self.protected_from, self.not_attested = self.run_start, self.run_index
            rotation = json.loads(log.retired_keys) if log.retired_keys else {}
            self.rotation = rotation.get('keys') or {}
            self.rotation_attested = bool(rotation.get('attested'))
            self.errors_at_first_keyed = self.error_count
        elif recomputable:
            if self.run_start is None:
                self.run_start, self.run_index = log.id, index
        else:
            self.run_start = None

    def finish(self, whole_table, upper_id):
        # A first keyed entry that fails explains what follows from it
        if (self.key_id is not None and self.first_keyed is not None
                and not self.errors_at_first_keyed):
            self._check_retired(upper_id)
        if whole_table and self.first is not None:
            self._check_chain_start()

        if self.error_count:
            status = 'broken'
        elif (self.key_id is None or (self.checked and self.first_keyed is None)
              or (self.retired and not self.rotation_attested)):
            # The last case: other keys this server has no record of rotating from
            status = 'unprotected'
        else:
            status = 'intact'
        self.errors.sort(key=lambda e: e['id'])
        intact_from = self.protected_from if self.first_keyed is not None else None
        not_attested = self.not_attested if intact_from is not None else self.checked
        return {
            'valid': not self.error_count,
            'status': status,
            'first_error_id': self.first_error[0] if self.first_error else None,
            'first_error_code': self.first_error[1] if self.first_error else None,
            'checked': self.checked,
            'attested': self.checked - len(self.unsealed),
            'unsealed': self.unsealed,
            'error_count': self.error_count,
            'errors': self.errors,
            'protection': {
                'key_available': self.key_id is not None,
                'protected': self.checked - not_attested,
                'protected_from_id': intact_from,
                'not_attested': not_attested,
                'retired_key': self.retired_count,
                'key_rotation_id': self.first_keyed if self.rotation else None,
                'rotation_attested': self.rotation_attested if self.rotation else None,
            },
        }

    def _check_retired(self, upper_id):
        """Entries under another key pass only up to the last id the rotation attested."""
        for key_id, (first_id, last_id) in self.retired.items():
            limit = self.rotation.get(key_id)
            if limit is not None and last_id <= limit:
                continue
            offender = first_id if limit is None else (
                db.session.query(func.min(AuditLog.id))
                .filter(AuditLog.hash_key_id == key_id, AuditLog.id > limit,
                        AuditLog.id <= upper_id).scalar())
            self.error(offender, 'unattested_key',
                       'entry under a key no rotation of the current key attests')

    def _check_chain_start(self):
        """The first entry is where the ledger began, or where a sealed record says it now begins."""
        first_id, first_version, first_prev = self.first
        message = f'entries before #{first_id} were removed outside a purge'
        if self.first_keyed is not None:
            # Under the key, only records it seals say where the ledger starts;
            # none left intact is a break unless another error already explains it.
            if self.keyed_start is None:
                if not self.error_count:
                    self.error(first_id, 'truncated', message)
            elif first_id > self.keyed_start:
                self.error(first_id, 'truncated', message)
            elif first_id < self.keyed_min_start and first_id != self.first_keyed:
                # Below the first id the key ever recorded: added since
                self.error(first_id, 'before_start',
                           f'entry #{first_id} precedes where the ledger started')
        elif self.any_start is not None:
            if first_id > self.any_start:
                self.error(first_id, 'truncated', message)
        elif first_version == KEYED_CHAIN and first_prev != GENESIS:
            self.error(first_id, 'truncated', message)


def verify_chain(logs, whole_table: bool) -> dict:
    """Walk `logs` (ascending ids, any iterable) once and say what the chain attests.

    status: 'broken' (first_error_id names the entry), 'unprotected' (no
    master key, or no entry sealed under it yet) or 'intact' (every entry from
    protected_from_id on is bound by the key). `valid` means no entry fails
    its check; unsealed rows before the key took over are listed, not failed.
    """
    walk = _Walk(chain_key())
    last_id = None
    for log in logs:
        walk.feed(log)
        last_id = log.id
    return walk.finish(whole_table, last_id)
