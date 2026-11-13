"""Regression tests: Kerberos keytab validation (issue #229 item 4).

Before this fix, uploading a keytab only checked its file extension/size --
there was no feedback on whether it actually parsed, or whether its
principal matched the configured SPN, short of the generic "settings
saved" toast. ``negotiate_auth.inspect_keytab`` now parses the keytab via
the same GSSAPI call the real acceptor uses, so a "valid" result means it
will actually work at request time.

``_VALID_KEYTAB_B64`` is a hand-built, real (RFC-shape) MIT keytab file
containing a single ``HTTP/testhost.example.test@EXAMPLE.TEST`` entry,
confirmed against a real GSSAPI installation (ucm2.vm.hagland.home) to
parse successfully and report that exact principal -- not a mock.
"""
import base64
from pathlib import Path

import pytest

from services.kerberos import negotiate_auth
from tests.windows_profile_support import windows_profiles_restored, upload_keytab  # noqa: F401

try:
    import gssapi  # noqa: F401
    HAS_GSSAPI = True
except ImportError:
    HAS_GSSAPI = False

requires_gssapi = pytest.mark.skipif(
    not HAS_GSSAPI,
    reason='gssapi not installed (optional pyspnego[kerberos] extra); '
           'positive-parse cases need the real GSSAPI keytab loader',
)

_VALID_KEYTAB_B64 = (
    'BQIAAABeAAIADEVYQU1QTEUuVEVTVAAESFRUUAAVdGVzdGhvc3QuZXhhbXBsZS50ZXN0AAAA'
    'AWd0hYABABIAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fAAAAAQ=='
)


@pytest.fixture
def valid_keytab_path(tmp_path):
    path = tmp_path / 'valid.keytab'
    path.write_bytes(base64.b64decode(_VALID_KEYTAB_B64))
    return str(path)


@pytest.fixture
def garbage_keytab_path(tmp_path):
    path = tmp_path / 'garbage.keytab'
    path.write_bytes(b'this is not a keytab file at all, just garbage bytes')
    return str(path)


class TestInspectKeytab:
    @requires_gssapi
    def test_valid_keytab_reports_principal(self, valid_keytab_path):
        result = negotiate_auth.inspect_keytab(valid_keytab_path)
        assert result == {
            'valid': True,
            'principal': 'HTTP/testhost.example.test@EXAMPLE.TEST',
            'entries': [{'principal': 'HTTP/testhost.example.test@EXAMPLE.TEST',
                         'realm': 'EXAMPLE.TEST', 'kvno': 1, 'enctype': 18}],
            'error': None,
        }

    def test_malformed_keytab_is_invalid_not_a_crash(self, garbage_keytab_path):
        result = negotiate_auth.inspect_keytab(garbage_keytab_path)
        assert result['valid'] is False
        assert result['principal'] is None
        assert result['error']  # some GSSAPI-provided reason, exact text is library-specific

    def test_missing_keytab_is_invalid(self, tmp_path):
        result = negotiate_auth.inspect_keytab(str(tmp_path / 'does-not-exist.keytab'))
        assert result == {'valid': False, 'principal': None, 'entries': [],
                          'error': 'No keytab uploaded'}
    @requires_gssapi
    def test_default_path_is_keytab_path(self, monkeypatch, valid_keytab_path):
        monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', Path(valid_keytab_path))
        result = negotiate_auth.inspect_keytab()
        assert result['valid'] is True
        assert result['principal'] == 'HTTP/testhost.example.test@EXAMPLE.TEST'


class TestKeytabUploadEndpoint:
    """Exercises the keytab upload of api/v2/windows_profiles.py through the
    real Flask app, since the validate-before-persist ordering (reject a
    malformed keytab without overwriting a working one) is the actual
    behavior being fixed, not just inspect_keytab in isolation."""

    def test_malformed_upload_is_rejected_and_not_persisted(self, auth_client, app, tmp_path, monkeypatch):
        keytab_target = tmp_path / 'persisted.keytab'
        monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', keytab_target)

        # Seed a working keytab first, so we can prove the bad upload didn't clobber it.
        keytab_target.write_bytes(base64.b64decode(_VALID_KEYTAB_B64))
        before = keytab_target.read_bytes()

        r = upload_keytab(auth_client, b'not a real keytab', filename='bad.keytab')

        assert r.status_code == 400
        assert keytab_target.read_bytes() == before  # untouched
    @requires_gssapi
    def test_valid_upload_is_persisted_and_reports_principal(self, auth_client, app, tmp_path, monkeypatch):
        keytab_target = tmp_path / 'persisted2.keytab'
        monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', keytab_target)
        monkeypatch.setattr(negotiate_auth, 'get_spn', lambda: 'HTTP/testhost.example.test@EXAMPLE.TEST')

        keytab_bytes = base64.b64decode(_VALID_KEYTAB_B64)
        r = upload_keytab(auth_client, keytab_bytes, filename='good.keytab')

        assert r.status_code == 200
        body = r.get_json()
        assert body['data']['keytab_set'] is True
        assert [e['principal'] for e in body['data']['keytab_entries']] == [
            'HTTP/testhost.example.test@EXAMPLE.TEST']
        assert keytab_target.read_bytes() == keytab_bytes
    def test_a_keytab_for_another_host_than_the_spn_is_refused(self, auth_client, app, tmp_path, monkeypatch):
        """The unnamed acceptor takes a ticket for any entry: one for another host is refused."""
        keytab_target = tmp_path / 'persisted3.keytab'
        monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', keytab_target)
        monkeypatch.setattr(negotiate_auth, 'get_spn', lambda: 'HTTP/some-other-host.example.test@EXAMPLE.TEST')
        monkeypatch.setattr(negotiate_auth, '_gssapi_load', lambda target: ('HTTP/testhost.example.test@EXAMPLE.TEST', None))

        keytab_bytes = base64.b64decode(_VALID_KEYTAB_B64)
        r = upload_keytab(auth_client, keytab_bytes, filename='good.keytab')

        assert r.status_code == 400
        assert 'HTTP/testhost.example.test@EXAMPLE.TEST' in r.get_json()['message']
        assert not keytab_target.exists()
