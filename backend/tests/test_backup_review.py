"""Backups: findings of the independent review of #347's changes."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from models import db, CA, Certificate, SystemConfig


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _ca_dict(app, ca_id):
    with app.app_context():
        return CA.query.get(ca_id)


class TestOldBackupKeepsRevocation:
    def test_backup_without_revocation_fields_leaves_a_revoked_ca_revoked(self, app, create_ca):
        parent = create_ca(cn='Old Backup Parent')
        sub = create_ca(cn='Old Backup Sub', parent_id=parent['id']) if 'parent_id' in create_ca.__code__.co_varnames else None
        with app.app_context():
            row = db.session.get(CA, parent['id'])
            row.revoked = True; row.revoke_reason = 'keyCompromise'; row.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()
            old_backup = {'certificate_authorities': [{
                'refid': row.refid, 'descr': row.descr, 'subject': row.subject, 'issuer': row.issuer,
                'serial': row.serial, 'caref': row.caref,
                'certificate_pem': base64.b64decode(row.crt).decode(),
                # no revoked / revoked_at / revoke_reason: written before v2.226
            }]}
            results = {'cas': 0, 'certificates': 0}
            _service()._restore_cas(old_backup, results, master_key=None)
            db.session.commit()
            db.session.expire_all()
            assert db.session.get(CA, parent['id']).revoked is True


class TestOfflineAndFieldsRoundTrip:
    def test_offline_state_dates_and_urls_survive_a_restore(self, app, create_ca):
        ca = create_ca(cn='Offline Round Trip CA')
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.offline = True; row.offline_mode = 'password_protected'; row.offline_reason = 'vault'
            row.cdp_enabled = True; row.set_cdp_urls(['http://cdp.example.test/ca.crl'])
            row.ocsp_enabled = True; row.set_ocsp_urls(['http://ocsp.example.test'])
            db.session.commit()
            svc = _service()
            exported = svc._export_cas(True)
            data = next(c for c in exported if c['refid'] == row.refid)
            assert data['offline'] is True and data['valid_to']
            refid, valid_to = row.refid, row.valid_to
            db.session.delete(row); db.session.commit()
            results = {'cas': 0, 'certificates': 0}
            svc._restore_cas({'certificate_authorities': [data]}, results, master_key=None)
            db.session.commit()
            restored = CA.query.filter_by(refid=refid).first()
            assert restored.offline is True and restored.offline_mode == 'password_protected'
            assert restored.offline_reason == 'vault'
            assert restored.valid_to == valid_to and restored.valid_from is not None
            assert restored.cdp_enabled and restored.get_cdp_urls() == ['http://cdp.example.test/ca.crl']
            assert restored.ocsp_enabled and restored.get_ocsp_urls() == ['http://ocsp.example.test']


class TestRevokedSerialsWithUnknownCa:
    def test_dangling_records_are_skipped_and_counted(self, app, create_ca):
        ca = create_ca(cn='Known Serial CA')
        with app.app_context():
            from models.revoked_serial import RevokedSerial
            refid = db.session.get(CA, ca['id']).refid
            now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            results = {'cas': 0, 'certificates': 0}
            _service()._restore_revoked_serials({'revoked_serials': [
                {'caref': refid, 'serial_number': '4242', 'revoked_at': now, 'valid_to': now},
                {'caref': 'ghost-ca-refid', 'serial_number': '4343', 'revoked_at': now, 'valid_to': now},
            ]}, results)
            db.session.commit()
            assert results['revoked_serials'] == 1 and results['revoked_serials_skipped'] == 1
            assert RevokedSerial.query.filter_by(caref='ghost-ca-refid').first() is None
            assert RevokedSerial.query.filter_by(caref=refid, serial_number='4242').first() is not None


class TestCertificateInvalidityDateRoundTrip:
    def test_invalidity_at_is_exported_and_restored(self, app, create_ca, create_cert):
        ca = create_ca(cn='Invalidity CA')
        cert = create_cert(cn='invalidity.example.com', ca_id=ca['id'])
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            when = datetime(2026, 9, 1, 12, 0, 0)
            row.revoked = True; row.revoke_reason = 'keyCompromise'; row.revoked_at = when; row.invalidity_at = when
            db.session.commit()
            svc = _service()
            data = next(c for c in svc._export_certificates(True) if c['refid'] == row.refid)
            assert data['invalidity_at'].startswith('2026-09-01')
            row.invalidity_at = None; db.session.commit()
            svc._restore_certificates({'certificates': [data]}, {'cas': 0, 'certificates': 0}, master_key=None)
            db.session.commit(); db.session.expire_all()
            assert db.session.get(Certificate, cert['id']).invalidity_at == when


class TestPasswordRuleEverywhere:
    def test_legacy_backup_route_applies_the_rule_with_the_reason(self, auth_client):
        r = auth_client.post('/api/v2/settings/backup/create', data=json.dumps({'password': 'abcabcabcabc'}),
                             content_type='application/json')
        assert r.status_code == 400, r.data
        assert 'distinct' in json.loads(r.data)['message']

    def test_scheduled_backup_password_is_checked_when_saved(self, auth_client):
        r = auth_client.put('/api/v2/settings/general', data=json.dumps({'backup_password': 'aaaaaaaaaaaa'}),
                            content_type='application/json')
        if r.status_code == 405:
            r = auth_client.patch('/api/v2/settings/general', data=json.dumps({'backup_password': 'aaaaaaaaaaaa'}),
                                  content_type='application/json')
        assert r.status_code == 400, r.data
        assert 'distinct' in json.loads(r.data)['message']


class TestRestoreWrongPassword:
    def test_wrong_password_is_named(self, auth_client):
        import io
        blob = _service().create_backup('Correct-Horse-Battery-9')
        r = auth_client.post('/api/v2/system/restore', data={'password': 'Wrong-Horse-Battery-9',
                             'file': (io.BytesIO(blob), 'b.ucmbkp')}, content_type='multipart/form-data')
        assert r.status_code == 400, r.data
        assert 'password' in json.loads(r.data)['message'].lower()
