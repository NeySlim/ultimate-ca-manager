"""build_subject reads short DN keys only: a key it does not know is a programming error, not a dropped field."""
import json

import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID

from models import Certificate, db
from services.trust_store import TrustStoreService

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def test_known_keys_build_the_subject():
    name = TrustStoreService.build_subject({'CN': 'a.example', 'O': 'Org', 'C': 'FR', 'email': 'a@example.com'})
    assert name.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'a.example'
    assert len(name) == 4


@pytest.mark.parametrize('key', ['commonName', 'organizationName', 'countryName', 'cn'])
def test_an_unknown_key_is_refused_by_name(key):
    with pytest.raises(ValueError, match=key):
        TrustStoreService.build_subject({'CN': 'a.example', key: 'x'})


def test_an_admin_generated_mtls_certificate_carries_the_name_as_cn(app, auth_client, create_ca):
    ca = create_ca(cn='Admin mTLS CN CA')
    r = auth_client.post('/api/v2/users/1/mtls/certificates',
                         data=json.dumps({'mode': 'generate', 'ca_id': ca['id'], 'name': 'alice-laptop',
                                          'password': 'changeme123'}),
                         content_type='application/json')
    assert r.status_code == 201, r.get_json()
    data = r.get_json()['data']
    try:
        cert = x509.load_pem_x509_certificate(data['certificate'].encode())
        assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'alice-laptop'
    finally:
        with app.app_context():
            from models.auth_certificate import AuthCertificate
            AuthCertificate.query.filter_by(id=data['id']).delete()
            row = db.session.get(Certificate, data['cert_id'])
            if row:
                db.session.delete(row)
            db.session.commit()
