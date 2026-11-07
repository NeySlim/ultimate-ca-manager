"""GetNextCACert (RFC 8894 §4.7) serves the rollover certificate of the
current CA: same subject DN, usable (not revoked, not offline, key held) and
expiring later. A display-name match alone is no successor."""
import base64
import uuid

import asn1crypto.cms
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs7

from models import CA, SystemConfig, db

URL = '/scep/pkiclient.exe?operation=GetNextCACert'


def _set_scep_ca(ca_id):
    row = SystemConfig.query.filter_by(key='scep_ca_id').first()
    if row is None:
        db.session.add(SystemConfig(key='scep_ca_id', value=str(ca_id)))
    else:
        row.value = str(ca_id)
    db.session.commit()


@pytest.fixture
def current(app, create_ca):
    cn = f'SCEP Next CA {uuid.uuid4().hex[:8]}'
    ca = create_ca(cn=cn, validityYears=5)
    with app.app_context():
        _set_scep_ca(ca['id'])
    yield cn, ca
    with app.app_context():
        row = SystemConfig.query.filter_by(key='scep_ca_id').first()
        if row:
            db.session.delete(row)
            db.session.commit()


def _served_serials(response):
    inner = asn1crypto.cms.ContentInfo.load(response.data)['content']['encap_content_info']['content'].native
    return [c.serial_number for c in pkcs7.load_der_pkcs7_certificates(inner)]


def _serial(app, ca_id):
    with app.app_context():
        return x509.load_pem_x509_certificate(base64.b64decode(db.session.get(CA, ca_id).crt)).serial_number


def test_same_display_name_other_subject_is_not_a_successor(app, client, create_ca, current):
    cn, ca = current
    unrelated = create_ca(cn=f'{cn} unrelated', organization='Other Org', validityYears=10)
    with app.app_context():
        db.session.get(CA, unrelated['id']).descr = db.session.get(CA, ca['id']).descr
        db.session.commit()

    assert client.get(URL).status_code == 404


def test_same_subject_under_another_name_is_the_successor(app, client, create_ca, current):
    cn, _ca = current
    successor = create_ca(cn=cn, validityYears=10)
    with app.app_context():
        db.session.get(CA, successor['id']).descr = 'renamed successor'
        db.session.commit()

    response = client.get(URL)
    assert response.status_code == 200
    assert _served_serials(response) == [_serial(app, successor['id'])]


@pytest.mark.parametrize('state', ['revoked', 'offline', 'keyless'])
def test_unusable_successor_is_not_served(app, client, create_ca, current, state):
    cn, _ca = current
    successor = create_ca(cn=cn, validityYears=10)
    with app.app_context():
        row = db.session.get(CA, successor['id'])
        if state == 'revoked':
            row.revoked = True
        elif state == 'offline':
            row.offline = True
        else:
            row.prv = None
        db.session.commit()

    assert client.get(URL).status_code == 404


def test_unusable_newer_successor_falls_back_to_a_usable_one(app, client, create_ca, current):
    cn, _ca = current
    usable = create_ca(cn=cn, validityYears=8)
    revoked = create_ca(cn=cn, validityYears=10)
    with app.app_context():
        db.session.get(CA, revoked['id']).revoked = True
        db.session.commit()

    response = client.get(URL)
    assert response.status_code == 200
    assert _served_serials(response) == [_serial(app, usable['id'])]
