"""Tests for the custom_command DNS provider — lego-bridge use case (#249)."""
import os
import sys

import pytest

from services.acme.dns_providers import create_provider
from services.acme.dns_providers import custom_command as cc
from services.acme.dns_providers.custom_command import CustomCommandDnsProvider


@pytest.fixture(autouse=True)
def hooks(tmp_path, monkeypatch):
    """Hooks live in a directory of the test account, trusted in place of root's."""
    d = tmp_path / 'dns-hooks'
    d.mkdir(mode=0o755)
    monkeypatch.setattr(cc, 'HOOKS_DIR', str(d))
    monkeypatch.setattr(cc, '_HOOK_OWNER_UID', os.getuid())
    return d


def _install(hooks, name, body):
    path = hooks / name
    path.write_text(f'#!{sys.executable}\n{body}\n')
    path.chmod(0o755)
    return name


@pytest.fixture
def script(tmp_path, hooks):
    """A python helper that records its env into a trace file."""
    trace = tmp_path / 'trace.log'
    helper = hooks / 'helper.py'
    helper.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "open(sys.argv[1], 'a').write('|'.join([\n"
        "    os.environ.get('ACTION',''), os.environ.get('DOMAIN',''),\n"
        "    os.environ.get('RECORD_NAME',''), os.environ.get('RECORD_VALUE',''),\n"
        "    os.environ.get('TTL',''),\n"
        "]) + '\\n')\n"
    )
    helper.chmod(0o755)
    return helper.name, trace


def _creds(helper, extra=None, delete=True):
    c = {
        'create_command': f'{helper} /tmp/trace-test.log',
        'timeout_seconds': '10',
    }
    if delete:
        c['delete_command'] = f'{helper} /tmp/trace-test.log'
    c.update(extra or {})
    return c


def _read_trace():
    try:
        with open('/tmp/trace-test.log') as f:
            return f.read().strip().splitlines()
    except FileNotFoundError:
        return []


class TestCustomCommandProvider:
    def test_create_invokes_with_env(self, script, tmp_path):
        helper, _ = script
        with open('/tmp/trace-test.log', 'w'):
            pass
        p = create_provider('custom_command', _creds(helper))
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'txtvalue42')
        assert ok, msg
        lines = _read_trace()
        assert lines[-1] == 'create|example.com|_acme-challenge.example.com|txtvalue42|300'
        os.unlink('/tmp/trace-test.log')

    def test_delete_optional_noop_when_missing(self, script):
        helper, _ = script
        p = create_provider('custom_command', _creds(helper, delete=False))
        ok, msg = p.delete_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert ok and 'No command' in msg

    def test_absolute_binary_refused(self, tmp_path):
        p = create_provider('custom_command', {'create_command': f'{sys.executable} -c 1'})
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert not ok and 'hook' in msg

    def test_missing_binary_refused(self):
        p = create_provider('custom_command', {'create_command': 'dns.sh'})
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert not ok and 'not found' in msg

    def test_nonzero_rc_fails_with_output(self, hooks):
        failer = _install(hooks, 'failer.py', "import sys; sys.stderr.write('DNS API denied write\\n'); sys.exit(3)")
        p = create_provider('custom_command', {'create_command': failer})
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert not ok
        assert 'rc=3' in msg and 'DNS API denied write' in msg

    def test_no_shell_metachar_injection(self, tmp_path, hooks):
        """A sneaky record_name/txt value must not spawn shells or write files."""
        pwned = tmp_path / 'pwned'
        echo = _install(hooks, 'echo.py', "import os; print(os.environ['RECORD_NAME'])")
        p = create_provider('custom_command', {'create_command': echo})
        ok, msg = p.create_txt_record(
            'example.com',
            f"_acme-challenge; touch {pwned} #.example.com",
            'v')
        assert ok
        assert not pwned.exists(), 'shell injection: record name was interpreted'

    def test_timeout_enforced(self, hooks):
        slow = _install(hooks, 'slow.py', 'import time; time.sleep(30)')
        p = create_provider('custom_command', {
            'create_command': slow, 'timeout_seconds': '5'})

        import time as _t
        started = _t.monotonic()
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        elapsed = _t.monotonic() - started
        assert not ok and 'timed out' in msg
        # The provider floors the timeout at 5s (max(5, ...)), so this wait is
        # not reducible from the test: it is the product's own lower bound.
        assert elapsed < 15

    def test_schema_advertises_create_command(self):
        schema = CustomCommandDnsProvider.get_credential_schema()
        names = {f['name'] for f in schema}
        assert 'create_command' in names and any(f['required'] for f in schema)
