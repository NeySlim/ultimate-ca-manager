"""An ACME issuing CA that was chosen but cannot sign refuses the order.

A CA chosen for a domain, or as the default, that has no private key is never
replaced by another CA: the order is refused as a server error and nothing is
issued. Only when nothing was chosen does the first CA able to sign issue.
"""
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SystemConfig, db
from models.acme_models import AcmeAccount, AcmeDomain, AcmeLocalDomain, AcmeOrder, DnsProvider
from services.acme.acme_service import AcmeService

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

KEY = 'acme.issuing_ca_id'
NO_KEY = 'has no private key'
_FORMS = {'refid': lambda ca: ca.refid, 'id': lambda ca: str(ca.id), 'padded': lambda ca: f' +0{ca.id} '}


@pytest.fixture
def default_setting(app):
    """acme.issuing_ca_id as the test sets it, put back afterwards."""
    with app.app_context():
        row = SystemConfig.query.filter_by(key=KEY).first()
        before = None if row is None else row.value
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key=KEY).first()
        if before is None:
            if row is not None:
                db.session.delete(row)
        else:
            row.value = before
        db.session.commit()


def _set_default(value):
    row = SystemConfig.query.filter_by(key=KEY).first()
    if row is None:
        db.session.add(SystemConfig(key=KEY, value=value))
    else:
        row.value = value
    db.session.commit()


def _drop_key(ca_id):
    ca = db.session.get(CA, ca_id)
    ca.prv = None
    ca.hsm_key_id = None
    db.session.commit()
    assert not ca.has_private_key
    return ca


def _domain():
    return f'w{uuid.uuid4().hex[:12]}.example.com'


def _finalize(monkeypatch, domain, **kwargs):
    """(success, error, service, order) of finalizing a fresh order for *domain*."""
    from utils import caa_checker
    monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
    acct = AcmeAccount(jwk='{}', jwk_thumbprint=uuid.uuid4().hex + uuid.uuid4().hex[:11], status='valid')
    db.session.add(acct)
    db.session.flush()
    order = AcmeOrder(account_id=acct.account_id, status='ready',
                      identifiers=json.dumps([{'type': 'dns', 'value': domain}]))
    db.session.add(order)
    db.session.commit()
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), False)
           .sign(key, hashes.SHA256()))
    service = AcmeService(base_url='http://localhost')
    assert service.begin_order_processing(order)
    service._finalizing_order_id = order.order_id
    try:
        success, error = service.finalize_order(
            order.order_id, csr.public_bytes(serialization.Encoding.PEM).decode(), **kwargs)
    finally:
        service._finalizing_order_id = None
    db.session.refresh(order)
    return success, error, service, order


def _issuer_refid(order):
    return db.session.get(Certificate, order.certificate_id).caref


def _assert_refused(success, error, service, order, words):
    assert not success
    assert words in error, error
    # RFC 8555 §7.4: a server-side failure; the route puts the order back to ready
    assert service._last_finalize_error_type == 'serverInternal'
    assert order.status == 'processing' and order.certificate_id is None


def test_a_local_domain_ca_without_key_refuses_despite_a_valid_default(app, monkeypatch, create_ca,
                                                                        default_setting):
    valid = create_ca(cn='Valid ACME default')
    chosen = create_ca(cn='Local domain CA without key')
    domain = _domain()
    with app.app_context():
        _set_default(db.session.get(CA, valid['id']).refid)
        _drop_key(chosen['id'])
        db.session.add(AcmeLocalDomain(domain=domain, issuing_ca_id=chosen['id']))
        db.session.commit()
        result = _finalize(monkeypatch, domain)
        _assert_refused(*result, words=NO_KEY)
        assert domain in result[1]


def test_a_dns_domain_ca_without_key_refuses_despite_a_valid_default(app, monkeypatch, create_ca,
                                                                      default_setting):
    valid = create_ca(cn='Valid ACME default for DNS')
    chosen = create_ca(cn='DNS domain CA without key')
    domain = _domain()
    with app.app_context():
        _set_default(db.session.get(CA, valid['id']).refid)
        _drop_key(chosen['id'])
        provider = DnsProvider(name=f'manual-{uuid.uuid4().hex[:8]}', provider_type='manual')
        db.session.add(provider)
        db.session.flush()
        mapping = AcmeDomain(domain=domain, dns_provider_id=provider.id, issuing_ca_id=chosen['id'])
        db.session.add(mapping)
        db.session.commit()
        try:
            result = _finalize(monkeypatch, domain)
            _assert_refused(*result, words=NO_KEY)
            assert domain in result[1]
        finally:
            db.session.delete(mapping)
            db.session.commit()
            db.session.delete(provider)
            db.session.commit()


@pytest.mark.parametrize('form', sorted(_FORMS))
def test_a_default_ca_without_key_refuses(app, monkeypatch, create_ca, default_setting, form):
    """Each form of the value names the keyless CA: the refusal says so, never 'no longer exists'."""
    create_ca(cn='A CA able to sign')
    chosen = create_ca(cn=f'Default ACME CA without key ({form})')
    with app.app_context():
        ca = _drop_key(chosen['id'])
        _set_default(_FORMS[form](ca))
        success, error, service, order = _finalize(monkeypatch, _domain())
        _assert_refused(success, error, service, order, words=NO_KEY)
        assert 'ACME settings' in error and 'no longer exists' not in error


def test_a_domain_choice_able_to_sign_wins_over_an_unusable_default(app, monkeypatch, create_ca,
                                                                     default_setting):
    chosen = create_ca(cn='Local domain CA able to sign')
    keyless = create_ca(cn='Default ACME CA without key, unused')
    domain = _domain()
    with app.app_context():
        _set_default(_drop_key(keyless['id']).refid)
        db.session.add(AcmeLocalDomain(domain=domain, issuing_ca_id=chosen['id']))
        db.session.commit()
        success, error, _service, order = _finalize(monkeypatch, domain)
        assert success, error
        assert _issuer_refid(order) == db.session.get(CA, chosen['id']).refid


def test_nothing_chosen_signs_with_the_first_ca_able_to_sign(app, monkeypatch, create_ca, default_setting):
    """Today's behaviour kept: no domain mapping and no default, the lowest-numbered CA able to sign."""
    create_ca(cn='Some CA able to sign')
    with app.app_context():
        _set_default('')
        able = [c for c in CA.query.order_by(CA.id.asc())
                if c.has_private_key and c.crt and not c.offline and not c.revoked_in_chain]
        success, error, _service, order = _finalize(monkeypatch, _domain())
        assert success, error
        assert _issuer_refid(order) == able[0].refid


def test_the_refusal_issues_and_counts_nothing(app, monkeypatch, create_ca, default_setting):
    create_ca(cn='A CA that would have signed')
    chosen = create_ca(cn='Default ACME CA without key, counted')
    with app.app_context():
        _set_default(_drop_key(chosen['id']).refid)
        certificates = Certificate.query.count()
        counted = db.session.query(db.func.coalesce(db.func.sum(CA.serial), 0)).scalar()
        success, error, service, order = _finalize(monkeypatch, _domain())
        _assert_refused(success, error, service, order, words=NO_KEY)
        assert Certificate.query.count() == certificates
        assert db.session.query(db.func.coalesce(db.func.sum(CA.serial), 0)).scalar() == counted


def test_a_resumed_approval_whose_ca_lost_its_key_is_not_signed_by_another(app, monkeypatch, create_ca,
                                                                           default_setting):
    """The approval carries the CA retained when the order was held: never another one."""
    create_ca(cn='A CA able to sign, not held')
    held = create_ca(cn='Held ACME CA that lost its key')
    with app.app_context():
        _set_default('')
        ca = _drop_key(held['id'])
        success, error, service, order = _finalize(monkeypatch, _domain(), ca_refid=ca.refid,
                                                   approval=object())
        _assert_refused(success, error, service, order, words=NO_KEY)
