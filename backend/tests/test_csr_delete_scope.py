"""What the CSR routes are allowed to delete.

A certificate signing request and an issued certificate are the same table and
the same counter of identifiers: a CSR is a row whose `csr` is set and whose
`crt` is not. The certificate route refuses to delete a valid, unrevoked
certificate with a 409, so the CRL and the responder keep reflecting it. The
CSR routes called the deletion service straight, with no such check, under a
permission the certificate route does not ask for.

The result was an effective escalation: the `operator` role holds
`delete:csrs` and not `delete:certificates`, so the refusal it is given on one
route was handed to it on the other, and a valid certificate left the instance
without the revocation list ever learning of it.
"""
import base64
from datetime import timedelta

import pytest

from models import db
from utils.datetime_utils import utc_now


@pytest.fixture
def an_issued_certificate(app, create_ca):
    """A row that is a certificate, not a request: `crt` is set, under a CA holding its key
    (a CA held without its key publishes no revocation: its certificates go unrevoked)."""
    from models import CA, Certificate

    with app.app_context():
        keyed = CA.query.filter(CA.prv.isnot(None), CA.prv != '').order_by(CA.id).first()
        refid = keyed.refid if keyed is not None else None
    refid = refid or create_ca(cn='CSR scope CA')['refid']
    with app.app_context():
        cert = Certificate(
            refid='csr-scope-issued', descr='csr scope issued',
            caref=refid,
            crt=base64.b64encode(b'-----BEGIN CERTIFICATE-----\nx\n'
                                 b'-----END CERTIFICATE-----\n').decode(),
            csr='-----BEGIN CERTIFICATE REQUEST-----\nx\n'
                '-----END CERTIFICATE REQUEST-----\n',
            subject_cn='csr-scope.example.test', revoked=False,
            valid_from=utc_now(), valid_to=utc_now() + timedelta(days=30))
        db.session.add(cert)
        db.session.commit()
        cert_id = cert.id

    yield cert_id

    with app.app_context():
        from models import Certificate
        row = db.session.get(Certificate, cert_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


@pytest.fixture
def a_pending_request(app):
    """A row that is a request: `crt` is empty."""
    from models import Certificate

    with app.app_context():
        csr = Certificate(
            refid='csr-scope-pending', descr='csr scope pending',
            csr='-----BEGIN CERTIFICATE REQUEST-----\ny\n'
                '-----END CERTIFICATE REQUEST-----\n',
            subject_cn='csr-scope-pending.example.test')
        db.session.add(csr)
        db.session.commit()
        yield csr.id

    with app.app_context():
        from models import Certificate
        row = db.session.get(Certificate, csr.id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


def _still_there(app, cert_id):
    from models import Certificate
    with app.app_context():
        return db.session.get(Certificate, cert_id) is not None


class TestACertificateIsNotDeletableThroughTheCsrRoutes:
    def test_the_single_route_refuses_an_issued_certificate(
            self, app, auth_client, an_issued_certificate):
        response = auth_client.delete(f'/api/v2/csrs/{an_issued_certificate}')

        assert response.status_code == 404, (
            f'the CSR route answered {response.status_code} for an issued '
            'certificate: it deleted a row that is not a request')
        assert _still_there(app, an_issued_certificate), (
            'a valid certificate was removed without ever being revoked, so '
            'the CRL and the responder will not mention it')

    def test_the_bulk_route_refuses_an_issued_certificate(
            self, app, auth_client, an_issued_certificate):
        response = auth_client.post('/api/v2/csrs/bulk/delete',
                                    json={'ids': [an_issued_certificate]})

        assert response.status_code in (200, 207), response.data
        assert _still_there(app, an_issued_certificate), (
            'the bulk route deleted an issued certificate; the single route '
            'refuses it, and both carry the same permission')

    def test_the_certificate_route_still_refuses_it_too(
            self, app, auth_client, an_issued_certificate):
        """The refusal the CSR routes were bypassing, still in place."""
        response = auth_client.delete(
            f'/api/v2/certificates/{an_issued_certificate}')
        assert response.status_code == 409, response.data


class TestARequestIsStillDeletable:
    def test_the_single_route_deletes_a_request(
            self, app, auth_client, a_pending_request):
        response = auth_client.delete(f'/api/v2/csrs/{a_pending_request}')

        assert response.status_code == 204, response.data
        assert not _still_there(app, a_pending_request)
