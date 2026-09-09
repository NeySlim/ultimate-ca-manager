"""Revocation of an intermediate CA by its parent (#343) and OCSP answers
for the certificates of CAs signed by the requested issuer (#344)."""
import base64
import json
import os
import sys

import pytest
from cryptography import x509
from cryptography.x509 import ocsp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db, CA, RevokedSerial  # noqa: E402
from services.ocsp_service import OCSPService  # noqa: E402
from services.crl_service import CRLService  # noqa: E402

CAS = '/api/v2/cas'


def _json(r):
    return json.loads(r.data)


def _post(client, path, body=None):
    return client.post(path, data=json.dumps(body or {}), content_type='application/json')


def _intermediate(auth_client, root, cn):
    r = _post(auth_client, CAS, {
        'type': 'intermediate', 'parentCAId': root['id'],
        'commonName': cn, 'organization': 'Test Org', 'country': 'US',
        'state': 'CA', 'locality': 'Test City',
        'keyType': 'RSA', 'keySize': 2048, 'validityYears': 5, 'hashAlgorithm': 'sha256',
    })
    assert r.status_code in (200, 201), r.data
    return _json(r)['data']


def _serial_int(ca_id):
    ca = db.session.get(CA, ca_id)
    cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
    return cert.serial_number


def _ocsp_status(parent_id, serial):
    der, status = OCSPService().generate_response(db.session.get(CA, parent_id), serial)
    resp = ocsp.load_der_ocsp_response(der)
    assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
    return status, resp


def _crl_serials(parent_id):
    parent = db.session.get(CA, parent_id)
    CRLService.generate_crl(parent.id, username='test')
    crl = x509.load_pem_x509_crl(CRLService.get_crl_pem(parent.refid).encode())
    return {entry.serial_number: entry for entry in crl}


class TestOcspSubCaStatus:
    """#344: a sub-CA's serial is answered good, not unknown."""

    def test_valid_sub_ca_is_good(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='OCSP Sub Root')
            sub = _intermediate(auth_client, root, 'OCSP Sub CA good')
            status, resp = _ocsp_status(root['id'], _serial_int(sub['id']))
            assert status == 'good'
            assert resp.certificate_status == ocsp.OCSPCertStatus.GOOD
            # CertID recomputed from the real certificate, as for a leaf
            assert resp.serial_number == _serial_int(sub['id'])

    def test_unknown_serial_stays_unknown(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='OCSP Sub Root unknown')
            status, resp = _ocsp_status(root['id'], 0x1234567)
            assert status == 'unknown'
            assert resp.certificate_status == ocsp.OCSPCertStatus.UNKNOWN


class TestRevokeIntermediateCa:

    def test_revoke_publishes_on_parent_crl_and_ocsp(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Revoke Root')
            sub = _intermediate(auth_client, root, 'Revoke Sub CA')
            serial = _serial_int(sub['id'])
            assert sub['revoked'] is False and sub['status'] == 'Active'

            r = _post(auth_client, f'{CAS}/{sub["id"]}/revoke',
                      {'reason': 'keyCompromise', 'invalidity_date': '2026-09-01T00:00:00Z'})
            assert r.status_code == 200, r.data
            data = _json(r)['data']
            assert data['revoked'] is True
            assert data['status'] == 'Revoked'
            assert data['revoke_reason'] == 'keyCompromise'
            assert data['revoked_at'] and data['invalidity_at'].startswith('2026-09-01')

            # Persistent record under the parent
            db.session.expire_all()
            rs = RevokedSerial.query.filter_by(caref=root['refid'], serial_number=str(serial)).first()
            assert rs is not None and rs.revoke_reason == 'keyCompromise' and rs.certificate_id is None

            # Parent CRL carries the serial with the reason and invalidity date
            entries = _crl_serials(root['id'])
            assert serial in entries
            reason = entries[serial].extensions.get_extension_for_class(x509.CRLReason).value
            assert reason.reason == x509.ReasonFlags.key_compromise
            inv = entries[serial].extensions.get_extension_for_class(x509.InvalidityDate).value
            assert inv.invalidity_date.year == 2026 and inv.invalidity_date.month == 9

            # Parent OCSP answers revoked with the reason
            status, resp = _ocsp_status(root['id'], serial)
            assert status == 'revoked'
            assert resp.certificate_status == ocsp.OCSPCertStatus.REVOKED
            assert resp.revocation_reason == x509.ReasonFlags.key_compromise

            # GET shows the state
            r = auth_client.get(f'{CAS}/{sub["id"]}')
            assert _json(r)['data']['status'] == 'Revoked'

    def test_revoke_is_permanent(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Revoke Root twice')
            sub = _intermediate(auth_client, root, 'Revoke Sub twice')
            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'superseded'}).status_code == 200
            r = _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'superseded'})
            assert r.status_code == 409

    def test_root_ca_not_revocable(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Revoke Root refused')
            r = _post(auth_client, f'{CAS}/{root["id"]}/revoke', {'reason': 'keyCompromise'})
            assert r.status_code == 400
            assert 'root' in _json(r)['message'].lower()
            assert _json(auth_client.get(f'{CAS}/{root["id"]}'))['data']['revoked'] is False

    def test_invalid_reason_and_future_invalidity(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Revoke Root reasons')
            sub = _intermediate(auth_client, root, 'Revoke Sub reasons')
            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'becauseISaidSo'}).status_code == 400
            r = _post(auth_client, f'{CAS}/{sub["id"]}/revoke',
                      {'reason': 'unspecified', 'invalidity_date': '2999-01-01T00:00:00Z'})
            assert r.status_code == 400
            assert _json(auth_client.get(f'{CAS}/{sub["id"]}'))['data']['revoked'] is False

    def test_not_found_and_permissions(self, app, auth_client, viewer_client, create_ca):
        with app.app_context():
            assert _post(auth_client, f'{CAS}/999999/revoke', {'reason': 'unspecified'}).status_code == 404
            root = create_ca(cn='Revoke Root viewer')
            sub = _intermediate(auth_client, root, 'Revoke Sub viewer')
            r = _post(viewer_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'unspecified'})
            assert r.status_code in (401, 403)

    def test_revoked_ca_signs_nothing(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            root = create_ca(cn='Revoke Root signing')
            sub = _intermediate(auth_client, root, 'Revoke Sub signing')
            leaf = create_cert(cn='before-revoke.example.com', ca_id=sub['id'])
            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'cACompromise'}).status_code == 200

            # Issue form
            r = _post(auth_client, '/api/v2/certificates', {
                'cn': 'after-revoke.example.com', 'ca_id': sub['id'],
                'key_type': 'RSA 2048', 'validity_days': 30, 'cert_type': 'server',
            })
            assert r.status_code == 400, r.data
            assert 'revoked' in _json(r)['message'].lower()

            # Sign CSR
            r = _post(auth_client, '/api/v2/csrs', {'cn': 'csr-after-revoke.example.com', 'key_type': 'RSA 2048'})
            csr_id = _json(r)['data']['id']
            r = _post(auth_client, f'/api/v2/csrs/{csr_id}/sign', {'ca_id': sub['id'], 'validity_days': 30})
            assert r.status_code == 400
            assert 'revoked' in _json(r)['message'].lower()

            # Renew a certificate it issued
            r = _post(auth_client, f'/api/v2/certificates/{leaf["id"]}/renew', {})
            assert r.status_code == 400, r.data

            # A sub-CA under it
            r = _post(auth_client, CAS, {
                'type': 'intermediate', 'parentCAId': sub['id'], 'commonName': 'Grandchild after revoke',
                'organization': 'Test Org', 'country': 'US', 'state': 'CA', 'locality': 'Test City',
                'keyType': 'RSA', 'keySize': 2048, 'validityYears': 2, 'hashAlgorithm': 'sha256',
            })
            assert r.status_code == 400
            assert 'revoked' in _json(r)['message'].lower()

            # Its own CRL still regenerates (serving continues until deletion)
            CRLService.generate_crl(sub['id'], username='test')

    def test_grandchild_blocked_when_ancestor_revoked(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Revoke Root chain')
            sub = _intermediate(auth_client, root, 'Revoke Sub chain')
            grand = _intermediate(auth_client, sub, 'Revoke Grandchild chain')
            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'keyCompromise'}).status_code == 200
            db.session.expire_all()
            assert db.session.get(CA, grand['id']).revoked_in_chain is True
            assert db.session.get(CA, grand['id']).revoked is False
            r = _post(auth_client, '/api/v2/certificates', {
                'cn': 'under-revoked-chain.example.com', 'ca_id': grand['id'],
                'key_type': 'RSA 2048', 'validity_days': 30, 'cert_type': 'server',
            })
            assert r.status_code == 400
            assert 'revoked' in _json(r)['message'].lower()

    def test_deleting_revoked_ca_keeps_parent_crl_entry(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Revoke Root delete')
            sub = _intermediate(auth_client, root, 'Revoke Sub delete')
            serial = _serial_int(sub['id'])
            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'cessationOfOperation'}).status_code == 200
            r = auth_client.delete(f'{CAS}/{sub["id"]}')
            assert r.status_code in (200, 204), r.data
            assert serial in _crl_serials(root['id'])
            status, _ = _ocsp_status(root['id'], serial)
            assert status == 'revoked'

    def test_ca_list_status_filter_value(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Revoke Root list')
            sub = _intermediate(auth_client, root, 'Revoke Sub list')
            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'unspecified'}).status_code == 200
            r = auth_client.get(f'{CAS}?per_page=200')
            rows = {c['id']: c for c in _json(r)['data']}
            assert rows[sub['id']]['status'] == 'Revoked'
            assert rows[sub['id']]['revoked'] is True


class TestRevocationReviewFollowUps:
    """Review of the first cut: a re-imported CA keeps its revocation, an
    unpublished CRL is reported, a malformed body revokes nothing, and a
    dedicated TSA signer under a revoked CA is refused."""

    def test_reimported_ca_stays_revoked(self, app, auth_client, create_ca):
        with app.app_context():
            from utils.key_codec import load_pem_bytes
            root = create_ca(cn='Reimport Root')
            sub = _intermediate(auth_client, root, 'Reimport Sub CA')
            serial = _serial_int(sub['id'])
            record = db.session.get(CA, sub['id'])
            cert_pem = base64.b64decode(record.crt)
            key_pem = load_pem_bytes(record.prv, context='test')

            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'keyCompromise'}).status_code == 200
            assert auth_client.delete(f'{CAS}/{sub["id"]}').status_code in (200, 204)

            r = auth_client.post(f'{CAS}/import',
                                 data={'pem_content': (cert_pem + key_pem).decode(), 'name': 'Reimported Sub CA'},
                                 content_type='multipart/form-data')
            assert r.status_code in (200, 201), r.data
            imported = _json(r)['data']
            assert imported['refid'] != sub['refid']
            assert imported['revoked'] is True
            assert imported['status'] == 'Revoked'
            assert imported['revoke_reason'] == 'keyCompromise'

            db.session.expire_all()
            new_ca = db.session.get(CA, imported['id'])
            assert new_ca.has_private_key
            assert new_ca.revoked_in_chain is True

            status, resp = _ocsp_status(root['id'], serial)
            assert status == 'revoked'
            assert resp.certificate_status == ocsp.OCSPCertStatus.REVOKED

            r = _post(auth_client, '/api/v2/certificates', {
                'cn': 'after-reimport.example.com', 'ca_id': imported['id'],
                'validity_days': 30, 'key_type': 'RSA 2048', 'cert_type': 'server',
            })
            assert r.status_code == 400, r.data
            assert 'revoked' in _json(r)['message'].lower()

    def test_record_wins_over_a_cleared_flag(self, app, auth_client, create_ca):
        """Even a row whose flag was cleared by hand stays revoked: the
        parent's record is the source of truth for OCSP and signing."""
        with app.app_context():
            root = create_ca(cn='Flag Root')
            sub = _intermediate(auth_client, root, 'Flag Sub CA')
            serial = _serial_int(sub['id'])
            assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'superseded'}).status_code == 200
            record = db.session.get(CA, sub['id'])
            record.revoked = False
            db.session.commit()
            db.session.expire_all()
            assert db.session.get(CA, sub['id']).is_revoked is True
            assert db.session.get(CA, sub['id']).revoked_in_chain is True
            status, _ = _ocsp_status(root['id'], serial)
            assert status == 'revoked'

    def test_unpublished_crl_is_reported(self, app, auth_client, create_ca, monkeypatch):
        with app.app_context():
            root = create_ca(cn='Unpublished Root')
            r = auth_client.patch(f'{CAS}/{root["id"]}', data=json.dumps({'cdp_enabled': True}),
                                  content_type='application/json')
            assert r.status_code == 200, r.data
            sub = _intermediate(auth_client, root, 'Unpublished Sub CA')

            def _fail(*a, **k):
                raise RuntimeError('CA is offline; restore it before generating a CRL')
            monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(_fail))

            r = _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'cACompromise'})
            assert r.status_code == 200, r.data
            body = _json(r)
            assert body['data']['revoked'] is True
            assert body['data']['warnings'], body
            assert 'could not be regenerated' in body['data']['warnings'][0]
            assert 'not fully published' in body['message']
            # The record is there for the next successful CRL
            rs = RevokedSerial.query.filter_by(caref=root['refid'], serial_number=str(_serial_int(sub['id']))).first()
            assert rs is not None

    def test_cdp_disabled_parent_is_reported(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='NoCDP Root')
            r = auth_client.patch(f'{CAS}/{root["id"]}', data=json.dumps({'cdp_enabled': False}),
                                  content_type='application/json')
            assert r.status_code == 200, r.data
            sub = _intermediate(auth_client, root, 'NoCDP Sub CA')
            r = _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'unspecified'})
            assert r.status_code == 200, r.data
            assert any('CDP is disabled' in w for w in _json(r)['data']['warnings'])

    def test_published_revocation_has_no_warning(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Published Root')
            r = auth_client.patch(f'{CAS}/{root["id"]}', data=json.dumps({'cdp_enabled': True}),
                                  content_type='application/json')
            assert r.status_code == 200, r.data
            sub = _intermediate(auth_client, root, 'Published Sub CA')
            r = _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'unspecified'})
            assert r.status_code == 200, r.data
            assert _json(r)['data']['warnings'] == []
            assert _json(r)['message'] == 'CA revoked'

    def test_malformed_body_revokes_nothing(self, app, auth_client, create_ca):
        with app.app_context():
            root = create_ca(cn='Malformed Root')
            sub = _intermediate(auth_client, root, 'Malformed Sub CA')
            r = auth_client.post(f'{CAS}/{sub["id"]}/revoke', data='{"reason":', content_type='application/json')
            assert r.status_code == 400, r.data
            r = auth_client.post(f'{CAS}/{sub["id"]}/revoke', data='[1, 2]', content_type='application/json')
            assert r.status_code == 400, r.data
            assert _json(auth_client.get(f'{CAS}/{sub["id"]}'))['data']['revoked'] is False
            # An empty body still means "unspecified"
            r = auth_client.post(f'{CAS}/{sub["id"]}/revoke')
            assert r.status_code == 200, r.data
            assert _json(r)['data']['revoke_reason'] == 'unspecified'

    def test_dedicated_tsa_signer_refused_under_revoked_ca(self, app, auth_client, create_ca):
        with app.app_context():
            from models import SystemConfig
            from services.tsa_signer_cert import issue_tsa_signer_certificate
            from services.tsa_service import (
                SIGNER_CONFIG_KEY, TSAConfigurationError, load_configured_signer,
            )
            root = create_ca(cn='TSA Signer Root')
            sub = _intermediate(auth_client, root, 'TSA Signer Sub CA')
            signer = issue_tsa_signer_certificate(ca=db.session.get(CA, sub['id']), cn='tsa-signer.example.com')
            cfg = SystemConfig.query.filter_by(key=SIGNER_CONFIG_KEY).first()
            previous = cfg.value if cfg else None
            if cfg is None:
                cfg = SystemConfig(key=SIGNER_CONFIG_KEY, value=signer.refid)
                db.session.add(cfg)
            else:
                cfg.value = signer.refid
            db.session.commit()
            try:
                assert load_configured_signer() is not None
                assert _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'keyCompromise'}).status_code == 200
                db.session.expire_all()
                with pytest.raises(TSAConfigurationError) as exc:
                    load_configured_signer()
                assert exc.value.reason == 'revoked'
                assert 'revoked CA' in str(exc.value)
            finally:
                cfg = SystemConfig.query.filter_by(key=SIGNER_CONFIG_KEY).first()
                if cfg is not None:
                    if previous:
                        cfg.value = previous
                    else:
                        db.session.delete(cfg)
                    db.session.commit()
