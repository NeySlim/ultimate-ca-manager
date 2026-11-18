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
