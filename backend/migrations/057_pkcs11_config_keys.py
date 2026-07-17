"""Migration 057: normalize legacy PKCS#11 HSM provider config keys.

``auto_register_softhsm`` stored ``library_path`` and ``pin`` while
``PKCS11Provider`` expects ``module_path`` and ``user_pin``, breaking
SoftHSM-Default test connection on existing installs.
"""

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _rewrite_config(config_str: str):
    from utils.pkcs11_config import (
        normalize_pkcs11_config,
        pkcs11_config_needs_normalization,
    )

    try:
        cfg = json.loads(config_str or '{}')
    except (json.JSONDecodeError, TypeError):
        return config_str, False
    if not isinstance(cfg, dict) or not pkcs11_config_needs_normalization(cfg):
        return config_str, False
    return json.dumps(normalize_pkcs11_config(cfg)), True


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='hsm_providers'"
    )
    if not cur.fetchone():
        logger.info("[057] hsm_providers absent, skipping")
        return

    rows = conn.execute(
        "SELECT id, config FROM hsm_providers WHERE type = 'pkcs11'"
    ).fetchall()
    rewritten = 0
    for pid, config_str in rows:
        new_config, changed = _rewrite_config(config_str)
        if changed:
            conn.execute(
                "UPDATE hsm_providers SET config = ? WHERE id = ?",
                (new_config, pid),
            )
            rewritten += 1
    if rewritten:
        logger.info(
            "[057] normalized PKCS#11 config keys for %s provider(s) (SQLite)",
            rewritten,
        )


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'hsm_providers' not in set(insp.get_table_names()):
        logger.info("[057] hsm_providers absent, skipping")
        return

    rows = conn.execute(text(
        "SELECT id, config FROM hsm_providers WHERE type = 'pkcs11'"
    )).fetchall()
    rewritten = 0
    for row in rows:
        pid, config_str = row[0], row[1]
        new_config, changed = _rewrite_config(config_str)
        if changed:
            conn.execute(
                text("UPDATE hsm_providers SET config = :cfg WHERE id = :id"),
                {'cfg': new_config, 'id': pid},
            )
            rewritten += 1
    if rewritten:
        logger.info(
            "[057] normalized PKCS#11 config keys for %s provider(s) (PG)",
            rewritten,
        )


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
        return
    _upgrade_pg(conn)


def downgrade(conn):
    pass
