"""The issuer of a cross-certificate answers for it: CRL, OCSP, lookup, alerts (#400)."""
import base64
import uuid
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from services.crl_service import CRLService
from services.ocsp_service import OCSPService
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import make_cert, new_key, pem
from tests.test_serial_encoding_crl_ocsp import _make_ca
from utils.datetime_utils import utc_now


@pytest.fixture
def world(app, auth_client):
    """Root A (keyed, OCSP and CRL on), Root B held, B's cross-certificate by A attached."""
    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        a, key_a, cert_a = _make_ca(f'xs-a-{tag}', f'XS Root A {tag}')
        key_b = new_key()
        root_b = make_cert(f'XS Root B {tag}', key_b)
        SmartImporter().execute(pem(root_b))
        b = CA.query.filter_by(descr=f'XS Root B {tag}').one()
        cross = make_cert(f'XS Root B {tag}', key_b, f'XS Root A {tag}', key_a, days=300)
        r = auth_client.post(f'/api/v2/cas/{b.id}/cross-certificates', json={'certificate': pem(cross)})
        assert r.status_code == 201, r.data
        yield {'a': a.id, 'b': b.id, 'cross': cross, 'cert_a': cert_a, 'xid': r.get_json()['data']['id'],
               'root_b': root_b}


def _ocsp(a_id, serial, request_hash=hashes.SHA1()):
    der, status = OCSPService().generate_response(db.session.get(CA, a_id), serial, hash_algorithm=request_hash)
    return der, status


def _openssl_ocsp(tmp_path, der, cert_a, cross):
    import subprocess
    (tmp_path / 'r.der').write_bytes(der)
    (tmp_path / 'a.pem').write_bytes(pem(cert_a).encode())
    (tmp_path / 'x.pem').write_bytes(pem(cross).encode())
    out = subprocess.run(['openssl', 'ocsp', '-respin', 'r.der', '-issuer', 'a.pem', '-CAfile', 'a.pem',
                          '-cert', 'x.pem', '-no_nonce'], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout + out.stderr


def test_ocsp_of_the_issuer_answers_good_then_revoked_never_unknown(app, auth_client, world, tmp_path):
    with app.app_context():
        der, status = _ocsp(world['a'], world['cross'].serial_number)
        assert status == 'good'
        assert ': good' in _openssl_ocsp(tmp_path, der, world['cert_a'], world['cross'])
    r = auth_client.post(f"/api/v2/cas/{world['b']}/cross-certificates/{world['xid']}/revoke",
                         json={'reason': 'keyCompromise'})
    assert r.status_code == 200, r.data
    with app.app_context():
        der, status = _ocsp(world['a'], world['cross'].serial_number)
        assert status == 'revoked'
        assert ': revoked' in _openssl_ocsp(tmp_path, der, world['cert_a'], world['cross'])
        assert db.session.get(CA, world['b']).revoked is False


def test_crl_of_the_issuer_lists_the_revoked_cross_certificate_only(app, auth_client, world):
    auth_client.post(f"/api/v2/cas/{world['b']}/cross-certificates/{world['xid']}/revoke", json={})
    with app.app_context():
        crl = x509.load_pem_x509_crl(CRLService.generate_crl(world['a']).crl_pem.encode())
        assert world['cross'].serial_number in [e.serial_number for e in crl]
        assert world['root_b'].serial_number not in [e.serial_number for e in crl]
        root = db.session.get(CA, world['b'])
        assert root.revoked is False and root.is_revoked is False


def test_ocsp_for_a_serial_the_issuer_never_signed_is_still_unknown(app, world):
    with app.app_context():
        assert _ocsp(world['a'], world['root_b'].serial_number)[1] == 'unknown'


def test_revoked_cross_certificate_stays_revoked_at_its_issuer_lookup(app, auth_client, world):
    from services.cert import issued_lookup as lookup
    auth_client.post(f"/api/v2/cas/{world['b']}/cross-certificates/{world['xid']}/revoke", json={})
    with app.app_context():
        issuer = db.session.get(CA, world['a'])
        assert lookup.issued_certificate_status(issuer, world['cross'])[1] == lookup.REVOKED


def test_expiry_pass_announces_a_cross_certificate_close_to_its_end(app, world, monkeypatch):
    from services import expiry_alert_service
    seen = []
    monkeypatch.setattr('services.webhook_service.emit_cert_expiring',
                        lambda cert, days_left=None, ca_refid=None: seen.append(('expiring', cert, ca_refid)))
    monkeypatch.setattr('services.webhook_service.emit_cert_expired',
                        lambda cert, ca_refid=None: seen.append(('expired', cert, ca_refid)))
    with app.app_context():
        row = db.session.get(CACrossCertificate, world['xid'])
        refid = row.issuer_caref

        def mine():
            return [s for s in seen if s[1].get('type') == 'ca_cross_certificate' and s[1]['cross_certificate_id'] == row.id]

        expiry_alert_service._emit_expiry_webhooks()
        assert not mine()
        row.valid_to = utc_now() + timedelta(days=5)
        db.session.commit()
        expiry_alert_service._emit_expiry_webhooks()
        assert [(m[0], m[2]) for m in mine()] == [('expiring', refid)]
        row.valid_to = utc_now() - timedelta(hours=2)
        db.session.commit()
        expiry_alert_service._emit_expiry_webhooks()
        assert mine()[-1][0] == 'expired'
        row.revoked = True
        db.session.commit()
        before = len(mine())
        expiry_alert_service._emit_expiry_webhooks()
        assert len(mine()) == before


def test_ocsp_revokes_from_the_issuers_record_when_the_row_lost_its_flag(app, world):
    """A restore may bring the issuer's revocation record without the row's flag."""
    from models import RevokedSerial
    with app.app_context():
        issuer = db.session.get(CA, world['a'])
        db.session.add(RevokedSerial(caref=issuer.refid, serial_number=str(world['cross'].serial_number),
                                     revoke_reason='superseded', valid_to=utc_now() + timedelta(days=30)))
        db.session.commit()
        assert db.session.get(CACrossCertificate, world['xid']).revoked is False
        assert _ocsp(world['a'], world['cross'].serial_number)[1] == 'revoked'


def test_purging_a_ca_removes_its_cross_certificates(app, world):
    from services.deletion_blockers import purge_ca_dependents
    with app.app_context():
        purge_ca_dependents(db.session.get(CA, world['b']))
        assert CACrossCertificate.query.filter_by(ca_id=world['b']).count() == 0


def test_merging_a_duplicate_issuer_repoints_the_cross_certificates(app, world):
    from services.ski_aki_backfill import _move_ca_dependents
    with app.app_context():
        keeper = _make_ca(f'xs-keeper-{uuid.uuid4().hex[:6]}', 'XS Keeper')[0]
        dupe = db.session.get(CA, world['a'])
        dupe_refid = dupe.refid
        _move_ca_dependents(db, dupe, keeper)
        db.session.commit()
        row = db.session.get(CACrossCertificate, world['xid'])
        assert row.issuer_caref == keeper.refid != dupe_refid
