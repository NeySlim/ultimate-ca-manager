"""POST /api/v2/certificates/<id>/submit-ct sends the leaf with its full issuer chain.

RFC 6962 §4.1: ``add-chain`` takes the leaf followed by the certificates that
chain it to a root the log accepts, one DER certificate per element. The chain
is walked through ``caref`` up to the root; a chain stored inline in
``Certificate.crt`` is split, one element per certificate.
"""
import base64
import json
import uuid

import pytest
from cryptography import x509

from models import CA, Certificate, SystemConfig, db
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import make_cert, new_key, pem
from tests.fixtures.cross_world import build_world
from utils.ct_client import _pem_chain_to_base64

KEYS = ('ct_enabled', 'ct_log_urls')
LOG_URL = 'https://ct.example.test/log'
SCT = {'log_url': LOG_URL, 'timestamp': 1}


@pytest.fixture
def ct_settings(app):
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in KEYS}

    def apply(**values):
        with app.app_context():
            for k, v in values.items():
                row = SystemConfig.query.filter_by(key=k).first()
                if v is None:
                    if row:
                        db.session.delete(row)
                    continue
                if row is None:
                    row = SystemConfig(key=k)
                    db.session.add(row)
                row.value = v
            db.session.commit()

    apply(ct_enabled='true', ct_log_urls=json.dumps([LOG_URL]))
    yield apply
    with app.app_context():
        for k, v in saved.items():
            row = SystemConfig.query.filter_by(key=k).first()
            if v is None:
                if row:
                    db.session.delete(row)
            elif row is None:
                db.session.add(SystemConfig(key=k, value=v))
            else:
                row.value = v
        db.session.commit()


@pytest.fixture
def submissions(monkeypatch):
    calls = []

    def fake_collect(chain, urls=None):
        calls.append({'chain': list(chain), 'urls': urls})
        return [dict(SCT)]

    monkeypatch.setattr('api.v2.certificates.ct.collect_scts', fake_collect)
    return calls


@pytest.fixture
def pki(app, auth_client):
    """Creates CAs and certificates through the API and deletes them afterwards."""
    cas, certs = [], []

    def ca(parent=None):
        body = {'type': 'intermediate' if parent else 'root',
                'commonName': f'CT submit {uuid.uuid4().hex[:8]}',
                'organization': 'Test Org', 'country': 'US', 'keyAlgo': 'RSA', 'keySize': 2048,
                'validityYears': 5, 'hashAlgorithm': 'sha256'}
        if parent:
            body['parentCAId'] = parent['id']
        r = auth_client.post('/api/v2/cas', json=body)
        assert r.status_code in (200, 201), r.data
        data = r.get_json()['data']
        cas.append(data['id'])
        return data

    def cert(issuer):
        r = auth_client.post('/api/v2/certificates', json={
            'cn': f'ct-{uuid.uuid4().hex[:8]}.example.com', 'ca_id': issuer['id'], 'validity_days': 30})
        assert r.status_code in (200, 201), r.data
        data = r.get_json()['data']
        certs.append(data['id'])
        return data

    yield ca, cert
    from services.ca_service import CAService
    from services.cert_service import CertificateService
    failures = []
    with app.app_context():
        for cid in certs:
            try:
                if not CertificateService.delete_certificate(cid, username='admin'):
                    failures.append(f'certificate {cid} not deleted')
            except Exception as e:
                db.session.rollback()
                failures.append(f'certificate {cid}: {e}')
        for cid in reversed(cas):
            try:
                if not CAService.delete_ca(cid, username='admin'):
                    failures.append(f'CA {cid} not deleted')
            except Exception as e:
                db.session.rollback()
                failures.append(f'CA {cid}: {e}')
        try:
            for cid in certs:
                row = SystemConfig.query.filter_by(key=f'cert_scts_{cid}').first()
                if row:
                    db.session.delete(row)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            failures.append(f'cert_scts rows: {e}')
    assert not failures, failures


def _pem_of(app, model, row_id):
    with app.app_context():
        return base64.b64decode(db.session.get(model, row_id).crt).decode()


def _submit(auth_client, cert_id):
    return auth_client.post(f'/api/v2/certificates/{cert_id}/submit-ct')


def _assert_signed_chain(chain):
    certs = [x509.load_pem_x509_certificate(p.encode() if isinstance(p, str) else p) for p in chain]
    for child, parent in zip(certs, certs[1:], strict=False):
        child.verify_directly_issued_by(parent)
    return certs


def test_root_then_leaf(app, auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    root = ca()
    leaf = cert(root)
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 200, r.data
    assert len(submissions) == 1
    chain = submissions[0]['chain']
    assert len(chain) == 2
    assert chain[0].strip() == _pem_of(app, Certificate, leaf['id']).strip()
    assert chain[1].strip() == _pem_of(app, CA, root['id']).strip()
    assert submissions[0]['urls'] == [LOG_URL]
    _assert_signed_chain(chain)


def test_root_intermediate_leaf_in_order(app, auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    root = ca()
    inter = ca(root)
    leaf = cert(inter)
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 200, r.data
    chain = submissions[0]['chain']
    assert len(chain) == 3
    assert [p.strip() for p in chain] == [
        _pem_of(app, Certificate, leaf['id']).strip(),
        _pem_of(app, CA, inter['id']).strip(),
        _pem_of(app, CA, root['id']).strip(),
    ]
    _assert_signed_chain(chain)


def test_two_intermediates_reach_the_root(app, auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    root = ca()
    int1 = ca(root)
    int2 = ca(int1)
    leaf = cert(int2)
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 200, r.data
    chain = submissions[0]['chain']
    assert len(chain) == 4
    certs = _assert_signed_chain(chain)
    assert certs[-1].issuer == certs[-1].subject
    assert chain[-1].strip() == _pem_of(app, CA, root['id']).strip()


def test_the_chain_converts_to_one_der_element_per_certificate(auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    root = ca()
    leaf = cert(ca(root))
    assert _submit(auth_client, leaf['id']).status_code == 200
    chain = submissions[0]['chain']
    encoded = _pem_chain_to_base64(chain)
    assert len(encoded) == len(chain) == 3
    for element in encoded:
        x509.load_der_x509_certificate(base64.b64decode(element))


@pytest.mark.parametrize('caref', [None, pytest.param('no-such-ca-refid', marks=pytest.mark.sqlite_only(
    reason='a dangling caref is refused by certificates_caref_fkey on PostgreSQL'))])
def test_an_orphan_certificate_is_sent_alone(app, auth_client, ct_settings, submissions, pki, caref):
    ca, cert = pki
    leaf = cert(ca())
    with app.app_context():
        row = db.session.get(Certificate, leaf['id'])
        leaf_pem = base64.b64decode(row.crt).decode()
        row.caref = caref
        db.session.commit()
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 200, r.data
    assert [p.strip() for p in submissions[0]['chain']] == [leaf_pem.strip()]


def test_an_inline_chain_is_split_per_certificate(app, auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    root = ca()
    inter = ca(root)
    leaf = cert(inter)
    leaf_pem = _pem_of(app, Certificate, leaf['id'])
    inter_pem = _pem_of(app, CA, inter['id'])
    with app.app_context():
        row = db.session.get(Certificate, leaf['id'])
        row.crt = base64.b64encode((leaf_pem.strip() + '\n' + inter_pem.strip() + '\n').encode()).decode()
        db.session.commit()
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 200, r.data
    chain = submissions[0]['chain']
    assert [p.strip() for p in chain] == [leaf_pem.strip(), inter_pem.strip()]
    _assert_signed_chain(chain)
    assert len(_pem_chain_to_base64(chain)) == 2


def test_ct_disabled_is_a_400(auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    leaf = cert(ca())
    ct_settings(ct_enabled=None)
    assert _submit(auth_client, leaf['id']).status_code == 400
    assert submissions == []


def test_an_unknown_certificate_is_a_404(auth_client, ct_settings, submissions):
    assert _submit(auth_client, 999999999).status_code == 404
    assert submissions == []


def test_no_log_accepting_is_a_400(auth_client, ct_settings, monkeypatch, pki):
    monkeypatch.setattr('api.v2.certificates.ct.collect_scts', lambda chain, urls=None: [])
    ca, cert = pki
    leaf = cert(ca())
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 400
    assert b'No CT logs accepted' in r.data


def test_a_malformed_log_configuration_is_a_400(auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    leaf = cert(ca())
    ct_settings(ct_log_urls='{oops')
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 400
    assert b'No valid CT log configured' in r.data
    assert submissions == []


def test_no_log_configuration_uses_the_default_logs(auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    leaf = cert(ca())
    ct_settings(ct_log_urls=None)
    assert _submit(auth_client, leaf['id']).status_code == 200
    assert len(submissions) == 1
    assert submissions[0]['urls'] is None


@pytest.fixture
def cross_world(app, auth_client):
    """Root B > Int B > leaf, Int B serving a cross-certificate issued by Root C; removed afterwards."""
    w = build_world(app, auth_client)
    key_c = new_key()
    name_c = f'Cross Root C {w.pki.tag}'
    int_cross = make_cert(f'Cross Int B {w.pki.tag}', w.pki.key_int, name_c, key_c, path_length=0)
    with app.app_context():
        SmartImporter().execute(pem(make_cert(name_c, key_c)))
        c_id = CA.query.filter_by(descr=name_c).one().id
    r = auth_client.post(f'/api/v2/cas/{w.int_id}/cross-certificates',
                         json={'certificate': pem(int_cross), 'served': True})
    assert r.status_code == 201, r.data
    yield w, int_cross
    from services.ca_service import CAService
    failures = []
    with app.app_context():
        try:
            Certificate.query.filter_by(id=w.leaf_id).delete()
            row = SystemConfig.query.filter_by(key=f'cert_scts_{w.leaf_id}').first()
            if row:
                db.session.delete(row)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            failures.append(f'leaf {w.leaf_id}: {e}')
        for cid in (w.int_id, w.b_id, w.a_id, c_id):
            try:
                if not CAService.delete_ca(cid, username='admin'):
                    failures.append(f'CA {cid} not deleted')
            except Exception as e:
                db.session.rollback()
                failures.append(f'CA {cid}: {e}')
    assert not failures, failures


def test_an_intermediate_serving_a_cross_is_sent_with_its_own_certificate(
        app, auth_client, ct_settings, submissions, cross_world):
    w, int_cross = cross_world
    r = _submit(auth_client, w.leaf_id)
    assert r.status_code == 200, r.data
    chain = submissions[0]['chain']
    assert [p.strip() for p in chain] == [
        _pem_of(app, Certificate, w.leaf_id).strip(),
        _pem_of(app, CA, w.int_id).strip(),
        _pem_of(app, CA, w.b_id).strip(),
    ]
    assert pem(int_cross).strip() not in [p.strip() for p in chain]
    _assert_signed_chain(chain)


def test_the_scts_are_stored(app, auth_client, ct_settings, submissions, pki):
    ca, cert = pki
    leaf = cert(ca())
    r = _submit(auth_client, leaf['id'])
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['scts_count'] == 1
    with app.app_context():
        stored = SystemConfig.query.filter_by(key=f'cert_scts_{leaf["id"]}').first()
        assert stored is not None
        assert json.loads(stored.value) == [SCT]
