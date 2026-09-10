"""Leaf CSRs may only contribute an allow-listed set of extensions.

Before this fix, ``TrustStoreService.sign_csr`` copied every extension it did
not explicitly handle straight from the CSR onto the issued leaf, and then
skipped the CA's own CRL Distribution Points / AIA / Certificate Policies
when the CSR already carried one. An enrollee reaching the shared trunk
through ACME, EST or WSTEP could therefore pick the revocation endpoints of
its own certificate, or inject a Microsoft SID security extension
(szOID_NTDS_CA_SECURITY_EXT) -- the strong-mapping bypass KB5014754 exists
to close. Sub-CA signing (``cert_type='intermediate_ca'``) keeps its wider
behaviour: an operator holding write:cas signs those on purpose.
"""

import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import (
    AuthorityInformationAccessOID, ExtensionOID, NameOID,
)

from models import CA, db
from services.trust_store.csr_operations_mixin import (
    _MS_CERTIFICATE_TEMPLATE_OID,
    _SID_SECURITY_EXT_OID,
    _ad_security_extension,
    _certificate_template_extension,
)
from services.trust_store.trust_store_service import TrustStoreService
from tests.test_est_rfc7030 import (  # reuse the EST harness
    EST_BASE, _basic_auth, _post_csr, est_config,  # noqa: F401
)

ATTACKER_CDP = 'http://attacker.example/stale.crl'
ATTACKER_OCSP = 'http://attacker.example/ocsp'
ATTACKER_SID = 'S-1-5-21-1-2-3-500'
TEMPLATE_OID = '1.3.6.1.4.1.311.21.8.1.2.3.4.5.6.7.8'


def _test_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Allow-list Test CA')])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _hostile_csr(common_name='device.example.test', *, with_template=False,
                 with_tls_feature=False, ku_critical=False, tls_features=None):
    """A CSR carrying every extension an enrollee must not be able to set."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    )
    builder = builder.add_extension(
        x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False
    )
    builder = builder.add_extension(
        x509.KeyUsage(
            digital_signature=True, key_encipherment=True, content_commitment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False,
        ),
        critical=ku_critical,
    )
    builder = builder.add_extension(
        x509.CRLDistributionPoints([
            x509.DistributionPoint(
                full_name=[x509.UniformResourceIdentifier(ATTACKER_CDP)],
                relative_name=None, reasons=None, crl_issuer=None,
            )
        ]),
        critical=False,
    )
    builder = builder.add_extension(
        x509.AuthorityInformationAccess([
            x509.AccessDescription(
                AuthorityInformationAccessOID.OCSP,
                x509.UniformResourceIdentifier(ATTACKER_OCSP),
            )
        ]),
        critical=False,
    )
    builder = builder.add_extension(
        x509.CertificatePolicies([
            x509.PolicyInformation(
                policy_identifier=x509.ObjectIdentifier('1.3.6.1.4.1.99999.1'),
                policy_qualifiers=['http://attacker.example/cps'],
            )
        ]),
        critical=False,
    )
    builder = builder.add_extension(_ad_security_extension(ATTACKER_SID), critical=False)
    if with_template:
        builder = builder.add_extension(
            _certificate_template_extension(TEMPLATE_OID), critical=False
        )
    if with_tls_feature or tls_features:
        builder = builder.add_extension(
            x509.TLSFeature(tls_features or [x509.TLSFeatureType.status_request]),
            critical=False,
        )
    return builder.sign(key, hashes.SHA256()), key


def _has(cert, oid):
    try:
        cert.extensions.get_extension_for_oid(oid)
        return True
    except x509.ExtensionNotFound:
        return False


def _cdp_urls(cert):
    ext = cert.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS)
    return [name.value for dp in ext.value for name in (dp.full_name or [])]


def _aia_urls(cert):
    ext = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
    return [desc.access_location.value for desc in ext.value]


def _sign(app, csr, ca_cert, ca_key, **kwargs):
    with app.app_context():
        pem = TrustStoreService.sign_csr(
            csr_pem=csr.public_bytes(serialization.Encoding.PEM),
            ca_cert=ca_cert, ca_private_key=ca_key, validity_days=30, **kwargs,
        )
    return x509.load_pem_x509_certificate(pem, default_backend())


class TestLeafCsrAllowList:
    """The shared trunk, exercised directly."""

    def test_revocation_endpoints_come_from_the_ca_not_the_csr(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr()
        cert = _sign(
            app, csr, ca_cert, ca_key,
            cdp_url='http://ca.example.test/ca.crl',
            ocsp_url='http://ca.example.test/ocsp',
            cps_uri='http://ca.example.test/cps',
        )
        assert _cdp_urls(cert) == ['http://ca.example.test/ca.crl']
        assert _aia_urls(cert) == ['http://ca.example.test/ocsp']
        policies = cert.extensions.get_extension_for_oid(ExtensionOID.CERTIFICATE_POLICIES)
        assert [p.policy_qualifiers for p in policies.value] == [['http://ca.example.test/cps']]

    def test_csr_endpoints_are_dropped_when_the_ca_sets_none(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr()
        cert = _sign(app, csr, ca_cert, ca_key)
        assert not _has(cert, ExtensionOID.CRL_DISTRIBUTION_POINTS)
        assert not _has(cert, ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
        assert not _has(cert, ExtensionOID.CERTIFICATE_POLICIES)

    def test_sid_security_extension_is_never_copied_from_a_csr(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr()
        cert = _sign(app, csr, ca_cert, ca_key)
        assert not _has(cert, _SID_SECURITY_EXT_OID)

    def test_requester_sid_kwarg_still_lands(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr()
        cert = _sign(app, csr, ca_cert, ca_key, requester_sid='S-1-5-21-9-9-9-1105')
        ext = cert.extensions.get_extension_for_oid(_SID_SECURITY_EXT_OID)
        assert ext.value.value == _ad_security_extension('S-1-5-21-9-9-9-1105').value

    def test_csr_borne_template_extension_does_not_collide_with_wstep_template(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr(with_template=True)
        cert = _sign(app, csr, ca_cert, ca_key, ms_certificate_template_oid=TEMPLATE_OID)
        ext = cert.extensions.get_extension_for_oid(_MS_CERTIFICATE_TEMPLATE_OID)
        assert ext.value.public_bytes() == _certificate_template_extension(TEMPLATE_OID).value
        assert len([e for e in cert.extensions if e.oid == _MS_CERTIFICATE_TEMPLATE_OID]) == 1

    def test_csr_borne_template_extension_is_dropped_without_a_template(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr(with_template=True)
        cert = _sign(app, csr, ca_cert, ca_key)
        assert not _has(cert, _MS_CERTIFICATE_TEMPLATE_OID)

    def test_tls_feature_is_kept_and_not_duplicated(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr(with_tls_feature=True)
        cert = _sign(app, csr, ca_cert, ca_key)
        assert _has(cert, ExtensionOID.TLS_FEATURE)
        cert = _sign(app, csr, ca_cert, ca_key, ocsp_must_staple=True)
        assert [e for e in cert.extensions if e.oid == ExtensionOID.TLS_FEATURE]
        assert len([e for e in cert.extensions if e.oid == ExtensionOID.TLS_FEATURE]) == 1

    def test_must_staple_joins_a_csr_that_asked_for_another_tls_feature(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr(tls_features=[x509.TLSFeatureType.status_request_v2])
        cert = _sign(app, csr, ca_cert, ca_key, ocsp_must_staple=True)
        features = [e for e in cert.extensions if e.oid == ExtensionOID.TLS_FEATURE]
        assert len(features) == 1
        assert set(features[0].value) == {
            x509.TLSFeatureType.status_request, x509.TLSFeatureType.status_request_v2,
        }

    def test_leaf_key_usage_is_critical_even_when_the_csr_said_otherwise(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr(ku_critical=False)
        cert = _sign(app, csr, ca_cert, ca_key)
        assert cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).critical is True

    def test_san_and_eku_still_come_from_the_csr(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _ = _hostile_csr()
        cert = _sign(app, csr, ca_cert, ca_key)
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        assert san.value.get_values_for_type(x509.DNSName) == ['device.example.test']

    def test_sub_ca_csr_keeps_its_name_constraints(self, app):
        """Control: the intermediate-CA path is untouched."""
        ca_cert, ca_key = _test_ca()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Sub CA')]))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.NameConstraints(
                    permitted_subtrees=[x509.DNSName('.example.test')],
                    excluded_subtrees=None,
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        cert = _sign(app, csr, ca_cert, ca_key, cert_type='intermediate_ca')
        assert _has(cert, ExtensionOID.NAME_CONSTRAINTS)


CA_CDP = 'http://ca.example.test/crl/{ca_refid}.crl'
CA_OCSP = 'http://ca.example.test/ocsp'


def _publish_endpoints(app, ca_id):
    """Give the CA row CRL and OCSP endpoints so the leaf must carry them."""
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca.cdp_enabled = True
        ca.set_cdp_urls([CA_CDP])
        ca.ocsp_enabled = True
        ca.set_ocsp_urls([CA_OCSP])
        db.session.commit()
        return CA_CDP.replace('{ca_refid}', ca.url_ref)


class TestProtocolPathsReachTheAllowList:

    def test_est_enrollee_cannot_choose_its_revocation_endpoints(self, client, app, est_config):
        expected_cdp = _publish_endpoints(app, est_config['id'])
        csr, _ = _hostile_csr('est-device.example.test')
        response = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
        assert response.status_code == 200, response.data
        certs = pkcs7.load_der_pkcs7_certificates(base64.b64decode(response.data))
        leaf = [c for c in certs if not c.extensions.get_extension_for_oid(
            ExtensionOID.BASIC_CONSTRAINTS).value.ca][0]
        assert not _has(leaf, _SID_SECURITY_EXT_OID)
        assert _cdp_urls(leaf) == [expected_cdp]
        assert _aia_urls(leaf) == [CA_OCSP]

    def test_wstep_username_password_enrollee_cannot_inject_a_sid(self, app, create_ca):
        from services.wstep import wstep_service
        ca_data = create_ca(cn='Allow-list WSTEP CA')
        expected_cdp = _publish_endpoints(app, ca_data['id'])
        csr, _ = _hostile_csr('wstep-device.example.test')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert_pem, error = wstep_service.issue(
                ca, csr.public_bytes(serialization.Encoding.DER), 30
            )
        assert error is None, error
        leaf = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        assert not _has(leaf, _SID_SECURITY_EXT_OID)
        assert _cdp_urls(leaf) == [expected_cdp]
        assert _aia_urls(leaf) == [CA_OCSP]
