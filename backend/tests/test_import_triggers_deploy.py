"""An import that replaces a certificate queues its deploy bindings (discussion #440)."""
import json

import pytest

from tests.deploy_leftovers import delete_leftovers
from tests.test_deploy_hooks import _create_target, _create_binding
from tests.test_import_review import _cert, _gen, _ca_from_fixture, _store_cert, _import

IMPORT = '/api/v2/certificates/import'


_cleanup = pytest.fixture(autouse=True)(delete_leftovers)

def _deliveries(app, cert_id):
    with app.app_context():
        from models import DeployDelivery, DeployBinding
        # creating a binding queues an 'initial' push; only the import's matters
        return [(d.event_type, d.status) for d in DeployDelivery.query
                .join(DeployBinding, DeployDelivery.binding_id == DeployBinding.id)
                .filter(DeployBinding.certificate_id == cert_id,
                        DeployDelivery.event_type != 'initial').all()]


def _setup(app, auth_client, create_ca, cn, bound=True):
    ca = create_ca(cn=f'{cn} CA')
    ca_cert, ca_key, caref, _ = _ca_from_fixture(app, ca)
    key = _gen()
    old = _cert(cn, key, issuer_cert=ca_cert, signer=ca_key)
    cert_id = _store_cert(app, old, key, caref=caref)
    if bound:
        target = _create_target(auth_client)
        _create_binding(auth_client, target['id'], cert_id)
    return ca_cert, ca_key, key, old, cert_id


class TestImportReplacementDeploys:
    def test_replacement_queues_one_delivery_per_active_binding(self, app, auth_client, create_ca):
        ca_cert, ca_key, key, old, cert_id = _setup(
            app, auth_client, create_ca, 'r7-replace.example.com', bound=False)
        for _ in range(2):
            _create_binding(auth_client, _create_target(auth_client)['id'], cert_id)
        off_binding = _create_binding(auth_client, _create_target(auth_client)['id'], cert_id)
        off_target = _create_target(auth_client)
        _create_binding(auth_client, off_target['id'], cert_id)
        with app.app_context():
            from models import db, DeployBinding, DeployTarget
            db.session.get(DeployBinding, off_binding['id']).enabled = False
            db.session.get(DeployTarget, off_target['id']).enabled = False
            db.session.commit()
        new = _cert('r7-replace.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        r = _import(auth_client, IMPORT, new)
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['id'] == cert_id
        assert _deliveries(app, cert_id) == [('certificate.renewed', 'pending')] * 2

    def test_same_serial_reimport_queues_nothing(self, app, auth_client, create_ca):
        *_, old, cert_id = _setup(app, auth_client, create_ca, 'r7-same.example.com')
        r = _import(auth_client, IMPORT, old)
        assert r.status_code == 200, r.data
        assert _deliveries(app, cert_id) == []

    def test_replacement_without_binding_fires_the_event_and_queues_nothing(self, app, auth_client, create_ca):
        ca_cert, ca_key, key, old, cert_id = _setup(app, auth_client, create_ca, 'r7-nobind.example.com', bound=False)
        new = _cert('r7-nobind.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        from unittest.mock import patch
        with patch('services.webhook_service.emit_cert_renewed') as emitted:
            assert _import(auth_client, IMPORT, new).status_code == 200
        emitted.assert_called_once()
        assert _deliveries(app, cert_id) == []

    def test_failed_commit_emits_nothing(self, app, auth_client, create_ca, monkeypatch):
        ca_cert, ca_key, key, old, cert_id = _setup(app, auth_client, create_ca, 'r7-fail.example.com')
        new = _cert('r7-fail.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        from api.v2.certificates import cert_import
        from utils.response import error_response
        monkeypatch.setattr(cert_import, 'safe_commit', lambda *a, **k: (False, error_response('boom', 500)))
        assert _import(auth_client, IMPORT, new).status_code == 500
        monkeypatch.undo()
        assert _deliveries(app, cert_id) == []


    def test_row_without_readable_certificate_is_a_first_issuance(self, app, auth_client, create_ca):
        ca_cert, ca_key, key, old, cert_id = _setup(app, auth_client, create_ca, 'r7-keyonly.example.com')
        with app.app_context():
            from models import db, Certificate
            db.session.get(Certificate, cert_id).crt = None
            db.session.commit()
        new = _cert('r7-keyonly.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        from unittest.mock import patch
        with patch('services.webhook_service.emit_cert_renewed') as emitted:
            r = _import(auth_client, IMPORT, new)
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['id'] == cert_id
        emitted.assert_not_called()
