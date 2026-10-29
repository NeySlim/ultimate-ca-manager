"""A stored cross-signed world: Roots A and B, Int B, B's cross-certificate and a leaf issued by Int B."""
import base64
import contextlib
import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta

from cryptography.hazmat.primitives.serialization import Encoding

from models import CA, Certificate, db
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, key_pem, pem
from utils.datetime_utils import utc_now
from utils.key_codec import store_pem_bytes


@dataclass
class World:
    pki: object
    a_id: int
    b_id: int
    int_id: int
    int_refid: str
    leaf_id: int
    xid: int


def build_world(app, auth_client, served=False):
    pki = build_cross_pki()
    with app.app_context():
        for cert in (pki.root_a, pki.root_b, pki.int_b):
            SmartImporter().execute(pem(cert))
        a = CA.query.filter_by(descr=pki.name_a).one()
        b = CA.query.filter_by(descr=pki.name_b).one()
        int_ca = CA.query.filter(CA.subject.contains(f'Cross Int B {pki.tag}')).one()
        assert int_ca.caref == b.refid
        a_id, b_id, int_id, int_refid = a.id, b.id, int_ca.id, int_ca.refid
    r = auth_client.post(f'/api/v2/cas/{b_id}/cross-certificates',
                         json={'certificate': pem(pki.cross_b), 'served': served})
    assert r.status_code == 201, r.data
    with app.app_context():
        leaf = Certificate(
            refid=uuid.uuid4().hex, descr=f'leaf {pki.tag}', caref=int_refid, source='imported',
            crt=base64.b64encode(pem(pki.leaf).encode()).decode(), prv=store_pem_bytes(key_pem(pki.key_leaf).encode()),
            serial_number=str(pki.leaf.serial_number), subject=pki.leaf.subject.rfc4514_string(),
            issuer=pki.leaf.issuer.rfc4514_string(), valid_from=utc_now(), valid_to=utc_now() + timedelta(days=30))
        db.session.add(leaf)
        db.session.commit()
        leaf_id = leaf.id
    return World(pki, a_id, b_id, int_id, int_refid, leaf_id, r.get_json()['data']['id'])


def set_served(auth_client, world, served):
    r = auth_client.patch(f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}', json={'served': served})
    assert r.status_code == 200, r.data


@contextlib.contextmanager
def admin_enrolment(app, leaf):
    """An mTLS enrolment of *leaf* for the admin user, removed on exit (other tests count on there being none)."""
    from models import AuthCertificate, User
    with app.app_context():
        row = AuthCertificate(user_id=User.query.filter_by(username='admin').one().id, cert_pem=pem(leaf).encode(),
                              cert_serial=str(leaf.serial_number), cert_subject=leaf.subject.rfc4514_string(),
                              cert_fingerprint=hashlib.sha256(leaf.public_bytes(Encoding.DER)).hexdigest(),
                              name='chain test')
        db.session.add(row)
        db.session.commit()
        auth_id = row.id
    try:
        yield auth_id
    finally:
        with app.app_context():
            AuthCertificate.query.filter_by(id=auth_id).delete()
            db.session.commit()
