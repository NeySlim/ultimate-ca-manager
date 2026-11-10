"""Approval requests saved before migration 144 name their certificate in hex; the
checks against the now-decimal column must still recognise the same certificate."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import Certificate, db
from models.policy import ApprovalRequest

# A serial with hex letters, and one whose hex spelling is all digits (ambiguous text)
SERIALS = (0xabcdef0123456789, 0x1234567890123456)
OTHER = 0x0fedcba987654321


def _crt(serial):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'legacy-hex')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(serial).not_valid_before(now - timedelta(days=300))
            .not_valid_after(now + timedelta(days=10)).sign(key, hashes.SHA256()))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


@pytest.fixture
def rows(app):
    made = {'certs': [], 'requests': []}
    with app.app_context():
        def cert(serial):
            row = Certificate(refid=str(uuid.uuid4()), descr='legacy-hex', subject_cn='legacy-hex',
                              source='manual', crt=_crt(serial), serial_number=serial)
            db.session.add(row)
            db.session.flush()
            made['certs'].append(row.id)
            return row

        def request(kind, data, status='pending'):
            row = ApprovalRequest(request_type=kind, status=status, request_data=json.dumps(data))
            db.session.add(row)
            db.session.flush()
            made['requests'].append(row.id)
            return row

        yield type('Rows', (), {'cert': staticmethod(cert), 'request': staticmethod(request)})
        db.session.rollback()
        ApprovalRequest.query.filter(ApprovalRequest.id.in_(made['requests'])).delete(synchronize_session=False)
        Certificate.query.filter(Certificate.id.in_(made['certs'])).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('serial', SERIALS)
def test_revocation_request_in_hex_still_names_its_certificate(rows, serial):
    from api.v2.policies import _approval_target_gone
    cert = rows.cert(serial)
    approval = rows.request('revocation', {'certificate_id': cert.id, 'serial_number': format(serial, 'x')})
    assert _approval_target_gone(approval) is None


def test_revocation_request_for_a_replaced_certificate_is_still_refused(rows):
    from api.v2.policies import _approval_target_gone, _revoke_approved_certificate
    cert = rows.cert(SERIALS[0])
    data = {'certificate_id': cert.id, 'serial_number': format(OTHER, 'x')}
    approval = rows.request('revocation', data)
    assert 'renewed since the request' in _approval_target_gone(approval)
    with pytest.raises(ValueError, match='renewed since the request'):
        _revoke_approved_certificate(approval, data)


@pytest.mark.parametrize('serial', SERIALS)
def test_approved_revocation_in_hex_revokes(rows, serial, monkeypatch):
    import api.v2.policies as policies
    cert = rows.cert(serial)
    data = {'certificate_id': cert.id, 'serial_number': format(serial, 'x'), 'reason': 'superseded'}
    approval = rows.request('revocation', data)

    class Reached(Exception):
        pass

    def revoke(*a, **k):
        raise Reached(k.get('cert_id'))
    monkeypatch.setattr('services.cert_service.CertificateService.revoke_certificate', staticmethod(revoke))
    with pytest.raises(Reached) as hit:
        policies._revoke_approved_certificate(approval, data)
    assert hit.value.args == (cert.id,)


@pytest.mark.parametrize('serial', SERIALS)
def test_declined_renewal_in_hex_stays_declined(rows, serial):
    from services.auto_renewal_service import AutoRenewalService
    cert = rows.cert(serial)
    rows.request('renewal', {'certificate_id': cert.id, 'trigger': 'auto', 'serial_number': format(serial, 'x')},
                 status='rejected')
    assert AutoRenewalService._declined(cert) is True


def test_declined_renewal_of_a_replaced_certificate_is_not_declined(rows):
    from services.auto_renewal_service import AutoRenewalService
    cert = rows.cert(SERIALS[0])
    rows.request('renewal', {'certificate_id': cert.id, 'trigger': 'auto', 'serial_number': format(OTHER, 'x')},
                 status='rejected')
    assert AutoRenewalService._declined(cert) is False
