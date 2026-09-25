"""Diagnostic log bundle service.

Builds a ZIP archive containing the most relevant UCM logs and a small system
diagnostic file, with sensitive-looking tokens redacted. The bundle is meant
for support / troubleshooting: the user downloads it from Settings and
attaches it to a support request or GitHub issue.

Contents:
  - ucm.log      (last ~2 MB of application log)
  - error.log    (last ~2 MB of gunicorn/error log)
  - journal.log  (last 2000 lines of `journalctl -u ucm`, systemd hosts only)
  - access.log   (last 1 MB of access log, when present)
  - system.txt    (version, migration count, DB backend, services status)

Sanitisation (defence in depth — logs should never contain secrets, but a
redaction pass guards against accidental leakage):
  - RFC 6750 Bearer tokens:  `Authorization: Bearer xxx` → `Authorization: Bearer [redacted]`
  - `password=...`, `pass=...`, `pwd=...`, `passphrase=...`, `secret=...`,
    `pin=...` assignments, including the names UCM's own settings and provider
    credential schemas use (`client_secret`, `challenge_password`,
    `bind_password`, `secret_key`, `eab_hmac_key`, `user_pin`), in the
    query-string, JSON and quoted forms
  - `token=...`, `api_key=...` and the other key names that carry a secret
  - `Cookie:` / `Set-Cookie:` header values
  - the password in a URL's userinfo (`https://user:pw@host`)
  - PEM private key blocks (BEGIN ... PRIVATE KEY ... END ... PRIVATE KEY)
  - Long JWT-like strings (three base64 segments separated by dots)

Size policy: each included log file is truncated to its last ``MAX_BYTES_PER_FILE``
bytes before being added; the resulting ZIP stays well under the ~5 MB target.
"""
from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import is_docker

logger = logging.getLogger(__name__)

# --- size policy -----------------------------------------------------------
MAX_BYTES_PER_FILE = 2 * 1024 * 1024      # 2 MB per log file (last N bytes retained)
MAX_BYTES_ACCESS = 1 * 1024 * 1024       # 1 MB for the access log
MAX_JOURNAL_LINES = 2000                  # last N lines of journalctl

# Where UCM stores its file logs (matches the gunicorn/logging config).
LOG_DIR = Path(os.environ.get('UCM_LOG_DIR', '/var/log/ucm'))

# --- sanitisation patterns -------------------------------------------------
# Each entry is (compiled_regex, replacement_template).
_PATTERNS: list[tuple[re.Pattern, str]] = []


def _add(pattern: str, repl: str, flags: int = 0) -> None:
    _PATTERNS.append((re.compile(pattern, flags), repl))


# Authorization header, any casing.  `Bearer xyz`, `Basic xyz`, etc.
_add(r'(?i)(authorization\s*[:=]\s*)([A-Za-z]+)\s+([^\s,;]+)', r'\1\2 [redacted]')
# Bare `Bearer <token>` (in JSON payloads / logs).
_add(r'(?i)\b(bearer)\s+([A-Za-z0-9_\-=\.]+)', r'\1 [redacted]')
# `password=secret`, `pass=`, `pwd=`, `passwd=`, `secret=`, in the query-string,
# config and JSON forms.
#
# The boundary is a lookbehind and not `\b`, because `\b` does not match after
# an underscore: with it, UCM's own secrets went through untouched, every one of
# them being a prefixed name — `client_secret` (Intune), `challenge_password`
# (SCEP), `bind_password` (LDAP), `smtp_password`. The optional quote around the
# separator is what catches `"password": "..."` in a logged JSON body.
#
# The names are UCM's own, read off the settings and the provider credential
# schemas: `secret_key`, `eab_hmac_key`, `user_pin` and `passphrase` all went
# out in full before this list was checked against them. A name is matched only
# where a separator follows it, which is what keeps `password_set=true`,
# `min_password_length=8`, `token_label=ucm-hsm` and `token_url=...` readable:
# redaction that eats the diagnostics is no more use than redaction that misses.
_SECRET_NAME = (r'pass(?:word|wd|phrase)?'
                r'|(?:secret|hmac|master|encryption|consumer|application|account)'
                r'(?:[_-][a-z0-9]+)?[_-]?keys?'
                r'|secret|hmac|pin')
_TOKEN_NAME = r'tokens?|api[_-]?keys?|access[_-]?tokens?|refresh[_-]?tokens?'
# A quoted value is taken whole: stopping at the first space left the tail of
# `"password": "hunter 2"` in the file.
_VALUE = r'(?:"[^"]*"|\'[^\']*\'|[^\s,;&"\']+)'
_ASSIGNMENT = r'(?i)((?<![A-Za-z0-9])(?:%s)["\']?\s*[:=]\s*)' + _VALUE
_add(_ASSIGNMENT % _SECRET_NAME, r'\1[redacted]')
# `token=...` (API tokens in URLs / config)
_add(_ASSIGNMENT % _TOKEN_NAME, r'\1[redacted]')
# `Cookie: session=...` and its reply. A session cookie is a credential for as
# long as the session lives, and the value is the whole of what follows.
# Everything to the end of the line goes, not the first value: a cookie header
# carries several, separated by the `;` that bounds every other pattern here,
# and stopping at it would redact the session and leave the rest of the jar.
_add(r'(?i)((?:set-)?cookie\s*[:=]\s*).+', r'\1[redacted]')
# `https://user:pw@host` — a password in the authority of a URL, which is how a
# proxy, an LDAP or a database URL carries one.
_add(r'(?i)\b([a-z][a-z0-9+.\-]*://[^\s:/@]+):[^\s/@]+@', r'\1:[redacted]@')
# JWT-ish: three base64url segments separated by dots, middle one reasonably long.
_add(r'\beyJ[A-Za-z0-9_\-=]{6,}\.[A-Za-z0-9_\-=]{6,}\.[A-Za-z0-9_\-=]{6,}\b', '[redacted-jwt]')
# Whole PEM private-key blocks (RSA, EC, OPENSSH, ENCRYPTED, ...). Scanned in
# one pass: a lazy `.*?` between the markers is quadratic on a log seeded with
# unclosed BEGIN lines, which anyone can write there through a User-Agent.
_PEM_BEGIN = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')
_PEM_END = re.compile(r'-----END [A-Z ]*PRIVATE KEY-----')


def _redact_pem(text: str) -> str:
    out, pos = [], 0
    while True:
        begin = _PEM_BEGIN.search(text, pos)
        if begin is None:
            out.append(text[pos:])
            return ''.join(out)
        end = _PEM_END.search(text, begin.end())
        if end is None:
            # No END anywhere after this marker: nothing later can close either
            out.append(text[pos:])
            return ''.join(out)
        out.append(text[pos:begin.start()])
        out.append('[redacted-private-key]')
        pos = end.end()


def redact(text: str) -> str:
    """Apply every sanitisation pattern to ``text`` and return the redacted copy."""
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return _redact_pem(text)


# --- file collection -------------------------------------------------------
def _tail_bytes(path: Path, max_bytes: int) -> Optional[bytes]:
    """Return the last ``max_bytes`` bytes of ``path`` (raw), or None if unreadable."""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    try:
        with path.open('rb') as fh:
            if size > max_bytes:
                fh.seek(-max_bytes, os.SEEK_END)
                # drop partial first line so we start at a line boundary
                fh.readline()
            return fh.read()
    except OSError as exc:
        logger.warning('log_bundle: could not read %s: %s', path, exc)
        return None


def collect_journal() -> Optional[bytes]:
    """Return the last ``MAX_JOURNAL_LINES`` lines of the ucm unit journal.

    Skipped on Docker (no systemd journal) and when journalctl is missing.
    Returns raw bytes (may be empty); None when journalctl is unavailable.
    """
    if is_docker():
        return None
    exe = shutil.which('journalctl')
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, '-u', 'ucm', '--no-pager', '-n', str(MAX_JOURNAL_LINES),
             '--output=short-iso'],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            # DEBUG, not INFO: the log viewer asks this question to decide
            # whether to offer the journal as a source, and on a host whose
            # service user cannot read the journal the answer is always a
            # failure. At INFO each of those answers was written into the
            # application log, which is the log the viewer is reading.
            logger.debug('log_bundle: journalctl rc=%d: %s', proc.returncode,
                         (proc.stderr or '').strip()[:200])
        return (proc.stdout or '').encode('utf-8', errors='replace') or None
    except Exception as exc:  # noqa: BLE001
        logger.debug('log_bundle: journalctl skipped: %s', exc)
        return None


# --- system diagnostic -----------------------------------------------------
def _system_diagnostic() -> str:
    """Build a short, secret-free diagnostic string."""
    lines: list[str] = []
    lines.append(f'Generated: {datetime.now(timezone.utc).isoformat()}')
    lines.append(f'Deployment: {"docker" if is_docker() else "systemd"}')
    lines.append(f'Hostname: {os.uname().nodename}')
    try:
        from services.updates import get_current_version
        lines.append(f'Version: {get_current_version()}')
    except Exception:  # noqa: BLE001
        pass
    try:
        from utils.db_url import is_postgres_url
        backend = 'postgresql' if is_postgres_url(os.getenv('DATABASE_URL', '')) else 'sqlite'
        lines.append(f'DB backend: {backend}')
    except Exception:  # noqa: BLE001
        pass
    try:
        from app import db
        from sqlalchemy import text
        mig = db.session.execute(text("SELECT value FROM system_config WHERE key='migration_version'")).scalar()
        lines.append(f'Migration version: {mig}')
    except Exception:  # noqa: BLE001
        pass
    # Service statuses (reuses the dashboard helper, no secrets).
    try:
        from api.v2.dashboard import get_system_status
        st = get_system_status() or {}
        lines.append('Services:')
        for k, v in st.items():
            lines.append(f'  {k}: {v}')
    except Exception:  # noqa: BLE001
        pass
    return '\n'.join(lines) + '\n'


# --- bundle assembly -------------------------------------------------------
def build_bundle() -> bytes:
    """Assemble the diagnostic bundle and return it as ZIP bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # primary logs. The application log is taken from the path the logging
        # setup actually chose, so the bundle is not empty on Docker (which
        # writes nothing under LOG_DIR) or wherever that path was unwritable.
        from utils.app_log import resolved_path
        app_log = resolved_path() or (LOG_DIR / 'ucm.log')
        for path, arcname, cap in ((app_log, 'ucm.log', MAX_BYTES_PER_FILE),
                                   (LOG_DIR / 'error.log', 'error.log', MAX_BYTES_PER_FILE),
                                   (LOG_DIR / 'access.log', 'access.log', MAX_BYTES_ACCESS)):
            raw = _tail_bytes(path, cap)
            if raw is None:
                continue
            text = raw.decode('utf-8', errors='replace')
            zf.writestr(arcname, redact(text))
        # journal (systemd only)
        jraw = collect_journal()
        if jraw:
            zf.writestr('journal.log', redact(jraw.decode('utf-8', errors='replace')))
        # diagnostic
        try:
            zf.writestr('system.txt', redact(_system_diagnostic()))
        except Exception as exc:  # noqa: BLE001 — never break the download over the diagnostic
            logger.warning('log_bundle: diagnostic failed: %s', exc)
    data = buf.getvalue()
    logger.info('log_bundle: built %.1f KB', len(data) / 1024.0)
    return data


def bundle_filename() -> str:
    """Suggested download filename, e.g. ``ucm-logs-netsuit-20260627T1123.zip``."""
    host = os.uname().nodename
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    return f'ucm-logs-{host}-{ts}.zip'
