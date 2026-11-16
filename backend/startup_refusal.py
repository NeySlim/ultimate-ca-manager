"""A database this release will not start on stops the service with its own exit code.

78 is EX_CONFIG (sysexits.h): the systemd unit lists it in RestartPreventExitStatus, as
restarting cannot change the database. Importable before the application and its settings.
"""
EXIT_CODE = 78


class DatabaseRefused(RuntimeError):
    """Refused or not migrated at startup: the cause is in the migration log above."""


def migrate_or_refuse(lock) -> None:
    """The encoding first, on a bare driver connection: every SQLAlchemy connection after it
    (the HA restore wait, the startup lock, the migrations) fails on a SQL_ASCII database."""
    from migration_runner import _get_db_url, run_at_startup, startup_encoding_refusal
    refusal = startup_encoding_refusal()
    if refusal:
        raise DatabaseRefused(refusal)
    from utils.ha import ha_enabled
    if ha_enabled():
        # A restore that has not committed holds the cluster: no migration or write before it ends
        from services.cluster_maintenance import wait_while_restoring
        wait_while_restoring(_get_db_url())
    if not run_at_startup(lock):
        raise DatabaseRefused(
            "Schema migration failed or the database was refused at startup. "
            "Refusing to start with an inconsistent database. Check the migration "
            "log above and fix the issue before restarting the service."
        )
