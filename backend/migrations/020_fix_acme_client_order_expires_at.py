"""
Migration 020: Fix AcmeClientOrder.expires_at for issued orders (issue #74)

Background
----------
RFC 8555 §7.1.3 says the ACME order resource's ``expires`` field is the
expiry of the *order resource itself*, NOT the issued certificate's
``notAfter``. Let's Encrypt sets this to ~7 days.

Prior to v2.128, ``acme_client_service.finalize_order`` left
``order.expires_at`` at that 7-day value even after the certificate was
issued. ``acme_renewal_service.scheduled_acme_renewal`` then compares
``expires_at <= now + 30 days`` and concludes the cert needs renewal —
forever. This causes a renewal storm and trips the LE production rate
limits (`see issue #74 <https://github.com/NeySlim/ultimate-ca-manager/issues/74>`_).

This migration backfills ``expires_at`` on every issued order to the
linked certificate's actual ``not_after`` so the renewal scheduler stops
re-issuing them.

Multi-backend convention (v2.128+)
----------------------------------
This is the first migration that runs on **both** SQLite and PostgreSQL.
It declares ``pg_compatible = True`` so the runner invokes it on PG, and
exposes an ``upgrade(arg)`` that accepts either:
  * ``sqlite3.Connection`` — when running against SQLite (legacy path)
  * ``sqlalchemy.Engine``   — when running against PostgreSQL

Migrations 000-019 are SQLite-only by design (they predate PG support);
the runner silently marks them applied on PG installs because fresh PG
installs use ``SQLAlchemy.create_all()`` and don't need the historical
schema deltas.
"""
import sqlite3

pg_compatible = True


_BACKFILL_SQL = """
UPDATE acme_client_orders
SET expires_at = (
    SELECT certificates.not_after
    FROM certificates
    WHERE certificates.id = acme_client_orders.certificate_id
)
WHERE acme_client_orders.status = 'issued'
  AND acme_client_orders.certificate_id IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM certificates
      WHERE certificates.id = acme_client_orders.certificate_id
        AND certificates.not_after IS NOT NULL
  )
"""


def _upgrade_sqlite(conn):
    cursor = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name IN ('acme_client_orders', 'certificates')"
    )
    tables = {row[0] for row in cursor.fetchall()}
    if 'acme_client_orders' not in tables or 'certificates' not in tables:
        return
    conn.execute(_BACKFILL_SQL)
    conn.commit()


def _upgrade_pg(engine):
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    if 'acme_client_orders' not in existing or 'certificates' not in existing:
        return
    with engine.begin() as conn:
        conn.execute(text(_BACKFILL_SQL))


def upgrade(arg):
    """Dispatch to SQLite or PostgreSQL backend based on argument type."""
    if isinstance(arg, sqlite3.Connection):
        _upgrade_sqlite(arg)
    else:
        _upgrade_pg(arg)


def downgrade(arg):
    """No-op — we won't restore the broken 7-day window."""
    pass
