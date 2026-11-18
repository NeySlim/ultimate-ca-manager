"""What a renewal does with the RelatedCertificate extension (RFC 9763 §4.1), said to the caller.

A certificate whose extension named a certificate since replaced renews naming nothing and the
result says why; one whose named certificate is held but unreadable is refused, nothing written.
"""
import base64
import logging

import pytest
from cryptography import x509

from models import AuditLog, Certificate, db
from tests.test_approval_on_sign_and_renew import _json
from tests.test_renewal_overtaken import _auto_pass, _linked_rows

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

UNREADABLE = base64.b64encode(b'not a certificate').decode()


def _a_replaced_since(app):
    """``(a_id, old_b)``: A renewed with its newest B, so the older B's extension hashes a
    certificate no row holds any more."""
    from services.cert.renewal import renew_certificate_in_place
    a_id, (old_b, _new_b) = _linked_rows(app, n_b=2)
    with app.app_context():
        renew_certificate_in_place(db.session.get(Certificate, a_id), username='admin',
                                   regenerate_crl=False)
        db.session.remove()
    return a_id, old_b


def _names_none(app, cert_id):
    from utils.related_cert import read_related_certificate
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        named = read_related_certificate(x509.load_pem_x509_certificate(base64.b64decode(row.crt)))
        linked = row.related_certificate_id
        db.session.remove()
    return named is None and linked is None


def _said(text, cert_id):
    return (f'Certificate {cert_id} was renewed without its RelatedCertificate extension' in text
            and 'has been replaced or removed' in text)


def _renewed_audit(app, cert_id):
    with app.app_context():
        rows = AuditLog.query.filter_by(action='certificate_renewed', resource_id=str(cert_id)).all()
        details = [r.details for r in rows]
        db.session.remove()
    return details


def test_a_manual_renewal_says_the_named_certificate_was_replaced(app, auth_client):
    _a_id, old_b = _a_replaced_since(app)
    r = _json(auth_client, 'post', f'/api/v2/certificates/{old_b}/renew', {})
    assert r.status_code == 200, r.get_json()
    notices = r.get_json()['meta']['notices']
    assert any(_said(n, old_b) for n in notices), notices
    assert _names_none(app, old_b)
    assert any(_said(d, old_b) for d in _renewed_audit(app, old_b))


def test_a_bulk_renewal_says_the_named_certificate_was_replaced(app, auth_client):
    _a_id, old_b = _a_replaced_since(app)
    r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': [old_b]})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()['data']
    assert data['success'] == [old_b] and data['failed'] == []
    [entry] = data['notices']
    assert entry['id'] == old_b and any(_said(n, old_b) for n in entry['notices']), entry
    assert _names_none(app, old_b)


def test_a_scheduled_renewal_logs_that_the_named_certificate_was_replaced(app, monkeypatch, caplog):
    _a_id, old_b = _a_replaced_since(app)
    with caplog.at_level(logging.INFO, logger='services.auto_renewal_service'):
        stats, _sent, _audits = _auto_pass(app, monkeypatch, old_b)
    assert stats['renewed'] == 1, stats
    assert any(_said(r.getMessage(), old_b) for r in caplog.records
               if r.name == 'services.auto_renewal_service'), caplog.text
    assert _names_none(app, old_b)
    assert any(_said(d, old_b) for d in _renewed_audit(app, old_b))


def test_a_renewal_naming_a_current_certificate_says_nothing_of_it(app, auth_client):
    """The pair renewed together: B' names A', no notice about the extension."""
    _a_id, (b_id,) = _linked_rows(app)
    r = _json(auth_client, 'post', f'/api/v2/certificates/{b_id}/renew', {})
    assert r.status_code == 200, r.get_json()
    notices = (r.get_json().get('meta') or {}).get('notices') or []
    assert not any('RelatedCertificate' in n for n in notices), notices


def _a_unreadable(app, held=True):
    """``(a_id, b_id, before)``: B names A and A's stored certificate cannot be decoded; A's
    key not held unless *held*, so B renews alone. *before* is what both rows hold."""
    a_id, (b_id,) = _linked_rows(app)
    with app.app_context():
        a = db.session.get(Certificate, a_id)
        a.crt = UNREADABLE
        if not held:
            a.prv = None
        db.session.commit()
        db.session.remove()
    return a_id, b_id, _rows(app, a_id, b_id)


def _rows(app, *ids):
    with app.app_context():
        out = [(r.crt, r.serial_number, r.related_certificate_id, r.renewed_times)
               for r in (db.session.get(Certificate, i) for i in ids)]
        db.session.remove()
    return out


def _refusal(text, a_id):
    return f'Related certificate {a_id} cannot be read' in text


@pytest.mark.parametrize('held', [True, False])
def test_a_manual_renewal_naming_an_unreadable_certificate_is_refused(app, auth_client, held):
    a_id, b_id, before = _a_unreadable(app, held)
    r = _json(auth_client, 'post', f'/api/v2/certificates/{b_id}/renew', {})
    assert r.status_code == 409, r.get_json()
    assert _refusal(r.get_json()['message'], a_id), r.get_json()
    assert _rows(app, a_id, b_id) == before


@pytest.mark.parametrize('held', [True, False])
def test_a_bulk_renewal_naming_an_unreadable_certificate_is_refused(app, auth_client, held):
    a_id, b_id, before = _a_unreadable(app, held)
    r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': [b_id]})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()['data']
    assert data['success'] == [] and [f['id'] for f in data['failed']] == [b_id], data
    assert _refusal(data['failed'][0]['error'], a_id), data
    assert _rows(app, a_id, b_id) == before


def test_a_scheduled_renewal_naming_an_unreadable_certificate_fails_and_goes_on(app, monkeypatch):
    """The pass audits the refusal and renews the next certificate."""
    from services.auto_renewal_service import AutoRenewalService as svc
    from tests.test_renewal_concurrency_pg import _leaf
    a_id, b_id, before = _a_unreadable(app, held=False)
    lone_id, _, _ = _leaf(app)
    lone_before = _rows(app, lone_id)
    reasons = []
    monkeypatch.setattr(svc, '_log_failure', staticmethod(
        lambda cert_id, cn, reason: reasons.append((cert_id, reason))))
    monkeypatch.setattr(svc, '_send_failure_notification', staticmethod(lambda stats: None))
    monkeypatch.setattr(svc, '_publish_crls', staticmethod(lambda carefs: None))
    with app.app_context():
        svc.set_renewal_config({'enabled': True})
        monkeypatch.setattr(svc, 'get_certificates_for_renewal', staticmethod(
            lambda: [db.session.get(Certificate, b_id), db.session.get(Certificate, lone_id)]))
        stats = svc.run_auto_renewal()
        db.session.remove()
    assert (stats['renewed'], stats['failed']) == (1, 1), stats
    assert [c for c, _ in reasons] == [b_id] and _refusal(reasons[0][1], a_id), reasons
    assert _rows(app, a_id, b_id) == before
    assert _rows(app, lone_id) != lone_before


def test_a_pair_member_whose_partner_cannot_be_read_is_refused_by_the_scheduler(app, monkeypatch,
                                                                               caplog):
    """A's key held: the pair is chosen, and its unreadable A refuses B's renewal, from the
    approval check on."""
    from services.auto_renewal_service import AutoRenewalService as svc
    a_id, b_id, before = _a_unreadable(app, held=True)
    reasons = []
    monkeypatch.setattr(svc, '_log_failure', staticmethod(
        lambda cert_id, cn, reason: reasons.append((cert_id, reason))))
    monkeypatch.setattr(svc, '_send_failure_notification', staticmethod(lambda stats: None))
    monkeypatch.setattr(svc, '_publish_crls', staticmethod(lambda carefs: None))
    with app.app_context():
        svc.set_renewal_config({'enabled': True})
        monkeypatch.setattr(svc, 'get_certificates_for_renewal',
                            staticmethod(lambda: [db.session.get(Certificate, b_id)]))
        stats = svc.run_auto_renewal()
        db.session.remove()
    assert stats['failed'] == 1, stats
    assert [c for c, _ in reasons] == [b_id] and _refusal(reasons[0][1], a_id), reasons
    assert _rows(app, a_id, b_id) == before
    # Recorded once as a failure: no second line with a traceback at each pass
    assert not [r for r in caplog.records if r.exc_info and 'not read' in r.getMessage()]


@pytest.mark.parametrize('held', [True, False])
def test_a_malformed_extension_refuses_the_renewal(app, auth_client, held):
    """B's extension carries a hash that cannot be read: refused naming B, nothing written,
    whether B renews with A or alone."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509 import UnrecognizedExtension
    from models import CA
    from services.hsm.ca_key_loader import get_ca_signing_key
    from utils.related_cert import RELATED_CERT_EXTENSION_OID
    a_id, (b_id,) = _linked_rows(app)
    with app.app_context():
        b = db.session.get(Certificate, b_id)
        cert_b = x509.load_pem_x509_certificate(base64.b64decode(b.crt))
        broken = (x509.CertificateBuilder().subject_name(cert_b.subject).issuer_name(cert_b.issuer)
                  .public_key(cert_b.public_key()).serial_number(cert_b.serial_number)
                  .not_valid_before(cert_b.not_valid_before_utc)
                  .not_valid_after(cert_b.not_valid_after_utc)
                  .add_extension(UnrecognizedExtension(RELATED_CERT_EXTENSION_OID, b'\x30\x00'),
                                 critical=False)
                  .sign(get_ca_signing_key(CA.query.filter_by(refid=b.caref).one()), hashes.SHA256()))
        b.crt = base64.b64encode(broken.public_bytes(serialization.Encoding.PEM)).decode()
        if not held:  # B renews alone
            db.session.get(Certificate, a_id).prv = None
        db.session.commit()
        db.session.remove()
    before = _rows(app, a_id, b_id)
    r = _json(auth_client, 'post', f'/api/v2/certificates/{b_id}/renew', {})
    assert r.status_code == 409, r.get_json()
    assert f'Certificate {b_id} cannot be read' in r.get_json()['message'], r.get_json()
    assert _rows(app, a_id, b_id) == before


def _lone_unreadable(app):
    """``(id, before)``: a certificate with no pair whose stored certificate cannot be decoded."""
    from tests.test_renewal_concurrency_pg import _leaf
    cert_id, _, _ = _leaf(app)
    with app.app_context():
        db.session.get(Certificate, cert_id).crt = UNREADABLE
        db.session.commit()
        db.session.remove()
    return cert_id, _rows(app, cert_id)


def _named(text, cert_id):
    return f'Certificate {cert_id} cannot be read' in text and 'RFC 9763' not in text


def test_a_manual_renewal_of_an_unreadable_lone_certificate_is_refused(app, auth_client):
    cert_id, before = _lone_unreadable(app)
    r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {})
    assert r.status_code == 409, r.get_json()
    assert _named(r.get_json()['message'], cert_id), r.get_json()
    assert _rows(app, cert_id) == before


def test_a_bulk_renewal_of_an_unreadable_lone_certificate_is_refused(app, auth_client):
    cert_id, before = _lone_unreadable(app)
    r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': [cert_id]})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()['data']
    assert [f['id'] for f in data['failed']] == [cert_id], data
    assert _named(data['failed'][0]['error'], cert_id), data
    assert _rows(app, cert_id) == before


def test_a_scheduled_renewal_of_an_unreadable_lone_certificate_fails_once_and_goes_on(app, monkeypatch):
    from services.auto_renewal_service import AutoRenewalService as svc
    from tests.test_renewal_concurrency_pg import _leaf
    bad_id, before = _lone_unreadable(app)
    good_id, _, _ = _leaf(app)
    good_before = _rows(app, good_id)
    reasons = []
    monkeypatch.setattr(svc, '_log_failure', staticmethod(
        lambda cert_id, cn, reason: reasons.append((cert_id, reason))))
    monkeypatch.setattr(svc, '_send_failure_notification', staticmethod(lambda stats: None))
    monkeypatch.setattr(svc, '_publish_crls', staticmethod(lambda carefs: None))
    with app.app_context():
        svc.set_renewal_config({'enabled': True})
        monkeypatch.setattr(svc, 'get_certificates_for_renewal', staticmethod(
            lambda: [db.session.get(Certificate, bad_id), db.session.get(Certificate, good_id)]))
        stats = svc.run_auto_renewal()
        db.session.remove()
    assert (stats['renewed'], stats['failed']) == (1, 1), stats
    assert [c for c, _ in reasons] == [bad_id] and _named(reasons[0][1], bad_id), reasons
    assert _rows(app, bad_id) == before
    assert _rows(app, good_id) != good_before


def test_a_row_whose_certificate_cannot_be_decoded_is_refused_by_the_extension_read(app):
    from services.cert.renewal import RenewalError, _named_related
    cert_id, _ = _lone_unreadable(app)
    with app.app_context():
        with pytest.raises(RenewalError) as refusal:
            _named_related(db.session.get(Certificate, cert_id))
        db.session.remove()
    assert refusal.value.status == 409 and _named(refusal.value.message, cert_id)
