"""EST and SCEP renewals ask the connector of the renewed SID's domain, and only it (A9): a
domain no connector serves carries the SID over as is; a connector whose domain is unknown
(a migrated row never tested) is asked only for a SID of no known domain. WSTEP applies the
same rule within the connector of the certificate's profile, never another (C-05)."""
import base64

import pytest
from cryptography import x509

from models import CA, ADConnectorConfig, db
from services.ad_connector import lookup as ad_lookup
from services.ad_connector import renewal_identity
from services.trust_store.csr_operations_mixin import _ad_security_extension
from tests.ad_connector_support import add_connector, clear_connectors
from tests.test_est_rfc7030 import est_config  # noqa: F401
from tests.test_protocol_renewal_sid import (
    _count, _est_leaf, _est_reenrol, _issue, _scep_renew, _sid_ext, scep_ca,  # noqa: F401
)
from tests.test_scep_rfc8894_operations import PKI_STATUS_OID, _decrypt_response
from tests.test_wstep_renew import wstep_renew_config  # noqa: F401
from tests.test_wstep_renewal_sid import _issued, _renew_tls
from tests.test_wstep_renewal_sid import _issue as _wstep_issue
from tests.test_wstep_renewal_sid import _sid_ext as _wstep_sid_ext
from tests.windows_profile_support import connectors_kept
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

DOMAIN_A = 'S-1-5-21-1111111111-2222222222-3333333333'
DOMAIN_B = 'S-1-5-21-4444444444-5555555555-6666666666'
DOMAIN_C = 'S-1-5-21-7777777777-8888888888-9999999999'
SID_B, SID_C = DOMAIN_B + '-1105', DOMAIN_C + '-1105'


@pytest.fixture(autouse=True)
def _own_connectors(app):
    with connectors_kept(app):
        with app.app_context():
            clear_connectors()
        yield


@pytest.fixture(autouse=True)
def _a_default_profile(app):
    """A default profile for ``link=True`` to point at; removed when this file made it."""
    from models import WindowsEnrollmentProfile
    from tests.windows_profile_support import default_profile
    with app.app_context():
        made = default_profile() is None
        default_profile(create=True)
        db.session.commit()
        profile_id = default_profile().id
    yield
    if made:
        with app.app_context():
            WindowsEnrollmentProfile.query.filter_by(id=profile_id).delete()
            db.session.commit()


@pytest.fixture
def forests(app):
    """A (the default profile's) and B, both enabled and of a known domain."""
    with app.app_context():
        a = add_connector('forest-a', server='dc.a.example', base_dn='DC=a,DC=example', bind_dn='svc',
                          enabled=True, domain_sid=DOMAIN_A, link=True)
        b = add_connector('forest-b', server='dc.b.example', base_dn='DC=b,DC=example', bind_dn='svc',
                          enabled=True, domain_sid=DOMAIN_B)
        return {'a': a.id, 'b': b.id}


def _asked(monkeypatch, answer='HOST$'):
    asked = []

    def lookup_account_by_sid(config, sid):
        asked.append(config.id)
        return answer(config) if callable(answer) else answer
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lookup_account_by_sid)
    return asked


# Criterion 1
def test_an_est_renewal_asks_the_connector_of_the_sid_domain_only(client, app, est_config, forests, monkeypatch):
    asked = _asked(monkeypatch)
    old, key = _issue(app, est_config['id'], 'route-est-b.example.test', sid=SID_B)
    assert _sid_ext(_est_leaf(_est_reenrol(client, old, key))) == _ad_security_extension(SID_B).value
    assert asked == [forests['b']]


def test_a_scep_renewal_asks_the_connector_of_the_sid_domain_only(app, scep_ca, forests, monkeypatch):
    asked = _asked(monkeypatch)
    (ca, ca_cert), ca_id = scep_ca
    old, old_key = _issue(app, ca_id, 'route-scep-b.example.test', sid=SID_B)
    attrs, response = _scep_renew(ca, ca_cert, old, old_key)
    assert attrs[PKI_STATUS_OID] == '0'
    from cryptography.hazmat.primitives.serialization import pkcs7
    renewed = pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, old_key, old))[0]
    assert _sid_ext(renewed) == _ad_security_extension(SID_B).value
    assert asked == [forests['b']]


def test_a_wstep_renewal_asks_the_connector_of_its_profile_only(client, app, wstep_renew_config, forests,
                                                                monkeypatch):
    """The default profile's connector is A's: a SID of A is checked there; one of B is carried
    over, since no connector of the profile serves B, and B's connector is never asked."""
    asked = _asked(monkeypatch)
    for sid, expected in ((DOMAIN_A + '-1105', [forests['a']]), (SID_B, [])):
        old, key = _wstep_issue(app, wstep_renew_config['id'], f'route-wstep-{len(expected)}.example.test', sid=sid)
        renewed = _issued(_renew_tls(client, old, key))
        assert _wstep_sid_ext(renewed).value.value == _ad_security_extension(sid).value
        assert asked == expected
        asked.clear()


# Criterion 2: a domain no connector serves
def test_an_est_renewal_of_a_domain_without_connector_carries_the_sid(client, app, est_config, forests, monkeypatch):
    asked = _asked(monkeypatch, ad_lookup.NO_ACCOUNT)
    old, key = _issue(app, est_config['id'], 'route-est-c.example.test', sid=SID_C)
    assert _sid_ext(_est_leaf(_est_reenrol(client, old, key))) == _ad_security_extension(SID_C).value
    assert asked == []


def test_a_scep_renewal_of_a_domain_without_connector_carries_the_sid(app, scep_ca, forests, monkeypatch):
    asked = _asked(monkeypatch, ad_lookup.NO_ACCOUNT)
    (ca, ca_cert), ca_id = scep_ca
    old, old_key = _issue(app, ca_id, 'route-scep-c.example.test', sid=SID_C)
    attrs, _response = _scep_renew(ca, ca_cert, old, old_key)
    assert attrs[PKI_STATUS_OID] == '0'
    assert asked == []


def test_a_wstep_renewal_of_a_domain_without_connector_carries_the_sid(client, app, wstep_renew_config, forests,
                                                                       monkeypatch):
    asked = _asked(monkeypatch, ad_lookup.NO_ACCOUNT)
    old, key = _wstep_issue(app, wstep_renew_config['id'], 'route-wstep-c.example.test', sid=SID_C)
    assert _wstep_sid_ext(_issued(_renew_tls(client, old, key))).value.value == _ad_security_extension(SID_C).value
    assert asked == []


# Criterion 2: the domain's connector is active and the account is gone (codes of S-20)
def test_an_est_renewal_whose_account_is_gone_from_its_domain_is_refused(client, app, est_config, forests,
                                                                         monkeypatch):
    asked = _asked(monkeypatch, lambda config: 'HOST$' if config.id == forests['a'] else ad_lookup.NO_ACCOUNT)
    old, key = _issue(app, est_config['id'], 'route-est-gone.example.test', sid=SID_B)
    before = _count(app)
    r = _est_reenrol(client, old, key)
    assert r.status_code == 400 and renewal_identity.NOT_FOUND_MESSAGE.encode() in r.data
    assert asked == [forests['b']] and _count(app) == before


def test_a_scep_renewal_whose_account_is_gone_from_its_domain_is_refused(app, scep_ca, forests, monkeypatch):
    asked = _asked(monkeypatch, lambda config: 'HOST$' if config.id == forests['a'] else ad_lookup.NO_ACCOUNT)
    (ca, ca_cert), ca_id = scep_ca
    old, old_key = _issue(app, ca_id, 'route-scep-gone.example.test', sid=SID_B)
    before = _count(app)
    attrs, _response = _scep_renew(ca, ca_cert, old, old_key)
    assert attrs[PKI_STATUS_OID] == '2'
    assert asked == [forests['b']] and _count(app) == before


def test_a_wstep_renewal_whose_account_is_gone_from_its_domain_is_refused(client, app, wstep_renew_config, forests,
                                                                          monkeypatch):
    asked = _asked(monkeypatch, lambda config: 'HOST$' if config.id == forests['b'] else ad_lookup.NO_ACCOUNT)
    old, key = _wstep_issue(app, wstep_renew_config['id'], 'route-wstep-gone.example.test', sid=DOMAIN_A + '-1105')
    before = _count(app)
    r = _renew_tls(client, old, key)
    assert r.status_code == 400 and renewal_identity.NOT_FOUND_MESSAGE.encode() in r.data
    assert asked == [forests['a']] and _count(app) == before


# Criterion 4: the rule for disabled connectors and connectors of unknown domain
def _requester_sid(app, create_ca, sid):
    ca_data = create_ca(cn='SID routing rule CA')
    old, _key = _issue(app, ca_data['id'], 'route-rule.example.test', sid=sid)
    with app.app_context():
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(db.session.get(CA, ca_data['id']).crt))
        return renewal_identity.renewal_requester_sid(old, ca_cert, 'TEST')


def _connector(name, **values):
    defaults = {'server': f'dc.{name}.example', 'base_dn': f'DC={name},DC=example', 'bind_dn': 'svc',
                'enabled': True}
    return add_connector(name, **{**defaults, **values}).id


def test_a_disabled_connector_serves_its_domain_with_no_check(app, create_ca, monkeypatch):
    """Disabled is what 2.x did with its one connector off: the SID is carried over, and a
    connector of unknown domain is not asked in its place since the domain is known."""
    asked = _asked(monkeypatch, ad_lookup.NO_ACCOUNT)
    with app.app_context():
        _connector('b', domain_sid=DOMAIN_B, enabled=False)
        _connector('u', link=True)
    assert _requester_sid(app, create_ca, SID_B) == SID_B
    assert asked == []


def test_a_connector_of_unknown_domain_is_asked_only_for_a_sid_of_no_known_domain(app, create_ca, monkeypatch):
    """A migrated single connector keeps checking its renewals until a test reads its domain SID."""
    asked = _asked(monkeypatch)
    with app.app_context():
        b = _connector('b', domain_sid=DOMAIN_B)
        other = _connector('other')
        unknown = _connector('u', link=True)
    assert _requester_sid(app, create_ca, SID_B) == SID_B
    assert asked == [b]
    asked.clear()
    assert _requester_sid(app, create_ca, SID_C) == SID_C
    assert asked == [unknown]  # the default profile's first, the first found ends the search
    asked.clear()
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid',
                        lambda config, sid: asked.append(config.id) or ad_lookup.NO_ACCOUNT)
    with pytest.raises(renewal_identity.RenewalAccountGone):
        _requester_sid(app, create_ca, SID_C)
    assert asked == [unknown, other]


def test_a_domain_served_by_two_connectors_needs_the_account_in_one(app, create_ca, monkeypatch):
    """Two base DNs in one domain each see part of it: one finding the account is enough, a
    directory that did not answer is a fault only when no other found it."""
    with app.app_context():
        first = _connector('b1', domain_sid=DOMAIN_B)
        second = _connector('b2', domain_sid=DOMAIN_B)
    answers = {first: ad_lookup.UNREACHABLE, second: 'HOST$'}
    _asked(monkeypatch, lambda config: answers[config.id])
    assert _requester_sid(app, create_ca, SID_B) == SID_B
    answers[second] = ad_lookup.NO_ACCOUNT
    with pytest.raises(renewal_identity.RenewalIdentityUnresolved):
        _requester_sid(app, create_ca, SID_B)


def test_no_connector_at_all_carries_the_sid(app, create_ca, monkeypatch):
    asked = _asked(monkeypatch, ad_lookup.NO_ACCOUNT)
    with app.app_context():
        assert ADConnectorConfig.query.count() == 0
    assert _requester_sid(app, create_ca, SID_B) == SID_B
    assert asked == []
