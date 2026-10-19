"""Policy ceilings bind the protocols too.

`max_validity_days` and `san_restrictions.max_dns_names` were applied by the
issue form, CSR signing, renewals and approvals only: ACME, EST, WSTEP and
SCEP checked key type and hash, and issued whatever validity and name count
was asked. The validity is now capped and an excess of names refused there.
"""
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CA, CertificatePolicy, db
from services.policy_service import PolicyViolation
from tests.test_policy_algorithms_397 import _drop, _policy, _signed, _store_csr


def _csr(*names):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
            .sign(key, hashes.SHA256()))


def _lifetime(cert):
    return cert.not_valid_after_utc - cert.not_valid_before_utc


class TestAcmeSigning:
    """CertificateService.sign_csr, the ACME finalize path."""

    def test_validity_is_capped(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Limits ACME CA')
        pid = _policy(app, 'limits-acme-validity', ca['id'], {'max_validity_days': 20})
        cid = _store_csr(app, _csr('acme.limits.test'))
        try:
            with app.app_context():
                CertificateService.sign_csr(cert_id=cid, caref=db.session.get(CA, ca['id']).refid,
                                            validity_days=90, digest='sha256')
                db.session.commit()
            assert _lifetime(_signed(app, cid)) <= timedelta(days=20, hours=1)
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_too_many_names_are_refused(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Limits ACME CA 2')
        pid = _policy(app, 'limits-acme-names', ca['id'], {'san_restrictions': {'max_dns_names': 1}})
        cid = _store_csr(app, _csr('a.limits.test', 'b.limits.test'))
        try:
            with app.app_context():
                with pytest.raises(PolicyViolation, match='DNS names'):
                    CertificateService.sign_csr(cert_id=cid, caref=db.session.get(CA, ca['id']).refid,
                                                validity_days=90, digest='sha256')
                db.session.rollback()
        finally:
            _drop(app, CertificatePolicy, pid)


class TestEstSigning:
    """CAService.sign_csr_from_crypto, the EST and WSTEP path."""

    def test_validity_is_capped(self, app, create_ca):
        from services.ca_service import CAService
        ca = create_ca(cn='Limits EST CA')
        pid = _policy(app, 'limits-est', ca['id'], {'max_validity_days': 15})
        try:
            with app.app_context():
                pem, _serial = CAService.sign_csr_from_crypto(
                    db.session.get(CA, ca['id']), _csr('est.limits.test'), validity_days=365)
                cert = x509.load_pem_x509_certificate(pem if isinstance(pem, bytes) else pem.encode())
            assert _lifetime(cert) <= timedelta(days=15, hours=1)
        finally:
            _drop(app, CertificatePolicy, pid)


class TestScep:

    def test_names_and_validity(self, app, create_ca):
        from services.scep.scep_service import SCEPService
        ca = create_ca(cn='Limits SCEP CA')
        pid = _policy(app, 'limits-scep', ca['id'],
                      {'max_validity_days': 10, 'san_restrictions': {'max_dns_names': 1}})
        try:
            with app.app_context():
                svc = SCEPService(db.session.get(CA, ca['id']).refid)
                _, v = svc._policy_signing_hash(_csr('a.scep.test', 'b.scep.test'))
                assert any('DNS names' in m for m in v)
                assert svc._policy_signing_hash(_csr('a.scep.test'))[1] == []
                assert svc._policy_validity(_csr('a.scep.test'), 365) == 10
        finally:
            _drop(app, CertificatePolicy, pid)
