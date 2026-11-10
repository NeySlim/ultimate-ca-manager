"""
Database Admin — publish DATABASE_URL into /etc/ucm/ucm.env.

``ucm.env`` is shared installation state: besides DATABASE_URL it carries the
key-encryption key, the listen address, the HTTPS port and whatever else the
package or the operator put there. Rewriting it with ``Path.write_text``
truncates the file before the new bytes land, so a crash, a full disk or a
kill at the wrong moment takes every other variable with it.

Everything here therefore goes through a temporary file in the same directory,
fsync'd, given the original mode and owner, then moved over the target with
``os.replace``. A concurrent reader sees either the whole old file or the whole
new one, never a truncated one. The file is read back afterwards to prove what
actually landed on disk, and the previous content is kept in an ``EnvBackup``
so the caller can undo the change when it cannot follow through — typically
when the restart that would make the new URL effective cannot be requested.

Comments are preserved, including a commented-out ``#DATABASE_URL=``: dotenv
never acts on it, so removing it would destroy operator history for no gain.
"""

import logging
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from config.settings import is_docker
from services.backup.storage import _fsync_directory

from .helpers import UCM_ENV_PATH, _redact_uri, _short_err

logger = logging.getLogger(__name__)

_VAR = "DATABASE_URL"

# python-dotenv parses this file: it accepts an optional ``export`` prefix and
# whitespace around ``=``, and treats a leading ``#`` as a comment. Only the
# forms dotenv would actually act on count as a definition to replace.
_DEFINITION_RE = re.compile(r"^\s*(?:export\s+)?" + _VAR + r"\s*=(.*)$")

_DEFAULT_MODE = 0o640
_TEMP_PREFIX = ".ucm.env."
_TEMP_SUFFIX = ".tmp"

_DOCKER_REFUSAL = "Cannot modify ucm.env in Docker. Set DATABASE_URL env var instead."


@dataclass(frozen=True)
class EnvBackup:
    """The env file exactly as it was before a write.

    ``content`` is ``None`` when the file did not exist yet; restoring such a
    backup removes the file again. ``uid``/``gid`` use the ``os.chown``
    convention where ``-1`` means "leave as created".
    """

    path: Path
    content: Optional[str]
    mode: int
    uid: int
    gid: int


def _env_path() -> Path:
    """Resolve the env path at call time so tests can redirect it."""
    return Path(UCM_ENV_PATH)


_DEFAULT_ENV_PATH = Path("/etc/ucm/ucm.env")


def env_file_path() -> Path:
    """Env file to rewrite: a redirected UCM_ENV_PATH wins, then Docker, then /etc."""
    configured = Path(UCM_ENV_PATH)
    if configured != _DEFAULT_ENV_PATH:
        return configured
    if os.environ.get('UCM_DOCKER', '').lower() in ('1', 'true'):
        for candidate in ('/opt/ucm/.env', '/app/.env', '/app/backend/.env'):
            if Path(candidate).exists():
                return Path(candidate)
        return Path('/opt/ucm/.env')
    return configured


def _read_env_text(path: Path) -> str:
    """Current content of the env file; empty string when it does not exist."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _read_back(path: Path) -> str:
    """Re-read the published file to prove what landed on disk.

    Deliberately separate from ``_read_env_text``: this one must not tolerate
    a missing file, and it is the single point a test can subvert to simulate
    a write that did not take.
    """
    return path.read_text(encoding="utf-8")


def _extract_database_url(content: str) -> Optional[str]:
    """The value dotenv would end up with, or None when unset.

    The last assignment wins, as in dotenv.
    """
    value = None
    for line in content.splitlines():
        match = _DEFINITION_RE.match(line)
        if match:
            value = match.group(1).strip()
    return value


def _render(existing: str, database_url: Optional[str]) -> str:
    """Return ``existing`` with DATABASE_URL set, replaced or removed.

    Every other line keeps its text, its position and its line ending;
    duplicate definitions collapse into the first one. A file that ended
    without a newline gains one, since a definition can only be appended on
    its own line.
    """
    out = []
    replaced = False
    new_line = f"{_VAR}={database_url}" if database_url else None

    for raw in existing.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        ending = raw[len(body):] or "\n"
        match = _DEFINITION_RE.match(body)
        if match:
            if new_line is not None and not replaced:
                # Keep the "export " the line already had: dotenv and systemd
                # ignore it, but a shell that sources this file does not, and
                # the edit has no business changing how it is consumed.
                prefix = match.group(0)[:match.group(0).lower().index('database_url')]
                out.append(f"{prefix}{new_line}{ending}")
                replaced = True
            continue
        out.append(body + ending)

    if new_line is not None and not replaced:
        out.append(new_line + "\n")

    return "".join(out)


def _capture(path: Path) -> EnvBackup:
    """Snapshot content, mode and owner before touching anything."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return EnvBackup(path=path, content=None, mode=_DEFAULT_MODE, uid=-1, gid=-1)
    return EnvBackup(
        path=path,
        content=_read_env_text(path),
        mode=stat.S_IMODE(st.st_mode),
        uid=st.st_uid,
        gid=st.st_gid,
    )


def _sync_parent(path: Path) -> None:
    """Best-effort fsync of the directory entry; never fails the write."""
    try:
        _fsync_directory(path.parent)
    except OSError as exc:
        logger.warning("Could not fsync %s: %s", path.parent, exc)


def _apply_ownership(temp_path: Path, uid: int, gid: int) -> None:
    """Give the replacement the original owner.

    The writer may be root while the file belongs to the service account; a
    file the service can no longer write would break the next edit, so a chown
    that is needed and fails aborts the publication instead of shipping the
    wrong owner.
    """
    if uid == -1 and gid == -1:
        return
    current = os.stat(temp_path)
    if uid in (-1, current.st_uid) and gid in (-1, current.st_gid):
        return
    os.chown(temp_path, uid, gid)


def _atomic_write(path: Path, content: str, mode: int, uid: int, gid: int) -> None:
    """Publish ``content`` at ``path`` atomically, leaving no temporary behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=_TEMP_PREFIX, suffix=_TEMP_SUFFIX, dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        # chown before chmod: changing the owner can clear mode bits.
        _apply_ownership(temp_path, uid, gid)
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                logger.warning("Could not remove temporary env file %s", temp_path)
    _sync_parent(path)


def _restore(backup: EnvBackup) -> None:
    """Put the file back exactly as the backup found it. Raises on failure."""
    if backup.content is None:
        try:
            os.unlink(backup.path)
        except FileNotFoundError:
            pass
        _sync_parent(backup.path)
        return
    _atomic_write(backup.path, backup.content, backup.mode, backup.uid, backup.gid)


def _rollback(backup: EnvBackup) -> bool:
    """Undo a write that could not be verified; True when the file is back."""
    try:
        _restore(backup)
        return True
    except Exception as exc:
        logger.error(
            "Could not restore %s after a failed write: %s",
            backup.path, _redact_uri(str(exc)))
        return False


# python-dotenv expands ``${NAME}`` (and ``$NAME``) when the service reads
# this file at startup, so a password containing one would reach the driver as
# something else entirely — or as nothing. The write would still verify,
# because the file holds exactly what we put in it; the service would simply
# fail to connect after the restart. Percent-encoding is the way out, and the
# operator has to be told so before the switch, not after it.
_INTERPOLATED_RE = re.compile(r"\$(?:\{|[A-Za-z_])")


def _interpolation_refusal(database_url: Optional[str]) -> Optional[str]:
    """Why this URL cannot be written verbatim, or None."""
    if database_url and _INTERPOLATED_RE.search(database_url):
        return (
            "The database URL contains '$', which the configuration reader "
            "expands as a variable when the service starts, so the service "
            "would connect with a different value than the one verified "
            "here. Percent-encode it as %24 and retry."
        )
    return None


def update_env_file(
    path: Path,
    render,
    *,
    verify=None,
    what: str = "the configuration",
) -> Tuple[bool, str, Optional[EnvBackup]]:
    """Rewrite an environment file whole, or leave it exactly as it was.

    ``render(existing_text) -> new_text`` decides the content; ``verify`` is
    given what is on disk afterwards and says whether it is what was meant.

    Every caller that edits one of these files needs the same five things,
    and each one that hand-rolled them lost one: a backup, a temporary file
    in the same directory, the original mode and owner, an atomic rename, and
    a read-back. ``Path.write_text`` has none of them — it truncates the file
    first, so an interrupted write destroys the variables that had nothing to
    do with the edit: the encryption key, the listen address, whatever else
    the installation put there.

    Returns ``(ok, message, backup)``. On failure the file is back to what it
    was and ``backup`` is None; on success ``backup`` is the undo token.
    """
    backup = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = _capture(path)
        new_content = render(backup.content or "")
        _atomic_write(path, new_content, backup.mode, backup.uid, backup.gid)
    except PermissionError as e:
        logger.error("Permission denied writing %s: %s", path, _redact_uri(str(e)))
        return False, _short_err(
            f"Permission denied writing the configuration file: {e}"), None
    except Exception as e:
        # The error can quote the line being written, URI included
        logger.error("Writing %s failed: %s", path, _redact_uri(str(e)))
        return False, _short_err(f"Failed to persist {what}: {e}"), None

    # Prove what is on disk rather than what was handed to the OS.
    try:
        observed = _read_back(path)
        verified = observed == new_content and (verify is None or verify(observed))
    except OSError as e:
        logger.error("Could not re-read %s after write: %s", path, _redact_uri(str(e)))
        verified = False

    if not verified:
        restored = _rollback(backup)
        message = ("Re-reading the configuration file after the write did not "
                   "give back what was written")
        message += (
            "; previous content restored" if restored
            else "; PREVIOUS CONTENT COULD NOT BE RESTORED: check the file by hand"
        )
        return False, message, None

    return True, f"{what} persisted", backup


def persist_database_url_with_backup(
    database_url: Optional[str],
) -> Tuple[bool, str, Optional[EnvBackup]]:
    """Write DATABASE_URL to ucm.env and hand back the undo token.

    Returns ``(ok, message, backup)``. On success ``backup`` holds the previous
    content for :func:`restore_previous_database_url`; on failure it is None
    and the file is left as it was found.
    """
    if is_docker():
        return False, _DOCKER_REFUSAL, None

    refusal = _interpolation_refusal(database_url)
    if refusal:
        return False, refusal, None

    expected = database_url or None
    return update_env_file(
        _env_path(),
        lambda existing: _render(existing, database_url),
        verify=lambda observed: _extract_database_url(observed) == expected,
        what="DATABASE_URL",
    )


def persist_database_url(database_url: Optional[str]) -> Tuple[bool, str]:
    """
    Write DATABASE_URL to /etc/ucm/ucm.env (set/update/remove).
    Pass None or empty string to remove (= use SQLite default).
    Refuses in Docker (caller must check first).

    Every other variable, comment and line order in the file is preserved.
    Use :func:`persist_database_url_with_backup` when the change may need to
    be undone.
    """
    ok, message, _ = persist_database_url_with_backup(database_url)
    return ok, message


def restore_previous_database_url(backup: Optional[EnvBackup]) -> Tuple[bool, str]:
    """Put ucm.env back to the state ``backup`` captured.

    For the caller that persisted a new URL and then could not go through with
    it (restart refused, migration abandoned): the file returns to its previous
    bytes, mode and owner, or is removed again if it did not exist before.
    """
    if is_docker():
        return False, _DOCKER_REFUSAL
    if backup is None:
        return False, "No ucm.env backup to restore"

    try:
        _restore(backup)
    except Exception as e:
        logger.error("restore_previous_database_url failed: %s", _redact_uri(str(e)))
        return False, _redact_uri(f"Failed to restore {backup.path}: {e}")
    return True, "Previous DATABASE_URL restored"
