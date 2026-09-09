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
