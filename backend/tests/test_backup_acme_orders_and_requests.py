"""ACME client orders, approvals and key recovery requests travel in every archive.

They were optional sections no route asked for, so a restore lost the renewal
schedule, the pending approvals and the recovery requests without a word.
"""
from datetime import timedelta

import pytest

from models import db
from services.backup.manifest import SECTIONS
from tests.test_backup_cross_installation import PASSWORD, _service
from tests.test_backup_hostile_corpus import _reseal
from tests.test_restore_replace_dependents import (  # noqa: F401  (fixture)
    _authority_row, _certificate_row, _orphans, _restore, _snapshot, _user, target,
)
from utils.datetime_utils import utc_now

CARRIED = ('acme_client_orders', 'approval_requests', 'key_recovery_requests')


def _order(**columns):
    from models.acme_models import AcmeClientOrder
    columns.setdefault('domains', '["orders.example.test"]')
    columns.setdefault('environment', 'production')
    row = AcmeClientOrder(**columns)
    db.session.add(row)
    db.session.flush()
    return row


def _orders():
    from models.acme_models import AcmeClientOrder
    return AcmeClientOrder.query.order_by(AcmeClientOrder.created_at).all()


def _payload(blob):
    return _service()._decrypt_framed(blob, PASSWORD)[1]


def _edited(blob, edit):
    data = _payload(blob)
    edit(data)
    return _reseal(blob, data)


# -- carried ------------------------------------------------------------------

def test_a_default_archive_carries_the_three_sections(target):
    from models.key_recovery import KeyRecoveryRequest
    from models.policy import ApprovalRequest

    user = _user('orders-admin')
    issuer = _authority_row('orders-ca')
    leaf = _certificate_row('orders-leaf', issuer)
    _order(order_url='https://ca.example.test/order/1', certificate_id=leaf.id, status='issued')
    db.session.add(ApprovalRequest(request_type='certificate', certificate_id=leaf.id,
                                   requester_id=user.id, created_at=utc_now()))
    db.session.add(KeyRecoveryRequest(cert_id=leaf.id, cert_refid=leaf.refid, reason='r',
                                      requested_by='orders-admin', requested_at=utc_now()))

    data = _payload(_snapshot())

    assert all(not SECTIONS[name].optional for name in CARRIED)
    assert {name: len(data[name]) for name in CARRIED} == dict.fromkeys(CARRIED, 1)
    assert not set(CARRIED) & set(data['metadata']['excluded_sections'])


# -- identity and fusion ----------------------------------------------------

def test_an_order_whose_url_changed_here_is_the_same_order(target):
    """A renewal hands the parent a new order URL: the archived row still finds it."""
    _user('orders-admin')
    _order(order_url='https://ca.example.test/order/first', status='issued')
    _order(domains='["pending.example.test"]', status='pending')    # no order URL yet
    blob = _snapshot()

    renewed = _orders()[0]
    renewed.order_url = 'https://ca.example.test/order/second'
    db.session.commit()

    for _ in range(2):
        _restore(blob, mode='merge')

    assert [(o.domains, o.order_url) for o in _orders()] == [
        ('["orders.example.test"]', 'https://ca.example.test/order/first'),
        ('["pending.example.test"]', None)]


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_a_renewal_finds_its_parent_restored_after_it(target, mode):
    """Both are new here: the child's link is set once the parent exists."""
    _user('orders-admin')
    parent = _order(order_url='https://ca.example.test/order/p', status='issued',
                    created_at=utc_now() - timedelta(days=30))
    _order(order_url='https://ca.example.test/order/c', status='pending',
           renewal_enabled=False, renewal_of_order_id=parent.id)
    blob = _snapshot()
    data = _payload(blob)
    for _order_row in _orders():
        db.session.delete(_order_row)
    db.session.flush()
    # Another order here, holding the parent's number where the engine hands it out again
    _order(domains='["other.example.test"]', status='issued', created_at=utc_now())
    db.session.commit()
    # The child first in the archive: its parent does not exist yet when it is written
    data['acme_client_orders'].sort(key=lambda row: row['renewal_of_order_id'] is None)

    results = _restore(_reseal(blob, data), mode=mode)

    restored_parent, child = [o for o in _orders() if o.domains == '["orders.example.test"]']
    assert child.renewal_of_order_id == restored_parent.id
    assert results['acme_client_orders'] == 2
    assert _orphans() == []


def test_a_pending_key_comes_back_under_this_installation_s_master_key(target):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from security.encryption import key_encryption

    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    _user('orders-admin')
    order = _order(order_url='https://ca.example.test/order/k', status='processing')
    order.pending_key = pem
    blob = _snapshot()
    assert _payload(blob)['acme_client_orders'][0]['pending_key'] == pem

    order.pending_key = None
    db.session.commit()
    _restore(blob)

    back = _orders()[0]
    assert back.pending_key == pem
    assert key_encryption.is_encrypted(back._pending_key) == key_encryption.is_enabled


# -- migration 121 on restored rows -------------------------------------------

def test_the_doubled_renewals_an_archive_brings_back_are_repaired(target):
    _user('orders-admin')
    issuer = _authority_row('orders-ca')
    kept = _certificate_row('orders-kept', issuer)
    other = _certificate_row('orders-other', issuer)
    start = utc_now() - timedelta(days=60)
    _order(order_url='https://ca.example.test/order/o', certificate_id=kept.id,
           status='issued', renewal_enabled=True, last_renewal_at=start,
           created_at=start)
    # What a renewal left before 121: its certificate and order URL are the older order's
    leftover = _order(order_url='https://ca.example.test/order/o', certificate_id=kept.id,
                      status='issued', created_at=start + timedelta(days=1))
    _order(order_url='https://ca.example.test/order/r', status='error', renewal_enabled=False,
           renewal_of_order_id=leftover.id, created_at=start + timedelta(days=3))
    # Taken off the schedule by a status check, certificate still live
    _order(domains='["valid.example.test"]', order_url='https://ca.example.test/order/v',
           certificate_id=other.id, status='valid', created_at=start + timedelta(days=2))
    blob = _snapshot()
    for row in _orders():
        db.session.delete(row)
    db.session.commit()

    results = _restore(blob)

    assert [(o.order_url, o.status, o.renewal_of_order_id) for o in _orders()] == [
        ('https://ca.example.test/order/o', 'issued', None),
        ('https://ca.example.test/order/v', 'issued', None),
        ('https://ca.example.test/order/r', 'error', None)]
    assert results['acme_client_orders_repaired'] == {'reissued': 1, 'dropped': 1}
    assert _orphans() == []


# -- a replacing restore over a renewal finished here -------------------------

def test_the_archive_wins_over_a_renewal_finished_here_and_says_so(target):
    from services.backup.restore_report import with_restore_warnings

    _user('orders-admin')
    issuer = _authority_row('orders-ca')
    leaf = _certificate_row('orders-leaf', issuer)
    mother = _order(order_url='https://ca.example.test/order/m', certificate_id=leaf.id,
                    status='issued', created_at=utc_now() - timedelta(days=60))
    _order(order_url='https://ca.example.test/order/c', status='pending',
           renewal_enabled=False, renewal_of_order_id=mother.id)
    blob = _snapshot()

    # The renewal finished here: the child is folded into its mother
    child = _orders()[1]
    mother.order_url, mother.last_renewal_at = child.order_url, utc_now()
    db.session.delete(child)
    db.session.commit()

    results = _restore(blob)

    mother, child = _orders()
    assert (mother.order_url, mother.last_renewal_at) == ('https://ca.example.test/order/m', None)
    assert (child.status, child.renewal_of_order_id) == ('pending', mother.id)
    warning = next(w for w in results['warnings'] if 'renewed here' in w)
    assert '["orders.example.test"]' in warning
    assert 'renewed here' in with_restore_warnings('Restored', results)


# -- approvals ------------------------------------------------------------------

def test_an_approval_whose_certificate_was_gone_at_export_does_not_refuse_the_archive(target):
    from models.policy import ApprovalRequest

    user = _user('orders-admin')
    issuer = _authority_row('orders-ca')
    leaf = _certificate_row('orders-leaf', issuer)
    db.session.add(ApprovalRequest(request_type='renewal', certificate_id=leaf.id,
                                   requester_id=user.id, created_at=utc_now()))

    def gone_at_export(data):
        # What the export writes when the certificate was deleted without the cleanup
        for row in data['approval_requests']:
            row['certificate_id'], row['certificate_id_ref'] = 900_321, None
    blob = _edited(_snapshot(), gone_at_export)
    db.session.query(ApprovalRequest).delete()
    db.session.commit()

    results = _restore(blob, mode='merge')

    assert ApprovalRequest.query.one().certificate_id is None
    assert any('certificate_id link was left empty' in w for w in results['warnings'])


# -- key recovery requests ----------------------------------------------------

def _recovery(cert, status='approved'):
    from models.key_recovery import KeyRecoveryRequest
    row = KeyRecoveryRequest(cert_id=cert.id, cert_refid=cert.refid, reason=status,
                             status=status, requested_by='orders-admin',
                             requested_at=utc_now())
    db.session.add(row)
    db.session.flush()
    return row


def test_a_recovery_request_follows_its_certificate_s_refid(target):
    """The archived number is the source's; an archive without its identity proves it."""
    from api.v2.key_recovery import _requested_certificate
    from models.key_recovery import KeyRecoveryRequest

    _user('orders-admin')
    issuer = _authority_row('orders-ca')
    _certificate_row('orders-a', issuer)
    wanted = _certificate_row('orders-b', issuer)
    _recovery(wanted)
    blob = _snapshot()
    data = _payload(blob)
    for row in data['key_recovery_requests']:
        row.pop('cert_id_ref', None)
        row['cert_id'] = 900_123
    blob = _reseal(blob, data)

    db.session.query(KeyRecoveryRequest).delete()
    db.session.delete(wanted)
    db.session.flush()
    _certificate_row('orders-x', issuer)        # takes the freed number on SQLite
    db.session.commit()

    _restore(blob, mode='merge')

    request = KeyRecoveryRequest.query.one()
    assert request.status == 'approved'
    assert _requested_certificate(request).refid == 'orders-b'


def test_an_open_request_whose_certificate_is_not_here_is_cancelled(target):
    from models import Certificate
    from models.key_recovery import KeyRecoveryRequest
    from services.backup.restore_report import with_restore_warnings

    _user('orders-admin')
    issuer = _authority_row('orders-ca')
    leaf = _certificate_row('orders-gone', issuer)
    _recovery(leaf, 'approved')
    _recovery(leaf, 'recovered')
    blob = _snapshot('users', 'key_recovery_requests')
    db.session.query(KeyRecoveryRequest).delete()
    db.session.delete(leaf)
    db.session.commit()

    results = _restore(blob, mode='merge')

    by_reason = {r.reason: (r.status, r.cert_id) for r in KeyRecoveryRequest.query.all()}
    assert by_reason == {'approved': ('cancelled', 0), 'recovered': ('recovered', 0)}
    assert db.session.get(Certificate, 0) is None
    assert 'orders-gone was cancelled' in with_restore_warnings('Restored', results)


# -- the three sections, carried or not, in a replacing restore ---------------

def test_carried_sections_are_replaced_like_any_other(target):
    """Rows added after the archive go, the archived ones come back on their certificate."""
    from models.acme_models import AcmeClientOrder
    from models.key_recovery import KeyRecoveryRequest
    from models.policy import ApprovalRequest

    user = _user('orders-admin')
    issuer = _authority_row('orders-ca')
    kept = _certificate_row('orders-kept', issuer)
    _order(order_url='https://ca.example.test/order/kept', certificate_id=kept.id, status='issued')
    db.session.add(ApprovalRequest(request_type='renewal', certificate_id=kept.id,
                                   requester_id=user.id, created_at=utc_now()))
    _recovery(kept)
    blob = _snapshot()

    gone = _certificate_row('orders-gone', issuer)
    _order(domains='["later.example.test"]', certificate_id=gone.id, status='issued')
    db.session.add(ApprovalRequest(request_type='renewal', certificate_id=gone.id,
                                   requester_id=user.id, created_at=utc_now()))
    _recovery(gone)
    db.session.commit()

    results = _restore(blob)

    assert [o.certificate_id for o in AcmeClientOrder.query.all()] == [kept.id]
    assert [a.certificate_id for a in ApprovalRequest.query.all()] == [kept.id]
    assert [(r.cert_refid, r.status) for r in KeyRecoveryRequest.query.all()] == [
        ('orders-kept', 'approved')]
    assert {name: results['removed'].get(name) for name in CARRIED} == dict.fromkeys(CARRIED, 1)
    assert 'acme_client_orders.certificate_id' not in results['unlinked_dependents']
    assert 'approval_requests' not in results['cleared_dependents']
    assert not results['closed_dependents']
    assert _orphans() == []


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_an_archive_without_them_leaves_them_alone(target, mode):
    """An older archive, or an include map without them: the rows here stay."""
    from models.key_recovery import KeyRecoveryRequest

    _user('orders-admin')
    issuer = _authority_row('orders-ca')
    leaf = _certificate_row('orders-leaf', issuer)
    blob = _edited(_snapshot(), lambda data: [data.pop(name) for name in CARRIED])
    _order(order_url='https://ca.example.test/order/here', certificate_id=leaf.id, status='issued')
    _recovery(leaf)
    db.session.commit()

    _restore(blob, mode=mode)

    assert [o.order_url for o in _orders()] == ['https://ca.example.test/order/here']
    assert KeyRecoveryRequest.query.one().status == 'approved'
