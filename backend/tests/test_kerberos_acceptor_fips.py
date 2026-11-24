"""The Kerberos acceptor of XCEP and WSTEP in FIPS mode: refused outside a library built on OpenSSL.

The service key decrypts each ticket inside the Kerberos library, as the initiator's does: in FIPS
mode both bindings answer 503 before any token is read unless the libk5crypto python-gssapi runs
on hands its cryptography to the system OpenSSL. The library itself is faked here.
"""
import pytest

import fips_mode
from models import SystemConfig, WindowsEnrollmentProfile, db
from services import fips_preflight
from services.kerberos import negotiate_auth
from services.msca import kerberos
from tests.keytab_support import keytab
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


HOST = 'ucm.example.test'


def _switch(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        row = SystemConfig(key=key)
        db.session.add(row)
    row.value = value
    return row


@pytest.fixture
def profiles(session, monkeypatch, tmp_path):
    """A profile in each serving state, the switch on, an SPN set, and the node's file holding the
    key of SHARED.TEST only; ``profiles.switch`` and ``profiles.spn`` are the two settings."""
    from services.windows_profiles import default_profile, keytab_holders
    assert keytab_holders() == [], 'this test owns the keytabs'
    served = tmp_path / 'kerberos.keytab'
    served.write_bytes(keytab(f'HTTP/{HOST}@SHARED.TEST'))
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', served)
    for name, realm, enabled, own in (('krb-own', 'OWN.TEST', True, b'\x05\x02one'),
                                      ('krb-shared', 'SHARED.TEST', True, None),
                                      ('krb-off', 'OFF.TEST', False, b'\x05\x02two'),
                                      ('krb-keyless', 'NONE.TEST', True, None)):
        profile = WindowsEnrollmentProfile(name=name, realm=realm, enabled=enabled, is_default=False)
        profile.set_keytab(own)
        session.add(profile)
    # The default profile without a realm is refused (NO_REALM), keytab or not
    default = default_profile()
    if default is None:
        default = WindowsEnrollmentProfile(name='krb-default', is_default=True)
        session.add(default)
    default.realm, default.enabled = None, True
    default.set_keytab(b'\x05\x02three')
    state = type('State', (), {})()
    state.switch = _switch('kerberos_enabled', 'true')
    state.spn = _switch('kerberos_spn', f'HTTP/{HOST}@SHARED.TEST')
    session.flush()
    return state


def _served_examples():
    finding = _finding(fips_preflight.run(), 'kerberos.acceptor_outside_fips')
    return None if finding is None else [e.split(' (#')[0] + e.rpartition(')')[2] for e in finding['examples']]


@pytest.mark.parametrize('problem', [PROBLEM, None], ids=['outside', 'on-openssl'])
def test_profiles_the_acceptor_serves_block_fips_mode_outside_the_module(profiles, monkeypatch, problem):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: problem)
    report = fips_preflight.run()
    assert report['errors'] == []
    finding = _finding(report, 'kerberos.acceptor_outside_fips')
    if problem is None:
        assert finding is None
        return
    assert finding['severity'] == 'blocker' and finding['count'] == 2


def test_exactly_the_profiles_served_are_listed(profiles, monkeypatch):
    """Its own keytab, or its realm's key in the served file; never a disabled profile, one with
    no key for its realm, nor the default profile without a realm."""
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    assert _served_examples() == ['krb-own: OWN.TEST', 'krb-shared: SHARED.TEST']


def test_a_served_file_that_cannot_be_read_serves_only_the_profiles_with_a_keytab(profiles, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    negotiate_auth.KEYTAB_PATH.write_bytes(b'not a keytab')
    assert _served_examples() == ['krb-own: OWN.TEST']


def test_a_binding_switched_off_without_spn_file_or_library_blocks_nothing(profiles, monkeypatch):
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: False)
    assert _served_examples() is None
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    assert _served_examples() is not None
    profiles.spn.value = ''
    assert _served_examples() is None
    profiles.spn.value = f'HTTP/{HOST}@SHARED.TEST'
    negotiate_auth.KEYTAB_PATH.unlink()
    assert _served_examples() is None
    negotiate_auth.KEYTAB_PATH.write_bytes(keytab(f'HTTP/{HOST}@SHARED.TEST'))
    profiles.switch.value = 'false'
    assert _served_examples() is None
