"""An imported CA is chained under the stored CA whose key signed it, whatever the order of the batch."""
import json
import uuid

import pytest
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import CA, SystemConfig, db
from tests.fixtures.cross_pki import key_pem, make_cert, new_key, pem


@pytest.fixture(autouse=True)
def _forget_cas(app):
    with app.app_context():
        before = {c.id for c in CA.query.all()}
    yield
    with app.app_context():
        # ORM delete: SQLite tests run without foreign keys, so a bulk delete would orphan cross rows
        for ca in CA.query.filter(~CA.id.in_(before)).all():
            db.session.delete(ca)
        db.session.commit()


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row:
            db.session.delete(row)
    elif row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _cn(cert):
    return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value


@pytest.mark.parametrize('endpoint', ['/api/v2/cas/import'])
def test_imported_child_ca_is_linked_to_its_imported_parent_at_once(app, client, auth_client, endpoint):
    """Parent known from the import response on, and GetCACert in chain mode serves both
    certificates without waiting for the hourly backfill."""
    tag = uuid.uuid4().hex[:6]
    root_key, child_key = new_key('rsa'), new_key('rsa')  # SCEP encrypts to an RSA key
    root_cn, child_cn = f'Import Root {tag}', f'Import Child {tag}'
    root = make_cert(root_cn, root_key)
    child = make_cert(child_cn, child_key, root_cn, root_key, path_length=0)
    ids = []
    with app.app_context():
        saved = {k: (row.value if (row := SystemConfig.query.filter_by(key=k).first()) else None)
                 for k in ('scep_enabled', 'scep_ca_id', 'scep_getcacert_chain')}
    try:
        for cert, key in ((root, root_key), (child, child_key)):
            r = auth_client.post(endpoint, data={'pem_content': pem(cert) + key_pem(key)},
                                 content_type='multipart/form-data')
            assert r.status_code in (200, 201), r.data
            ids.append(json.loads(r.data)['data']['id'])
        with app.app_context():
            root, child = db.session.get(CA, ids[0]), db.session.get(CA, ids[1])
            assert child.caref == root.refid
            assert root.caref is None
            _set('scep_enabled', 'true')
            _set('scep_ca_id', str(ids[1]))
            _set('scep_getcacert_chain', 'true')
        r = client.get('/scep/pkiclient.exe?operation=GetCACert')
        assert r.status_code == 200, r.data
        assert {_cn(c) for c in pkcs7.load_der_pkcs7_certificates(r.data)} == {root_cn, child_cn}
    finally:
        with app.app_context():
            for k, v in saved.items():
                _set(k, v)
