"""Migration 029: encrypt ACME private keys stored in system_config.

Historically the ACME client account key (``acme.client.<env>.account_key``)
and the server-side ACME account key (``acme.account.<id>.private_key``)
were written as raw PEM into ``system_config.value``. They are now passed
through ``security.encryption.encrypt_private_key()`` on write.

This migration walks the existing rows once and rewrites any plain PEM
to the encrypted form. If encryption is disabled (no master.key, no
KEY_ENCRYPTION_KEY env var), ``encrypt_private_key`` is a no-op so this
migration is also a no-op — the rows just stay readable as before.

Idempotent: ``encrypt_private_key`` already detects the ENC: marker and
returns the input unchanged, so re-running this migration is safe.
"""

import logging

logger = logging.getLogger(__name__)


def upgrade(conn):
    try:
        from security.encryption import encrypt_private_key, key_encryption
    except Exception as e:  # pragma: no cover — encryption module missing
        logger.warning(f"029: cannot import security.encryption ({e}); skipping")
        return

    if not getattr(key_encryption, 'is_enabled', False):
        logger.info("029: encryption disabled, leaving ACME keys as-is")
        return

    cur = conn.execute(
        "SELECT key, value FROM system_config "
        "WHERE key LIKE 'acme.client.%.account_key' "
        "   OR key LIKE 'acme.account.%.private_key'"
    )
    rows = cur.fetchall()

    rewritten = 0
    for row in rows:
        # Row may be a tuple or a Row object depending on DB driver
        key = row[0] if not hasattr(row, 'keys') else row['key']
        value = row[1] if not hasattr(row, 'keys') else row['value']
        if not value:
            continue
        new_value = encrypt_private_key(value)
        if new_value != value:
            conn.execute(
                "UPDATE system_config SET value = ? WHERE key = ?",
                (new_value, key),
            )
            rewritten += 1

    conn.commit()
    if rewritten:
        logger.info(f"029: encrypted {rewritten} ACME private key(s) at rest")


def downgrade(conn):
    # Best effort: decrypt back to plain PEM so old code can read them.
    try:
        from security.encryption import decrypt_private_key, key_encryption
    except Exception:
        return
    if not getattr(key_encryption, 'is_enabled', False):
        return

    cur = conn.execute(
        "SELECT key, value FROM system_config "
        "WHERE key LIKE 'acme.client.%.account_key' "
        "   OR key LIKE 'acme.account.%.private_key'"
    )
    for row in cur.fetchall():
        key = row[0] if not hasattr(row, 'keys') else row['key']
        value = row[1] if not hasattr(row, 'keys') else row['value']
        if not value:
            continue
        try:
            plain = decrypt_private_key(value)
        except Exception:
            continue
        if plain != value:
            conn.execute(
                "UPDATE system_config SET value = ? WHERE key = ?",
                (plain, key),
            )
    conn.commit()
