"""CA revocation (#343): findings of the independent review of v2.226."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import db, CA
from models.revoked_serial import RevokedSerial


def _revoke(auth_client, ca_id, reason='keyCompromise'):
    return auth_client.post(f'/api/v2/cas/{ca_id}/revoke', data=json.dumps({'reason': reason}),
                            content_type='application/json')


def _sub(auth_client, create_ca, parent, cn):
    return create_ca(cn=cn, type='intermediate', parentCAId=parent['id']) if 'parentCAId' in create_ca.__code__.co_varnames else _sub_api(auth_client, parent, cn)


def _sub_api(auth_client, parent, cn):
    r = auth_client.post('/api/v2/cas', data=json.dumps({
        'type': 'intermediate', 'parentCAId': parent['id'], 'commonName': cn, 'validityYears': 2,
        'organization': 'T', 'country': 'FR', 'keyType': 'RSA', 'keySize': 2048, 'hashAlgorithm': 'sha256'}),
        content_type='application/json')
    assert r.status_code in (200, 201), r.data
    return json.loads(r.data)['data']


class TestRevokeCaRules:
    def test_hold_refused_and_second_revocation_keeps_the_date(self, app, auth_client, create_ca):
        root = create_ca(cn='Rules Root')
        sub = _sub_api(auth_client, root, 'Rules Sub')
        r = _revoke(auth_client, sub['id'], 'certificateHold')
        assert r.status_code == 400 and 'hold' in json.loads(r.data)['message'].lower()
        r = _revoke(auth_client, sub['id'])
        assert r.status_code == 200, r.data
        body = json.loads(r.data)['data']
        assert 'warning_codes' in body
        with app.app_context():
            row = db.session.get(CA, sub['id'])
            rec = RevokedSerial.query.filter_by(serial_number=row.serial_number).first()
            first_at = rec.revoked_at
            assert row.valid_to == x509.load_pem_x509_certificate(base64.b64decode(row.crt)).not_valid_after_utc.replace(tzinfo=None)
            # The row loses its flag (a restore of an older backup): the record still says revoked
            row.revoked = False; row.revoked_at = None; row.revoke_reason = None; db.session.commit()
        r = auth_client.get(f"/api/v2/cas/{sub['id']}")
        body = json.loads(r.data)['data']
        assert body['revoked'] is True and body['status'] == 'Revoked' and body['revoke_reason'] == 'keyCompromise'
        r = _revoke(auth_client, sub['id'])
        assert r.status_code == 409 and 'already' in json.loads(r.data)['message']
        with app.app_context():
            db.session.expire_all()
            rec = RevokedSerial.query.filter_by(serial_number=db.session.get(CA, sub['id']).serial_number).first()
            assert rec.revoked_at == first_at          # RFC 5280: the date does not move
            assert db.session.get(CA, sub['id']).revoked is True   # the flag is back

    def test_offline_refused_on_a_revoked_ca(self, app, auth_client, create_ca):
        root = create_ca(cn='Offline Revoked Root')
        sub = _sub_api(auth_client, root, 'Offline Revoked Sub')
        assert _revoke(auth_client, sub['id']).status_code == 200
        r = auth_client.post(f"/api/v2/cas/{sub['id']}/offline", data=json.dumps({'password': 'Correct-Horse-9-Battery', 'mode': 'password_protected'}),
                             content_type='application/json')
        assert r.status_code == 409


class TestChainRevocationExposed:
    def test_grandchild_reports_revoked_in_chain_and_scep_tile_follows(self, app, auth_client, create_ca):
        from api.v2.dashboard import _scep_ca_usable
        root = create_ca(cn='Chain Root')
        sub = _sub_api(auth_client, root, 'Chain Sub')
        grand = _sub_api(auth_client, sub, 'Chain Grand')
        assert _revoke(auth_client, sub['id']).status_code == 200
        body = json.loads(auth_client.get(f"/api/v2/cas/{grand['id']}").data)['data']
        assert body['revoked'] is False and body['revoked_in_chain'] is True
        with app.app_context():
            assert _scep_ca_usable(db.session.get(CA, grand['id'])) is False
        # The settings that name a signing CA refuse it
        r = auth_client.put('/api/v2/tsa/config', data=json.dumps({'ca_id': grand['id']}), content_type='application/json')
        if r.status_code == 405:
            r = auth_client.patch('/api/v2/tsa/config', data=json.dumps({'ca_id': grand['id']}), content_type='application/json')
        assert r.status_code == 400, r.data
        for path in ('/api/v2/est/config', '/api/v2/xcep/config'):
            r = auth_client.put(path, data=json.dumps({'ca_id': grand['id']}), content_type='application/json')
            if r.status_code == 405:
                r = auth_client.patch(path, data=json.dumps({'ca_id': grand['id']}), content_type='application/json')
            assert r.status_code == 400, (path, r.data)


class TestParentCrlFromTheRow:
    def test_revoked_child_ca_listed_without_its_record(self, app, auth_client, create_ca):
        from services.crl.query import CRLQueryMixin
        root = create_ca(cn='Row CRL Root')
        sub = _sub_api(auth_client, root, 'Row CRL Sub')
        assert _revoke(auth_client, sub['id']).status_code == 200
        with app.app_context():
            row = db.session.get(CA, sub['id'])
            RevokedSerial.query.filter_by(serial_number=row.serial_number).delete(); db.session.commit()
            serials = {str(getattr(e, 'serial_number', '')) for e in CRLQueryMixin.get_revoked_certificates(root['id'])}
            assert row.serial_number in serials

    def test_backup_exports_the_list_with_the_cas(self, app, create_ca):
        with app.app_context():
            from services.backup_service import BackupService
            svc = BackupService()
            blob = svc.create_backup('Correct-Horse-9-Battery', include={'cas': True, 'certificates': False})
            _key, data = svc._decrypt_v2(blob, 'Correct-Horse-9-Battery')
        assert isinstance(data.get('revoked_serials'), list)


class TestExternalCaUnderRevokedAncestor:
    def test_certificate_from_a_healthy_issuer_can_still_be_installed(self, app, auth_client, create_ca):
        root = create_ca(cn='Healthy Root')
        sub = _sub_api(auth_client, root, 'Doomed Sub')
        r = auth_client.post('/api/v2/cas', data=json.dumps({
            'type': 'external', 'commonName': 'External Under Doomed', 'organization': 'T', 'country': 'FR',
            'keyType': 'RSA', 'keySize': 2048, 'hashAlgorithm': 'sha256'}), content_type='application/json')
        assert r.status_code in (200, 201), r.data
        ext = json.loads(r.data)['data']
        csr = x509.load_pem_x509_csr(ext['csr_pem'].encode())
        with app.app_context():
            from services.hsm.ca_key_loader import get_ca_signing_key
            sub_obj = db.session.get(CA, sub['id']); root_obj = db.session.get(CA, root['id'])
            sub_cert = x509.load_pem_x509_certificate(base64.b64decode(sub_obj.crt))
            root_cert = x509.load_pem_x509_certificate(base64.b64decode(root_obj.crt))
            now = datetime.now(timezone.utc)
            def issued_by(issuer_cert, issuer_key):
                return (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(issuer_cert.subject)
                        .public_key(csr.public_key()).serial_number(x509.random_serial_number())
                        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                        .sign(issuer_key, hashes.SHA256()))
            first = issued_by(sub_cert, get_ca_signing_key(sub_obj))
            healthy = issued_by(root_cert, get_ca_signing_key(root_obj))
        pem = lambda c: c.public_bytes(serialization.Encoding.PEM).decode()
        r = auth_client.post(f"/api/v2/cas/{ext['id']}/certificate", data={'pem_content': pem(first)}, content_type='multipart/form-data')
        assert r.status_code == 200, r.data
        assert _revoke(auth_client, sub['id']).status_code == 200
        # Now under a revoked ancestor: a certificate from the healthy root must install
        r = auth_client.post(f"/api/v2/cas/{ext['id']}/certificate", data={'pem_content': pem(healthy)}, content_type='multipart/form-data')
        assert r.status_code == 200, r.data
        body = json.loads(auth_client.get(f"/api/v2/cas/{ext['id']}").data)['data']
        assert body['revoked_in_chain'] is False


class TestReviewOfTheReviewFixes:
    def test_settings_refuse_a_changed_ca_but_keep_a_saved_one(self, app, auth_client, create_ca):
        root = create_ca(cn='Settings Root')
        sub = _sub_api(auth_client, root, 'Settings Sub')
        # TSA by refid (the form the UI sends)
        with app.app_context():
            sub_refid = db.session.get(CA, sub['id']).refid
        r = auth_client.patch('/api/v2/tsa/config', data=json.dumps({'ca_refid': sub_refid}), content_type='application/json')
        if r.status_code == 405:
            r = auth_client.put('/api/v2/tsa/config', data=json.dumps({'ca_refid': sub_refid}), content_type='application/json')
        assert r.status_code == 200, r.data
        assert _revoke(auth_client, sub['id']).status_code == 200
        # Re-saving the unchanged CA with another setting is not refused
        r = auth_client.patch('/api/v2/tsa/config', data=json.dumps({'ca_refid': sub_refid, 'enabled': False}), content_type='application/json')
        if r.status_code == 405:
            r = auth_client.put('/api/v2/tsa/config', data=json.dumps({'ca_refid': sub_refid, 'enabled': False}), content_type='application/json')
        assert r.status_code == 200, r.data
        # Choosing it afresh is
        other = create_ca(cn='Settings Other Root')
        with app.app_context():
            other_refid = db.session.get(CA, other['id']).refid
        r = auth_client.patch('/api/v2/tsa/config', data=json.dumps({'ca_refid': other_refid}), content_type='application/json')
        if r.status_code == 405:
            r = auth_client.put('/api/v2/tsa/config', data=json.dumps({'ca_refid': other_refid}), content_type='application/json')
        assert r.status_code == 200
        r = auth_client.patch('/api/v2/tsa/config', data=json.dumps({'ca_refid': sub_refid}), content_type='application/json')
        if r.status_code == 405:
            r = auth_client.put('/api/v2/tsa/config', data=json.dumps({'ca_refid': sub_refid}), content_type='application/json')
        assert r.status_code == 400 and 'revoked' in json.loads(r.data)['message']
        # WSTEP refuses a revoked CA too
        r = auth_client.patch('/api/v2/wstep/config', data=json.dumps({'ca_id': sub['id']}), content_type='application/json')
        if r.status_code == 405:
            r = auth_client.put('/api/v2/wstep/config', data=json.dumps({'ca_id': sub['id']}), content_type='application/json')
        assert r.status_code == 400, r.data

    def test_chain_message_differs_from_own_revocation(self, app, auth_client, create_ca):
        from utils.signing_ca import signing_ca_problem
        root = create_ca(cn='Msg Root')
        sub = _sub_api(auth_client, root, 'Msg Sub')
        grand = _sub_api(auth_client, sub, 'Msg Grand')
        assert _revoke(auth_client, sub['id']).status_code == 200
        with app.app_context():
            assert signing_ca_problem(db.session.get(CA, sub['id'])) == 'CA is revoked'
            assert 'above' in signing_ca_problem(db.session.get(CA, grand['id']))

    def test_request_cache_does_not_hide_a_revocation_made_in_the_request(self, app, auth_client, create_ca):
        root = create_ca(cn='Cache Root')
        sub = _sub_api(auth_client, root, 'Cache Sub')
        r = _revoke(auth_client, sub['id'])
        body = json.loads(r.data)['data']
        assert body['revoked'] is True and body['status'] == 'Revoked'
        listed = next(c for c in json.loads(auth_client.get('/api/v2/cas?per_page=300').data)['data'] if c['id'] == sub['id'])
        assert listed['status'] == 'Revoked'

    def test_delta_crl_lists_a_revoked_child_ca_from_its_row(self, app, auth_client, create_ca):
        root = create_ca(cn='Delta Root')
        with app.app_context():
            row = db.session.get(CA, root['id'])
            row.cdp_enabled = True; row.delta_crl_enabled = True; db.session.commit()
            from services.crl_service import CRLService
            CRLService.generate_crl(root['id'])
        sub = _sub_api(auth_client, root, 'Delta Sub')
        assert _revoke(auth_client, sub['id']).status_code == 200
        with app.app_context():
            row = db.session.get(CA, sub['id'])
            RevokedSerial.query.filter_by(serial_number=row.serial_number).delete()
            # The revocation regenerated the base CRL: a delta carries what came
            # after it, so the row's revocation is dated after that base
            from models.crl import CRLMetadata
            base = CRLMetadata.query.filter_by(ca_id=root['id'], is_delta=False).order_by(CRLMetadata.crl_number.desc()).first()
            row.revoked_at = base.this_update + timedelta(seconds=5)
            db.session.commit()
            from services.crl_service import CRLService
            delta = CRLService.generate_delta_crl(root['id'])
            crl = x509.load_pem_x509_crl(delta.crl_pem.encode())
            assert any(rc.serial_number == int(row.serial_number) for rc in crl)
