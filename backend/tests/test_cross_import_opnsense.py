"""An OPNsense import attaches a cross-certificate to the self-signed CA it certifies (#400)."""
import base64
import json
import uuid

import pytest

from models import CA
from tests.fixtures.cross_pki import build_cross_pki, pem
from tests.test_opnsense_import import _Session


def _row(cert, descr):
    return {'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': descr,
            'crt': base64.b64encode(pem(cert).encode()).decode(), 'serial': '1'}


def _run(auth_client, monkeypatch, ca_rows):
    from api.v2 import import_opnsense
    monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: _Session(ca_rows, []))
    r = auth_client.post('/api/v2/import/opnsense/import', json={
        'host': '192.168.1.254', 'port': 443, 'api_key': 'k', 'api_secret': 's',
        'verify_ssl': False, 'items': []})
    assert r.status_code == 200, r.data
    return json.loads(r.data)['data']


def test_cross_certificate_listed_before_its_root_is_attached(app, auth_client, monkeypatch):
    pki = build_cross_pki()
    rows = [_row(pki.root_a, pki.name_a), _row(pki.cross_b, 'B cross'), _row(pki.root_b, pki.name_b)]
    body = _run(auth_client, monkeypatch, rows)
    assert body['imported']['cas'] == 2 and body['cross_certificates_attached'] == 1
    with app.app_context():
        records = CA.query.filter(CA.subject.contains(pki.tag)).all()
        assert len(records) == 2
        root = CA.query.filter_by(descr=pki.name_b).one()
        assert root.subject == root.issuer
        assert [x.serial_number for x in root.cross_certificates] == [str(pki.cross_b.serial_number)]


def test_importing_the_same_cross_certificate_again_adds_nothing(app, auth_client, monkeypatch):
    pki = build_cross_pki()
    first = [_row(pki.root_a, pki.name_a), _row(pki.root_b, pki.name_b), _row(pki.cross_b, 'B cross')]
    _run(auth_client, monkeypatch, first)
    again = _run(auth_client, monkeypatch, [_row(pki.cross_b, 'B cross')])
    assert again['imported']['cas'] == 0 and again['skipped'] == 1
    with app.app_context():
        assert CA.query.filter(CA.subject.contains(pki.tag)).count() == 2
        assert len(CA.query.filter_by(descr=pki.name_b).one().cross_certificates) == 1


def test_certificates_naming_an_attached_entry_link_to_its_counterpart_and_its_key_is_kept(app, auth_client,
                                                                                         monkeypatch):
    from api.v2 import import_opnsense
    from models import Certificate
    from tests.test_opnsense_import import _key_pem
    from utils.key_codec import load_pem_bytes
    pki = build_cross_pki()
    cross_row = _row(pki.cross_b, 'B cross')
    cross_row['prv'] = base64.b64encode(_key_pem(pki.key_b)).decode()
    leaf = {'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': f'leaf {pki.tag}',
            'crt': base64.b64encode(pem(pki.leaf).encode()).decode(), 'caref': cross_row['refid']}
    monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: _Session(
        [_row(pki.root_a, pki.name_a), _row(pki.root_b, pki.name_b), cross_row], [leaf]))
    r = auth_client.post('/api/v2/import/opnsense/import', json={
        'host': '192.168.1.254', 'port': 443, 'api_key': 'k', 'api_secret': 's',
        'verify_ssl': False, 'items': []})
    assert r.status_code == 200, r.data
    with app.app_context():
        root = CA.query.filter_by(descr=pki.name_b).one()
        assert Certificate.query.filter_by(descr=f'leaf {pki.tag}').one().caref == root.refid
        assert root.prv and load_pem_bytes(root.prv)
