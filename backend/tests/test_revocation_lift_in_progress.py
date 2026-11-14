"""An unhold in progress (row staged removeFromCRL, hold not lifted yet) is still the hold it was:
OCSP and the complete CRL say certificateHold with the hold's date, only the delta says
removeFromCRL (RFC 5280 §5.3.1), and a final record of the serial still prevails."""
import base64
import uuid

import pytest
from cryptography import x509

from models import CA, Certificate, RevokedSerial, db
from tests.test_import_issuer_signature import _leaf, _store
from tests.test_revocation_record_rule import EARLY, LATER, _held, _record, _row

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

HOLD = x509.ReasonFlags.certificate_hold
REMOVE = x509.ReasonFlags.remove_from_crl


def _issuer(app, create_ca, delta):
    data = create_ca(cn=f'Lift In Progress CA {uuid.uuid4().hex[:6]}',
                     keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        row = db.session.get(CA, data['id'])
        row.cdp_enabled, row.delta_crl_enabled = True, delta
        db.session.commit()
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        return row.id, row.refid, cert, get_ca_signing_key(row)


@pytest.fixture(scope='module')
def delta_issuer(app, create_ca):
    return _issuer(app, create_ca, True)


@pytest.fixture(scope='module')
def full_only_issuer(app, create_ca):
    return _issuer(app, create_ca, False)


def _held_leaf(app, issuer, cn, record=True):
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf(cn, ca_cert, ca_key, days=200)
    row_id = _store(app, real, refid, key=key)
    _held(app, row_id)
    record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id) if record else None
    return real, row_id, record_id


def _staged(app, row_id, at=None):
    """The row as the unhold's first commit leaves it: the hold's date is kept unless ``at``."""
    with app.app_context():
        row = db.session.get(Certificate, row_id)
        row.revoked, row.revoke_reason = True, 'removeFromCRL'
        if at is not None:
            row.revoked_at = at
        db.session.commit()


def _reason(entry):
    if entry is None:
        return None
    try:
        return entry.extensions.get_extension_for_class(x509.CRLReason).value.reason
    except x509.ExtensionNotFound:
        return x509.ReasonFlags.unspecified


def _ocsp(app, ca_id, cert):
    from services.ocsp_service import OCSPService
    with app.app_context():
        db.session.expire_all()
        _, status, at, reason = OCSPService._status_for_serial(db.session.get(CA, ca_id), cert.serial_number)
        return status, (at.replace(tzinfo=None) if at else None), reason


def _full_crl(app, ca_id, cert):
    """(reason, date) of the certificate on a complete CRL generated now, or None."""
    from services.crl_service import CRLService
    with app.app_context():
        db.session.expire_all()
        crl = x509.load_pem_x509_crl(CRLService.generate_crl(ca_id).crl_pem.encode())
        entry = crl.get_revoked_certificate_by_serial_number(cert.serial_number)
        return None if entry is None else (_reason(entry), entry.revocation_date_utc.replace(tzinfo=None))


def _delta_reason(app, ca_id, cert):
    """The certificate's reason on a delta generated now (over a base listing it as held)."""
    from services.crl_service import CRLService
    with app.app_context():
        db.session.expire_all()
        crl = x509.load_pem_x509_crl(CRLService.generate_delta_crl(ca_id).crl_pem.encode())
        return _reason(crl.get_revoked_certificate_by_serial_number(cert.serial_number))


class TestALiftStoppedBetweenItsCommits:

    def test_ocsp_and_the_full_crl_still_say_hold_with_its_date(self, app, delta_issuer):
        ca_id = delta_issuer[0]
        real, row_id, _ = _held_leaf(app, delta_issuer, 'lift-stopped.example.test')
        _staged(app, row_id)
        assert _ocsp(app, ca_id, real) == ('revoked', EARLY, HOLD)
        assert _full_crl(app, ca_id, real) == (HOLD, EARLY)
        assert _delta_reason(app, ca_id, real) == REMOVE

    def test_resuming_the_lift_makes_it_good(self, app, auth_client, delta_issuer):
        ca_id = delta_issuer[0]
        real, row_id, record_id = _held_leaf(app, delta_issuer, 'lift-resumed.example.test')
        _staged(app, row_id)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        assert _row(app, row_id) == (False, None, None)
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id) is None
        assert _ocsp(app, ca_id, real)[0] == 'good'
        assert _full_crl(app, ca_id, real) is None

    def test_a_final_record_of_the_serial_prevails(self, app, delta_issuer):
        ca_id = delta_issuer[0]
        real, row_id, record_id = _held_leaf(app, delta_issuer, 'lift-final-record.example.test')
        _staged(app, row_id)
        with app.app_context():
            db.session.get(RevokedSerial, record_id).revoke_reason = 'keyCompromise'
            db.session.commit()
        assert _ocsp(app, ca_id, real) == ('revoked', EARLY, x509.ReasonFlags.key_compromise)
        assert _full_crl(app, ca_id, real) == (x509.ReasonFlags.key_compromise, EARLY)
        assert _delta_reason(app, ca_id, real) is None  # unchanged since the base, which says it

    def test_a_row_only_hold_answers_hold_with_the_row_date(self, app, delta_issuer):
        """No record: the row keeps the hold's own date through the staging."""
        ca_id = delta_issuer[0]
        real, row_id, _ = _held_leaf(app, delta_issuer, 'lift-row-only.example.test', record=False)
        _staged(app, row_id)
        assert _ocsp(app, ca_id, real) == ('revoked', EARLY, HOLD)
        assert _full_crl(app, ca_id, real) == (HOLD, EARLY)
        assert _delta_reason(app, ca_id, real) == REMOVE

    def test_a_row_and_record_revoked_as_remove_from_crl_is_no_lift(self, app, delta_issuer):
        """Reason 8 on the record too (an old ACME revocation): not a hold, answered as before."""
        ca_id = delta_issuer[0]
        real, row_id, record_id = _held_leaf(app, delta_issuer, 'lift-reason-eight.example.test')
        _staged(app, row_id, at=LATER)
        with app.app_context():
            db.session.get(RevokedSerial, record_id).revoke_reason = 'removeFromCRL'
            db.session.commit()
        assert _ocsp(app, ca_id, real) == ('revoked', LATER, x509.ReasonFlags.unspecified)
        assert _full_crl(app, ca_id, real) == (x509.ReasonFlags.unspecified, LATER)


class TestTheWindowOfARealUnhold:

    def test_while_the_delta_goes_out_the_certificate_is_held(self, app, auth_client, delta_issuer,
                                                               monkeypatch):
        """Seen from another node while the removeFromCRL delta is published: still on hold."""
        from services.crl_service import CRLService
        ca_id = delta_issuer[0]
        real, row_id, _ = _held_leaf(app, delta_issuer, 'lift-window.example.test')
        seen, delta = [], CRLService.generate_delta_crl

        def generate_delta_crl(target, *args, **kwargs):
            out = delta(target, *args, **kwargs)
            if not seen:
                entry = x509.load_pem_x509_crl(out.crl_pem.encode()) \
                    .get_revoked_certificate_by_serial_number(real.serial_number)
                seen.append((_reason(entry), _ocsp(app, ca_id, real)))
            return out
        monkeypatch.setattr(CRLService, 'generate_delta_crl', staticmethod(generate_delta_crl))
        assert auth_client.post(f'/api/v2/certificates/{row_id}/unhold').status_code == 200
        assert seen == [(REMOVE, ('revoked', EARLY, HOLD))]
        assert _ocsp(app, ca_id, real)[0] == 'good'

    def test_a_hold_without_a_record_keeps_its_date_while_the_delta_goes_out(
            self, app, auth_client, delta_issuer, monkeypatch):
        """The staging does not move the hold's date: OCSP and a full CRL keep saying it."""
        from services.crl_service import CRLService
        ca_id = delta_issuer[0]
        real, row_id, _ = _held_leaf(app, delta_issuer, 'lift-window-row.example.test', record=False)
        assert _full_crl(app, ca_id, real) == (HOLD, EARLY)  # the base the delta builds on
        seen, delta = [], CRLService.generate_delta_crl

        def generate_delta_crl(target, *args, **kwargs):
            out = delta(target, *args, **kwargs)
            if not seen:
                seen.append((_ocsp(app, ca_id, real), _full_crl(app, ca_id, real)))
            return out
        monkeypatch.setattr(CRLService, 'generate_delta_crl', staticmethod(generate_delta_crl))
        assert auth_client.post(f'/api/v2/certificates/{row_id}/unhold').status_code == 200
        assert seen == [(('revoked', EARLY, HOLD), (HOLD, EARLY))]
        assert _ocsp(app, ca_id, real)[0] == 'good'


class TestACaWithoutDeltaCrls:

    def test_an_unhold_goes_from_hold_to_valid_with_nothing_between(self, app, auth_client,
                                                                     full_only_issuer, monkeypatch):
        from api.v2.certificates import cert_lifecycle
        from services.crl_service import CRLService
        ca_id = full_only_issuer[0]
        real, row_id, _ = _held_leaf(app, full_only_issuer, 'lift-no-delta.example.test')
        before, lift = [], cert_lifecycle._lift_holds

        def watched(members, *args, **kwargs):
            before.extend((m.revoked, m.revoke_reason) for m in members)
            return lift(members, *args, **kwargs)
        monkeypatch.setattr(cert_lifecycle, '_lift_holds', watched)
        monkeypatch.setattr(CRLService, 'generate_delta_crl', staticmethod(
            lambda *a, **k: pytest.fail('no delta CRL on this CA')))
        assert auth_client.post(f'/api/v2/certificates/{row_id}/unhold').status_code == 200
        assert before == [(True, 'certificateHold')]
        assert _ocsp(app, ca_id, real)[0] == 'good'
        assert _full_crl(app, ca_id, real) is None
