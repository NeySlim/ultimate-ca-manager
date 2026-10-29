"""The SCEP default CA and the EST labels refuse a CA that cannot sign, but keep the one already saved (#426)."""
import json

import pytest

from models import CA, db
from models.hsm import HsmKey, HsmProvider
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


def test_scep_default_ca_refuses_an_hsm_ca(app, auth_client, cas):
    signer, _, _ = cas
    with app.app_context():
        provider = HsmProvider(name='settings-hsm', type='openbao')
        provider.config = json.dumps({'url': 'http://bao.test', 'token': 't'})
        db.session.add(provider)
        db.session.commit()
        key = HsmKey(provider_id=provider.id, key_identifier='settings-key', label='settings',
                     algorithm='rsa', key_type='rsa', purpose='sign')
        db.session.add(key)
        db.session.commit()
        db.session.get(CA, signer['id']).hsm_key_id = key.id
        db.session.commit()
    try:
        r = auth_client.patch('/api/v2/scep/config', json={'ca_id': signer['id']})
        assert r.status_code == 400, r.data
        assert r.get_json()['message'].startswith('Selected CA is HSM-backed')
    finally:
        with app.app_context():
            db.session.get(CA, signer['id']).hsm_key_id = None
            db.session.commit()


def test_scep_default_ca_saved_as_refid(app, auth_client, cas):
    _, keyless, refids = cas
    with app.app_context():
        _restore('scep_ca_id', refids[keyless['id']])
    assert auth_client.get('/api/v2/scep/config').get_json()['data']['ca_id'] == keyless['id']
    r = auth_client.patch('/api/v2/scep/config', json={'ca_id': keyless['id']})
    assert r.status_code == 200, r.data


@pytest.mark.parametrize('stored_as', ['id', 'refid'])
def test_default_scep_ca_cannot_be_deleted(app, auth_client, cas, stored_as):
    signer, _, refids = cas
    with app.app_context():
        _restore('scep_ca_id', str(signer['id']) if stored_as == 'id' else refids[signer['id']])
    r = auth_client.delete(f"/api/v2/cas/{signer['id']}")
    assert r.status_code == 409, r.data
    assert 'default SCEP CA' in r.get_json()['message']
    with app.app_context():
        assert db.session.get(CA, signer['id']) is not None
