"""The Kerberos acceptor of XCEP and WSTEP in FIPS mode: refused outside a library built on OpenSSL.

The service key decrypts each ticket inside the Kerberos library, as the initiator's does: in FIPS
mode both bindings answer 503 before any token is read unless the libk5crypto python-gssapi runs
on hands its cryptography to the system OpenSSL. The library itself is faked here.
"""
import pytest

import fips_mode
from models import SystemConfig, WindowsEnrollmentProfile
from services import fips_preflight
from services.kerberos import negotiate_auth
from services.msca import kerberos
from tests.test_fips_preflight import installation, session  # noqa: F401  (fixtures)
from tests.windows_profile_support import restore, set_config, snapshot

PROBLEM = '/usr/lib/x86_64-linux-gnu/libk5crypto.so.3.1 does its own cryptography, outside the FIPS module'
XCEP_KRB_URL = '/ADPolicyProvider_CEP_Kerberos/service.svc'
WSTEP_KRB_URL = '/ADCertificateService_CES_Kerberos/service.svc'


@pytest.fixture(scope='module')
def bindings_on(app):
    keys = ('xcep_enabled', 'wstep_enabled')
    with app.app_context():
        previous = snapshot(keys)
        for key in keys:
            set_config(key, 'true')
    yield
    with app.app_context():
        restore(previous)


@pytest.fixture
def acceptor(monkeypatch, bindings_on):
    """A configured acceptor whose every Negotiate leg is recorded; ``acceptor(fips, problem)``."""
    legs = []
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda header, key: legs.append(header) or negotiate_auth.NegotiateResult('challenge'))

    def set_state(fips, problem):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: fips)
        monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: problem)
        return legs
    return set_state


@pytest.mark.parametrize('url', [XCEP_KRB_URL, WSTEP_KRB_URL], ids=['xcep', 'wstep'])
def test_fips_mode_refuses_both_bindings_before_any_token(client, acceptor, url):
    legs = acceptor(True, PROBLEM)
    r = client.post(url, headers={'Authorization': 'Negotiate dG9rZW4='})
    assert r.status_code == 503, r.data
    assert r.data == b'Kerberos binding not available in FIPS mode'
    assert legs == []


@pytest.mark.parametrize('url', [XCEP_KRB_URL, WSTEP_KRB_URL], ids=['xcep', 'wstep'])
@pytest.mark.parametrize('fips, problem', [(False, PROBLEM), (True, None)], ids=['standard', 'on-openssl'])
def test_outside_fips_mode_or_on_openssl_the_binding_negotiates(client, acceptor, url, fips, problem):
    legs = acceptor(fips, problem)
    r = client.post(url, headers={'Authorization': 'Negotiate dG9rZW4='})
    assert r.status_code == 401, r.data
    assert legs == ['Negotiate dG9rZW4=']


def test_the_refusal_names_the_library(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    assert negotiate_auth.fips_refusal() == f'Kerberos binding not available in FIPS mode: {PROBLEM}'
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    assert negotiate_auth.fips_refusal() is None


def test_the_acceptor_itself_refuses_a_token_in_fips_mode(monkeypatch):
    """Any caller of the acceptor, not only the two endpoints, gets no context."""
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    monkeypatch.setattr(negotiate_auth, '_new_acceptor', lambda: pytest.fail('an acceptor was built'))
    result = negotiate_auth.authenticate_negotiate('Negotiate dG9rZW4=', '192.0.2.1')
    assert result.status == 'failed' and PROBLEM in result.error


def test_the_profiles_show_the_fips_refusal(app, monkeypatch):
    from services import windows_profiles
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'not_configured_reason', lambda: None)
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    with app.app_context():
        assert windows_profiles.kerberos_binding_reason() == negotiate_auth.fips_refusal()
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: None)
    with app.app_context():
        assert windows_profiles.kerberos_binding_reason() is None


def test_policies_stop_offering_the_kerberos_binding(monkeypatch):
    """The CEP answer advertises Kerberos only where the binding serves: the same reason decides."""
    from api import xcep_protocol
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr('services.windows_profiles.kerberos_refusal', lambda profile: None)
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    assert xcep_protocol.kerberos_binding_offered(None) is False
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: None)
    assert xcep_protocol.kerberos_binding_offered(None) is True


# --- readiness check -----------------------------------------------------------------------

def _finding(report, detector_id):
    return next((f for f in report['findings'] if f['id'] == detector_id), None)


@pytest.fixture
def profiles(session):
    """Three profiles: one with a keytab, one disabled with a keytab, one without; the switch on."""
    from services.windows_profiles import keytab_holders
    assert keytab_holders() == [], 'this test owns the keytabs'
    rows = []
    for name, realm, enabled, keytab in (('krb-served', 'SERVED.TEST', True, b'\x05\x02one'),
                                         ('krb-off', 'OFF.TEST', False, b'\x05\x02two'),
                                         ('krb-none', 'NONE.TEST', True, None)):
        profile = WindowsEnrollmentProfile(name=name, realm=realm, enabled=enabled, is_default=False)
        profile.set_keytab(keytab)
        session.add(profile)
        rows.append(profile)
    switch = SystemConfig.query.filter_by(key='kerberos_enabled').first()
    if switch is None:
        switch = SystemConfig(key='kerberos_enabled')
        session.add(switch)
    switch.value = 'true'
    session.flush()
    return switch


@pytest.mark.parametrize('problem', [PROBLEM, None], ids=['outside', 'on-openssl'])
def test_profiles_with_a_keytab_block_fips_mode_outside_the_module(profiles, monkeypatch, problem):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: problem)
    report = fips_preflight.run()
    assert report['errors'] == []
    finding = _finding(report, 'kerberos.acceptor_outside_fips')
    if problem is None:
        assert finding is None
        return
    assert finding['severity'] == 'blocker' and finding['count'] == 1
    assert finding['examples'][0].startswith('krb-served (#') and finding['examples'][0].endswith(': SERVED.TEST')


def test_a_binding_switched_off_or_without_library_blocks_nothing(profiles, monkeypatch):
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: False)
    assert _finding(fips_preflight.run(), 'kerberos.acceptor_outside_fips') is None
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    profiles.value = 'false'
    assert _finding(fips_preflight.run(), 'kerberos.acceptor_outside_fips') is None
