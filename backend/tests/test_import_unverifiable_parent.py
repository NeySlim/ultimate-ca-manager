"""A CA is attached to a parent only when the parent's key verifies its signature:
a parent whose key type cannot be checked here leaves the imported CA without one."""
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from models import CA, db
from tests.conftest import get_json
from tests.test_scep_fortios_shape import _ca_pem, _key_pem
from utils import cert_issuer

@pytest.mark.parametrize('verifiable', [True, False])
def test_a_child_is_linked_only_under_a_parent_whose_signature_is_verified(app, auth_client, monkeypatch, verifiable):
    tag = uuid.uuid4().hex[:6]
    root_key, child_key = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
    root_cn, child_cn = f'Unverifiable Root {tag}', f'Unverifiable Child {tag}'
    if not verifiable:
        def cannot_check(cert, issuer):
            raise cert_issuer.UnsupportedIssuerKey('key type not handled')
        monkeypatch.setattr(cert_issuer, 'certificate_signed_by', cannot_check)
    refids = []
    try:
        _import_both(auth_client, refids, root_cn, root_key, child_cn, child_key)
        with app.app_context():
            assert CA.query.filter_by(refid=refids[1]).one().caref == (refids[0] if verifiable else None)
    finally:
        with app.app_context():
            for refid in reversed(refids):
                CA.query.filter_by(refid=refid).delete()
            db.session.commit()


def _import_both(auth_client, refids, root_cn, root_key, child_cn, child_key):
    for pem, key in ((_ca_pem(root_cn, root_key, serial=21), root_key),
                     (_ca_pem(child_cn, child_key, root_cn, root_key, serial=22), child_key)):
        r = auth_client.post('/api/v2/cas/import', data={'pem_content': pem + _key_pem(key)},
                             content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        refids.append(get_json(r)['data']['refid'])
