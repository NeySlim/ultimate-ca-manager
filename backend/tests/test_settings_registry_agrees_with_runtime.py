"""The settings screen reports what the running system resolves.

`SystemConfig` is a bare key/value table. Every reader hand-rolled its own
query, coercion and fallback, and the settings API drifted furthest because it
restates the defaults as literals in its GET handler instead of asking the
code that uses them. The screen said timestamping was off while `/tsa` was
serving; it said accounts locked for 300 seconds while the enforcer locked for
900; it said the ACME directory was published on 443 while the directory URL
advertised 8443; it reported an empty log list where the certificate
transparency client reads "absent" as "use the built-in logs".

`services/settings_registry.py` holds each key's default and how a stored
value is read, and the API asks it. The registry records what the reader that
*decides* already does, so what changed is what the screen reports.

Two keys in the same survey are **not** divergences and are left alone; the
last class says why.
"""
import json

import pytest

from models import db, SystemConfig
from services.settings_registry import SETTINGS, default_for, effective


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row:
            db.session.delete(row)
    elif row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


@pytest.fixture
def cfg(app):
    """Set keys for one test and put back whatever was there."""
    saved = {}

    def _apply(**pairs):
        with app.app_context():
            for name, value in pairs.items():
                key = name.replace('__', '.')
                row = SystemConfig.query.filter_by(key=key).first()
                saved.setdefault(key, row.value if row else None)
                _set(key, value)

    yield _apply

    with app.app_context():
        for key, value in saved.items():
            _set(key, value)


def _general(auth_client):
    r = auth_client.get('/api/v2/settings/general')
    assert r.status_code == 200, r.data
    return json.loads(r.data)['data']


class TestTheScreenAgreesWithTheRuntime:
    def test_timestamping(self, app, auth_client, cfg):
        cfg(tsa_enabled=None)
        from services.tsa_service import tsa_is_enabled
        with app.app_context():
            runtime = tsa_is_enabled()
        api = json.loads(auth_client.get('/api/v2/tsa/config').data)['data']['enabled']
        assert (runtime, api) == (True, True)

        # Only the exact word turns it off, on both sides.
        cfg(tsa_enabled='yes')
        with app.app_context():
            runtime = tsa_is_enabled()
        api = json.loads(auth_client.get('/api/v2/tsa/config').data)['data']['enabled']
        assert (runtime, api) == (False, False)

    def test_account_lockout(self, app, auth_client, cfg):
        cfg(lockout_duration=None)
        from api.v2.sso.helpers import _get_lockout_settings
        with app.app_context():
            runtime = _get_lockout_settings()[1]
        assert runtime == _general(auth_client)['lockout_duration'] == 900

    def test_the_advertised_acme_port(self, app, auth_client, cfg):
        from utils.public_endpoints import get_acme_public_port
        for stored in (None, '', 'garbage'):
            cfg(acme_public_port=stored)
            with app.app_context():
                runtime = get_acme_public_port()
            assert _general(auth_client)['acme_public_port'] == runtime, stored

    def test_certificate_transparency_logs(self, app, auth_client, cfg):
        cfg(ct_log_urls=None)
        api = json.loads(auth_client.get('/api/v2/settings/ct').data)['data']['log_urls']
        # None, not [] — the client reads absent as "use the built-in logs",
        # and an empty list reads as "no logs configured".
        assert api is None
        with app.app_context():
            assert effective('ct_log_urls') is None

    def test_mutual_tls(self, app, auth_client, cfg):
        """Strict, because it is the TLS socket that decides."""
        from services.mtls_auth_service import MTLSAuthService
        for stored, expected in (('yes', False), ('1', False),
                                 ('true', True), ('false', False), (None, False)):
            cfg(mtls_enabled=stored)
            with app.app_context():
                runtime = MTLSAuthService.is_mtls_enabled()
            api = json.loads(
                auth_client.get('/api/v2/mtls/settings').data)['data']['enabled']
            assert (runtime, api) == (expected, expected), stored

    @pytest.mark.parametrize('key,method', [
        ('crl_auto_delete_expired_revoked', 'is_auto_delete_enabled'),
        ('crl_auto_purge_stale_serials', 'is_purge_stale_serials_enabled'),
    ])
    def test_crl_housekeeping(self, app, auth_client, cfg, key, method):
        from services.crl.query import CRLQueryMixin
        for stored, expected in (('yes', True), ('on', True), ('1', True),
                                 ('false', False), (None, False)):
            cfg(**{key: stored})
            with app.app_context():
                runtime = getattr(CRLQueryMixin, method)()
            assert (runtime, _general(auth_client)[key]) == (expected, expected), stored

    @pytest.mark.parametrize('key,reading', [
        ('hsts_enabled', lambda header: header is not None),
        ('hsts_include_subdomains', lambda header: 'includeSubDomains' in header),
    ])
    def test_strict_transport_security(self, app, auth_client, cfg, key, reading):
        from utils.hsts import build_hsts_header
        for stored, expected in (('yes', True), ('off', False),
                                 ('false', False), (None, True)):
            cfg(**{key: stored})
            with app.app_context():
                runtime = reading(build_hsts_header())
            assert (runtime, _general(auth_client)[key]) == (expected, expected), stored

    def test_the_acme_server_switch(self, app, auth_client, cfg):
        """The dashboard tile's reading, which is the documented intent."""
        for stored, expected in (('yes', True), ('true', True),
                                 ('false', False), ('0', False), (None, True)):
            cfg(acme__enabled=stored)
            api = json.loads(auth_client.get('/api/v2/acme/settings').data)['data']['enabled']
            with app.app_context():
                assert effective('acme.enabled') is expected, stored
            assert api is expected, stored

    def test_the_clock_display_preference(self, app, auth_client, cfg):
        """Ask the reader that decides, not a copy of it.

        This used to restate `row.value != 'false'` inline and parametrise
        the three words where that copy and the registry happen to agree.
        `0`, `no` and `off` are the ones where they did not, and the copy is
        why the test could not see it: it was checking itself.
        """
        from auth.session_payload import display_settings

        for stored, expected in (('yes', True), ('true', True),
                                 ('false', False), ('0', False),
                                 ('no', False), ('off', False), (None, True)):
            cfg(show_time=stored)
            with app.app_context():
                auth_reader = display_settings()['show_time']
            assert (auth_reader, _general(auth_client)['show_time']) == \
                (expected, expected), stored


class TestTheRegistryItself:
    def test_an_unknown_key_is_a_failure_not_a_silent_default(self):
        with pytest.raises(KeyError):
            effective('no.such.setting')

    def test_a_computed_default_is_resolved_not_returned_as_a_callable(self, app):
        with app.app_context():
            assert isinstance(default_for('acme_public_port'), int)

    def test_every_entry_says_why_it_is_what_it_is(self):
        missing = [key for key, setting in SETTINGS.items() if not setting.why]
        assert missing == []

    def test_a_blank_row_reads_as_absent(self, app, cfg):
        cfg(lockout_duration='   ')
        with app.app_context():
            assert effective('lockout_duration') == 900

    def test_an_unparsable_number_falls_back_rather_than_raising(self, app, cfg):
        cfg(lockout_duration='not-a-number')
        with app.app_context():
            assert effective('lockout_duration') == 900


class TestWhatWasNotACollapsibleDivergence:
    """Two keys in the survey answer different questions on each side."""

    def test_the_renewal_lead_time_was_already_the_same_number(self, app, cfg):
        """ARI passes None and resolves it to 30 one layer down."""
        cfg(auto_renewal_days=None)
        from services.auto_renewal_service import AutoRenewalService
        from services.acme import ari
        with app.app_context():
            scheduler = AutoRenewalService.get_renewal_config()['days_before_expiry']
        assert scheduler == ari._DEFAULT_RENEW_BEFORE_DAYS == default_for('auto_renewal_days')

    def test_the_acme_client_address_keeps_its_placeholder(self, app, cfg):
        """"What did the operator configure" and "what do I register with"
        are different questions; an installation that set no address still
        has to be able to create its account row."""
        cfg(acme__client__email=None)
        with app.app_context():
            assert effective('acme.client.email') == 'admin@localhost'
            row = SystemConfig.query.filter_by(key='acme.client.email').first()
            assert row is None      # the settings API still reports "unset"
