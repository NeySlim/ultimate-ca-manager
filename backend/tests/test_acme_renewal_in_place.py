"""ACME client: a renewal keeps the certificate row, its key survives a cut, one renewal at a time."""
import base64
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text

from models import Certificate, DnsProvider, RevokedSerial, SystemConfig, db
from models.acme_models import AcmeClientOrder
from models.deploy import DeployBinding, DeployDelivery, DeployTarget
from services import acme_renewal_service as renew_mod
from services.acme.order_lease import LEASE_DURATION, OrderLease
from services.cert_service import CertificateService
from tests.acme_fake_ca import FakeCA, key_pem, leaf_of, names_json
from tests.db_write_probe import watching_writes
from utils.datetime_utils import utc_now
from utils.key_codec import load_pem_bytes


def _pub(key_or_cert):
    return key_or_cert.public_key().public_bytes(serialization.Encoding.DER,
                                                 serialization.PublicFormat.SubjectPublicKeyInfo)


def _stored_key(row):
    return serialization.load_pem_private_key(load_pem_bytes(row.prv, context='test'), None)


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    previous = row.value if row else None
    if row is None:
        row = SystemConfig(key=key, description='test')
        db.session.add(row)
    row.value = value
    db.session.commit()
    return previous


def _restore_config(key, previous):
    row = SystemConfig.query.filter_by(key=key).first()
    if previous is None and row is not None:
        db.session.delete(row)
    elif row is not None:
        row.value = previous
    db.session.commit()


class Bench:
    """An issued order, its certificate imported from the fake CA, and what a renewal needs."""

    def __init__(self, name):
        self.name = name
        self.ca = FakeCA(base=f'https://ca-{uuid.uuid4().hex[:8]}.example')
        self.key = ec.generate_private_key(ec.SECP256R1())
        pem = self.ca.issue(self.key.public_key(), [name])
        leaf_pem, chain_pem = pem.split('-----END CERTIFICATE-----\n', 1)
        row = CertificateService.import_certificate(
            descr=name, cert_pem=leaf_pem + '-----END CERTIFICATE-----\n', key_pem=key_pem(self.key),
            chain_pem=chain_pem, username='system', source='acme_client')
        self.provider = DnsProvider(name=f'inplace-{uuid.uuid4().hex[:8]}', provider_type='gandi',
                                    credentials='{}')
        db.session.add(self.provider)
        db.session.flush()
        self.old_url = self.ca.order(f'{self.ca.base}/order/old', [name], pem=pem)
        parent = AcmeClientOrder(domains=names_json([name]), environment='production', challenge_type='dns-01',
                                 status='issued', renewal_enabled=True, dns_provider_id=self.provider.id,
                                 order_url=self.old_url, certificate_id=row.id, key_source='generate',
                                 key_type='EC-P256', expires_at=row.valid_to)
        db.session.add(parent)
        db.session.commit()
        self.parent_id, self.cert_id, self.refid = parent.id, row.id, row.refid
        self.old_serial, self.old_pem = row.serial_number, base64.b64decode(row.crt)
        self.extra_orders, self.extra_certs = [], []
        self.client = self.ca.client()
        self.client._fetch_directory = lambda: {}
        self.client._get_account_url = lambda: 'https://ca.example/acct/1'
        self.client.verify_challenge = lambda _order, _domain: (True, 'submitted')
        self.client.revoke_certificate = MagicMock(return_value=SimpleNamespace(status_code=200))
        self.client.create_order = MagicMock(side_effect=self._create_order)

    def child(self, status='ready', **fields):
        url = self.ca.order(f'{self.ca.base}/order/{uuid.uuid4().hex[:8]}', [self.name], status=status)
        row = AcmeClientOrder(domains=names_json([self.name]), environment='production',
                              challenge_type='dns-01', status=status, order_url=url,
                              finalize_url=f'{url}/finalize', dns_provider_id=self.provider.id,
                              key_type='EC-P256', **fields)
        row.set_challenges_dict({self.name: {'dns_txt_value': 'token'}})
        db.session.add(row)
        db.session.commit()
        self.extra_orders.append(row.id)
        return row

    def _create_order(self, **_kwargs):
        return True, 'ok', self.child()

    def renew(self, parent_id=None, wait=None, **kwargs):
        dns = MagicMock()
        dns.create_txt_record.return_value = (True, 'ok')
        dns.delete_txt_record.return_value = (True, 'ok')
        waited = wait or (lambda *_a, **_k: {'ok': True, 'missing': [], 'waited': 0})
        with patch('services.acme.dns_providers.create_provider', return_value=dns), \
                patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=self.client), \
                patch('services.acme.acme_client_service.time.sleep', return_value=None), \
                patch.object(renew_mod, 'wait_for_challenges', side_effect=waited):
            return renew_mod.renew_certificate(self.parent(parent_id), **kwargs)

    def parent(self, parent_id=None):
        return db.session.get(AcmeClientOrder, parent_id or self.parent_id)

    def second_parent(self):
        """Another issued order for the same names, with a certificate and a key of its own."""
        key = ec.generate_private_key(ec.SECP256R1())
        pem = self.ca.issue(key.public_key(), [self.name])
        leaf_pem, chain_pem = pem.split('-----END CERTIFICATE-----\n', 1)
        row = CertificateService.import_certificate(
            descr=self.name, cert_pem=leaf_pem + '-----END CERTIFICATE-----\n', key_pem=key_pem(key),
            chain_pem=chain_pem, username='system', source='acme_client')
        url = self.ca.order(f'{self.ca.base}/order/{uuid.uuid4().hex[:8]}', [self.name], pem=pem)
        order = AcmeClientOrder(domains=names_json([self.name]), environment='production', challenge_type='dns-01',
                                status='issued', renewal_enabled=True, dns_provider_id=self.provider.id,
                                order_url=url, certificate_id=row.id, key_source='generate',
                                key_type='EC-P256', expires_at=row.valid_to)
        db.session.add(order)
        db.session.commit()
        self.extra_orders.append(order.id)
        self.extra_certs.append(row.id)
        return order, row.id

    def row(self):
        db.session.expire_all()
        return db.session.get(Certificate, self.cert_id)

    def cleanup(self):
        db.session.rollback()
        ids = [self.parent_id] + self.extra_orders
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(ids)).delete(synchronize_session=False)
        names = f'%{self.name}%'
        cert_ids = ([c.id for c in Certificate.query.filter(Certificate.descr == self.name)]
                    + [self.cert_id] + [c for c in self.extra_certs if c])
        binding_ids = [b.id for b in DeployBinding.query.filter(DeployBinding.certificate_id.in_(cert_ids))]
        target_ids = [b.target_id for b in DeployBinding.query.filter(DeployBinding.id.in_(binding_ids))]
        DeployDelivery.query.filter(DeployDelivery.binding_id.in_(binding_ids)).delete(synchronize_session=False)
        DeployBinding.query.filter(DeployBinding.id.in_(binding_ids)).delete(synchronize_session=False)
        DeployTarget.query.filter(DeployTarget.id.in_(target_ids)).delete(synchronize_session=False)
        RevokedSerial.query.filter(RevokedSerial.certificate_id.in_(cert_ids)).delete(synchronize_session=False)
        Certificate.query.filter(Certificate.id.in_(cert_ids)).delete(synchronize_session=False)
        db.session.delete(db.session.get(DnsProvider, self.provider.id))
        db.session.commit()
        assert names


@pytest.fixture
def bench(app):
    with app.app_context():
        email = _set_config('acme.client.email', 'inplace@example.com')
        b = Bench(f'inplace-{uuid.uuid4().hex[:8]}.example.com')
        yield b
        b.cleanup()
        _restore_config('acme.client.email', email)


# ---- renewal in place -------------------------------------------------------------------

def test_a_renewal_writes_the_new_certificate_into_the_same_row(bench):
    ok, _message = bench.renew()
    assert ok
    row = bench.row()
    assert (row.id, row.refid) == (bench.cert_id, bench.refid)
    leaf = leaf_of(base64.b64decode(row.crt).decode())
    assert str(leaf.serial_number) == row.serial_number != bench.old_serial
    key = _stored_key(row)
    assert _pub(key) == _pub(leaf) != _pub(bench.key)  # a new key, the certificate's
    assert row.renewed_times == 1 and row.valid_to == leaf.not_valid_after_utc.replace(tzinfo=None)
    assert Certificate.query.filter_by(descr=bench.name).count() == 1

    parent = bench.parent()
    assert parent.certificate_id == bench.cert_id and parent.status == 'issued'
    assert parent.order_url != bench.old_url and parent.certificate_url == f'{parent.order_url}/cert'
    assert parent.expires_at == row.valid_to and parent.renewal_failures == 0
    # The order the renewal opened is gone, with its pending key
    assert AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(bench.extra_orders)).count() == 0


def test_a_deployment_bound_to_the_certificate_is_queued_by_the_renewal(bench):
    target = DeployTarget(name=f't-{uuid.uuid4().hex[:8]}', host='h.example', username='u', private_key='k')
    db.session.add(target)
    db.session.flush()
    binding = DeployBinding(target_id=target.id, certificate_id=bench.cert_id, cert_path='/srv/c.pem')
    db.session.add(binding)
    db.session.commit()
    binding_id = binding.id
    bench.renew()
    queued = DeployDelivery.query.filter_by(binding_id=binding_id).all()
    assert [d.event_type for d in queued] == ['certificate.renewed']


def test_the_renewal_event_names_the_same_certificate(bench):
    with patch('services.webhook_service.emit_cert_renewed') as emitted:
        bench.renew()
    payload = emitted.call_args.args[0]
    assert (payload['id'], payload['refid']) == (bench.cert_id, bench.refid)
    assert payload['serial_number'] != bench.old_serial


def test_the_ari_window_of_the_replaced_certificate_is_forgotten(bench):
    # Same id after the renewal: a window kept under it would make the new certificate due at once
    renew_mod._ARI_CACHE[(None, bench.cert_id)] = {'info': {}, 'retry_after': utc_now() + timedelta(hours=6)}
    bench.renew()
    assert (None, bench.cert_id) not in renew_mod._ARI_CACHE


def test_a_revoked_row_keeps_its_revocation_and_the_order_moves_to_a_new_row(bench):
    row = bench.row()
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    bench.renew()
    parent = bench.parent()
    assert parent.certificate_id != bench.cert_id
    assert bench.row().revoked and bench.row().serial_number == bench.old_serial


def test_a_deleted_row_is_replaced_by_a_new_one(bench):
    parent = bench.parent()
    parent.certificate_id = None
    db.session.commit()
    bench.renew()
    new = db.session.get(Certificate, bench.parent().certificate_id)
    assert new is not None and new.id != bench.cert_id and new.descr == bench.name


# ---- revoke_on_renewal ------------------------------------------------------------------

@pytest.fixture
def revoke_on_renewal(app):
    previous = _set_config('acme.revoke_on_renewal', 'true')
    yield
    _restore_config('acme.revoke_on_renewal', previous)


def test_revocation_on_renewal_sends_the_old_certificate_and_leaves_the_row_valid(bench, revoke_on_renewal):
    bench.renew()
    row = bench.row()
    assert not row.revoked
    sent = bench.client.revoke_certificate.call_args
    assert sent.args[0] == bench.old_pem and sent.kwargs == {'reason': 4}
    # No CA held here for this issuer: nothing for a local CRL
    assert RevokedSerial.query.filter_by(certificate_id=bench.cert_id).count() == 0


def test_revocation_on_renewal_records_the_old_serial_under_a_ca_held_here(bench, revoke_on_renewal, create_ca):
    ca = create_ca()
    row = bench.row()
    row.caref = ca['refid']
    db.session.commit()
    bench.renew()
    record = RevokedSerial.query.filter_by(certificate_id=bench.cert_id).one()
    assert (record.caref, record.serial_number, record.revoke_reason) == (ca['refid'], bench.old_serial, 'superseded')
    assert not bench.row().revoked


# ---- the key is kept before the finalize request ------------------------------------------

def test_the_key_is_committed_before_the_finalize_request(app, bench):
    order = bench.child()
    seen = {}
    with watching_writes() as pending_writes:
        def at_finalize(order_url):
            seen['writes'] = pending_writes()
            stored = db.session.execute(text(
                f'SELECT pending_key FROM {AcmeClientOrder.__tablename__} WHERE id = :i'), {'i': order.id}).scalar()
            seen['stored'] = stored
        bench.ca.on_finalize = at_finalize
        ok, _msg, cert_id = bench.client.finalize_order(order)
    assert ok
    assert seen['writes'] == [] and seen['stored']
    stored = db.session.get(AcmeClientOrder, order.id)
    assert stored.pending_key is None and stored.certificate_id == cert_id
    bench.extra_certs.append(cert_id)


def _raw_pending_key(order_id):
    return db.session.execute(text(f'SELECT pending_key FROM {AcmeClientOrder.__tablename__} WHERE id = :i'),
                              {'i': order_id}).scalar()


def test_the_pending_key_is_stored_like_a_certificate_key_and_never_shown(app, bench, encryption_enabled):
    order = bench.child()
    pem = key_pem(ec.generate_private_key(ec.SECP256R1()))
    order.pending_key = pem
    db.session.commit()
    raw = _raw_pending_key(order.id)
    assert encryption_enabled.key_encryption.is_encrypted(raw)
    assert load_pem_bytes(raw, context='test').decode() == pem
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order.id).pending_key == pem
    assert not any('pending' in k or 'claimed' in k or 'renewal_of' in k for k in order.to_dict())


def test_enabling_encryption_encrypts_a_pending_key_kept_before(app, bench, encryption_enabled, monkeypatch):
    order = bench.child()
    pem = key_pem(ec.generate_private_key(ec.SECP256R1()))
    with patch.object(encryption_enabled.key_encryption, '_enabled', False):  # written before the key existed
        order.pending_key = pem
        db.session.commit()
    assert not encryption_enabled.key_encryption.is_encrypted(_raw_pending_key(order.id))
    every = encryption_enabled.master_key_values
    monkeypatch.setattr(encryption_enabled, 'master_key_values',
                        lambda: (v for v in every() if isinstance(v[1], AcmeClientOrder) and v[1].id == order.id))
    encrypted, _skipped, errors = encryption_enabled.encrypt_all_keys(dry_run=False)
    assert (encrypted, errors) == (1, [])
    assert encryption_enabled.key_encryption.is_encrypted(_raw_pending_key(order.id))
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order.id).pending_key == pem


class _Killed(BaseException):
    """What a SIGKILL leaves: no handler runs."""


def test_a_finalization_cut_after_the_request_is_resumed_with_its_key(app, bench):
    order = bench.child()
    order_id = order.id

    def killed(_order_url):
        raise _Killed()

    bench.ca.on_download = killed
    with pytest.raises(_Killed):
        bench.client.finalize_order(order)
    db.session.rollback()
    cut = db.session.get(AcmeClientOrder, order_id)
    assert cut.status == 'valid' and cut.pending_key and cut.certificate_id is None

    bench.ca.on_download = None
    ok, message, cert_id = bench.client.finalize_order(cut)
    assert ok, message
    bench.extra_certs.append(cert_id)
    row = db.session.get(Certificate, cert_id)
    leaf = leaf_of(base64.b64decode(row.crt).decode())
    assert _pub(_stored_key(row)) == _pub(leaf)
    done = db.session.get(AcmeClientOrder, order_id)
    assert done.status == 'issued' and done.pending_key is None


def test_a_valid_order_with_an_external_csr_is_imported_without_a_key(app, bench):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    key = ec.generate_private_key(ec.SECP256R1())
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, bench.name)])).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(bench.name)]), critical=False).sign(key, hashes.SHA256())
    order = bench.child(key_source='csr', csr_pem=csr.public_bytes(serialization.Encoding.PEM).decode())
    bench.ca.orders[order.order_url].update(status='valid', pem=bench.ca.issue(key.public_key(), [bench.name]))
    ok, message, cert_id = bench.client.finalize_order(order)
    assert ok, message
    bench.extra_certs.append(cert_id)
    assert db.session.get(Certificate, cert_id).prv is None


def test_a_valid_order_reusing_a_key_takes_it_from_its_source(app, bench):
    order = bench.child(key_source='reuse', source_certificate_id=bench.cert_id)
    bench.ca.orders[order.order_url].update(status='valid', pem=bench.ca.issue(bench.key.public_key(), [bench.name]))
    ok, message, cert_id = bench.client.finalize_order(order)
    assert ok, message
    bench.extra_certs.append(cert_id)
    assert _pub(_stored_key(db.session.get(Certificate, cert_id))) == _pub(bench.key)


def test_a_valid_order_whose_key_was_never_kept_says_so(app, bench):
    order = bench.child()
    bench.ca.orders[order.order_url].update(
        status='valid', pem=bench.ca.issue(ec.generate_private_key(ec.SECP256R1()).public_key(), [bench.name]))
    ok, message, _cert = bench.client.finalize_order(order)
    assert not ok and 'was not kept' in message


def test_a_ready_order_that_kept_a_key_sends_it_again(app, bench):
    order = bench.child()
    kept = ec.generate_private_key(ec.SECP256R1())
    order.pending_key = key_pem(kept)
    db.session.commit()
    ok, message, cert_id = bench.client.finalize_order(order)
    assert ok, message
    bench.extra_certs.append(cert_id)
    assert _pub(_stored_key(db.session.get(Certificate, cert_id))) == _pub(kept)


def test_an_import_already_made_is_not_made_twice(app, bench):
    # A resumed finalization may follow an import whose order update was never saved
    key = ec.generate_private_key(ec.SECP256R1())
    pem = bench.ca.issue(key.public_key(), [bench.name])
    first = bench.client._import_certificate(cert_pem=pem, key_pem=key_pem(key), domains=[bench.name])
    again = bench.client._import_certificate(cert_pem=pem, key_pem=key_pem(key), domains=[bench.name])
    assert first and again == first


def test_a_certificate_for_another_key_is_refused(app, bench):
    order = bench.child(status='valid', renewal_enabled=False)
    order.pending_key = key_pem(ec.generate_private_key(ec.SECP256R1()))
    db.session.commit()
    bench.ca.orders[order.order_url].update(
        status='valid', pem=bench.ca.issue(ec.generate_private_key(ec.SECP256R1()).public_key(), [bench.name]))
    ok, message, _cert = bench.client.finalize_order(order, renews=bench.parent())
    assert not ok and 'does not match' in message
    assert bench.row().serial_number == bench.old_serial


def test_a_finalization_that_lost_its_lease_sends_nothing(app, bench):
    order = bench.child()
    stale = OrderLease.take(order.id)
    AcmeClientOrder.query.filter_by(id=order.id).update({'renewal_claimed_at': None})
    db.session.commit()
    OrderLease.take(order.id)  # another holder
    ok, message, _cert = bench.client.finalize_order(order, lease=stale)
    assert not ok and message == renew_mod.LEASE_LOST
    assert f'{order.order_url}/finalize' not in [url for url, _payload in bench.ca.posts]
    assert db.session.get(AcmeClientOrder, order.id).pending_key is None


# ---- a renewal resumes the order an interrupted one left ----------------------------------

def _cut_renewal(bench):
    """A renewal killed once the CA issued: its order holds the key, nothing was imported."""
    def killed(_order_url):
        raise _Killed()

    bench.ca.on_download = killed
    lease = OrderLease.take(bench.parent_id)
    with pytest.raises(_Killed):
        bench.renew(lease=lease)
    db.session.rollback()
    bench.ca.on_download = None
    # The dead holder's lease runs out
    AcmeClientOrder.query.filter_by(id=bench.parent_id).update(
        {'renewal_claimed_at': utc_now() - LEASE_DURATION - timedelta(seconds=1)})
    db.session.commit()
    kept = AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(bench.extra_orders)).one()
    assert kept.status == 'valid' and kept.pending_key and kept.renewal_enabled is False
    return kept


def test_the_next_renewal_imports_what_the_interrupted_one_left(bench):
    kept = _cut_renewal(bench)
    issued = bench.ca.orders[kept.order_url]['pem']
    bench.client.create_order.reset_mock()
    ok, _message = bench.renew()
    assert ok
    bench.client.create_order.assert_not_called()  # no second certificate asked for
    row = bench.row()
    assert base64.b64decode(row.crt).decode().startswith(issued.split('-----END CERTIFICATE-----')[0])
    assert _pub(_stored_key(row)) == _pub(leaf_of(issued))
    assert db.session.get(AcmeClientOrder, kept.id) is None
    assert bench.parent().order_url == kept.order_url


@pytest.mark.parametrize('state', ['invalid', 'gone', 'pending'])
def test_an_order_the_ca_will_not_complete_is_dropped_for_a_new_one(bench, state):
    kept = bench.child(status='processing', renewal_enabled=False, renewal_of_order_id=bench.parent_id)
    bench.ca.orders[kept.order_url]['status'] = state
    ok, _message = bench.renew()
    assert ok
    assert db.session.get(AcmeClientOrder, kept.id) is None
    bench.client.create_order.assert_called_once()


def test_an_order_of_the_operator_is_never_taken_by_a_renewal(bench):
    # Same names, but renewal_enabled is the operator's own order's: not a renewal's leftover
    own = bench.child(status='valid', pending_key=key_pem(ec.generate_private_key(ec.SECP256R1())))
    bench.renew()
    bench.client.create_order.assert_called_once()
    assert db.session.get(AcmeClientOrder, own.id) is not None


def test_a_failed_save_keeps_both_orders_and_the_next_renewal_finishes(bench):
    real = renew_mod.AcmeClientService._complete_renewal

    def save_fails(self, order, renews, *args):
        db.session.add(Certificate())  # refid is required: the commit fails
        return real(self, order, renews, *args)

    with patch.object(renew_mod.AcmeClientService, '_complete_renewal', save_fails), \
            pytest.raises(Exception, match='Database error'):
        bench.renew()
    db.session.rollback()
    kept = AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(bench.extra_orders)).one()
    assert kept.pending_key and bench.row().serial_number == bench.old_serial
    ok, _message = bench.renew()
    assert ok and bench.row().serial_number != bench.old_serial


# ---- one renewal at a time --------------------------------------------------------------

def test_a_held_order_is_not_renewed_and_a_stale_lease_is_taken_over(bench):
    held = OrderLease.take(bench.parent_id)
    assert held is not None and OrderLease.take(bench.parent_id) is None
    with pytest.raises(renew_mod.RenewalInProgress):
        bench.renew()
    bench.client.create_order.assert_not_called()
    AcmeClientOrder.query.filter_by(id=bench.parent_id).update(
        {'renewal_claimed_at': utc_now() - LEASE_DURATION - timedelta(seconds=1)})
    db.session.commit()
    ok, _message = bench.renew()
    assert ok
    assert not held.refresh()  # the first holder lost it


def test_the_lease_is_given_back_after_a_success_and_a_failure(bench):
    bench.renew()
    assert bench.parent().renewal_claimed_at is None
    bench.client.create_order.side_effect = RuntimeError('CA down')
    with pytest.raises(RuntimeError):
        bench.renew()
    db.session.expire_all()
    assert bench.parent().renewal_claimed_at is None


def test_the_scheduler_skips_an_order_another_renewal_holds(bench):
    OrderLease.take(bench.parent_id)
    with patch.object(renew_mod, '_order_is_due', return_value=True), \
            patch.object(renew_mod, 'renew_certificate') as renewed:
        renew_mod.scheduled_acme_renewal()
    assert bench.parent_id not in [c.args[0].id for c in renewed.call_args_list]
    assert bench.parent().renewal_failures == 0


def test_a_manual_renewal_answers_409_while_one_runs(app, auth_client, bench):
    OrderLease.take(bench.parent_id)
    answer = auth_client.post(f'/api/v2/acme/client/orders/{bench.parent_id}/renew')
    assert answer.status_code == 409, answer.get_json()


# ---- the routes ---------------------------------------------------------------------------

def test_a_status_check_imports_a_finalization_a_restart_cut_short(app, auth_client, bench):
    order = bench.child(status='processing')
    kept = ec.generate_private_key(ec.SECP256R1())
    order.pending_key = key_pem(kept)
    order.renewal_enabled = True  # a first issuance
    db.session.commit()
    bench.ca.orders[order.order_url].update(status='valid', pem=bench.ca.issue(kept.public_key(), [bench.name]))
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        answer = auth_client.get(f'/api/v2/acme/client/orders/{order.id}/status')
    assert answer.status_code == 200 and answer.get_json()['data']['status'] == 'issued'
    db.session.expire_all()
    done = db.session.get(AcmeClientOrder, order.id)
    bench.extra_certs.append(done.certificate_id)
    assert done.status == 'issued' and _pub(_stored_key(db.session.get(Certificate, done.certificate_id))) == _pub(kept)


def test_a_renewal_order_is_finalized_through_its_renewal_only(app, auth_client, bench):
    order = bench.child(status='processing', renewal_enabled=False, renewal_of_order_id=bench.parent_id)
    answer = auth_client.post(f'/api/v2/acme/client/orders/{order.id}/finalize')
    assert answer.status_code == 409 and str(bench.parent_id) in answer.get_json()['message']


def test_a_finalization_answers_409_while_another_runs(app, auth_client, bench):
    order = bench.child(renewal_enabled=True)
    OrderLease.take(order.id)
    answer = auth_client.post(f'/api/v2/acme/client/orders/{order.id}/finalize')
    assert answer.status_code == 409


def test_the_automatic_path_imports_an_order_the_ca_finished(app, bench, monkeypatch):
    from api.v2.acme_client import orders as orders_module
    monkeypatch.setattr(orders_module, '_dns_propagation_timeout', lambda: 0)
    monkeypatch.setattr(orders_module.time, 'sleep', lambda _seconds: None)
    kept = ec.generate_private_key(ec.SECP256R1())
    order = bench.child(status='processing', renewal_enabled=True)
    order.pending_key = key_pem(kept)
    db.session.commit()
    bench.ca.orders[order.order_url].update(status='valid', pem=bench.ca.issue(kept.public_key(), [bench.name]))
    bench.client.find_invalid_authorization = lambda _order: None
    result = orders_module._auto_poll_and_finalize(bench.client, order)
    assert result['finalized'], result
    bench.extra_certs.append(result['certificate_id'])


# ---- PostgreSQL ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_the_lease_the_kept_order_and_the_renewal_in_place_on_postgresql(app):
    from tests.test_crl_persistent_revocations import _PG_URL, _on_postgresql
    if not _PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set; skipping the PostgreSQL target')
    with _on_postgresql(app), app.app_context():
        _set_config('acme.client.email', 'inplace@example.com')
        bench = Bench(f'pg-{uuid.uuid4().hex[:8]}.example.com')
        lease = OrderLease.take(bench.parent_id)
        assert lease is not None and OrderLease.take(bench.parent_id) is None and lease.refresh()
        AcmeClientOrder.query.filter_by(id=bench.parent_id).update(
            {'renewal_claimed_at': utc_now() - LEASE_DURATION - timedelta(seconds=1)})
        db.session.commit()
        other = OrderLease.take(bench.parent_id)
        assert other is not None and not lease.refresh()
        other.release()
        assert bench.parent().renewal_claimed_at is None

        kept = _cut_renewal(bench)
        assert renew_mod.renewal_parent(kept).id == bench.parent_id
        assert renew_mod._kept_renewal_order(bench.parent(), None).id == kept.id
        ok, _message = bench.renew()
        assert ok and db.session.get(AcmeClientOrder, kept.id) is None
        row = bench.row()
        assert (row.id, row.refid) == (bench.cert_id, bench.refid) and row.serial_number != bench.old_serial
        assert _pub(_stored_key(row)) == _pub(leaf_of(base64.b64decode(row.crt).decode()))


# ---- a renewal's order is named by its link, never guessed -------------------------------

def _csr_for(key, name):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])).sign(key, hashes.SHA256())


def test_a_status_check_leaves_an_order_that_already_imported_its_certificate(app, auth_client, bench):
    order = bench.child(status='valid', key_source='reuse', source_certificate_id=bench.cert_id,
                        certificate_id=bench.cert_id, renewal_enabled=False)
    bench.ca.orders[order.order_url].update(status='valid', pem=bench.ca.issue(bench.key.public_key(), [bench.name]))
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        answer = auth_client.get(f'/api/v2/acme/client/orders/{order.id}/status')
    assert answer.status_code == 200
    db.session.expire_all()
    stored = db.session.get(AcmeClientOrder, order.id)
    assert stored.status != 'issued' and stored.renewal_enabled is False
    assert f'{order.order_url}/cert' not in [url for url, _payload in bench.ca.posts]


def test_a_renewal_of_an_order_without_account_is_still_its_renewal(app, auth_client, bench):
    from models import AcmeClientAccount
    account = AcmeClientAccount(directory_url=f'https://{uuid.uuid4().hex[:8]}.example/directory',
                                label='link', email='ops@example.com', account_key='k')
    db.session.add(account)
    db.session.commit()
    try:
        # A legacy parent has no account; the renewal ran under the resolved one
        order = bench.child(status='processing', renewal_enabled=False, renewal_of_order_id=bench.parent_id,
                            acme_client_account_id=account.id)
        assert renew_mod.renewal_parent(order).id == bench.parent_id
        answer = auth_client.post(f'/api/v2/acme/client/orders/{order.id}/finalize')
        assert answer.status_code == 409
    finally:
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(bench.extra_orders)).delete(synchronize_session=False)
        db.session.delete(db.session.get(AcmeClientAccount, account.id))
        db.session.commit()


def test_a_renewal_never_takes_the_order_of_another_order_for_the_same_names(bench):
    other, other_cert = bench.second_parent()
    stray = ec.generate_private_key(ec.SECP256R1())
    # Left by a renewal of the bench's order, created after the other one
    kept = bench.child(status='valid', renewal_enabled=False, renewal_of_order_id=bench.parent_id,
                       key_source='csr', csr_pem=_csr_for(stray, bench.name).public_bytes(serialization.Encoding.PEM).decode())
    bench.ca.orders[kept.order_url].update(pem=bench.ca.issue(stray.public_key(), [bench.name]))
    ok, _message = bench.renew(parent_id=other.id)
    assert ok
    bench.client.create_order.assert_called_once()
    assert db.session.get(AcmeClientOrder, kept.id) is not None
    row = db.session.get(Certificate, other_cert)
    assert _pub(_stored_key(row)) == _pub(leaf_of(base64.b64decode(row.crt).decode()))


def test_a_certificate_without_a_key_of_its_own_must_match_the_row_key(bench):
    stray = ec.generate_private_key(ec.SECP256R1())
    kept = bench.child(status='valid', renewal_enabled=False, renewal_of_order_id=bench.parent_id,
                       key_source='csr', csr_pem=_csr_for(stray, bench.name).public_bytes(serialization.Encoding.PEM).decode())
    issued = bench.ca.issue(stray.public_key(), [bench.name])
    bench.ca.orders[kept.order_url].update(pem=issued)
    ok, _message = bench.renew()
    assert ok
    # Refused, dropped and replaced by an order of its own: never a pair that does not match
    assert db.session.get(AcmeClientOrder, kept.id) is None
    bench.client.create_order.assert_called_once()
    row = bench.row()
    assert _pub(_stored_key(row)) == _pub(leaf_of(base64.b64decode(row.crt).decode())) != _pub(stray)


def test_a_kept_order_issued_for_another_key_is_replaced_by_a_new_order(bench, caplog):
    kept = bench.child(status='valid', renewal_enabled=False, renewal_of_order_id=bench.parent_id)
    kept.pending_key = key_pem(ec.generate_private_key(ec.SECP256R1()))
    db.session.commit()
    bench.ca.orders[kept.order_url].update(pem=bench.ca.issue(ec.generate_private_key(ec.SECP256R1()).public_key(),
                                                              [bench.name]))
    with caplog.at_level('WARNING', logger=renew_mod.logger.name):
        ok, _message = bench.renew()
    assert ok and db.session.get(AcmeClientOrder, kept.id) is None
    bench.client.create_order.assert_called_once()
    assert 'does not match the key kept for it' in caplog.text
    assert bench.parent().renewal_failures == 0


# ---- what follows the commit, the lease, the messages -------------------------------------

def test_a_snapshot_that_fails_after_the_commit_leaves_the_renewal_done(bench):
    with patch.object(Certificate, 'to_dict', side_effect=RuntimeError('snapshot')):
        ok, _message = bench.renew()
    assert ok and bench.row().serial_number != bench.old_serial


def test_a_lease_lost_during_the_dns_wait_submits_no_challenge(bench):
    bench.client.verify_challenge = MagicMock(return_value=(True, 'submitted'))

    def stolen(*_args, **_kwargs):
        AcmeClientOrder.query.filter_by(id=bench.parent_id).update({'renewal_claimed_at': utc_now()})
        db.session.commit()
        return {'ok': True, 'missing': [], 'waited': 0}

    lease = OrderLease.take(bench.parent_id)
    with pytest.raises(renew_mod.RenewalInProgress):
        bench.renew(wait=stolen, lease=lease)
    bench.client.verify_challenge.assert_not_called()
    assert AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(bench.extra_orders)).count() == 0


def test_a_ca_that_does_not_answer_is_named(bench):
    order = bench.child(status='processing')
    order.pending_key = key_pem(ec.generate_private_key(ec.SECP256R1()))
    db.session.commit()
    bench.client.check_order_status = lambda _order: ('processing', {})
    ok, message, _cert = bench.client.finalize_order(order)
    assert not ok and 'did not answer' in message


def test_a_revoked_row_renewed_into_a_new_one_is_not_revoked_again(bench, revoke_on_renewal, caplog):
    row = bench.row()
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    with patch.object(renew_mod.CertificateService, 'revoke_certificate') as local, \
            caplog.at_level('WARNING', logger=renew_mod.logger.name):
        ok, _message = bench.renew()
    assert ok
    local.assert_not_called()
    assert 'Failed to revoke' not in caplog.text
    assert bench.row().revoke_reason == 'keyCompromise'


# ---- second review ----------------------------------------------------------------------------

def _foreign_pending_key():
    """A pending key as another installation's master key wrote it."""
    from cryptography.fernet import Fernet
    from security.encryption import ENCRYPTED_MARKER
    pem = key_pem(ec.generate_private_key(ec.SECP256R1())).encode()
    return base64.b64encode(ENCRYPTED_MARKER + Fernet(Fernet.generate_key()).encrypt(base64.b64encode(pem))).decode()


def test_a_pending_key_under_another_master_key_is_no_key(app, auth_client, bench, encryption_enabled):
    order = bench.child(status='processing')
    order._pending_key = _foreign_pending_key()
    db.session.commit()
    assert db.session.get(AcmeClientOrder, order.id).pending_key is None
    bench.ca.orders[order.order_url].update(status='valid', pem=bench.ca.issue(bench.key.public_key(), [bench.name]))
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        answer = auth_client.get(f'/api/v2/acme/client/orders/{order.id}/status')
    assert answer.status_code == 200


def test_a_kept_order_whose_key_cannot_be_read_is_replaced(bench, encryption_enabled):
    kept = bench.child(status='valid', renewal_enabled=False, renewal_of_order_id=bench.parent_id)
    kept._pending_key = _foreign_pending_key()
    db.session.commit()
    bench.ca.orders[kept.order_url].update(pem=bench.ca.issue(bench.key.public_key(), [bench.name]))
    ok, _message = bench.renew()
    assert ok and db.session.get(AcmeClientOrder, kept.id) is None
    bench.client.create_order.assert_called_once()


def test_deleting_an_order_leaves_no_dangling_renewal_link(app, auth_client, bench):
    from services.database_admin.verify import check_declared_foreign_keys
    kept = bench.child(status='processing', renewal_enabled=False, renewal_of_order_id=bench.parent_id)
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        answer = auth_client.delete(f'/api/v2/acme/client/orders/{bench.parent_id}')
    assert answer.status_code == 200
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, kept.id).renewal_of_order_id is None
    # What the SQLite to PostgreSQL migration checks first
    assert check_declared_foreign_keys(db.engine)['orphans'] == 0


def test_a_kept_order_under_another_account_is_dropped_not_resumed(bench, caplog):
    from models import AcmeClientAccount
    account = AcmeClientAccount(directory_url=f'https://{uuid.uuid4().hex[:8]}.example/directory',
                                label='other', email='ops@example.com', account_key='k')
    db.session.add(account)
    db.session.commit()
    try:
        kept = bench.child(status='valid', renewal_enabled=False, renewal_of_order_id=bench.parent_id,
                           acme_client_account_id=account.id)
        kept.pending_key = key_pem(bench.key)
        db.session.commit()
        bench.ca.orders[kept.order_url].update(pem=bench.ca.issue(bench.key.public_key(), [bench.name]))
        with caplog.at_level('WARNING', logger=renew_mod.logger.name):
            ok, _message = bench.renew()
        assert ok and db.session.get(AcmeClientOrder, kept.id) is None
        bench.client.create_order.assert_called_once()
        assert 'another CA account' in caplog.text
    finally:
        db.session.rollback()
        AcmeClientOrder.query.filter_by(acme_client_account_id=account.id).delete(synchronize_session=False)
        db.session.delete(db.session.get(AcmeClientAccount, account.id))
        db.session.commit()


def test_a_csr_for_another_key_than_the_certificate_blocks_before_the_ca(bench):
    parent = bench.parent()
    parent.key_source = 'csr'
    parent.csr_pem = _csr_for(ec.generate_private_key(ec.SECP256R1()), bench.name).public_bytes(
        serialization.Encoding.PEM).decode()
    db.session.commit()
    with pytest.raises(renew_mod.RenewalBlocked, match='CSR made with that key'):
        bench.renew()
    bench.client.create_order.assert_not_called()
    assert bench.row().serial_number == bench.old_serial


def test_a_csr_for_the_certificate_key_renews_in_place(bench):
    parent = bench.parent()
    parent.key_source = 'csr'
    parent.csr_pem = _csr_for(bench.key, bench.name).public_bytes(serialization.Encoding.PEM).decode()
    db.session.commit()
    ok, _message = bench.renew()
    row = bench.row()
    assert ok and row.serial_number != bench.old_serial and _pub(_stored_key(row)) == _pub(bench.key)


def test_a_pending_http01_order_of_another_renewal_is_not_reused(bench):
    other, _cert = bench.second_parent()
    challenge = {bench.name: {'token': 't', 'key_authorization': 't.k'}}
    mine = AcmeClientOrder(domains=names_json([bench.name]), environment='production', challenge_type='http-01',
                           status='pending', order_url=f'{bench.ca.base}/order/h-{uuid.uuid4().hex[:6]}',
                           created_at=utc_now() - timedelta(minutes=1))
    theirs = AcmeClientOrder(domains=names_json([bench.name]), environment='production', challenge_type='http-01',
                             status='pending', order_url=f'{bench.ca.base}/order/h-{uuid.uuid4().hex[:6]}',
                             renewal_of_order_id=other.id)
    for row in (mine, theirs):
        row.set_challenges_dict(challenge)
        db.session.add(row)
    db.session.commit()
    bench.extra_orders += [mine.id, theirs.id]
    # Newest first: the other order's renewal is skipped, the unlinked one is taken
    assert renew_mod._pending_http01_order(bench.parent(), None).id == mine.id
