"""Issue #459: an imported CA takes an optional display name and description (default: the CN, no
description), from the CA import and from the smart import; a re-import keeps a name given since."""
import base64
import json
import uuid

import pytest

from models import CA, db
from tests.fixtures.cross_pki import key_pem, make_cert, new_key, pem


@pytest.fixture(autouse=True)
def _forget_cas(app):
    with app.app_context():
        before = {c.id for c in CA.query.all()}
    yield
    with app.app_context():
        for ca in CA.query.filter(~CA.id.in_(before)).all():
            db.session.delete(ca)
        db.session.commit()


def _ca_pem(tag):
    cn = f'Labelled import {tag} {uuid.uuid4().hex[:6]}'
    return cn, pem(make_cert(cn, new_key()))


# Both routes that create or update a CA from its certificate take the same labels
ROUTES = ['/api/v2/cas/import', '/api/v2/certificates/import']


def _import(auth_client, route='/api/v2/cas/import', **form):
    return auth_client.post(route, data=form, content_type='multipart/form-data')


def _stored(app, cn):
    with app.app_context():
        return [(c.descr, c.description) for c in CA.query.all() if c.common_name == cn]


@pytest.mark.parametrize('route', ROUTES)
def test_the_import_takes_a_name_and_a_description(app, auth_client, route):
    cn, cert = _ca_pem('named')
    r = _import(auth_client, route, pem_content=cert, name='  Partner Root  ',
                description='Signed by the partner\nkept')
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['data']['description'] == 'Signed by the partner\nkept'
    assert _stored(app, cn) == [('Partner Root', 'Signed by the partner\nkept')]


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('form', [{}, {'name': '   ', 'description': '  '}], ids=['absent', 'blank'])
def test_without_them_the_name_is_the_cn(app, auth_client, route, form):
    cn, cert = _ca_pem('plain')
    assert _import(auth_client, route, pem_content=cert, **form).status_code == 201
    assert _stored(app, cn) == [(cn, None)]


@pytest.mark.parametrize('form', [{'name': 'n' * 256}, {'description': 'd' * 1001}, {'description': 'bell\x07'}],
                         ids=['long-name', 'long-description', 'control'])
@pytest.mark.parametrize('route', ROUTES)
def test_an_unusable_label_refuses_the_import(app, auth_client, form, route):
    cn, cert = _ca_pem('refused')
    r = _import(auth_client, route, pem_content=cert, **form)
    assert r.status_code == 400, r.get_json()
    assert _stored(app, cn) == []


@pytest.mark.parametrize('route', ROUTES)
def test_a_reimport_keeps_the_name_given_since(app, auth_client, route):
    cn, cert = _ca_pem('kept')
    ca_id = _import(auth_client, pem_content=cert).get_json()['data']['id']
    r = auth_client.patch(f'/api/v2/cas/{ca_id}', json={'name': 'Renamed since', 'description': 'Mine'})
    assert r.status_code == 200, r.get_json()
    r = _import(auth_client, route, pem_content=cert, name='  ')
    assert r.status_code == 200, r.get_json()
    assert _stored(app, cn) == [('Renamed since', 'Mine')]
    assert _import(auth_client, route, pem_content=cert, name='Given now', description='New').status_code == 200
    assert _stored(app, cn) == [('Given now', 'New')]


def _pending_reimport(app, auth_client, monkeypatch, route='/api/v2/cas/import', **form):
    """Re-import a CA holding a renewal request, which goes through the install path; returns
    (response, a copy of each ca.updated payload as it was sent)."""
    key = new_key()
    cn = f'Labelled pending {uuid.uuid4().hex[:6]}'
    r = _import(auth_client, pem_content=pem(make_cert(cn, key)) + key_pem(key))
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        db.session.get(CA, r.get_json()['data']['id']).csr = base64.b64encode(b'outstanding').decode()
        db.session.commit()
    import services.webhook_service as webhooks
    sent = []
    monkeypatch.setattr(webhooks, 'emit_ca_updated', lambda ca_dict, **kw: sent.append(dict(ca_dict)))
    r = auth_client.post(route, data={'pem_content': pem(make_cert(cn, key)), **form},
                         content_type='multipart/form-data')
    return r, sent


@pytest.mark.parametrize('route', ROUTES)
def test_the_install_path_event_carries_the_new_description(app, auth_client, monkeypatch, route):
    r, sent = _pending_reimport(app, auth_client, monkeypatch, route, name='Installed Root',
                                description='Renewed here')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['description'] == 'Renewed here'
    assert [(p['descr'], p['description']) for p in sent] == [('Installed Root', 'Renewed here')]


def _smart(auth_client, content, **options):
    r = auth_client.post('/api/v2/import/execute', json={'content': content, 'options': options})
    return r.status_code, r.get_json()


def test_the_smart_import_names_each_ca_it_is_given_a_label_for(app, auth_client):
    cn_a, a = _ca_pem('smart a')
    cn_b, b = _ca_pem('smart b')
    status, body = _smart(auth_client, a + b, ca_labels={'1': {'name': ' Second ', 'description': 'From the bundle'}})
    assert status == 200, body
    assert body['data']['cas_imported'] == 2
    assert _stored(app, cn_a) == [(cn_a, None)]
    assert _stored(app, cn_b) == [('Second', 'From the bundle')]


@pytest.mark.parametrize('labels', [
    ['x'], {'9': {'name': 'Out of range'}}, {'a': {'name': 'Not a position'}}, {'0': 'Root'},
    {'0': {'name': 'n' * 256}}, {'0': {'description': 'bell\x07'}},
    {'0': {'name': 5}}, {'0': {'description': 0}}, {'\u00b2': {'name': 'Superscript'}},
], ids=['list', 'out-of-range', 'not-a-position', 'not-an-object', 'long-name', 'control',
        'name-not-text', 'description-not-text', 'non-ascii-digit'])
def test_an_unusable_smart_label_imports_nothing(app, auth_client, labels):
    cn, cert = _ca_pem('smart refused')
    status, body = _smart(auth_client, cert, ca_labels=labels)
    assert not (body.get('data') or {}).get('cas_imported'), body
    assert 'ca_labels' in json.dumps(body)
    assert 'Import failed' not in json.dumps(body)
    assert _stored(app, cn) == []
