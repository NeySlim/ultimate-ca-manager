"""A SCEP request remembers the profile it came through, so that approving
it by hand issues with that profile's template (validity, key usages), as
auto-approval does, instead of the CA defaults."""
import base64
import datetime
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import CA, Certificate, SCEPRequest, db
from models.certificate_template import CertificateTemplate
from models.scep import ScepProfile
from models.system_config import SystemConfig


def _csr(cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])).sign(key, hashes.SHA256())


def _template(app, name, validity_days=30, ekus=('clientAuth',)):
    with app.app_context():
        tpl = CertificateTemplate(
            name=name, template_type='usr_cert', key_type='RSA-2048', validity_days=validity_days,
            digest='sha256', dn_template=json.dumps({'CN': '{cn}'}),
            extensions_template=json.dumps({'extended_key_usage': list(ekus)}), is_active=True)
        db.session.add(tpl)
        db.session.commit()
        return tpl.id


def _profile(app, ca_id, name, template_id=None):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        profile = ScepProfile(name=name, url_slug=name.lower(), ca_refid=ca.refid,
                              template_id=template_id, enabled=True, auto_approve=False)
        db.session.add(profile)
        db.session.commit()
        return profile.id


def _request(app, ca_id, cn, profile_id=None):
    csr = _csr(cn)
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        req = SCEPRequest(transaction_id=f'txn-{cn}', ca_refid=ca.refid,
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode(),
                          status='pending', subject=f'CN={cn}', profile_id=profile_id)
        db.session.add(req)
        db.session.commit()
        return req.id


def _cleanup(app, req_id, profile_id=None, template_id=None):
    with app.app_context():
        req = db.session.get(SCEPRequest, req_id)
        if req is not None:
            if req.cert_refid:
                row = Certificate.query.filter_by(refid=req.cert_refid).first()
                if row:
                    db.session.delete(row)
            db.session.delete(req)
        if profile_id:
            p = db.session.get(ScepProfile, profile_id)
            if p:
                db.session.delete(p)
        if template_id:
            t = db.session.get(CertificateTemplate, template_id)
            if t:
                db.session.delete(t)
        db.session.commit()


def _issued(app, req_id):
    with app.app_context():
        req = db.session.get(SCEPRequest, req_id)
        row = Certificate.query.filter_by(refid=req.cert_refid).first()
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())


def _ekus(cert):
    return set(cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value)


def test_the_profile_service_carries_the_profile(app, create_ca):
    from api.scep_protocol import get_scep_service
    ca = create_ca(cn='SCEP profile carry CA')
    template_id = _template(app, 'scep-carry-tpl')
    profile_id = _profile(app, ca['id'], 'scep-carry', template_id)
    try:
        with app.app_context():
            previous = SystemConfig.query.filter_by(key='scep_enabled').first()
            previous_value = previous.value if previous else None
            if previous is None:
                db.session.add(SystemConfig(key='scep_enabled', value='true'))
            else:
                previous.value = 'true'
            db.session.commit()
            try:
                service, error = get_scep_service('scep-carry')
                assert error is None, error
                assert service.profile_id == profile_id and service.template.id == template_id
            finally:
                row = SystemConfig.query.filter_by(key='scep_enabled').first()
                if previous_value is None:
                    db.session.delete(row)
                else:
                    row.value = previous_value
                db.session.commit()
    finally:
        _cleanup(app, -1, profile_id, template_id)


def test_manual_approval_applies_the_profile_template(app, auth_client, create_ca):
    ca = create_ca(cn='SCEP profile approve CA')
    template_id = _template(app, 'scep-approve-tpl', validity_days=30, ekus=('clientAuth',))
    profile_id = _profile(app, ca['id'], 'scep-approve', template_id)
    req_id = _request(app, ca['id'], 'approve.example.test', profile_id)
    try:
        r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type='application/json')
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['data']['profile_id'] == profile_id
        cert = _issued(app, req_id)
        lifetime = cert.not_valid_after_utc - cert.not_valid_before_utc
        assert datetime.timedelta(days=29) < lifetime <= datetime.timedelta(days=31)
        assert _ekus(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}
    finally:
        _cleanup(app, req_id, profile_id, template_id)


def test_manual_approval_without_a_profile_keeps_the_defaults(app, auth_client, create_ca):
    ca = create_ca(cn='SCEP default approve CA')
    req_id = _request(app, ca['id'], 'default.example.test')
    try:
        r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type='application/json')
        assert r.status_code == 200, r.get_json()
        cert = _issued(app, req_id)
        lifetime = cert.not_valid_after_utc - cert.not_valid_before_utc
        assert lifetime > datetime.timedelta(days=300)
        assert ExtendedKeyUsageOID.SERVER_AUTH in _ekus(cert)
    finally:
        _cleanup(app, req_id)


def test_manual_approval_refuses_when_the_profile_is_gone(app, auth_client, create_ca):
    ca = create_ca(cn='SCEP gone profile CA')
    req_id = _request(app, ca['id'], 'gone.example.test', profile_id=999999)
    try:
        r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type='application/json')
        assert r.status_code == 409, r.get_json()
        with app.app_context():
            assert db.session.get(SCEPRequest, req_id).status == 'pending'
    finally:
        _cleanup(app, req_id)
