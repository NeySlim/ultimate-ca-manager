"""Custom External Command DNS Provider.

Runs a hook installed by the host administrator to create/delete the ACME
TXT record: the escape hatch for DNS providers with REST APIs we do not
ship a driver for (e.g. nicmanager), or for bridging external tooling such
as lego-based helpers (lego itself exposes no record-level CLI; call a
small wrapper instead).

Only executables of HOOKS_DIR (/etc/ucm/dns-hooks) run, named by their file
name. The directory and the hook must belong to root and be writable by no
one else, so holding write:acme never chooses what program runs.

The command is executed WITHOUT a shell (argv split, no expansion, no
pipes), with a fixed timeout, with record details passed through the
environment:

    DOMAIN         base domain being validated   (example.com)
    RECORD_NAME    full TXT name                 (_acme-challenge.example.com)
    RECORD_VALUE   TXT content                   (challenge digest)
    TTL            record TTL in seconds
    ACTION         "create" or "delete"

Command strings in `create_command` / `delete_command` are parsed with
shlex (posix): the first word is the hook name, the others its arguments.
`{placeholder}` substitution is NOT performed: keep the record reference in
$RECORD_NAME etc. via env, that avoids all command injection through domain
names.
"""
import os
import re
import shlex
import stat
import subprocess
from typing import Any, Dict, Optional, Tuple

from .base import BaseDnsProvider

_TIMEOUT_S = 60
_MAX_OUTPUT = 4000

HOOKS_DIR = '/etc/ucm/dns-hooks'
_HOOK_OWNER_UID = 0
_HOOK_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]*')
_COMMAND_KEYS = ('create_command', 'delete_command')


def _split(command: str) -> Tuple[Optional[list], str]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return None, f'Invalid command syntax: {exc}'
    if not argv:
        return None, 'Empty command'
    return argv, ''


def _name_error(name: str) -> str:
    if _HOOK_NAME.fullmatch(name):
        return ''
    return (f'The command must start with the name of a hook installed in {HOOKS_DIR} '
            f'(a file name, no path): {name!r}. Move the program into that directory, '
            'owned by root, and give its name')


def _trusted(st: os.stat_result, what: str) -> str:
    """Owned by the hook owner (root) and writable by no group or other account."""
    if st.st_uid != _HOOK_OWNER_UID:
        return f'{what} must be owned by root (uid {_HOOK_OWNER_UID}), not uid {st.st_uid}'
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return f'{what} must not be writable by its group or other accounts'
    return ''


def resolve_hook(name: str) -> Tuple[Optional[str], str]:
    """The real path of hook *name*, or None and the reason it may not run."""
    err = _name_error(name)
    if err:
        return None, err
    try:
        dst = os.lstat(HOOKS_DIR)
    except OSError:
        return None, f'Hook directory {HOOKS_DIR} does not exist'
    if not stat.S_ISDIR(dst.st_mode):
        return None, f'Hook directory {HOOKS_DIR} must be a directory, not a link'
    err = _trusted(dst, f'Hook directory {HOOKS_DIR}')
    if err:
        return None, err
    path = os.path.join(HOOKS_DIR, name)
    real = os.path.realpath(path)
    # A link inside the directory is followed; one that leads out of it is refused
    if os.path.dirname(real) != os.path.realpath(HOOKS_DIR):
        return None, f'Hook {name} leads outside {HOOKS_DIR}'
    try:
        hst = os.stat(real)
    except OSError:
        return None, f'Hook {name} not found in {HOOKS_DIR}'
    if not stat.S_ISREG(hst.st_mode) or not os.access(real, os.X_OK):
        return None, f'Hook {name} in {HOOKS_DIR} is not an executable file'
    err = _trusted(hst, f'Hook {name}')
    if err:
        return None, err
    return real, ''


class CustomCommandDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = 'custom_command'
    PROVIDER_NAME = 'Custom Command'
    PROVIDER_DESCRIPTION = (
        f'Runs a hook installed by the host administrator in {HOOKS_DIR} for TXT '
        'record create/delete. Env: DOMAIN, RECORD_NAME, RECORD_VALUE, TTL, ACTION. '
        'No shell; the command names the hook file, then its arguments.'
    )
    REQUIRED_CREDENTIALS = ['create_command']
    OPTIONAL_CREDENTIALS = ['delete_command', 'timeout_seconds', 'working_directory']

    @classmethod
    def validate_credentials(cls, credentials: Dict[str, Any]) -> None:
        for key in _COMMAND_KEYS:
            command = str((credentials or {}).get(key) or '').strip()
            if not command:
                continue
            argv, err = _split(command)
            if argv is None:
                raise ValueError(f'{key}: {err}')
            err = _name_error(argv[0])
            if err:
                raise ValueError(f'{key}: {err}')

    def _timeout(self) -> int:
        try:
            t = int(self.credentials.get('timeout_seconds') or _TIMEOUT_S)
            return max(5, min(t, 300))
        except (TypeError, ValueError):
            return _TIMEOUT_S

    def _run(self, command: str, action: str, domain: str,
             record_name: str, record_value: str = '',
             ttl: int = 300) -> Tuple[bool, str]:
        if not command or not command.strip():
            return True, f'No command configured for {action}'

        argv, err = _split(command)
        if argv is None:
            return False, err
        binary, err = resolve_hook(argv[0])
        if binary is None:
            return False, err
        argv[0] = binary

        env = dict(os.environ)
        env.update({
            'DOMAIN': domain,
            'RECORD_NAME': record_name,
            'RECORD_VALUE': record_value,
            'TTL': str(ttl),
            'ACTION': action,
        })

        workdir = (self.credentials.get('working_directory') or '').strip() or None
        if workdir and not os.path.isdir(workdir):
            return False, f'working_directory not found: {workdir}'

        try:
            proc = subprocess.run(
                argv,
                env=env,
                cwd=workdir,
                timeout=self._timeout(),
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, f'Command timed out after {self._timeout()}s'
        except OSError as exc:
            return False, f'Failed to run command: {exc}'

        stdout = (proc.stdout or '')[:_MAX_OUTPUT].strip()
        stderr = (proc.stderr or '')[:_MAX_OUTPUT].strip()
        if proc.returncode != 0:
            joined = ' / '.join(s for s in (stdout, stderr) if s)
            return False, f'Command failed (rc={proc.returncode}): {joined}'

        return True, (stdout or f'{action} OK')

    # ---------------------------------------------------------------

    def create_txt_record(self, domain: str, record_name: str,
                          record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        return self._run(
            self.credentials['create_command'], 'create',
            domain, record_name, record_value=record_value, ttl=ttl)

    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        return self._run(
            (self.credentials.get('delete_command') or '').strip(),
            'delete', domain, record_name, record_value=record_value)

    def test_connection(self) -> Tuple[bool, str]:
        """Check that every configured hook may run."""
        for key in _COMMAND_KEYS:
            cmd = (self.credentials.get(key) or '').strip()
            if not cmd:
                continue
            argv, err = _split(cmd)
            if argv is None:
                return False, f'{key}: {err}'
            binary, err = resolve_hook(argv[0])
            if binary is None:
                return False, f'{key}: {err}'
        return True, f'Hooks found in {HOOKS_DIR}, owned by root and executable'

    @classmethod
    def get_credential_schema(cls):
        return [
            {
                'name': 'create_command',
                'label': 'Create TXT record command',
                'type': 'text',
                'required': True,
                'help': f'Name of a hook in {HOOKS_DIR}, then its arguments, e.g. ucm-dns.sh --zone example.com: the record arrives in $RECORD_NAME / $RECORD_VALUE env vars.',
            },
            {
                'name': 'delete_command',
                'label': 'Delete TXT record command (optional)',
                'type': 'text',
                'required': False,
                'help': 'A hook of the same directory, same env vars; skip cleanup if empty.',
            },
            {
                'name': 'timeout_seconds',
                'label': 'Command timeout (seconds)',
                'type': 'number',
                'required': False,
            },
            {
                'name': 'working_directory',
                'label': 'Working directory (optional)',
                'type': 'text',
                'required': False,
            },
        ]
