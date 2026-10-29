"""The SCEP default CA and the EST labels refuse a CA that cannot sign, but keep the one already saved (#426)."""
import json

import pytest

from models import CA, db
from models.system_config import SystemConfig


def _config(key):
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row else None


def _restore(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row:
            db.session.delete(row)
    elif row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _drop_key(app, ca_id):
    with app.app_context():
        db.session.get(CA, ca_id).prv = None
        db.session.commit()


@pytest.fixture
def cas(app, create_ca):
    signer = create_ca(cn='Settings signer CA')
    keyless = create_ca(cn='Settings keyless CA')
    _drop_key(app, keyless['id'])
    with app.app_context():
        saved = {k: _config(k) for k in ('scep_ca_id', 'scep_auto_approve', 'est_labels', 'est_validity_days')}
        refids = {c['id']: db.session.get(CA, c['id']).refid for c in (signer, keyless)}
    yield signer, keyless, refids
    with app.app_context():
        for key, value in saved.items():
            _restore(key, value)


def test_scep_default_ca_refuses_a_ca_without_key(auth_client, cas):
    signer, keyless, _ = cas
    r = auth_client.patch('/api/v2/scep/config', json={'ca_id': keyless['id']})
    assert r.status_code == 400, r.data
    assert 'no private key' in r.get_json()['message']
    assert auth_client.patch('/api/v2/scep/config', json={'ca_id': signer['id']}).status_code == 200


def test_scep_default_ca_already_saved_stays_saveable(app, auth_client, cas):
    signer, _, _ = cas
    assert auth_client.patch('/api/v2/scep/config', json={'ca_id': signer['id']}).status_code == 200
    _drop_key(app, signer['id'])
    r = auth_client.patch('/api/v2/scep/config', json={'ca_id': signer['id'], 'auto_approve': False})
    assert r.status_code == 200, r.data


def test_est_label_refuses_a_ca_without_key(auth_client, cas):
    _, keyless, refids = cas
    r = auth_client.patch('/api/v2/est/config', json={'labels': {'nokey': refids[keyless['id']]}})
    assert r.status_code == 400, r.data
    assert "Label 'nokey'" in r.get_json()['message']


def test_est_label_already_saved_stays_saveable(app, auth_client, cas):
    signer, _, refids = cas
    labels = {'main': refids[signer['id']]}
    assert auth_client.patch('/api/v2/est/config', json={'labels': labels}).status_code == 200
    _drop_key(app, signer['id'])
    r = auth_client.patch('/api/v2/est/config', json={'labels': labels, 'validity_days': 365})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert json.loads(_config('est_labels')) == labels
