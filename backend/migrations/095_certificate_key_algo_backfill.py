"""Migration 095: recompute certificates.key_algo from each certificate.

Issuance left it empty (only imports, renewals and the TSA signer wrote it)
and older versions wrote other spellings ("RSA", "ECDSA", "EdDSA"), so sorting
by key algorithm or compliance grade misplaced them. New rows fill it from crt.
"""

import sqlite3

pg_compatible = True

_SELECT = "SELECT id, crt, key_algo FROM certificates WHERE crt IS NOT NULL AND crt <> ''"


def _labels(rows):
    import base64
    from cryptography import x509
    from utils.key_algorithms import key_algo_for_public_key
    for row_id, crt, current in rows:
        try:
            cert = x509.load_pem_x509_certificate(base64.b64decode(crt))
        except Exception:
            continue  # unreadable rows keep their value
        label = key_algo_for_public_key(cert.public_key())
        if label != current:
            yield label, row_id


def _upgrade_sqlite(conn):
    rows = conn.execute(_SELECT).fetchall()
    conn.executemany("UPDATE certificates SET key_algo = ? WHERE id = ?", list(_labels(rows)))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import text

    rows = conn.execute(text(_SELECT)).fetchall()
    for label, row_id in _labels(rows):
        conn.execute(text("UPDATE certificates SET key_algo = :label WHERE id = :id"),
                     {'label': label, 'id': row_id})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: the values are derived from crt and harmless to older versions.
    pass
