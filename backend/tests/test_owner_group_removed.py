"""`owner_group_id` is neither taken nor shown.

It was stored on SSH CAs and SSH certificates and returned for CAs and
certificates, but no access check ever read it: a "group owner" that
restricted nothing.
"""
from models import Group, SSHCertificate, SSHCertificateAuthority, db
from tests.test_ssh import _create_ssh_ca, _generate_test_ssh_key, post_json, put_json


def _group_id(app):
    with app.app_context():
        group = Group.query.first()
        if group is None:
            group = Group(name='owner-group-test')
            db.session.add(group)
            db.session.commit()
        return group.id


def test_ssh_ca_ignores_it(app, auth_client):
    gid = _group_id(app)
    r = post_json(auth_client, '/api/v2/ssh/cas', {'descr': 'Owner group CA', 'ca_type': 'user',
                                                   'key_type': 'ed25519', 'owner_group_id': gid})
    assert r.status_code == 201, r.data
    ca = r.get_json()['data']
    assert 'owner_group_id' not in ca
    assert put_json(auth_client, f"/api/v2/ssh/cas/{ca['id']}", {'owner_group_id': gid}).status_code == 200
    with app.app_context():
        assert db.session.get(SSHCertificateAuthority, ca['id']).owner_group_id is None


def test_ssh_certificate_ignores_it(app, auth_client):
    gid = _group_id(app)
    ca = _create_ssh_ca(auth_client, ca_type='user', descr='Owner group sign CA')
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': _generate_test_ssh_key(), 'cert_type': 'user',
        'principals': ['owner'], 'owner_group_id': gid})
    assert r.status_code == 201, r.data
    cert = r.get_json()['data']
    assert 'owner_group_id' not in cert
    with app.app_context():
        assert db.session.get(SSHCertificate, cert['id']).owner_group_id is None


def test_cas_and_certificates_do_not_show_it(auth_client, create_ca):
    ca = create_ca(cn='Owner group X509 CA')
    assert 'owner_group_id' not in auth_client.get(f"/api/v2/cas/{ca['id']}").get_json()['data']
    r = post_json(auth_client, '/api/v2/certificates', {'cn': 'owner.group.test', 'ca_id': ca['id']})
    assert r.status_code in (200, 201), r.data
    cert_id = r.get_json()['data']['id']
    assert 'owner_group_id' not in auth_client.get(f'/api/v2/certificates/{cert_id}').get_json()['data']
