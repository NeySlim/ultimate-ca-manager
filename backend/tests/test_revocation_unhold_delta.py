"""An unhold on a CA publishing delta CRLs: a lift refused after the removeFromCRL delta was
published republishes the CRL."""
import base64
import uuid

import pytest
from cryptography import x509

from models import CA, RevokedSerial, db
from tests.test_import_issuer_signature import _leaf, _store
from tests.test_revocation_record_rule import EARLY, LATER, _held, _record, _row

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture(scope='module')
def delta_issuer(app, create_ca):
    data = create_ca(cn=f'Delta Unhold CA {uuid.uuid4().hex[:6]}',
                     keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        row = db.session.get(CA, data['id'])
        row.cdp_enabled, row.delta_crl_enabled = True, True
        db.session.commit()
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        return row.id, row.refid, cert, get_ca_signing_key(row)


def _held_leaf(app, issuer, cn):
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf(cn, ca_cert, ca_key, days=200)
    row_id = _store(app, real, refid, key=key)
    _held(app, row_id)
    return row_id, _record(app, refid, real, reason='certificateHold', certificate_id=row_id)


@pytest.fixture
def crl_calls(monkeypatch):
    """``(kind, ca_id)`` per CRL the route asks for, generated as usual."""
    from services.crl_service import CRLService
    calls, full, delta = [], CRLService.generate_crl, CRLService.generate_delta_crl

    def generate_crl(ca_id, *args, **kwargs):
        calls.append(('full', ca_id))
        return full(ca_id, *args, **kwargs)

    def generate_delta_crl(ca_id, *args, **kwargs):
        calls.append(('delta', ca_id))
        return delta(ca_id, *args, **kwargs)
    monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(generate_crl))
    monkeypatch.setattr(CRLService, 'generate_delta_crl', staticmethod(generate_delta_crl))
    return calls


def _final_meanwhile(app, monkeypatch, row_id, record_id, where):
    """Revoke the row or its record for good on another connection, right after the route's
    own check of the record."""
    import sys
    from sqlalchemy import update
    from models import Certificate
    from services.cert import issued_lookup
    read, done = issued_lookup.persisted_revocation, []

    def then_revoked(*args, **kwargs):
        found = read(*args, **kwargs)
        if sys._getframe(1).f_code.co_name == 'unhold_certificate' and not done:
            done.append(True)
            with db.engine.begin() as other:
                if 'row' in where:
                    other.execute(update(Certificate).where(Certificate.id == row_id).values(
                        revoked=True, revoke_reason='keyCompromise', revoked_at=LATER))
                if 'record' in where:
                    other.execute(update(RevokedSerial).where(RevokedSerial.id == record_id).values(
                        revoke_reason='keyCompromise', revoked_at=LATER))
        return found
    monkeypatch.setattr(issued_lookup, 'persisted_revocation', then_revoked)
    return done


class TestARefusedLiftRepublishesTheCrl:

    def test_after_a_409(self, app, auth_client, delta_issuer, monkeypatch, crl_calls):
        ca_id = delta_issuer[0]
        row_id, record_id = _held_leaf(app, delta_issuer, 'refused-lift.example.test')
        done = _final_meanwhile(app, monkeypatch, row_id, record_id, ('record',))
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert done and r.status_code == 409, r.data
        assert _row(app, row_id) == (True, 'certificateHold', EARLY)
        # The removeFromCRL delta, then a CRL that lists the certificate again
        assert crl_calls[0] == ('delta', ca_id)
        assert ('full', ca_id) in crl_calls[1:]

    def test_after_a_500(self, app, auth_client, delta_issuer, monkeypatch, crl_calls):
        from api.v2.certificates import cert_lifecycle
        ca_id = delta_issuer[0]
        row_id, _ = _held_leaf(app, delta_issuer, 'failed-lift.example.test')

        def broken(*args, **kwargs):
            raise RuntimeError('lift failed')
        monkeypatch.setattr(cert_lifecycle, '_lift_hold', broken)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 500, r.data
        assert _row(app, row_id) == (True, 'certificateHold', EARLY)
        assert crl_calls[0] == ('delta', ca_id)
        assert ('full', ca_id) in crl_calls[1:]
