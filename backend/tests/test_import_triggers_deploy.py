"""An import that replaces a certificate queues its deploy bindings (discussion #440)."""
import json

import pytest

from tests.test_deploy_hooks import _create_target, _create_binding
from tests.test_import_review import _cert, _gen, _ca_from_fixture, _store_cert, _import

IMPORT = '/api/v2/certificates/import'

# The CAs and certificates made here (the default test CA included) go with the module.
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


# Certificate ids are reused on SQLite: a binding or delivery older than the setup belongs to another test.
_SINCE = {}


def _last_ids(app):
    with app.app_context():
        from models import db, DeployDelivery, DeployBinding
        return (db.session.query(db.func.max(DeployDelivery.id)).scalar() or 0,
                db.session.query(db.func.max(DeployBinding.id)).scalar() or 0)


def _deliveries(app, cert_id):
    with app.app_context():
        from models import DeployDelivery, DeployBinding
        # creating a binding queues an 'initial' push; only the import's matters
        return [(d.event_type, d.status) for d in DeployDelivery.query
                .join(DeployBinding, DeployDelivery.binding_id == DeployBinding.id)
                .filter(DeployBinding.certificate_id == cert_id,
                        DeployDelivery.id > _SINCE.get(cert_id, (0, 0))[0],
                        DeployBinding.id > _SINCE.get(cert_id, (0, 0))[1],
                        DeployDelivery.event_type != 'initial').all()]


def _setup(app, auth_client, create_ca, cn, bound=True):
    since = _last_ids(app)
    ca = create_ca(cn=f'{cn} CA')
    ca_cert, ca_key, caref, _ = _ca_from_fixture(app, ca)
    key = _gen()
    old = _cert(cn, key, issuer_cert=ca_cert, signer=ca_key)
    cert_id = _store_cert(app, old, key, caref=caref)
    _SINCE[cert_id] = since
    if bound:
        target = _create_target(auth_client)
        _create_binding(auth_client, target['id'], cert_id)
    return ca_cert, ca_key, key, old, cert_id


class TestImportReplacementDeploys:
    def test_replacement_queues_one_delivery_per_binding(self, app, auth_client, create_ca):
        ca_cert, ca_key, key, old, cert_id = _setup(app, auth_client, create_ca, 'r7-replace.example.com')
        new = _cert('r7-replace.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        r = _import(auth_client, IMPORT, new)
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['id'] == cert_id
        assert _deliveries(app, cert_id) == [('certificate.renewed', 'pending')]

    def test_same_serial_reimport_queues_nothing(self, app, auth_client, create_ca):
        *_, old, cert_id = _setup(app, auth_client, create_ca, 'r7-same.example.com')
        r = _import(auth_client, IMPORT, old)
        assert r.status_code == 200, r.data
        assert _deliveries(app, cert_id) == []

    def test_replacement_without_binding_is_silent(self, app, auth_client, create_ca):
        ca_cert, ca_key, key, old, cert_id = _setup(app, auth_client, create_ca, 'r7-nobind.example.com', bound=False)
        new = _cert('r7-nobind.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        assert _import(auth_client, IMPORT, new).status_code == 200
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

    def test_a_replacement_its_ca_recorded_as_revoked_queues_nothing(self, app, auth_client, create_ca):
        ca_cert, ca_key, key, old, cert_id = _setup(app, auth_client, create_ca, 'r7-revoked.example.com')
        new = _cert('r7-revoked.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        from datetime import datetime
        from models import db, Certificate, RevokedSerial
        with app.app_context():
            caref = db.session.get(Certificate, cert_id).caref
            db.session.add(RevokedSerial(caref=caref, serial_number=str(new.serial_number),
                                         revoked_at=datetime(2026, 1, 2, 3, 4, 5), revoke_reason='keyCompromise',
                                         valid_to=new.not_valid_after_utc.replace(tzinfo=None)))
            db.session.commit()
        try:
            r = _import(auth_client, IMPORT, new)
            assert r.status_code == 200, r.data
            data = json.loads(r.data)['data']
            assert (data['id'], data['revoked']) == (cert_id, True)
            assert _deliveries(app, cert_id) == []
        finally:
            with app.app_context():
                RevokedSerial.query.filter_by(caref=caref, serial_number=str(new.serial_number)).delete()
                db.session.commit()

    def test_row_without_readable_certificate_is_not_a_renewal(self, app, auth_client, create_ca):
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
