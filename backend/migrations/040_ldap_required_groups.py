"""Migration 040: add ldap_required_groups to SSOProvider.

Allow LDAP/SSO providers to require users to belong to at least one
specified group before granting access (default-deny by group).

Also adds account_status_attr for detecting disabled accounts across
LDAP vendors (AD: userAccountControl, OpenLDAP: accountStatus).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    cur = conn.execute("PRAGMA table_info(pro_sso_providers)")
    existing = {row[1] for row in cur.fetchall()}
    if 'ldap_required_groups' not in existing:
        conn.execute(
            "ALTER TABLE pro_sso_providers ADD COLUMN ldap_required_groups TEXT"
        )
        logger.info("[040] added ldap_required_groups (SQLite)")
    if 'account_status_attr' not in existing:
        conn.execute(
            "ALTER TABLE pro_sso_providers ADD COLUMN account_status_attr TEXT"
        )
        logger.info("[040] added account_status_attr (SQLite)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    cols = {c['name'] for c in insp.get_columns('pro_sso_providers')}

    if 'ldap_required_groups' not in cols:
        conn.execute(text("ALTER TABLE pro_sso_providers ADD COLUMN ldap_required_groups TEXT"))
        logger.info("[040] added ldap_required_groups (PostgreSQL)")

    if 'account_status_attr' not in cols:
        conn.execute(text("ALTER TABLE pro_sso_providers ADD COLUMN account_status_attr TEXT"))
        logger.info("[040] added account_status_attr (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        cur = conn.execute("PRAGMA table_info(pro_sso_providers)")
        existing = {row[1] for row in cur.fetchall()}
        if 'ldap_required_groups' in existing:
            conn.execute("ALTER TABLE pro_sso_providers DROP COLUMN ldap_required_groups")
        if 'account_status_attr' in existing:
            conn.execute("ALTER TABLE pro_sso_providers DROP COLUMN account_status_attr")
        conn.commit()
    else:
        from sqlalchemy import inspect, text
        insp = inspect(conn)
        cols = {c['name'] for c in insp.get_columns('pro_sso_providers')}
        if 'ldap_required_groups' in cols:
            conn.execute(text("ALTER TABLE pro_sso_providers DROP COLUMN ldap_required_groups"))
        if 'account_status_attr' in cols:
            conn.execute(text("ALTER TABLE pro_sso_providers DROP COLUMN account_status_attr"))
