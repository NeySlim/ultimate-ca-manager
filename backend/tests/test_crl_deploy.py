"""CRL deployment bindings, bundle construction and event-driven queueing."""
import json

import pytest

from tests.conftest import assert_error, assert_success
from tests.deploy_leftovers import delete_leftovers

BASE = '/api/v2/deploy'
_seq = [0]

# Deliveries left behind keep binding ids that later files reuse
_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


def _post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def _patch(client, url, payload):
    return client.patch(url, data=json.dumps(payload), content_type='application/json')


def _target(client):
    _seq[0] += 1
    return assert_success(_post(client, f'{BASE}/targets', {
        'name': f'crl-target-{_seq[0]}',
        'host': 'crl.example.test',
        'username': 'ucm-deploy',
    }), status=201)


def _intermediate(client, create_ca):
    _seq[0] += 1
    root = create_ca(cn=f'CRL Deploy Root {_seq[0]}')
    intermediate = assert_success(_post(client, '/api/v2/cas', {
        'type': 'intermediate',
        'commonName': f'CRL Deploy Intermediate {_seq[0]}',
        'organization': 'Test Org',
        'country': 'US',
        'state': 'CA',
        'locality': 'Test City',
        'keyType': 'RSA',
        'keySize': 2048,
        'validityYears': 5,
        'hashAlgorithm': 'sha256',
        'parentCAId': root['id'],
    }), status=201)
    return root, intermediate


def _generate(app, ca_id):
    from services.crl import CRLService
    with app.app_context():
        return CRLService.generate_crl(ca_id, username='crl-test').id


def _binding(client, target_id, ca_id, **overrides):
    payload = {
        'target_id': target_id,
        'ca_id': ca_id,
        'crl_path': '/root/certs/CRL.crl',
        'format': 'pem',
        'include_parent_crls': False,
        'reload_command': 'nginx -t && nginx -s reload',
    }
    payload.update(overrides)
    return assert_success(_post(client, f'{BASE}/crl-bindings', payload), status=201)


class TestCRLBindings:
    def test_deleting_certificate_binding_keeps_same_numbered_crl_delivery(
            self, app, auth_client, create_ca, create_cert):
        """Certificate and CRL bindings use independent id sequences."""
        ca = create_ca(cn='CRL Delivery Collision CA')
        _generate(app, ca['id'])
        target = _target(auth_client)
        crl_binding = _binding(auth_client, target['id'], ca['id'])
        cert = create_cert(cn='delivery-collision.example.test', ca_id=ca['id'])
        cert_binding = assert_success(_post(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'],
            'cert_path': '/etc/ssl/collision.pem',
        }), status=201)

        from models import db, Certificate, DeployDelivery
        from services.cert_service import CertificateService
        with app.app_context():
            # The collision is written down rather than hoped for: the two id
            # sequences only coincide on a database nothing else has touched,
            # which a shared test database is not. A CRL delivery carrying the
            # certificate binding's number is the case the filter must survive.
            collision = DeployDelivery(binding_id=cert_binding['id'], binding_type='crl',
                                       event_type='crl.updated', status='pending')
            db.session.add(collision)
            db.session.commit()
            collision_id = collision.id
            db.session.get(Certificate, cert['id']).revoked = True
            db.session.commit()
            assert CertificateService.delete_certificate(cert['id']) is True
            kept = db.session.get(DeployDelivery, collision_id)
            assert kept is not None and kept.binding_type == 'crl'
            assert DeployDelivery.query.filter_by(
                binding_id=cert_binding['id'], binding_type='certificate').count() == 0
            db.session.delete(kept)
            db.session.commit()

    def test_create_lists_and_queues_initial_push(self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Binding CA')
        _generate(app, ca['id'])
        target = _target(auth_client)
        binding = _binding(auth_client, target['id'], ca['id'])

        rows = assert_success(auth_client.get(
            f"{BASE}/crl-bindings?ca_id={ca['id']}"))
        assert len(rows) == 1
        assert rows[0]['id'] == binding['id']
        assert rows[0]['last_delivery']['binding_type'] == 'crl'
        assert rows[0]['last_delivery']['event_type'] == 'initial'
        assert rows[0]['reload_command'] == 'nginx -t && nginx -s reload'

    def test_rejects_relative_path_and_der_parent_bundle(
            self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Validation CA')
        _generate(app, ca['id'])
        target = _target(auth_client)
        assert_error(_post(auth_client, f'{BASE}/crl-bindings', {
            'target_id': target['id'], 'ca_id': ca['id'],
            'crl_path': 'relative.crl', 'format': 'pem'}), 400)
        assert_error(_post(auth_client, f'{BASE}/crl-bindings', {
            'target_id': target['id'], 'ca_id': ca['id'],
            'crl_path': '/root/certs/CRL.der', 'format': 'der',
            'include_parent_crls': True}), 400)
        assert_error(_post(auth_client, f'{BASE}/crl-bindings', {
            'target_id': target['id'], 'ca_id': ca['id'],
            'crl_path': '/root/certs/CRL.pem', 'format': 'pem',
            'include_parent_crls': 'false'}), 400)

    def test_patch_validates_final_format_state(self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Patch CA')
        _generate(app, ca['id'])
        target = _target(auth_client)
        binding = _binding(auth_client, target['id'], ca['id'],
                           include_parent_crls=True)
        assert_error(_patch(auth_client, f"{BASE}/crl-bindings/{binding['id']}",
                            {'format': 'der'}), 400)

    def test_patch_executes_pending_delivery_immediately(
            self, app, auth_client, create_ca, monkeypatch):
        from datetime import timedelta
        from models import db, DeployDelivery
        from utils.datetime_utils import utc_now

        ca = create_ca(cn='CRL Patch Retry CA')
        _generate(app, ca['id'])
        target = _target(auth_client)
        binding = _binding(auth_client, target['id'], ca['id'])

        with app.app_context():
            pending = DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='crl', status='pending').one()
            pending.attempts = 4
            pending.next_attempt_at = utc_now() + timedelta(hours=1)
            pending.last_error = 'Reload command exited 1'
            pending.detail = '{"reload_exit": 1}'
            db.session.commit()

        import services.deploy.ssh as ssh_mod
        pushed = []

        class FakeClient:
            def close(self):
                pass

        monkeypatch.setattr(
            ssh_mod, 'open_client',
            lambda host, port, username, key, expected: (FakeClient(), None))
        monkeypatch.setattr(
            ssh_mod, 'push_files', lambda client, files: pushed.extend(files))
        monkeypatch.setattr(ssh_mod, 'run_command', lambda client, command: (0, ''))

        assert_success(_patch(
            auth_client, f"{BASE}/crl-bindings/{binding['id']}",
            {'format': 'der', 'include_parent_crls': False}))

        with app.app_context():
            rows = DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='crl').all()
            assert len(rows) == 1
            assert rows[0].status == 'delivered'
            assert rows[0].event_type == 'binding.updated'
            assert rows[0].attempts == 1
            assert rows[0].last_error is None
            assert rows[0].get_detail()['pushed'] == ['/root/certs/CRL.crl']
        assert len(pushed) == 1
        assert not pushed[0][1].startswith(b'-----BEGIN X509 CRL-----')


class TestCRLMaterial:
    def test_pem_bundle_contains_child_then_parent_crl(
            self, app, auth_client, create_ca):
        root, intermediate = _intermediate(auth_client, create_ca)
        _generate(app, root['id'])
        _generate(app, intermediate['id'])
        target = _target(auth_client)
        binding_data = _binding(
            auth_client, target['id'], intermediate['id'],
            include_parent_crls=True)

        from models import db, CRLDeployBinding
        from services.deploy import DeployService
        with app.app_context():
            binding = db.session.get(CRLDeployBinding, binding_data['id'])
            files = DeployService.resolve_crl_files(binding)
            assert files[0][0] == '/root/certs/CRL.crl'
            pem = files[0][1].decode()
            assert pem.count('-----BEGIN X509 CRL-----') == 2


class TestCRLEvents:
    def test_regeneration_queues_one_coalesced_delivery(
            self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Event CA')
        _generate(app, ca['id'])
        target = _target(auth_client)
        binding = _binding(auth_client, target['id'], ca['id'])

        from models import db, DeployDelivery
        with app.app_context():
            DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='crl').delete()
            db.session.commit()

        _generate(app, ca['id'])
        _generate(app, ca['id'])
        with app.app_context():
            rows = DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='crl').all()
            assert len(rows) == 1
            assert rows[0].event_type == 'crl.updated'
            assert rows[0].triggered_by == 'crl-test'

    def test_parent_update_refreshes_descendant_bundle(
            self, app, auth_client, create_ca):
        root, intermediate = _intermediate(auth_client, create_ca)
        _generate(app, root['id'])
        _generate(app, intermediate['id'])
        target = _target(auth_client)
        binding = _binding(
            auth_client, target['id'], intermediate['id'],
            include_parent_crls=True)

        from models import db, DeployDelivery
        with app.app_context():
            DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='crl').delete()
            db.session.commit()
        _generate(app, root['id'])
        with app.app_context():
            row = DeployDelivery.query.filter_by(
                binding_id=binding['id'], binding_type='crl').one()
            assert row.event_type == 'crl.updated'


class TestCRLDelivery:
    def test_manual_push_uses_atomic_transport_and_reload(
            self, app, auth_client, create_ca, monkeypatch):
        ca = create_ca(cn='CRL Manual Deploy CA')
        _generate(app, ca['id'])
        target = _target(auth_client)
        binding = _binding(auth_client, target['id'], ca['id'])

        import services.deploy.ssh as ssh_mod
        pushed = []
        commands = []

        class FakeClient:
            def close(self):
                pass

        monkeypatch.setattr(
            ssh_mod, 'open_client',
            lambda host, port, username, key, expected: (FakeClient(), None))
        monkeypatch.setattr(
            ssh_mod, 'push_files', lambda client, files: pushed.extend(files))
        monkeypatch.setattr(
            ssh_mod, 'run_command',
            lambda client, command: (commands.append(command) or (0, '')))

        result = assert_success(auth_client.post(
            f"{BASE}/crl-bindings/{binding['id']}/deploy"))
        assert result['status'] == 'delivered'
        assert result['binding_type'] == 'crl'
        assert len(pushed) == 1
        path, content, mode = pushed[0]
        assert path == '/root/certs/CRL.crl'
        assert content.startswith(b'-----BEGIN X509 CRL-----')
        assert mode == 0o644
        assert commands == ['nginx -t && nginx -s reload']
