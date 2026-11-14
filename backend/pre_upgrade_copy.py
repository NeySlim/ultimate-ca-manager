"""The copy of a SQLite database that the runner takes before migration 300 rewrites it.

The upgrade from 2.254 is one way: its first step only starts once a copy, taken through
SQLite's online backup API and checked, sits next to the database. PostgreSQL gets none.
"""
import os
import shutil
import sqlite3
from pathlib import Path

# Beside the database: same volume and owner, outside BACKUP_DIR, and a name that neither the
# archive listing (.ucmbkp, .json.enc), its retention, nor the Docker `ucm-backup-*.db` sweep matches
COPY_SUFFIX = ".2.254-before-3.0"
PARTIAL_SUFFIX = ".partial"
# Headroom over the database size: the backup's own journal and filesystem rounding
MARGIN_BYTES = 8 * 1024 * 1024

PG_NOTE = ("PostgreSQL: no automatic copy is taken before the upgrade from 2.254; "
           "take a pg_dump first (UPGRADE.md, Upgrading to v3.0)")


class CopyFailed(Exception):
    """The copy could not be taken or verified: the upgrade must not start."""


def copy_path(db_path) -> Path:
    db_path = Path(db_path)
    return db_path.with_name(db_path.name + COPY_SUFFIX)


def _mb(size: int) -> str:
    return f"{max(size, 0) / (1024 * 1024):.1f} MB"


def _size(conn) -> int:
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    return page_count * page_size


def required_bytes(db_path) -> int:
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    try:
        return _size(conn) + MARGIN_BYTES
    finally:
        conn.close()


def plan(db_path) -> str:
    """What a start will copy, for dry-run and status."""
    target = copy_path(Path(db_path).resolve())
    try:
        need = _mb(required_bytes(db_path))
    except sqlite3.Error:
        need = "unknown size"
    return f"a copy of the 2.254 database is taken first: {target} (needs {need} free)"


def _counts(conn) -> dict:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def _registry(conn) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM _migrations")}


def _integrity(conn) -> str:
    return "; ".join(r[0] for r in conn.execute("PRAGMA integrity_check"))


def _verify(path: Path, counts: dict, registry: set) -> None:
    from migration_runner import UPGRADE_MIGRATION, pivot_refusal
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        integrity = _integrity(conn)
        if integrity != "ok":
            raise CopyFailed(f"integrity check of the copy: {integrity}")
        copied = _registry(conn)
        if copied != registry or UPGRADE_MIGRATION in copied or pivot_refusal("tracked", copied):
            raise CopyFailed("the copy does not hold the 2.254 migration registry")
        if _counts(conn) != counts:
            raise CopyFailed("the copy does not hold the same rows as the database")
    finally:
        conn.close()


def _discard(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _create_private(path: Path, owner) -> None:
    """An empty file, 0600 from its creation, owned like the database when root runs this."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            os.fchown(fd, owner.st_uid, owner.st_gid)
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _fsync(path: Path, directory: bool = False) -> None:
    fd = os.open(path, os.O_RDONLY | (getattr(os, "O_DIRECTORY", 0) if directory else 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def take(db_path) -> Path:
    """Copy *db_path* next to itself and verify the copy, or raise CopyFailed.

    Written under a fixed temporary name then renamed: a retry replaces the previous copy,
    and an existing copy is only replaced by one that passed verification.
    """
    source_path = Path(db_path).resolve()
    target = copy_path(source_path)
    partial = target.with_name(target.name + PARTIAL_SUFFIX)
    directory = target.parent
    need = 0
    try:
        source = sqlite3.connect(str(source_path))
        try:
            source.isolation_level = None
            # One read transaction: the counts and the backup see the same database
            source.execute("BEGIN")
            need = _size(source) + MARGIN_BYTES
            free = shutil.disk_usage(directory).free
            if free < need:
                raise CopyFailed(f"{_mb(free)} available")
            counts, registry = _counts(source), _registry(source)
            _discard(partial)
            _create_private(partial, os.stat(source_path))
            dest = sqlite3.connect(str(partial))
            try:
                source.backup(dest)
            finally:
                dest.close()
            source.execute("COMMIT")
        finally:
            source.close()
        _verify(partial, counts, registry)
        _fsync(partial)
        os.replace(partial, target)
        _fsync(directory, directory=True)
    except (CopyFailed, OSError, sqlite3.Error) as exc:
        try:
            _discard(partial)
        except OSError:
            pass
        raise CopyFailed(
            f"Upgrade not started: the copy of the 2.254 database could not be taken ({exc}). "
            f"It needs {_mb(need) if need else 'the size of the database plus ' + _mb(MARGIN_BYTES)} "
            f"free in {directory}, written as {target.name}. Nothing was changed.") from exc
    return target
