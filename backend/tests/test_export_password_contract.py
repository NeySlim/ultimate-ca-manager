"""One rule for the password that encrypts an export, published so the UI
can state it.

Six routes hand out an encrypted bundle and each carried its own rule:

* `POST /api/v2/certificates/<id>/export` (pkcs12 / pfx / jks) checked only
  that a password was **present**, so a one-character password produced a
  PKCS#12 and a 200;
* `POST /api/v2/cas/<id>/export` required 4 to 256;
* the user-certificate, mTLS and key-recovery routes required 8, each with
  its own wording;
* the converter tool checked presence only.

`components/ExportModal.jsx` -- the dialog used for **both** certificates and
CAs -- refused anything under 8 and knew nothing of any ceiling. So the same
dialog was stricter than the server on one route and more permissive on the
other: a one-character password was unreachable from the UI but a script
could set one, and a 300-character password sailed through the dialog and
came back refused by the CA route alone.

The rule that survives is 8 to 256: eight because that is what the UI and
half the routes already required, and 256 because that is the only ceiling
anyone had a reason for (`BestAvailableEncryption` and pyjks degrade sharply
past a few hundred bytes). `GET /api/v2/export/password-policy` publishes it
so the dialog states it rather than restating it.
"""
import json

import pytest

from utils.export_password import (EXPORT_PASSWORD_MAX_LENGTH,
                                   EXPORT_PASSWORD_MIN_LENGTH,
                                   validate_export_password)

TOO_SHORT = 'x' * (EXPORT_PASSWORD_MIN_LENGTH - 1)
JUST_RIGHT = 'x' * EXPORT_PASSWORD_MIN_LENGTH
TOO_LONG = 'x' * (EXPORT_PASSWORD_MAX_LENGTH + 1)
AT_THE_CEILING = 'x' * EXPORT_PASSWORD_MAX_LENGTH


class TestTheRuleItself:
    def test_the_bounds_are_the_ones_the_dialog_shows(self):
        assert (EXPORT_PASSWORD_MIN_LENGTH, EXPORT_PASSWORD_MAX_LENGTH) == (8, 256)

    @pytest.mark.parametrize('value', [TOO_SHORT, 'a', 'ab'])
    def test_a_short_password_is_refused(self, value):
        assert validate_export_password(value) is not None

    @pytest.mark.parametrize('value', [JUST_RIGHT, AT_THE_CEILING, 'correct horse'])
    def test_a_good_password_is_accepted(self, value):
        assert validate_export_password(value) is None

    def test_a_long_password_is_refused(self):
        assert validate_export_password(TOO_LONG) is not None

    def test_the_message_names_both_bounds(self):
        message = validate_export_password('a')
        assert '8' in message and '256' in message

    def test_empty_is_refused_unless_it_means_no_encryption(self):
        assert validate_export_password('') is not None
        assert validate_export_password('', allow_empty=True) is None
        assert validate_export_password(None, allow_empty=True) is None

    def test_something_that_is_not_a_string_is_refused(self):
        assert validate_export_password(12345678) is not None


def _jks_available():
    """`pyjks` ships with the packages, never with requirements.txt.

    It pulls `twofish`, which needs a C toolchain, and UCM exports JKS only
    (never BKS, the one format that uses it), so the postinst installs it with
    `--no-deps` instead. A CI runner therefore has no `jks` module, and a test
    that needs one skips rather than failing, like the rest of the suite does
    for `certsrv` and `pkilint`.
    """
    import importlib.util
    return importlib.util.find_spec('jks') is not None


needs_jks = pytest.mark.skipif(not _jks_available(),
                               reason='pyjks is installed by the packages, not by requirements.txt')

EXPORT_FORMATS = ['pkcs12', 'pfx', pytest.param('jks', marks=needs_jks)]


class TestEveryExportRouteAppliesIt:
    @pytest.mark.parametrize('fmt', EXPORT_FORMATS)
    def test_a_certificate_export_refuses_a_short_password(
            self, auth_client, create_cert, fmt):
        cert = create_cert(cn=f'exportpw-{fmt}-short.example.com')
        r = auth_client.post(
            f'/api/v2/certificates/{cert["id"]}/export',
            data=json.dumps({'format': fmt, 'password': 'a'}),
            content_type='application/json')
        assert r.status_code == 400, (
            f'a one-character password produced a {fmt} bundle and a '
            f'{r.status_code}; the dialog has refused under eight for as '
            'long as it has existed, so only a script could get here')

    @pytest.mark.parametrize('fmt', EXPORT_FORMATS)
    def test_a_certificate_export_accepts_a_good_one(
            self, auth_client, create_cert, fmt):
        cert = create_cert(cn=f'exportpw-{fmt}-good.example.com')
        r = auth_client.post(
            f'/api/v2/certificates/{cert["id"]}/export',
            data=json.dumps({'format': fmt, 'password': JUST_RIGHT}),
            content_type='application/json')
        assert r.status_code == 200, r.data

    def test_a_ca_export_and_a_certificate_export_agree_at_the_floor(
            self, auth_client, create_cert, create_ca):
        cert = create_cert(cn='exportpw-agree.example.com')
        ca = create_ca(cn='ExportPW Agree CA')
        for length in (4, 7):
            password = 'x' * length
            on_cert = auth_client.post(
                f'/api/v2/certificates/{cert["id"]}/export',
                data=json.dumps({'format': 'pkcs12', 'password': password}),
                content_type='application/json')
            on_ca = auth_client.post(
                f'/api/v2/cas/{ca["id"]}/export',
                data=json.dumps({'format': 'pkcs12', 'password': password}),
                content_type='application/json')
            assert on_cert.status_code == on_ca.status_code == 400, (
                f'a {length}-character password: certificate export answered '
                f'{on_cert.status_code}, CA export answered '
                f'{on_ca.status_code}')

    def test_they_agree_at_the_ceiling(self, auth_client, create_cert, create_ca):
        cert = create_cert(cn='exportpw-ceiling.example.com')
        ca = create_ca(cn='ExportPW Ceiling CA')
        on_cert = auth_client.post(
            f'/api/v2/certificates/{cert["id"]}/export',
            data=json.dumps({'format': 'pkcs12', 'password': TOO_LONG}),
            content_type='application/json')
        on_ca = auth_client.post(
            f'/api/v2/cas/{ca["id"]}/export',
            data=json.dumps({'format': 'pkcs12', 'password': TOO_LONG}),
            content_type='application/json')
        assert on_cert.status_code == on_ca.status_code == 400, (
            f'{len(TOO_LONG)} characters: certificate export answered '
            f'{on_cert.status_code}, CA export answered {on_ca.status_code}')

    def test_a_key_export_still_takes_no_password_at_all(
            self, auth_client, create_ca):
        """An empty password on a private-key export means "do not encrypt",
        which is a deliberate answer and not a short password."""
        ca = create_ca(cn='ExportPW Plain CA')
        r = auth_client.post(
            f'/api/v2/cas/{ca["id"]}/export',
            data=json.dumps({'format': 'key', 'password': ''}),
            content_type='application/json')
        assert r.status_code == 200, r.data

    def test_a_user_certificate_export_refuses_a_long_password(
            self, auth_client, create_cert):
        """It had a floor and no ceiling, so it accepted what the CA route
        refused."""
        from utils.export_password import validate_export_password as _v
        assert _v(TOO_LONG) is not None


class TestTheRuleIsPublished:
    def test_the_policy_endpoint_answers(self, auth_client):
        r = auth_client.get('/api/v2/export/password-policy')
        assert r.status_code == 200, r.data
        data = (r.get_json() or {}).get('data') or {}
        assert data.get('min_length') == EXPORT_PASSWORD_MIN_LENGTH
        assert data.get('max_length') == EXPORT_PASSWORD_MAX_LENGTH

    def test_it_publishes_what_the_routes_enforce(self, auth_client, create_cert):
        data = (auth_client.get('/api/v2/export/password-policy')
                .get_json() or {}).get('data') or {}
        cert = create_cert(cn='exportpw-published.example.com')
        at_min = 'x' * data['min_length']
        below = 'x' * (data['min_length'] - 1)
        ok = auth_client.post(
            f'/api/v2/certificates/{cert["id"]}/export',
            data=json.dumps({'format': 'pkcs12', 'password': at_min}),
            content_type='application/json')
        refused = auth_client.post(
            f'/api/v2/certificates/{cert["id"]}/export',
            data=json.dumps({'format': 'pkcs12', 'password': below}),
            content_type='application/json')
        assert ok.status_code == 200, ok.data
        assert refused.status_code == 400, (
            'the published minimum is not the one the route applies')
