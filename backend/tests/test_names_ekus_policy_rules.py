"""Lot 9: EKU spellings resolve everywhere, name constraints cover every CN
and every name type, and issuance policy rules bind Sign CSR and renewal.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from models.certificate_template import CertificateTemplate
from models.policy import CertificatePolicy
from services.trust_store.constraints_mixin import validate_name_constraints
from utils.eku_validation import normalize_extra_ekus

SMARTCARD = '1.3.6.1.4.1.311.20.2.2'
UPN_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2.3')


def _utf8(value: str) -> bytes:
    data = value.encode()
    return b'\x0c' + bytes([len(data)]) + data


class TestEkuSpellings:

    def test_every_spelling_of_smartcard_logon_resolves(self):
        for spelling in ('msSmartcardLogin', 'smartcardLogon', 'msSmartcardLogon', SMARTCARD):
            oids, err = normalize_extra_ekus(['clientAuth', spelling])
            assert err is None, (spelling, err)
            assert SMARTCARD in oids, spelling

    def test_wstep_template_ekus_use_the_shared_resolver(self, app):
        from services.wstep.wstep_service import _template_extra_ekus
        with app.app_context():
            tpl = CertificateTemplate(name='spelling-tpl', template_type='custom', key_type='RSA-2048',
                                      validity_days=30, digest='sha256',
                                      extensions_template=json.dumps(
                                          {'extended_key_usage': ['clientAuth', 'msSmartcardLogin']}))
            db.session.add(tpl)
            db.session.commit()
            try:
                assert SMARTCARD in _template_extra_ekus(tpl)
            finally:
                db.session.delete(tpl)
                db.session.commit()


def _constrained_ca(permitted=None, excluded=None):
    key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Constrained CA')])
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.NameConstraints(permitted_subtrees=permitted, excluded_subtrees=excluded),
                       critical=True)
        .sign(key, hashes.SHA256())
    )


def _subject(*cns):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn) for cn in cns])


class TestNameConstraintsCoverage:

    def test_second_cn_in_excluded_subtree_is_refused(self, app):
        ca = _constrained_ca(excluded=[x509.DNSName('.blocked.example')])
        with app.app_context():
            with pytest.raises(ValueError):
                validate_name_constraints(ca, _subject('ok.example.com', 'host.blocked.example'),
                                          [x509.DNSName('ok.example.com')])

    def test_excluded_uri_subtree_is_enforced(self, app):
        ca = _constrained_ca(excluded=[x509.UniformResourceIdentifier('.evil.example')])
        with app.app_context():
            with pytest.raises(ValueError):
                validate_name_constraints(ca, _subject('svc.example.com'),
                                          [x509.UniformResourceIdentifier('https://x.evil.example/path')])
            validate_name_constraints(ca, _subject('svc.example.com'),
                                      [x509.UniformResourceIdentifier('https://x.good.example/')])

    def test_permitted_uri_subtree_does_not_refuse_dns_names(self, app):
        ca = _constrained_ca(permitted=[x509.UniformResourceIdentifier('.good.example')])
        with app.app_context():
            validate_name_constraints(ca, _subject('svc.example.com'), [x509.DNSName('svc.example.com')])
            with pytest.raises(ValueError):
                validate_name_constraints(ca, _subject('svc.example.com'),
                                          [x509.UniformResourceIdentifier('https://x.other.example/')])

    def test_excluded_directory_name_applies_to_the_subject(self, app):
        blocked = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Blocked Org')])
        ca = _constrained_ca(excluded=[x509.DirectoryName(blocked)])
        with app.app_context():
            with pytest.raises(ValueError):
                validate_name_constraints(ca, x509.Name([
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Blocked Org'),
                    x509.NameAttribute(NameOID.COMMON_NAME, 'someone'),
                ]), None)
            validate_name_constraints(ca, x509.Name([
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Other Org'),
                x509.NameAttribute(NameOID.COMMON_NAME, 'someone'),
            ]), None)

    def test_excluded_upn_domain_is_enforced(self, app):
        ca = _constrained_ca(excluded=[x509.OtherName(UPN_OID, _utf8('.corp.example'))])
        with app.app_context():
            with pytest.raises(ValueError):
                validate_name_constraints(ca, _subject('user'),
                                          [x509.OtherName(UPN_OID, _utf8('admin@ad.corp.example'))])
            validate_name_constraints(ca, _subject('user'),
                                      [x509.OtherName(UPN_OID, _utf8('user@other.example'))])


class TestPolicyRulesOnOperatorPaths:

    def _policy(self, app, ca_id, rules):
        with app.app_context():
            pol = CertificatePolicy(name=f'rules-{ca_id}-{len(rules)}', policy_type='issuance', ca_id=ca_id,
                                    requires_approval=False, min_approvers=1, is_active=True, priority=100)
            pol.set_rules(rules)
            db.session.add(pol)
            db.session.commit()
            return pol.id

    def _drop_policy(self, app, pid):
        with app.app_context():
            pol = db.session.get(CertificatePolicy, pid)
            if pol:
                db.session.delete(pol)
                db.session.commit()

    def test_sign_csr_honours_allowed_key_types(self, app, auth_client, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Rules Sign CSR CA')
        pid = self._policy(app, ca['id'], {'allowed_key_types': ['EC-P256']})
        with app.app_context():
            row = CertificateService.generate_csr(descr='rules-csr', dn={'CN': 'rules.example.test'},
                                                  key_type='2048')
            db.session.commit()
            csr_id = row.id
        try:
            r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', data=json.dumps({'ca_id': ca['id']}),
                                 content_type='application/json')
            assert r.status_code == 400, (r.status_code, r.get_json())
            assert b'Policy violation' in r.data
        finally:
            self._drop_policy(app, pid)
            with app.app_context():
                db.session.delete(db.session.get(Certificate, csr_id))
                db.session.commit()

    def test_renewal_is_capped_by_max_validity(self, app, create_ca):
        from services.cert_service import CertificateService
        from services.cert.renewal import renew_certificate_in_place
        ca = create_ca(cn='Rules renewal CA')
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            row = CertificateService.create_certificate(
                descr='rules-renew', caref=ca_row.refid, dn={'CN': 'rules-renew.example.test'},
                cert_type='server_cert', key_type='2048', validity_days=90, username='admin')
            db.session.commit()
            row_id = row.id
        pid = self._policy(app, ca['id'], {'max_validity_days': 10})
        try:
            with app.app_context():
                row = db.session.get(Certificate, row_id)
                renew_certificate_in_place(row, username='admin')
                db.session.commit()
                row = db.session.get(Certificate, row_id)
                assert (row.valid_to - row.valid_from).days <= 10
        finally:
            self._drop_policy(app, pid)
            with app.app_context():
                row = db.session.get(Certificate, row_id)
                if row:
                    db.session.delete(row)
                    db.session.commit()
