"""The copy of a SQLite database that the runner takes before migration 300 rewrites it.

The upgrade from 2.254 is one way: its first step only starts once a copy, taken through
SQLite's online backup API and checked, sits next to the database. PostgreSQL gets none.

Invariant: the copy is always the image of a database the upgrade had not touched yet. The
runner writes a marker table into the database once the copy is verified and before the first
step; the copy never holds it, and the transaction that records migration 300 drops it.
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

# A table rather than a system_config key: 2.254 exports and restores every setting, never an unknown table
MARKER_TABLE = "_upgrade_from_2_254_started"

FRESH, KEPT, NONE = "fresh", "kept", "none"

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


def _started(conn) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (MARKER_TABLE,)).fetchone() is not None


def _valid_copy(target: Path) -> bool:
    """Opens, passes the integrity check, and holds a 2.254 registry the pivot accepts."""
    from migration_runner import UPGRADE_MIGRATION, pivot_refusal
    if not target.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        try:
            if _integrity(conn) != "ok":
                return False
            names = _registry(conn)
            return UPGRADE_MIGRATION not in names and pivot_refusal("tracked", names) is None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def situation(db_path) -> str:
    """FRESH: no marker, the database is 2.254 and is copied. KEPT: the upgrade started and a
    valid copy exists. NONE: the upgrade started and no valid copy exists. Writes nothing."""
    source_path = Path(db_path).resolve()
    conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        started = _started(conn)
    finally:
        conn.close()
    if not started:
        return FRESH
    return KEPT if _valid_copy(copy_path(source_path)) else NONE


def _none_note(target: Path) -> str:
    what = "is not a valid 2.254 copy" if target.exists() else "is missing"
    return (f"no copy of the 2.254 database exists ({target} {what}): an earlier start already "
            f"began the upgrade, so the database is no longer the 2.254 one and is not copied; "
            f"the upgrade resumes")


def plan(db_path) -> str:
    """What a start will do about the copy, for dry-run and status."""
    target = copy_path(Path(db_path).resolve())
    try:
        case = situation(db_path)
    except sqlite3.Error:
        case = FRESH
    if case == KEPT:
        return f"the upgrade resumes with the copy taken by an earlier start: {target}"
    if case == NONE:
        return _none_note(target)
    try:
        need = _mb(required_bytes(db_path))
    except sqlite3.Error:
        need = "unknown size"
    replacing = ", replacing the one there" if target.exists() else ""
    return f"a copy of the 2.254 database is taken first{replacing}: {target} (needs {need} free)"


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
    and an existing copy is only replaced by one that passed verification. Called only on a
    database without the marker (situation FRESH).
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


def mark_started(db_path) -> None:
    """The marker, committed on its own: from now on the database is no longer copied."""
    conn = sqlite3.connect(str(Path(db_path).resolve()))
    try:
        with conn:
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{MARKER_TABLE}" (started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
            conn.execute(f'INSERT INTO "{MARKER_TABLE}" DEFAULT VALUES')
    finally:
        conn.close()


def clear_started(conn) -> None:
    """Drops the marker inside the caller's open transaction, the one that records migration 300."""
    if not conn.in_transaction:
        conn.execute("BEGIN")
    conn.execute(f'DROP TABLE IF EXISTS "{MARKER_TABLE}"')


def prepare(db_path) -> str:
    """Applies the decision table before migration 300; returns the line for the journal.

    Raises CopyFailed when a copy is due and cannot be taken, or the marker cannot be set."""
    try:
        case = situation(db_path)
    except sqlite3.Error as exc:
        raise CopyFailed(f"Upgrade not started: the database could not be read ({exc}). "
                         f"Nothing was changed.") from exc
    target = copy_path(Path(db_path).resolve())
    if case == KEPT:
        return f"→ kept the copy taken by an earlier start: {target}"
    if case == NONE:
        return f"! {_none_note(target)}"
    target = take(db_path)
    try:
        mark_started(db_path)
    except (OSError, sqlite3.Error) as exc:
        raise CopyFailed(f"Upgrade not started: the copy {target} was taken but the database could "
                         f"not record that the upgrade starts ({exc}). Nothing was changed.") from exc
    return f"→ copied the 2.254 database before the upgrade: {target}"
