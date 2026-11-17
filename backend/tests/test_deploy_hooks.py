"""
Tests for deploy hooks (#299): targets CRUD + RBAC, SSH key handling,
bindings, event-driven enqueue, queue processing with mocked SSH transport,
host-key pinning, manual deploy and retry.
"""
import json

import pytest

from tests.conftest import assert_error, assert_success, get_json

BASE = '/api/v2/deploy'

_seq = [0]


def _name(prefix='target'):
    _seq[0] += 1
    return f'{prefix}-{_seq[0]}'


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def patch_json(client, url, payload):
    return client.patch(url, data=json.dumps(payload), content_type='application/json')


def _create_target(auth_client, **overrides):
    payload = {
        'name': _name(),
        'host': 'web01.example.test',
        'username': 'ucm-deploy',
    }
    payload.update(overrides)
    return assert_success(post_json(auth_client, f'{BASE}/targets', payload), status=201)


def _create_binding(auth_client, target_id, cert_id, **overrides):
    payload = {
        'target_id': target_id,
        'certificate_id': cert_id,
        'cert_path': '/etc/ssl/ucm/cert.pem',
        'key_path': '/etc/ssl/ucm/key.pem',
        'fullchain_path': '/etc/ssl/ucm/fullchain.pem',
        'reload_command': 'systemctl reload nginx',
    }
    payload.update(overrides)
    return assert_success(post_json(auth_client, f'{BASE}/bindings', payload), status=201)


class _FakeSSH:
    """Monkeypatched transport: records pushes, simulates TOFU pinning."""

    HOST_KEY = 'ssh-ed25519 FAKEHOSTKEYBASE64'

    def __init__(self, monkeypatch):
        import services.deploy.ssh as ssh_mod
        self.ssh_mod = ssh_mod
        self.pushed = []
        self.commands = []
        self.reload_result = (0, '')
        self.presented_key = self.HOST_KEY

        class FakeClient:
            def close(self):
                pass

        def fake_open(host, port, username, key_text, expected):
            if expected is None:
                return FakeClient(), self.presented_key
            if expected != self.presented_key:
                raise ssh_mod.HostKeyMismatch('Host key verification failed (test)')
            return FakeClient(), None

        monkeypatch.setattr(ssh_mod, 'open_client', fake_open)
        monkeypatch.setattr(ssh_mod, 'push_files',
                            lambda client, files: self.pushed.extend(files))
        monkeypatch.setattr(ssh_mod, 'run_command', self._run)

    def _run(self, client, command):
        self.commands.append(command)
        return self.reload_result


@pytest.fixture()
def fake_ssh(monkeypatch):
    return _FakeSSH(monkeypatch)


class TestRBAC:
    def test_requires_auth(self, client):
        assert client.get(f'{BASE}/targets').status_code in (401, 403)

    def test_operator_denied(self, app, auth_client, create_user):
        create_user(username='op_deploy_test', role='operator')
        c = app.test_client()
        r = c.post('/api/v2/auth/login',
                   data=json.dumps({'username': 'op_deploy_test', 'password': 'TestPass123!'}),
                   content_type='application/json')
        assert r.status_code == 200
        assert c.get(f'{BASE}/targets').status_code == 403
        assert post_json(c, f'{BASE}/targets', {'name': 'x', 'host': 'h', 'username': 'u'}).status_code == 403


class TestTargets:
    def test_create_generates_keypair(self, auth_client):
        data = _create_target(auth_client)
        assert data['public_key'].startswith('ssh-ed25519 ')
        assert 'private_key' not in data
        assert data['host_key_pinned'] is False
        assert data['enabled'] is True
        assert data['port'] == 22
        assert 'reload_command' not in data

    def test_private_key_encrypted_at_rest(self, app, auth_client):
        data = _create_target(auth_client)
        from models import db, DeployTarget
        from services.deploy.ssh import load_private_key
        from security.encryption import decrypt_text, encrypt_text
        with app.app_context():
            target = db.session.get(DeployTarget, data['id'])
            # encrypt_text is a documented no-op without a master key (CI runs
            # without one) — only assert ciphertext when encryption is active
            if encrypt_text('probe') != 'probe':
                assert 'PRIVATE KEY' not in (target.private_key or '')
            load_private_key(decrypt_text(target.private_key))  # round-trips to a usable key

    def test_create_with_imported_key(self, auth_client):
        from services.deploy.ssh import generate_keypair
        priv, pub = generate_keypair()
        data = _create_target(auth_client, private_key=priv)
        assert data['public_key'].split()[1] == pub.split()[1]

    def test_create_rejects_bad_key(self, auth_client):
        r = post_json(auth_client, f'{BASE}/targets', {
            'name': _name(), 'host': 'h.example.test', 'username': 'u',
            'private_key': 'not a key'})
        assert_error(r, 400)

    def test_duplicate_name(self, auth_client):
        data = _create_target(auth_client)
        r = post_json(auth_client, f'{BASE}/targets', {
            'name': data['name'], 'host': 'h.example.test', 'username': 'u'})
        assert_error(r, 409)

    def test_validation(self, auth_client):
        assert_error(post_json(auth_client, f'{BASE}/targets',
                               {'host': 'h', 'username': 'u'}), 400)  # no name
        assert_error(post_json(auth_client, f'{BASE}/targets',
                               {'name': _name(), 'username': 'u'}), 400)  # no host
        assert_error(post_json(auth_client, f'{BASE}/targets',
                               {'name': _name(), 'host': 'h', 'username': 'u', 'port': 70000}), 400)

    def test_update_host_resets_pin(self, app, auth_client):
        data = _create_target(auth_client)
        from models import db, DeployTarget
        with app.app_context():
            db.session.get(DeployTarget, data['id']).host_key = 'ssh-ed25519 OLDPIN'
            db.session.commit()
        updated = assert_success(patch_json(
            auth_client, f"{BASE}/targets/{data['id']}", {'host': 'other.example.test'}))
        assert updated['host_key_pinned'] is False

    def test_delete_cascades(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        assert_success(auth_client.delete(f"{BASE}/targets/{target['id']}"))
        r = auth_client.get(f"{BASE}/bindings?certificate_id={cert['id']}")
        assert assert_success(r) == []
        assert_error(auth_client.get(f"{BASE}/targets/{target['id']}"), 404)


class TestBindings:
    def test_create_and_list(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        assert binding['target_name'] == target['name']
        listed = assert_success(auth_client.get(f"{BASE}/bindings?certificate_id={cert['id']}"))
        assert len(listed) == 1
        # attaching queues the initial push (F-07) — it shows as last delivery
        assert listed[0]['last_delivery']['event_type'] == 'initial'
        assert binding['include_root'] is False

    def test_include_root_is_stored_and_requires_boolean(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(
            auth_client, target['id'], cert['id'], include_root=True)
        assert binding['include_root'] is True
        updated = assert_success(patch_json(
            auth_client, f"{BASE}/bindings/{binding['id']}", {'include_root': False}))
        assert updated['include_root'] is False

        other_target = _create_target(auth_client)
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': other_target['id'], 'certificate_id': cert['id'],
            'fullchain_path': '/etc/ssl/fullchain.pem', 'include_root': 'false'})
        assert_error(r, 400)

    def test_requires_absolute_path(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': 'relative/cert.pem'})
        assert_error(r, 400)

    def test_requires_at_least_one_path(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id']})
        assert_error(r, 400)

    def test_duplicate_binding(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        _create_binding(auth_client, target['id'], cert['id'])
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/other.pem'})
        assert_error(r, 409)

    def test_unknown_refs(self, auth_client, create_cert):
        cert = create_cert()
        assert_error(post_json(auth_client, f'{BASE}/bindings', {
            'target_id': 999999, 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/c.pem'}), 404)
        target = _create_target(auth_client)
        assert_error(post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': 999999,
            'cert_path': '/etc/ssl/c.pem'}), 404)


class TestEnqueue:
    def test_issued_event_enqueues(self, app, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        _create_binding(auth_client, target['id'], cert['id'])
        from models import db, DeployDelivery
        from services.events import event_bus
        with app.app_context():
            before = DeployDelivery.query.count()
            event_bus.emit('certificate.renewed', {'certificate': {'id': cert['id']}},
                           meta={'actor': 'tester'})
            rows = DeployDelivery.query.order_by(DeployDelivery.id.desc()).all()
            assert DeployDelivery.query.count() == before + 1
            assert rows[0].event_type == 'certificate.renewed'
            assert rows[0].status == DeployDelivery.STATUS_PENDING
            assert rows[0].triggered_by == 'tester'

    def test_no_binding_no_delivery(self, app, create_cert):
        cert = create_cert()
        from models import db, DeployDelivery
        from services.events import event_bus
        with app.app_context():
            before = DeployDelivery.query.count()
            event_bus.emit('certificate.issued', {'certificate': {'id': cert['id']}})
            assert DeployDelivery.query.count() == before

    def test_disabled_binding_skipped(self, app, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        assert_success(patch_json(auth_client, f"{BASE}/bindings/{binding['id']}",
                                  {'enabled': False}))
        from models import DeployDelivery
        from services.events import event_bus
        with app.app_context():
            before = DeployDelivery.query.count()
            event_bus.emit('certificate.issued', {'certificate': {'id': cert['id']}})
            assert DeployDelivery.query.count() == before


class TestProcessing:
    def _pending_for(self, app, auth_client, create_cert, **target_overrides):
        target = _create_target(auth_client, **target_overrides)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        from models import db, DeployDelivery
        with app.app_context():
            # Session-scoped shared DB: drop pending rows left by earlier tests
            # so process_pending_deliveries only sees this test's delivery.
            DeployDelivery.query.filter_by(
                status=DeployDelivery.STATUS_PENDING).delete(synchronize_session=False)
            delivery = DeployDelivery(binding_id=binding['id'], event_type='manual',
                                      triggered_by='tester')
            db.session.add(delivery)
            db.session.commit()
            return target, cert, binding, delivery.id

    def test_process_success_and_pin(self, app, auth_client, create_cert, fake_ssh):
        target, cert, binding, delivery_id = self._pending_for(app, auth_client, create_cert)
        from models import db, DeployDelivery, DeployTarget
        from services.deploy import DeployService
        with app.app_context():
            result = DeployService.process_pending_deliveries()
            assert result['delivered'] >= 1
            d = db.session.get(DeployDelivery, delivery_id)
            assert d.status == DeployDelivery.STATUS_DELIVERED
            detail = d.get_detail()
            assert set(detail['pushed']) == {'/etc/ssl/ucm/cert.pem', '/etc/ssl/ucm/key.pem',
                                             '/etc/ssl/ucm/fullchain.pem'}
            assert detail['reload_exit'] == 0
            t = db.session.get(DeployTarget, target['id'])
            assert t.host_key == fake_ssh.HOST_KEY  # pinned on first connect
            assert t.failure_count == 0
        # key pushed with restrictive mode, cert public
        modes = {path: mode for path, _, mode in fake_ssh.pushed}
        assert modes['/etc/ssl/ucm/key.pem'] == 0o600
        assert modes['/etc/ssl/ucm/cert.pem'] == 0o644
        assert fake_ssh.commands == ['systemctl reload nginx']

    def test_pinned_mismatch_fails(self, app, auth_client, create_cert, fake_ssh):
        target, cert, binding, delivery_id = self._pending_for(app, auth_client, create_cert)
        from models import db, DeployDelivery, DeployTarget
        from services.deploy import DeployService
        with app.app_context():
            db.session.get(DeployTarget, target['id']).host_key = 'ssh-ed25519 DIFFERENTPIN'
            db.session.commit()
            DeployService.process_pending_deliveries()
            d = db.session.get(DeployDelivery, delivery_id)
            assert d.status == DeployDelivery.STATUS_PENDING  # retried
            assert 'Host key verification failed' in d.last_error

    def test_reload_failure_retries_then_fails(self, app, auth_client, create_cert, fake_ssh):
        fake_ssh.reload_result = (1, 'nginx: broken config')
        target, cert, binding, delivery_id = self._pending_for(app, auth_client, create_cert)
        from models import db, DeployDelivery
        from services.deploy import DeployService
        from utils.datetime_utils import utc_now
        with app.app_context():
            DeployService.process_pending_deliveries()
            d = db.session.get(DeployDelivery, delivery_id)
            assert d.status == DeployDelivery.STATUS_PENDING
            assert d.attempts == 1
            assert 'exited 1' in d.last_error
            # exhaust the remaining attempts
            for _ in range(DeployService.DEFAULT_MAX_ATTEMPTS - 1):
                d.next_attempt_at = utc_now()
                db.session.commit()
                DeployService.process_pending_deliveries()
                db.session.refresh(d)
            assert d.status == DeployDelivery.STATUS_FAILED

    def test_deploy_now_endpoint(self, app, auth_client, create_cert, fake_ssh):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        data = assert_success(auth_client.post(f"{BASE}/bindings/{binding['id']}/deploy"))
        assert data['status'] == 'delivered'
        assert data['event_type'] == 'manual'
        listed = assert_success(auth_client.get(f"{BASE}/deliveries?binding_id={binding['id']}"))
        assert listed and listed[0]['status'] == 'delivered'

    def test_deploy_now_failure_returns_502(self, app, auth_client, create_cert, fake_ssh):
        fake_ssh.reload_result = (1, 'boom')
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        r = auth_client.post(f"{BASE}/bindings/{binding['id']}/deploy")
        assert_error(r, 502)
        listed = assert_success(auth_client.get(f"{BASE}/deliveries?binding_id={binding['id']}"))
        assert listed[0]['status'] == 'failed'  # manual runs don't background-retry

    def test_retry_failed_delivery(self, app, auth_client, create_cert, fake_ssh):
        fake_ssh.reload_result = (1, 'boom')
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        auth_client.post(f"{BASE}/bindings/{binding['id']}/deploy")
        listed = assert_success(auth_client.get(f"{BASE}/deliveries?binding_id={binding['id']}"))
        delivery_id = listed[0]['id']
        fake_ssh.reload_result = (0, '')
        requeued = assert_success(auth_client.post(f"{BASE}/deliveries/{delivery_id}/retry"))
        assert requeued['status'] == 'pending'
        from services.deploy import DeployService
        with app.app_context():
            DeployService.process_pending_deliveries()
        listed = assert_success(auth_client.get(f"{BASE}/deliveries?binding_id={binding['id']}"))
        assert listed[0]['status'] == 'delivered'

    def test_key_path_without_private_key(self, app, auth_client, create_cert):
        """Binding with key_path on a cert whose key later disappears fails permanently."""
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        from models import db, Certificate, DeployDelivery
        from services.deploy import DeployService
        with app.app_context():
            db.session.get(Certificate, cert['id']).prv = None
            db.session.commit()
            delivery = DeployDelivery(binding_id=binding['id'], event_type='manual')
            db.session.add(delivery)
            db.session.commit()
            DeployService.process_pending_deliveries()
            db.session.refresh(delivery)
            assert delivery.status == DeployDelivery.STATUS_FAILED
            assert 'private key' in delivery.last_error


class TestFileResolution:
    def test_fullchain_omits_root_by_default(self, app, create_cert):
        """A leaf issued directly by a root deploys without that trust anchor."""
        cert = create_cert()
        from models import db, Certificate, DeployBinding
        from services.deploy import DeployService
        with app.app_context():
            c = db.session.get(Certificate, cert['id'])
            binding = DeployBinding(target_id=0, certificate_id=c.id,
                                    fullchain_path='/etc/ssl/fullchain.pem')
            files = DeployService.resolve_files(binding, c)
            content = files[0][1].decode()
            assert content.count('BEGIN CERTIFICATE') == 1

    def test_fullchain_can_include_root_explicitly(self, app, create_cert):
        cert = create_cert()
        from models import db, Certificate, DeployBinding
        from services.deploy import DeployService
        with app.app_context():
            c = db.session.get(Certificate, cert['id'])
            binding = DeployBinding(target_id=0, certificate_id=c.id,
                                    fullchain_path='/etc/ssl/fullchain.pem',
                                    include_root=True)
            files = DeployService.resolve_files(binding, c)
            content = files[0][1].decode()
            assert content.count('BEGIN CERTIFICATE') >= 2


class TestReviewFindings:
    """Fixes from the 2.215 code review (F-07/F-08/F-10/F-11)."""

    def test_binding_creation_queues_initial_push(self, app, auth_client, create_cert):
        """F-07: attaching an issued certificate queues the first deployment."""
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        listed = assert_success(
            auth_client.get(f"{BASE}/deliveries?binding_id={binding['id']}"))
        assert [d for d in listed
                if d['event_type'] == 'initial' and d['status'] == 'pending']

    def test_no_initial_push_for_disabled_target(self, app, auth_client, create_cert):
        target = _create_target(auth_client, enabled=False)
        assert_success(patch_json(auth_client, f"{BASE}/targets/{target['id']}",
                                  {'enabled': False}))
        cert = create_cert()
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/ucm/cert.pem'})
        assert r.status_code == 201
        # R-04: the message must not claim a queued deployment
        assert 'no deployment queued' in get_json(r)['message']
        binding = get_json(r)['data']
        listed = assert_success(
            auth_client.get(f"{BASE}/deliveries?binding_id={binding['id']}"))
        assert listed == []

    def test_disabled_binding_message_not_queued(self, auth_client, create_cert):
        """R-04: a binding created disabled announces no queued deployment."""
        target = _create_target(auth_client)
        cert = create_cert()
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/ucm/cert.pem', 'enabled': False})
        assert r.status_code == 201
        assert 'no deployment queued' in get_json(r)['message']

    def test_concurrent_duplicate_maps_integrity_error_to_409(
            self, app, auth_client, create_cert, monkeypatch):
        """R-03: a race past the uniqueness pre-check must yield 409, and the
        rolled-back binding must not be half-persisted."""
        from sqlalchemy.exc import IntegrityError
        from services.deploy import DeployService
        target = _create_target(auth_client)
        cert = create_cert()

        def _race(binding, actor='system'):
            raise IntegrityError('INSERT INTO deploy_bindings', {}, Exception('unique'))
        monkeypatch.setattr(DeployService, 'enqueue_initial_push',
                            staticmethod(_race))
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/ucm/cert.pem'})
        assert_error(r, 409)
        listed = assert_success(
            auth_client.get(f"{BASE}/bindings?target_id={target['id']}"))
        assert listed == []  # nothing half-persisted

    def test_flush_error_rolls_back_cleanly(
            self, app, auth_client, create_cert, monkeypatch):
        from services.deploy import DeployService
        target = _create_target(auth_client)
        cert = create_cert()

        def _boom(binding, actor='system'):
            raise RuntimeError('unexpected DB error')
        monkeypatch.setattr(DeployService, 'enqueue_initial_push',
                            staticmethod(_boom))
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/ucm/cert.pem'})
        assert_error(r, 500)
        listed = assert_success(
            auth_client.get(f"{BASE}/bindings?target_id={target['id']}"))
        assert listed == []

    def test_colliding_paths_rejected_on_create(self, auth_client, create_cert):
        """F-08: identical destination paths silently overwrite each other."""
        target = _create_target(auth_client)
        cert = create_cert()
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/same.pem', 'key_path': '/etc/ssl/same.pem'})
        assert_error(r, 400)
        assert 'distinct' in get_json(r)['message']

    def test_patch_collision_with_stored_path_rejected(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        # cert_path is stored as /etc/ssl/ucm/cert.pem — a partial PATCH
        # moving fullchain onto it must be refused
        r = patch_json(auth_client, f"{BASE}/bindings/{binding['id']}",
                       {'fullchain_path': '/etc/ssl/ucm/cert.pem'})
        assert_error(r, 400)

    def test_binding_patch_failure_starts_retry_after_immediate_attempt(
            self, app, auth_client, create_cert, monkeypatch):
        from models import db, DeployDelivery
        from utils.datetime_utils import utc_now

        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        with app.app_context():
            initial = DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='certificate').one()
            initial.status = 'failed'
            initial.attempts = initial.max_attempts
            initial.last_error = 'Reload command exited 1'
            db.session.commit()

        transport = _FakeSSH(monkeypatch)
        transport.reload_result = (1, 'reload failed')
        assert_success(patch_json(
            auth_client, f"{BASE}/bindings/{binding['id']}",
            {'reload_command': 'systemctl reload apache2'}))

        with app.app_context():
            rows = DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='certificate').all()
            assert len(rows) == 2
            failed = next(row for row in rows if row.status == 'failed')
            pending = next(row for row in rows if row.status == 'pending')
            assert failed.event_type == 'initial'
            assert pending.event_type == 'binding.updated'
            assert pending.attempts == 1
            assert 'Reload command exited 1' in pending.last_error
            assert pending.next_attempt_at > utc_now()
        assert transport.commands == ['systemctl reload apache2']

    def _admin_scoped_key(self, app, permissions, name):
        """API key owned by a DEDICATED admin user, scoped to the given deploy
        permissions. A dedicated owner (not the shared 'admin') keeps this test
        out of the 10-active-keys-per-user cap other tests consume in a
        full-suite run (same policy as test_subca_permission_and_pathlen)."""
        import hashlib
        import secrets
        from models import User, db
        from models.api_key import APIKey
        username = 'deploy_scope_probe_admin'
        with app.app_context():
            owner = User.query.filter_by(username=username).first()
            if not owner:
                owner = User(
                    username=username,
                    email=f'{username}@test.local',
                    password_hash='!',           # unused: key auth only
                    role='admin',
                    active=True,
                )
                db.session.add(owner)
                db.session.commit()
            raw_key = f'ucm_ak_{secrets.token_urlsafe(32)}'
            db.session.add(APIKey(
                user_id=owner.id,
                key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
                key_prefix=raw_key[:12],
                name=name,
                permissions=json.dumps(permissions),
            ))
            db.session.commit()
        return raw_key

    def test_write_scope_cannot_delete(self, app, auth_client, create_cert):
        """F-10: DELETE requires delete:deploy — a write:deploy key must not
        be able to remove targets and their delivery history."""
        target = _create_target(auth_client)
        write_key = self._admin_scoped_key(
            app, ['read:deploy', 'write:deploy'], 'deploy-write-only')
        delete_key = self._admin_scoped_key(
            app, ['read:deploy', 'delete:deploy'], 'deploy-delete-only')
        client = app.test_client()

        r = client.patch(f"{BASE}/targets/{target['id']}",
                         data=json.dumps({'enabled': False}),
                         content_type='application/json',
                         headers={'X-API-Key': write_key})
        assert r.status_code == 200, r.data[:300]
        r = client.delete(f"{BASE}/targets/{target['id']}",
                          headers={'X-API-Key': write_key})
        assert r.status_code == 403, r.data[:300]
        r = client.delete(f"{BASE}/targets/{target['id']}",
                          headers={'X-API-Key': delete_key})
        assert r.status_code == 200, r.data[:300]


class TestCertDeleteCleanup:
    def test_cert_delete_removes_bindings(self, app, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        # revoke first (valid certs can't be deleted, #296), then delete
        r = auth_client.post(f"/api/v2/certificates/{cert['id']}/revoke",
                             data=json.dumps({'reason': 'superseded'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data[:300]
        r = auth_client.delete(f"/api/v2/certificates/{cert['id']}")
        assert r.status_code in (200, 204), r.data[:300]
        listed = assert_success(auth_client.get(f"{BASE}/bindings?target_id={target['id']}"))
        assert listed == []
