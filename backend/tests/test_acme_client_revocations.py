"""ACME client revocations: the CA is told the local reason, and is asked again until it answers;
a key revoked as compromised stays known once its certificate is deleted (migration 125)."""
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models import CA, RevokedSerial, WebhookDelivery, db
from services import acme_renewal_service as renew_mod
from services.acme import compromised_keys
from services.cert_service import CertificateService
from services.webhook_service import WebhookEndpoint, WebhookService
from tests.test_acme_renewal_in_place import Bench, _restore_config, _set_config
from utils.datetime_utils import utc_now
from utils.revocation_reasons import reason_code
from utils.spki_digest import public_key_sha256

EVENT = 'acme_order.revocation_failed'
ERROR = 'urn:ietf:params:acme:error:'


@pytest.fixture
def bench(app):
    with app.app_context():
        email = _set_config('acme.client.email', 'revocations@example.com')
        revoke = _set_config('acme.revoke_on_renewal', 'true')
        b = Bench(f'revocations-{uuid.uuid4().hex[:8]}.example.com')
        yield b
        b.cleanup()
        _restore_config('acme.revoke_on_renewal', revoke)
        _restore_config('acme.client.email', email)


@pytest.fixture
def endpoint(app):
    row = WebhookEndpoint(name=f'revocations-{uuid.uuid4().hex[:8]}', url='https://hooks.example/x',
                          events=json.dumps([EVENT]), enabled=True)
    db.session.add(row)
    db.session.commit()
    yield row
    db.session.rollback()
    WebhookDelivery.query.filter_by(endpoint_id=row.id).delete()
    db.session.delete(db.session.get(WebhookEndpoint, row.id))
    db.session.commit()


def _answer(status, problem=None):
    body = {'type': ERROR + problem, 'detail': problem} if problem else {}
    return SimpleNamespace(status_code=status, json=lambda: body, headers={})


def _owed(bench):
    db.session.expire_all()
    return bench.parent().upstream_revocations_list


# ---- the reason sent ------------------------------------------------------------------------

@pytest.mark.parametrize('local, code', [('keyCompromise', 1), ('key_compromise', 1), ('cessationOfOperation', 5),
                                         ('superseded', 4), ('certificateHold', 6), ('nonsense', 0)])
def test_the_rfc_5280_code_of_a_stored_reason(local, code):
    assert reason_code(local) == code


def test_a_certificate_revoked_as_compromised_is_revoked_so_at_the_ca(bench):
    row = bench.row()
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    assert bench.renew()[0]
    sent = bench.client.revoke_certificate.call_args
    assert sent.args[0] == bench.old_pem and sent.kwargs == {'reason': 1}


def test_a_refused_reason_is_dropped_and_said(bench, caplog):
    row = bench.row()
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    bench.client.revoke_certificate = MagicMock(side_effect=[_answer(400, 'badRevocationReason'), _answer(200)])
    with caplog.at_level('WARNING', logger=renew_mod.logger.name):
        assert bench.renew()[0]
    assert [c.kwargs for c in bench.client.revoke_certificate.call_args_list] == [{'reason': 1}, {'reason': None}]
    assert 'refused revocation reason 1' in caplog.text
    assert _owed(bench) == []


def test_the_reason_field_is_left_out_when_there_is_none():
    from tests.test_acme_client_revocation_ari import _certificate
    from cryptography.hazmat.primitives import serialization
    from services.acme.acme_client_service import AcmeClientService
    cert, _ = _certificate()
    service = AcmeClientService.__new__(AcmeClientService)
    service._fetch_directory = lambda: {'revokeCert': 'https://ca.example/revoke'}
    sent = {}
    service._post = lambda url, payload, use_jwk=False: sent.update(payload) or _answer(200)
    service.revoke_certificate(cert.public_bytes(serialization.Encoding.PEM), reason=None)
    assert set(sent) == {'certificate'}


# ---- a revocation the CA did not confirm is asked again ------------------------------------

def test_a_failed_revocation_is_kept_announced_and_retried(bench, endpoint):
    bench.client.revoke_certificate = MagicMock(return_value=_answer(503))
    assert bench.renew()[0]
    owed = _owed(bench)
    assert [e['serial'] for e in owed] == [bench.old_serial] and owed[0]['attempts'] == 1
    assert owed[0]['reason'] == 4 and owed[0]['error'] == 'HTTP 503'
    payload = json.loads(WebhookDelivery.query.filter_by(endpoint_id=endpoint.id).one().payload)
    assert payload['serial_number'] == bench.old_serial and payload['attempts'] == 1
    assert payload['order']['upstream_revocations_owed'] == 1 and 'challenges' not in payload['order']

    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        assert renew_mod.retry_upstream_revocations() >= 1
        assert _owed(bench)[0]['attempts'] == 2
        bench.client.revoke_certificate.return_value = _answer(200)
        renew_mod.retry_upstream_revocations()
    assert _owed(bench) == []
    assert bench.client.revoke_certificate.call_args.args[0] == bench.old_pem.decode()


def test_a_certificate_already_revoked_at_the_ca_is_done(bench):
    bench.client.revoke_certificate = MagicMock(return_value=_answer(400, 'alreadyRevoked'))
    assert bench.renew()[0]
    assert _owed(bench) == []


def test_the_renewal_task_retries(bench):
    bench.client.revoke_certificate = MagicMock(return_value=_answer(500))
    bench.renew()
    bench.client.revoke_certificate.return_value = _answer(200)
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client), \
            patch.object(renew_mod, '_order_is_due', return_value=False):
        renew_mod.scheduled_acme_renewal()
    assert _owed(bench) == []


def _owe(bench, **entry):
    parent = bench.parent()
    parent.upstream_revocations_list = [{'serial': '77', 'certificate': bench.old_pem.decode(), 'reason': 4,
                                         'not_after': (utc_now() + timedelta(days=30)).isoformat(),
                                         'attempts': 1, **entry}]
    db.session.commit()


def test_an_expired_certificate_is_no_longer_sent(bench):
    _owe(bench, not_after=(utc_now() - timedelta(days=1)).isoformat())
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        renew_mod.retry_upstream_revocations()
    bench.client.revoke_certificate.assert_not_called()
    assert _owed(bench) == [] and bench.parent().upstream_revocations is None


@pytest.mark.parametrize('attempts, hours_ago, sent', [(4, 1, True), (5, 1, False), (5, 25, True)])
def test_after_five_attempts_the_ca_is_asked_once_a_day(bench, attempts, hours_ago, sent):
    _owe(bench, attempts=attempts, last_attempt_at=(utc_now() - timedelta(hours=hours_ago)).isoformat())
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        renew_mod.retry_upstream_revocations()
    assert bench.client.revoke_certificate.called is sent


def test_an_order_being_renewed_is_left_to_the_next_pass(bench):
    from services.acme.order_lease import OrderLease
    _owe(bench)
    OrderLease.take(bench.parent_id)
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        renew_mod.retry_upstream_revocations()
    bench.client.revoke_certificate.assert_not_called()


def test_the_event_can_be_subscribed_to():
    assert EVENT in WebhookService.ALL_EVENTS


# ---- the key of a revocation record ---------------------------------------------------------

def _under_a_ca_held_here(bench, create_ca):
    row = bench.row()
    row.caref = create_ca()['refid']
    db.session.commit()


def test_a_revocation_record_keeps_the_key_digest(bench, create_ca):
    _under_a_ca_held_here(bench, create_ca)
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    record = RevokedSerial.query.filter_by(certificate_id=bench.cert_id).one()
    assert record.public_key_sha256 == public_key_sha256(bench.key.public_key())


def test_a_compromised_key_is_known_after_its_certificate_is_deleted(bench, create_ca):
    _under_a_ca_held_here(bench, create_ca)
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    assert CertificateService.delete_certificate(bench.cert_id, username='admin')
    assert compromised_keys.key_revoked_as_compromised(bench.key.public_key())
    RevokedSerial.query.filter_by(public_key_sha256=public_key_sha256(bench.key.public_key())).delete()
    db.session.commit()


def test_a_record_older_than_the_column_learns_the_key_at_deletion(bench, create_ca):
    _under_a_ca_held_here(bench, create_ca)
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    RevokedSerial.query.filter_by(certificate_id=bench.cert_id).update({'public_key_sha256': None})
    db.session.commit()
    assert CertificateService.delete_certificate(bench.cert_id, username='admin')
    digest = public_key_sha256(bench.key.public_key())
    assert RevokedSerial.query.filter_by(public_key_sha256=digest).count() == 1
    RevokedSerial.query.filter_by(public_key_sha256=digest).delete()
    db.session.commit()


def test_a_key_that_cannot_be_read_never_fails_the_revocation(bench, create_ca):
    _under_a_ca_held_here(bench, create_ca)
    with patch('utils.spki_digest.x509.load_pem_x509_certificate', side_effect=RuntimeError('FIPS provider')):
        CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    record = RevokedSerial.query.filter_by(certificate_id=bench.cert_id).one()
    assert record.public_key_sha256 is None
    # The row is still there: the comparison of the certificate rows answers
    assert compromised_keys.key_revoked_as_compromised(bench.key.public_key())


def test_a_row_that_fails_to_load_says_nothing_of_the_key(bench):
    row = bench.row()
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    with patch.object(compromised_keys, '_row_public_key_der', side_effect=RuntimeError('FIPS provider')):
        assert compromised_keys.key_revoked_as_compromised(bench.key.public_key()) is False


def test_a_backup_carries_the_key_digest(app, bench, create_ca):
    from services.backup_service import BackupService
    _under_a_ca_held_here(bench, create_ca)
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    record = RevokedSerial.query.filter_by(certificate_id=bench.cert_id).one()
    exported = [r for r in BackupService()._export_revoked_serials(True)
                if r['serial_number'] == record.serial_number and r['caref'] == record.caref]
    assert exported[0]['public_key_sha256'] == record.public_key_sha256
    digest, caref, serial = record.public_key_sha256, record.caref, record.serial_number
    record.public_key_sha256 = None
    db.session.commit()
    BackupService()._restore_revoked_serials({'revoked_serials': exported}, {})
    db.session.commit()
    assert RevokedSerial.query.filter_by(caref=caref, serial_number=serial).one().public_key_sha256 == digest
    # An archive older than the column leaves the digest as it is
    BackupService()._restore_revoked_serials({'revoked_serials': [
        {k: v for k, v in exported[0].items() if k != 'public_key_sha256'}]}, {})
    db.session.commit()
    assert RevokedSerial.query.filter_by(caref=caref, serial_number=serial).one().public_key_sha256 == digest
    assert db.session.get(CA, CA.query.filter_by(refid=caref).one().id) is not None
