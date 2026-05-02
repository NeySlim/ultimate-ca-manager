"""
2FA backup codes — hashed storage and atomic consume.

Backup codes were historically stored in clear text (comma-separated
or JSON list) in `users.backup_codes`. Anyone with read access to the
DB or a backup could replay them as a 2FA bypass. They are also one
of the two paths a "recovery code double-spend" race could go through:
two parallel logins observe the same plaintext, both pass the
membership check, both delete it.

This module:

  * stores codes as a JSON list of werkzeug scrypt hashes;
  * verifies by iterating hashes with werkzeug.check_password_hash;
  * consumes atomically via an UPDATE...WHERE backup_codes = <old>
    optimistic-lock — the loser of the race observes rowcount == 0
    and is rejected.

The legacy plaintext format (",X-Y-Z,A-B-C,..." or JSON list of
plaintext strings) is still recognised on read so that 2FA users who
provisioned codes before this change keep working until they
regenerate.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional, Tuple

from sqlalchemy import update
from werkzeug.security import check_password_hash, generate_password_hash

from models import User, db

logger = logging.getLogger(__name__)

# Marker prefix that identifies the new hashed-list format. werkzeug
# password hashes start with "scrypt:", "pbkdf2:" or similar, so a
# JSON list whose first element starts with one of these is the new
# format.
_HASH_PREFIXES = ('scrypt:', 'pbkdf2:', 'argon2:')


def hash_codes(codes: List[str]) -> str:
    """Return the JSON-encoded blob to store in user.backup_codes."""
    return json.dumps([generate_password_hash(c, method='scrypt') for c in codes])


def _load_entries(blob: Optional[str]) -> Tuple[List[str], bool]:
    """
    Parse a stored backup_codes blob.

    Returns (entries, is_hashed). `entries` is a list of strings —
    each entry is either a werkzeug hash (when is_hashed=True) or a
    plaintext code (legacy format).
    """
    if not blob:
        return [], False
    blob = blob.strip()
    # Try JSON first
    if blob.startswith('['):
        try:
            data = json.loads(blob)
            if isinstance(data, list) and data:
                first = str(data[0])
                hashed = first.startswith(_HASH_PREFIXES)
                return [str(x) for x in data], hashed
            return [], False
        except (json.JSONDecodeError, ValueError):
            pass
    # Legacy comma-separated plaintext
    return [c for c in blob.split(',') if c], False


def count_remaining(blob: Optional[str]) -> int:
    entries, _ = _load_entries(blob)
    return len(entries)


def verify_code_only(blob: Optional[str], code: str) -> bool:
    """
    Constant-time-ish membership check WITHOUT consuming the code.
    Used for the 2FA-disable path, which then clears all codes anyway.
    """
    entries, hashed = _load_entries(blob)
    code = str(code).strip()
    if not code:
        return False
    if hashed:
        return any(check_password_hash(h, code) for h in entries)
    return code in entries


def consume_code(user: User, code: str) -> bool:
    """
    Atomically verify-and-consume a single backup code for `user`.

    Returns True iff the code matched AND we won the optimistic-lock
    race (i.e. nobody else consumed the same code concurrently).

    Caller is responsible for committing the transaction.
    """
    code = str(code).strip()
    if not code:
        return False

    # Re-fetch the current value to minimise the race window.
    current_blob = user.backup_codes
    entries, hashed = _load_entries(current_blob)
    if not entries:
        return False

    matched_index = -1
    if hashed:
        for i, h in enumerate(entries):
            try:
                if check_password_hash(h, code):
                    matched_index = i
                    break
            except Exception:
                continue
    else:
        for i, plain in enumerate(entries):
            if plain == code:
                matched_index = i
                break

    if matched_index < 0:
        return False

    remaining = entries[:matched_index] + entries[matched_index + 1:]
    new_blob = json.dumps(remaining) if remaining else json.dumps([])

    # Optimistic lock: only update if backup_codes still equals what
    # we just verified. The loser of any concurrent double-spend sees
    # rowcount == 0 and is rejected.
    result = db.session.execute(
        update(User)
        .where(User.id == user.id)
        .where(User.backup_codes == current_blob)
        .values(backup_codes=new_blob)
    )

    if result.rowcount != 1:
        # Lost the race. Refresh in-memory state so the caller sees
        # the up-to-date value.
        try:
            db.session.rollback()
        except Exception:
            pass
        db.session.refresh(user)
        logger.info("backup code consume: optimistic lock lost for user_id=%s", user.id)
        return False

    # Sync the in-memory ORM object so the rest of the request sees
    # the new blob.
    user.backup_codes = new_blob
    return True
