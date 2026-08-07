"""Custom External Command DNS Provider.

Runs administrator-configured local commands to create/delete the ACME
TXT record — the escape hatch for DNS providers with REST APIs we do not
ship a driver for (e.g. nicmanager), or for bridging external tooling such
as lego-based helpers (lego itself exposes no record-level CLI; call a
small wrapper instead).

The command is executed WITHOUT a shell (argv split, no expansion, no
pipes), with a fixed timeout, with record details passed through the
environment:

    DOMAIN         base domain being validated   (example.com)
    RECORD_NAME    full TXT name                 (_acme-challenge.example.com)
    RECORD_VALUE   TXT content                   (challenge digest)
    TTL            record TTL in seconds
    ACTION         "create" or "delete"

Command strings in `create_command` / `delete_command` are parsed with
shlex (posix). `{placeholder}` substitution is NOT performed — keep the
record reference in $RECORD_NAME etc. via env, that avoids all command
injection through domain names.

SECURITY posture: provider credentials are admin-controlled, but a command
provider executes local code as the UCM service account. Gate behind
``write:acme`` role and only accept absolute paths to existing executables.
"""
import os
import shlex
import subprocess
from typing import Any, Dict, Tuple

from .base import BaseDnsProvider

_TIMEOUT_S = 60
_MAX_OUTPUT = 4000


class CustomCommandDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = 'custom_command'
    PROVIDER_NAME = 'Custom Command'
    PROVIDER_DESCRIPTION = (
        'Runs local admin-configured commands for TXT record create/delete. '
        'Env: DOMAIN, RECORD_NAME, RECORD_VALUE, TTL, ACTION. No shell; '
        'absolute binary path required.'
    )
    REQUIRED_CREDENTIALS = ['create_command']
    OPTIONAL_CREDENTIALS = ['delete_command', 'timeout_seconds', 'working_directory']

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

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return False, f'Invalid command syntax: {exc}'
        if not argv:
            return False, 'Empty command'

        # Refuse relative binaries — PATH juggling by an attacker who can
        # also influence the environment must not redirect execution.
        binary = argv[0]
        if not binary.startswith('/'):
            return False, f'Command must use an absolute binary path: {binary!r}'
        if not (os.path.isfile(binary) and os.access(binary, os.X_OK)):
            return False, f'Binary not executable or missing: {binary}'

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

    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        return self._run(
            (self.credentials.get('delete_command') or '').strip(),
            'delete', domain, record_name)

    def test_connection(self) -> Tuple[bool, str]:
        """Smoke-test the configured binaries exist + are executable."""
        for key in ('create_command', 'delete_command'):
            cmd = (self.credentials.get(key) or '').strip()
            if not cmd:
                continue
            try:
                argv = shlex.split(cmd)
            except ValueError as exc:
                return False, f'{key}: invalid syntax: {exc}'
            binary = argv[0] if argv else ''
            if not binary.startswith('/'):
                return False, f'{key}: binary must be an absolute path ({binary!r})'
            if not (os.path.isfile(binary) and os.access(binary, os.X_OK)):
                return False, f'{key}: binary not executable: {binary}'
        return True, 'Command binaries verified present + executable'

    @classmethod
    def get_credential_schema(cls):
        return [
            {
                'name': 'create_command',
                'label': 'Create TXT record command',
                'type': 'text',
                'required': True,
                'help': 'Absolute binary path, e.g. /usr/local/bin/ucm-dns-create.sh — record arrives in $RECORD_NAME / $RECORD_VALUE env vars.',
            },
            {
                'name': 'delete_command',
                'label': 'Delete TXT record command (optional)',
                'type': 'text',
                'required': False,
                'help': 'Same env vars; skip cleanup if empty.',
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
