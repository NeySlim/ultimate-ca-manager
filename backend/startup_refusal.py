"""A database this release will not start on stops the service with its own exit code.

78 is EX_CONFIG (sysexits.h): the systemd unit lists it in RestartPreventExitStatus, as
restarting cannot change the database. Importable before the application and its settings.
"""
EXIT_CODE = 78


class DatabaseRefused(RuntimeError):
    """Refused or not migrated at startup: the cause is in the migration log above."""


def migrate_or_refuse(lock) -> None:
    from migration_runner import run_at_startup
    if not run_at_startup(lock):
        raise DatabaseRefused(
            "Schema migration failed or the database was refused at startup. "
            "Refusing to start with an inconsistent database. Check the migration "
            "log above and fix the issue before restarting the service."
        )
