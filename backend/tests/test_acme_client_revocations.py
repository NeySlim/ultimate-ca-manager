"""ACME client revocations: the CA is told the local reason, and is asked again until it answers;
a key revoked as compromised stays known once its certificate is deleted (migration 128)."""
import json
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models import CA, RevokedSerial, WebhookDelivery, db
from models.acme_models import AcmeClientOrder
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


def test_a_proxy_order_whose_upstream_account_is_gone_is_not_retried_under_another(bench):
    from services.acme.acme_client_service import PROXY_ACCOUNT_UNKNOWN
    parent = bench.parent()
    parent.is_proxy_order = True
    parent.acme_client_account_id = None
    parent.account_url = None
    db.session.commit()
    _owe(bench)
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client), \
            patch('services.acme.acme_client_service.AcmeClientService.for_issuance',
                  return_value=bench.client):
        renew_mod.retry_upstream_revocations()
    bench.client.revoke_certificate.assert_not_called()
    owed = _owed(bench)
    # Never recorded rather than deleted: the proxy client holds the account
    assert owed[0]['error'] == PROXY_ACCOUNT_UNKNOWN and owed[0]['attempts'] == 2
    assert 'no longer exists' not in owed[0]['error']


def test_an_order_being_renewed_is_left_to_the_next_pass(bench):
    from services.acme.order_lease import OrderLease
    _owe(bench)
    OrderLease.take(bench.parent_id)
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        renew_mod.retry_upstream_revocations()
    bench.client.revoke_certificate.assert_not_called()


def _entry(serial):
    return {'serial': serial, 'certificate': 'PEM', 'reason': 1,
            'not_after': (utc_now() + timedelta(days=30)).isoformat()}


def test_a_debt_written_meanwhile_survives_a_writer_holding_an_older_copy(bench):
    """A revoke route writes without the order's lease while a renewal holds it:
    the renewal's own debt, written from the row it loaded earlier, keeps the route's."""
    order = bench.parent()
    assert order.upstream_revocations_list == []  # the renewal's copy, loaded now
    # The revoke route's write, which the loaded copy does not see
    AcmeClientOrder.query.filter_by(id=order.id).update(
        {'upstream_revocations': json.dumps([_entry('AA')])}, synchronize_session=False)
    renew_mod._owe_upstream_revocation(order, _entry('BB'), 'HTTP 503')
    assert sorted(e['serial'] for e in _owed(bench)) == ['AA', 'BB']


def test_a_write_between_the_read_and_the_update_is_kept(bench):
    """Compare-and-set: a list changed after it was read is read again, not overwritten."""
    order_id = bench.parent_id
    calls = []

    def _add(entries):
        if not calls:  # another writer commits its entry between this read and the write
            AcmeClientOrder.query.filter_by(id=order_id).update(
                {'upstream_revocations': json.dumps([_entry('AA')])}, synchronize_session=False)
        calls.append(len(entries))
        return entries + [_entry('BB')]
    renew_mod.update_owed(order_id, _add)
    db.session.commit()
    assert calls == [0, 1]
    assert sorted(e['serial'] for e in _owed(bench)) == ['AA', 'BB']


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_APP_PG_URL'), reason='UCM_TEST_APP_PG_URL not set')
def test_two_transactions_on_postgresql_keep_both_debts(bench):
    """Another connection commits its debt while this transaction holds an older copy."""
    from sqlalchemy import text
    order = bench.parent()
    assert order.upstream_revocations_list == []
    with db.engine.begin() as other:
        other.execute(text('UPDATE acme_client_orders SET upstream_revocations = :v WHERE id = :i'),
                      {'v': json.dumps([_entry('AA')]), 'i': order.id})
    renew_mod._owe_upstream_revocation(order, _entry('BB'), 'HTTP 503')
    assert sorted(e['serial'] for e in _owed(bench)) == ['AA', 'BB']


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


@pytest.mark.parametrize('local, sent', [('keyCompromise', 1), ('affiliationChanged', 3),
                                         ('cessationOfOperation', 5), ('certificateHold', None),
                                         ('unspecified', None), ('privilegeWithdrawn', 9),
                                         ('aACompromise', None)])
def test_only_a_reason_a_replaced_certificate_may_carry_reaches_the_ca(bench, local, sent):
    # The set a revoke route sends too (RFC 5280 §5.3.1 end-entity final reasons)
    row = bench.row()
    row.revoked, row.revoke_reason = True, local
    db.session.commit()
    assert bench.renew()[0]
    assert bench.client.revoke_certificate.call_args.kwargs == {'reason': sent}


def test_a_refused_reason_zero_is_also_dropped():
    client = MagicMock()
    client.revoke_certificate.side_effect = [_answer(400, 'badRevocationReason'), _answer(200)]
    assert renew_mod.send_upstream_revocation(client, b'pem', 0, 'x') is None
    assert [c.kwargs for c in client.revoke_certificate.call_args_list] == [{'reason': 0}, {'reason': None}]


def test_a_renewal_in_place_records_the_old_key_on_the_old_serial(bench, create_ca):
    _under_a_ca_held_here(bench, create_ca)
    assert bench.renew()[0]
    record = RevokedSerial.query.filter_by(serial_number=bench.old_serial, certificate_id=bench.cert_id).one()
    assert record.public_key_sha256 == public_key_sha256(bench.key.public_key())
    record_id = record.id
    # Deleting the row (now the new certificate) leaves the old serial with the old key
    row = bench.row()
    row.valid_to = utc_now() - timedelta(days=1)
    db.session.commit()
    record.public_key_sha256 = None
    db.session.commit()
    assert CertificateService.delete_certificate(bench.cert_id, username='admin')
    record = db.session.get(RevokedSerial, record_id)
    assert record.public_key_sha256 is None  # never the new key
    db.session.delete(record)
    db.session.commit()
