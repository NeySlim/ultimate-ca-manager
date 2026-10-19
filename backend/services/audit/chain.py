"""Audit hash chain: sealing and verification.

Entries are sealed with HMAC-SHA256 under a key derived from the master key,
so rewriting the ledger takes that key and not only the database. Without a
master key they are sealed with SHA-256, which anyone can recompute, and the
verification says so.
"""
import hmac as _hmac
import logging

from models import db, AuditLog
from security.encryption import key_encryption

logger = logging.getLogger(__name__)

GENESIS = '0' * 64
SHA256_CHAIN = 1
KEYED_CHAIN = 2
_KEY_LABEL = b'ucm audit chain v2'


def chain_key():
    """(key, key id) sealing the chain, or None without a master key."""
    key = key_encryption.derive_key(_KEY_LABEL)
    if key is None:
        return None
    return key, _hmac.digest(key, b'ucm audit chain key id', 'sha256').hex()[:16]


def _sealed_under(entry, key_id) -> bool:
    return (entry is not None and entry.hash_version == KEYED_CHAIN
            and entry.hash_key_id == key_id)


def seal(entry):
    """Link a flushed entry to the one before it and seal it. The caller commits."""
    previous = (AuditLog.query.filter(AuditLog.id < entry.id)
                .order_by(AuditLog.id.desc()).first())
    prev_hash = previous.entry_hash if previous and previous.entry_hash else GENESIS
    key = chain_key()
    entry.prev_hash = prev_hash
    if key is None:
        entry.hash_version = SHA256_CHAIN
        entry.hash_key_id = None
        entry.entry_hash = entry.compute_hash(prev_hash)
        return entry
    entry.hash_version = KEYED_CHAIN
    entry.hash_key_id = key[1]
    if entry.chain_start is None and not _sealed_under(previous, key[1]):
        # First entry under this key: it records where the ledger starts, so
        # a prefix deleted later outside a purge is seen.
        entry.chain_start = db.session.query(db.func.min(AuditLog.id)).scalar()
    entry.entry_hash = entry.compute_hash(prev_hash, key[0])
    return entry


def verify_chain(logs, whole_table: bool) -> dict:
    """Walk `logs` (ascending ids) and say what the chain attests.

    status: 'broken' (first_error_id names the entry), 'unprotected' (no
    master key, or entries after the key took over that it does not seal),
    or 'intact' (every entry from protected_from_id on is bound by the key).
    `valid` means no entry fails its check; unsealed rows are listed, not failed.
    """
    key = chain_key()
    key_bytes, key_id = key if key else (None, None)

    errors, unsealed, retired = [], [], []
    keyed_ok = {}      # id -> sealed under the current key and verified
    recomputable = {}  # id -> SHA-256 entry that verified
    prev_hash = (logs[0].prev_hash or GENESIS) if logs else GENESIS

    for log in logs:
        if not log.entry_hash:
            unsealed.append(log.id)
            prev_hash = GENESIS
            continue

        if log.prev_hash and log.prev_hash != prev_hash:
            errors.append({'id': log.id, 'error': 'prev_hash mismatch',
                           'expected': prev_hash, 'actual': log.prev_hash})

        version = log.hash_version or SHA256_CHAIN
        if version == SHA256_CHAIN:
            computed = log.compute_hash(log.prev_hash)
            if _hmac.compare_digest(computed, log.entry_hash):
                recomputable[log.id] = True
            else:
                errors.append({'id': log.id, 'error': 'entry_hash mismatch (tampered)',
                               'expected': computed, 'actual': log.entry_hash})
        elif version == KEYED_CHAIN:
            if key_id is not None and log.hash_key_id == key_id:
                computed = log.compute_hash(log.prev_hash, key_bytes)
                if _hmac.compare_digest(computed, log.entry_hash):
                    keyed_ok[log.id] = True
                else:
                    # The expected seal is not returned: it is a valid MAC.
                    errors.append({'id': log.id, 'error': 'entry_hash mismatch (tampered)'})
            else:
                retired.append(log.id)
        else:
            errors.append({'id': log.id, 'error': f'unknown hash version {version}'})

        prev_hash = log.entry_hash

    # Bound entries: sealed under the key, or recomputable and covered by a
    # later keyed seal. A SHA-256 entry after the first keyed one was written
    # without the key, or rewritten without it: never counted as bound.
    first_keyed = next((log.id for log in logs if log.id in keyed_ok), None)
    bound = set()
    binding = False
    for log in reversed(logs):
        if log.id in keyed_ok:
            binding = True
            bound.add(log.id)
        elif log.id in recomputable:
            if binding and first_keyed is not None and log.id < first_keyed:
                bound.add(log.id)
        else:
            binding = False

    if whole_table and logs:
        _check_chain_start(logs, bound, first_keyed is not None, errors)

    unbound = [log.id for log in logs if log.id not in bound]
    after_key = [i for i in unbound if first_keyed is not None and i > first_keyed]
    if errors:
        status = 'broken'
    elif key_id is None or after_key or (logs and first_keyed is None):
        status = 'unprotected'
    else:
        status = 'intact'

    errors.sort(key=lambda e: e['id'])
    protected_from = min(bound) if bound and not after_key else None
    return {
        'valid': not errors,
        'status': status,
        'first_error_id': errors[0]['id'] if errors else None,
        'checked': len(logs),
        'attested': len(logs) - len(unsealed),
        'unsealed': unsealed,
        'errors': errors,
        'protection': {
            'key_available': key_id is not None,
            'protected': len(bound),
            'protected_from_id': protected_from,
            'unprotected_after_key': after_key[:100],
            'not_attested': len(unbound),
            'retired_key': len(retired),
        },
    }


def _check_chain_start(logs, bound, keyed, errors):
    """The first entry is where the ledger began, or where a sealed record says it now begins.

    Once an entry verifies under the current key, only records it binds count.
    """
    first = logs[0]
    starts = [log.chain_start for log in logs
              if log.chain_start is not None and log.entry_hash
              and (log.id in bound or not keyed)
              and not any(e['id'] == log.id for e in errors)]
    if starts:
        if first.id > max(starts):
            errors.append({'id': first.id,
                           'error': f'entries before #{first.id} were removed outside a purge'})
    elif first.hash_version == KEYED_CHAIN and (first.prev_hash or GENESIS) != GENESIS:
        errors.append({'id': first.id,
                       'error': f'entries before #{first.id} were removed outside a purge'})
