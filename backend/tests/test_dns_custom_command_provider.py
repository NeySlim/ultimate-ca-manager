"""Tests for the custom_command DNS provider — lego-bridge use case (#249)."""
import os
import stat
import sys

import pytest

from services.acme.dns_providers import create_provider
from services.acme.dns_providers.custom_command import CustomCommandDnsProvider


@pytest.fixture
def script(tmp_path):
    """A python helper that records its env into a trace file."""
    trace = tmp_path / 'trace.log'
    helper = tmp_path / 'helper.py'
    helper.write_text(
        "import os, sys\n"
        "open(sys.argv[1], 'a').write('|'.join([\n"
        "    os.environ.get('ACTION',''), os.environ.get('DOMAIN',''),\n"
        "    os.environ.get('RECORD_NAME',''), os.environ.get('RECORD_VALUE',''),\n"
        "    os.environ.get('TTL',''),\n"
        "]) + '\\n')\n"
    )
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
    return helper, trace


def _creds(helper, extra=None, delete=True):
    c = {
        'create_command': f'{sys.executable} {helper} /tmp/trace-test.log',
        'timeout_seconds': '10',
    }
    if delete:
        c['delete_command'] = f'{sys.executable} {helper} /tmp/trace-test.log'
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
        ok, msg = p.delete_txt_record('example.com', '_acme-challenge.example.com')
        assert ok and 'No command' in msg

    def test_relative_binary_refused(self, tmp_path):
        p = create_provider('custom_command', {'create_command': 'dns-helper create'})
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert not ok and 'absolute' in msg

    def test_missing_binary_refused(self):
        p = create_provider('custom_command', {'create_command': '/nonexistent/dns.sh'})
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert not ok and 'executable' in msg

    def test_nonzero_rc_fails_with_output(self, tmp_path):
        failer = tmp_path / 'failer.py'
        failer.write_text("import sys; sys.stderr.write('DNS API denied write\\n'); sys.exit(3)")
        failer.chmod(failer.stat().st_mode | stat.S_IXUSR)
        p = create_provider('custom_command', {'create_command': f'{sys.executable} {failer}'})
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert not ok
        assert 'rc=3' in msg and 'DNS API denied write' in msg

    def test_no_shell_metachar_injection(self, tmp_path):
        """A sneaky record_name/txt value must not spawn shells or write files."""
        pwned = tmp_path / 'pwned'
        p = create_provider('custom_command', {
            'create_command': f'{sys.executable} -c "import os; print(os.environ[\'RECORD_NAME\'])"',
        })
        ok, msg = p.create_txt_record(
            'example.com',
            f"_acme-challenge; touch {pwned} #.example.com",
            'v')
        assert ok
        assert not pwned.exists(), 'shell injection: record name was interpreted'

    def test_timeout_enforced(self, tmp_path):
        slow = tmp_path / 'slow.py'
        slow.write_text('import time; time.sleep(30)')
        slow.chmod(slow.stat().st_mode | stat.S_IXUSR)
        p = create_provider('custom_command', {
            'create_command': f'{sys.executable} {slow}', 'timeout_seconds': '5'})

        import time as _t
        started = _t.monotonic()
        ok, msg = p.create_txt_record('example.com', '_acme-challenge.example.com', 'v')
        elapsed = _t.monotonic() - started
        assert not ok and 'timed out' in msg
        assert elapsed < 15

    def test_schema_advertises_create_command(self):
        schema = CustomCommandDnsProvider.get_credential_schema()
        names = {f['name'] for f in schema}
        assert 'create_command' in names and any(f['required'] for f in schema)
