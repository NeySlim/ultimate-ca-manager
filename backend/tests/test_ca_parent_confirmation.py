"""A CA whose parent's signature cannot be checked here is linked to it only on an explicit
confirmation: proposed at import, confirmed or withdrawn through one audited route.
Runs on PostgreSQL too through UCM_TEST_APP_PG_URL."""
import base64
import datetime as dt
import json
import uuid

import pytest
from asn1crypto import core
from asn1crypto import x509 as ax
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models import CA, db
from models.audit_log import AuditLog
from tests.conftest import get_json
from tests.test_tolerant_foreign_algorithms import KEYS, _der_len, _seq, _spki
from utils import cert_issuer

ROUTE = '/api/v2/cas/{}/parent-confirmation'
GOST = 'GOST2012-256'
REASON = f'signature not verifiable here: {GOST}'


# ---------------------------------------------------------------- builders

def _gost_pem(cn, issuer_cn=None, serial=1, ski=None, aki=None, key=None):
    """A CA certificate signed by a GOST key; a root holds one, which pyca cannot load, so no
    signature by it can be checked here."""
    key_alg, _, sig_alg = KEYS['gost']
    if issuer_cn:
        # A subordinate holds a key of its own pyca reads; only its issuer's GOST key is unreadable
        spki = core.Sequence.load((key or rsa.generate_private_key(65537, 2048)).public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
    else:
        spki = _spki(key_alg, uuid.uuid4().bytes * 4)  # a key of its own: two sharing one are cross-certificates
    utc = dt.timezone.utc
    validity = _seq(core.UTCTime(dt.datetime(2026, 1, 1, tzinfo=utc)),
                    core.UTCTime(dt.datetime(2046, 1, 1, tzinfo=utc)))
    exts = [{'extn_id': 'basic_constraints', 'critical': True, 'extn_value': {'ca': True}}]
    if ski:
        exts.append({'extn_id': 'key_identifier', 'critical': False, 'extn_value': ski})
    if aki:
        exts.append({'extn_id': 'authority_key_identifier', 'critical': False,
                     'extn_value': {'key_identifier': aki}})
    encoded = ax.Extensions(exts).dump()
    body = b'\xa0\x03\x02\x01\x02' + b''.join(i.dump() for i in (
        core.Integer(serial), sig_alg, ax.Name.build({'common_name': issuer_cn or cn}), validity,
        ax.Name.build({'common_name': cn}), spki))
    body += b'\xa3' + _der_len(encoded) + encoded
    der = _seq(core.Sequence(contents=body), sig_alg, core.OctetBitString(b'\x99' * 64)).dump()
    return x509.load_der_x509_certificate(der).public_bytes(serialization.Encoding.PEM).decode()


def _rsa_pem(cn, key, issuer_cn=None, signer=None, serial=1):
    name = lambda v: x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, v)])  # noqa: E731
    cert = (x509.CertificateBuilder().subject_name(name(cn)).issuer_name(name(issuer_cn or cn))
            .public_key(key.public_key()).serial_number(serial)
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2036, 1, 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(signer or key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _import(auth_client, pem, route='/api/v2/cas/import', **form):
    r = auth_client.post(route, data={'pem_content': pem, **form}, content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.data
    return get_json(r)['data']


@pytest.fixture
def made(app):
    """Ids of the CAs a test stored, deleted after it (children first)."""
    ids = []
    yield ids
    with app.app_context():
        for ca_id in sorted(ids, reverse=True):
            CA.query.filter_by(id=ca_id).delete()
        db.session.commit()


def _tag():
    return uuid.uuid4().hex[:8]


def _serial():
    return uuid.uuid4().int >> 66


@pytest.fixture
def gost_pair(auth_client, made):
    """A GOST root and a CA under it whose issuer DN differs only by case (equal under RFC 5280)."""
    tag, ski = _tag(), uuid.uuid4().bytes
    root = _import(auth_client, _gost_pem(f'Gost Root {tag}', serial=_serial(), ski=ski))
    made.append(root['id'])
    child = _import(auth_client, _gost_pem(f'Gost Child {tag}', issuer_cn=f'GOST ROOT {tag}',
                                           serial=_serial(), aki=ski))
    made.append(child['id'])
    return root, child


def _confirm(client, child_id, parent_id, confirm=True):
    body = {'parent_id': parent_id}
    if confirm is not None:
        body['confirm'] = confirm
    return client.post(ROUTE.format(child_id), json=body)


def _audits(app, action, ca_id):
    with app.app_context():
        return AuditLog.query.filter_by(action=action, resource_type='ca', resource_id=str(ca_id)).count()


# ------------------------------------------------- the three-valued verdict

def test_the_verdict_tells_verified_invalid_and_unverifiable_apart():
    key, other = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
    parent = x509.load_pem_x509_certificate(_rsa_pem('V Root', key).encode())
    good = x509.load_pem_x509_certificate(_rsa_pem('V Child', other, 'V Root', key).encode())
    bad = x509.load_pem_x509_certificate(_rsa_pem('V Child', other, 'V Root', other).encode())
    gost_root = x509.load_pem_x509_certificate(_gost_pem('G Root').encode())
    gost_child = x509.load_pem_x509_certificate(_gost_pem('G Child', 'G Root').encode())
    assert cert_issuer.signature_verdict(good, parent) == (cert_issuer.VERIFIED, None)
    assert cert_issuer.signature_verdict(bad, parent) == (cert_issuer.INVALID, None)
    assert cert_issuer.signature_verdict(gost_child, gost_root) == (cert_issuer.UNVERIFIABLE, GOST)


# ------------------------------------------------- import: every path says it

def test_cas_import_leaves_it_unlinked_and_names_the_candidate(gost_pair):
    root, child = gost_pair
    assert child['caref'] is None
    assert child['parent_candidate'] == {'id': root['id'], 'name': root['name'],
                                         'algorithm': GOST, 'reason': REASON}
    assert child['parent_confirmed_by'] is None and child['parent_confirmed_at'] is None


def test_certificates_import_names_the_candidate(auth_client, made):
    tag, ski = _tag(), uuid.uuid4().bytes
    root = _import(auth_client, _gost_pem(f'Gost CR {tag}', serial=_serial(), ski=ski), '/api/v2/certificates/import')
    made.append(root['id'])
    child = _import(auth_client, _gost_pem(f'Gost CC {tag}', f'Gost CR {tag}', serial=_serial(), aki=ski),
                    '/api/v2/certificates/import')
    made.append(child['id'])
    assert child['caref'] is None
    assert child['parent_candidate']['id'] == root['id'] and child['parent_candidate']['reason'] == REASON


def test_smart_import_names_the_candidate(app, auth_client, made):
    tag, ski = _tag(), uuid.uuid4().bytes
    content = (_gost_pem(f'Gost SR {tag}', serial=_serial(), ski=ski)
               + _gost_pem(f'Gost SC {tag}', f'Gost SR {tag}', serial=_serial(), aki=ski))
    r = auth_client.post('/api/v2/import/execute', json={'content': content, 'options': {}})
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    made.extend(data['imported_ids']['cas'])
    with app.app_context():
        root = CA.query.filter_by(descr=f'Gost SR {tag}').one()
        child = CA.query.filter_by(descr=f'Gost SC {tag}').one()
        assert child.caref is None
        expected = {'ca_id': child.id, 'ca_name': child.descr, 'candidate': {'id': root.id, 'name': root.descr},
                    'algorithm': GOST, 'reason': REASON}
    assert data['unverifiable_parents'] == [expected]


def test_opnsense_api_import_names_the_candidate(app, auth_client, monkeypatch, made):
    from api.v2 import import_opnsense
    from tests.test_opnsense_import import _Session
    tag, ski = _tag(), uuid.uuid4().bytes

    def row(pem, descr):
        return {'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': descr,
                'crt': base64.b64encode(pem.encode()).decode(), 'serial': '1'}
    rows = [row(_gost_pem(f'Gost OC {tag}', f'Gost OR {tag}', serial=_serial(), aki=ski), f'Gost OC {tag}'),
            row(_gost_pem(f'Gost OR {tag}', serial=_serial(), ski=ski), f'Gost OR {tag}')]
    monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: _Session(rows, []))
    r = auth_client.post('/api/v2/import/opnsense/import', json={
        'host': '192.0.2.10', 'port': 443, 'api_key': 'k', 'api_secret': 's', 'verify_ssl': False, 'items': []})
    assert r.status_code == 200, r.data
    with app.app_context():
        root = CA.query.filter_by(refid=rows[1]['refid']).one()
        child = CA.query.filter_by(refid=rows[0]['refid']).one()
        made.extend([root.id, child.id])
        assert child.caref is None
        expected = {'ca_id': child.id, 'ca_name': child.descr, 'candidate': {'id': root.id, 'name': root.descr},
                    'algorithm': GOST, 'reason': REASON}
    assert json.loads(r.data)['data']['unverifiable_parents'] == [expected]


def test_opnsense_file_importer_names_the_candidate(app, monkeypatch, tmp_path, made):
    from services.opnsense import importer
    monkeypatch.setattr(importer, '__file__', str(tmp_path / 'services' / 'opnsense' / 'importer.py'))
    tag, ski = _tag(), uuid.uuid4().bytes
    rows = [{'refid': uuid.uuid4().hex[:13], 'descr': f'Gost FC {tag}', 'is_root': False,
             'crt': base64.b64encode(_gost_pem(f'Gost FC {tag}', f'Gost FR {tag}', serial=_serial(),
                                               aki=ski).encode()).decode(),
             'subject': f'CN=Gost FC {tag}', 'issuer': f'CN=Gost FR {tag}'},
            {'refid': uuid.uuid4().hex[:13], 'descr': f'Gost FR {tag}', 'is_root': True,
             'crt': base64.b64encode(_gost_pem(f'Gost FR {tag}', serial=_serial(), ski=ski).encode()).decode(),
             'subject': f'CN=Gost FR {tag}', 'issuer': f'CN=Gost FR {tag}'}]
    with app.app_context():
        stats = importer.ImportMixin().import_cas(rows)
        root = CA.query.filter_by(refid=rows[1]['refid']).one()
        child = CA.query.filter_by(refid=rows[0]['refid']).one()
        made.extend([root.id, child.id])
        assert child.caref is None
        assert stats['unverifiable_parents'] == [{
            'ca_id': child.id, 'ca_name': child.descr, 'candidate': {'id': root.id, 'name': root.descr},
            'algorithm': GOST, 'reason': REASON}]


# ------------------------------------------------- the candidate

def test_a_namesake_whose_key_identifier_differs_is_no_candidate(auth_client, made):
    tag = _tag()
    root = _import(auth_client, _gost_pem(f'Gost KR {tag}', serial=_serial(), ski=uuid.uuid4().bytes))
    made.append(root['id'])
    child = _import(auth_client, _gost_pem(f'Gost KC {tag}', f'Gost KR {tag}', serial=_serial(),
                                           aki=uuid.uuid4().bytes))
    made.append(child['id'])
    assert child['caref'] is None and child['parent_candidate'] is None


# ------------------------------------------------- confirmation

def test_confirmation_links_marks_and_audits(app, auth_client, gost_pair):
    root, child = gost_pair
    before = _audits(app, 'ca_parent_confirmed', child['id'])  # ids come back once a row is deleted
    r = _confirm(auth_client, child['id'], root['id'])
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    assert data['caref'] == root['refid'] and data['parent_id'] == root['id']
    assert data['parent_confirmed_by'] == 'admin' and data['parent_confirmed_at']
    assert data['parent_candidate'] is None
    assert _audits(app, 'ca_parent_confirmed', child['id']) == before + 1
    with app.app_context():
        stored = db.session.get(CA, child['id'])
        assert stored.caref == root['refid'] and stored.parent_confirmed_by == 'admin'
        assert stored.parent_confirmed_at is not None


def test_a_reader_cannot_confirm(app, viewer_client, gost_pair):
    root, child = gost_pair
    r = _confirm(viewer_client, child['id'], root['id'])
    assert r.status_code == 403, r.data
    with app.app_context():
        assert db.session.get(CA, child['id']).caref is None


@pytest.mark.parametrize('confirm', [None, False, 'true', 1])
def test_without_an_explicit_confirmation_nothing_is_linked(app, auth_client, gost_pair, confirm):
    root, child = gost_pair
    r = _confirm(auth_client, child['id'], root['id'], confirm)
    assert r.status_code == 400, r.data
    assert 'confirm' in get_json(r)['message'].lower()
    with app.app_context():
        assert db.session.get(CA, child['id']).caref is None


def test_a_parent_that_is_not_the_candidate_is_refused(app, auth_client, made, gost_pair):
    root, child = gost_pair
    other = _import(auth_client, _gost_pem(f'Gost Other {_tag()}', serial=_serial()))
    made.append(other['id'])
    before = _audits(app, 'ca_parent_confirmed', child['id'])
    r = _confirm(auth_client, child['id'], other['id'])
    assert r.status_code == 409, r.data
    assert 'not the proposed parent' in get_json(r)['message']
    with app.app_context():
        assert db.session.get(CA, child['id']).caref is None
    assert _audits(app, 'ca_parent_confirmed', child['id']) == before


def test_a_signature_that_does_not_verify_is_refused_even_confirmed(app, auth_client, made):
    tag = _tag()
    key, other = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
    root = _import(auth_client, _rsa_pem(f'Bad Root {tag}', key, serial=_serial()))
    made.append(root['id'])
    child = _import(auth_client, _rsa_pem(f'Bad Child {tag}', other, f'Bad Root {tag}', other, serial=_serial()))
    made.append(child['id'])
    assert child['caref'] is None and child['parent_candidate'] is None
    r = _confirm(auth_client, child['id'], root['id'])
    assert r.status_code == 409, r.data
    assert 'does not verify' in get_json(r)['message']
    with app.app_context():
        assert db.session.get(CA, child['id']).caref is None


def test_a_verified_parent_is_already_linked_with_nothing_to_confirm(app, auth_client, made):
    """Characterization: a verifying parent is linked at import, as before, and never marked."""
    tag = _tag()
    key, other = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
    root = _import(auth_client, _rsa_pem(f'Ok Root {tag}', key, serial=_serial()))
    made.append(root['id'])
    child = _import(auth_client, _rsa_pem(f'Ok Child {tag}', other, f'Ok Root {tag}', key, serial=_serial()))
    made.append(child['id'])
    assert child['caref'] == root['refid']
    assert child['parent_candidate'] is None and child['parent_confirmed_by'] is None
    r = _confirm(auth_client, child['id'], root['id'])
    assert r.status_code == 409, r.data
    assert 'already has a parent' in get_json(r)['message']
    with app.app_context():
        assert db.session.get(CA, child['id']).parent_confirmed_at is None


# ------------------------------------------------- the confirmed link holds

def test_the_hourly_repair_and_a_reimport_keep_the_confirmed_link(app, auth_client, gost_pair):
    from services.ski_aki_backfill import backfill_ski_aki
    root, child = gost_pair
    assert _confirm(auth_client, child['id'], root['id']).status_code == 200
    with app.app_context():
        backfill_ski_aki()
    with app.app_context():
        pem = base64.b64decode(db.session.get(CA, child['id']).crt).decode()
    assert _import(auth_client, pem)['id'] == child['id']
    with app.app_context():
        stored = db.session.get(CA, child['id'])
        assert stored.caref == root['refid'] and stored.parent_confirmed_by == 'admin'


def test_a_reimport_under_another_issuer_drops_the_confirmation(app, auth_client, gost_pair):
    root, child = gost_pair
    assert _confirm(auth_client, child['id'], root['id']).status_code == 200
    # Same subject, issued by a name nothing stored carries, replacing the stored certificate
    moved = _gost_pem(child['name'], f'Elsewhere {_tag()}', serial=_serial())
    assert _import(auth_client, moved, cross_mode='replace')['id'] == child['id']
    with app.app_context():
        stored = db.session.get(CA, child['id'])
        assert stored.caref is None and stored.parent_confirmed_at is None


def test_the_revoked_parent_revokes_the_chain_and_the_export_carries_it(app, auth_client, gost_pair):
    root, child = gost_pair
    assert _confirm(auth_client, child['id'], root['id']).status_code == 200
    exported = auth_client.get(f"/api/v2/cas/{child['id']}/export?format=pem&include_chain=true")
    assert exported.status_code == 200, exported.data
    with app.app_context():
        root_pem = base64.b64decode(db.session.get(CA, root['id']).crt)
        db.session.get(CA, root['id']).revoked = True
        db.session.commit()
    assert root_pem.strip() in exported.data
    shown = get_json(auth_client.get(f"/api/v2/cas/{child['id']}"))['data']
    assert shown['revoked_in_chain'] is True


def test_a_signature_found_false_later_is_no_longer_honored(app, auth_client, monkeypatch, gost_pair):
    """UCM learns the algorithm and the signature fails: issuing_ca() drops the confirmed parent."""
    root, child = gost_pair
    assert _confirm(auth_client, child['id'], root['id']).status_code == 200
    with app.app_context():
        db.session.get(CA, root['id']).revoked = True
        db.session.commit()
        assert db.session.get(CA, child['id']).issuing_ca().id == root['id']
    monkeypatch.setattr(cert_issuer, 'certificate_signed_by', lambda cert, issuer: False)
    with app.app_context():
        stored = db.session.get(CA, child['id'])
        assert stored.issuing_ca() is None
        assert stored.revoked_in_chain is False


# ------------------------------------------------- the external-CSR install path

@pytest.fixture
def held_gost_child(app, auth_client, made, gost_pair):
    """A CA holding its RSA key, linked by hand under a GOST root, with a renewal request outstanding."""
    root, _ = gost_pair
    tag, key = _tag(), rsa.generate_private_key(65537, 2048)
    with app.app_context():
        root_ski = bytes.fromhex(db.session.get(CA, root['id']).ski.replace(':', ''))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    cn = f'Gost Held {tag}'
    child = _import(auth_client, _gost_pem(cn, root['name'], serial=_serial(), aki=root_ski, key=key) + key_pem)
    made.append(child['id'])
    assert _confirm(auth_client, child['id'], root['id']).status_code == 200
    with app.app_context():
        db.session.get(CA, child['id']).csr = base64.b64encode(b'outstanding').decode()
        db.session.commit()
    return root, child, cn, key


def _install(app, auth_client, child, pem):
    assert _import(auth_client, pem, cross_mode='replace')['id'] == child['id']
    with app.app_context():
        assert db.session.get(CA, child['id']).csr is None  # went through complete_external_ca


def test_an_installed_renewal_from_an_unknown_issuer_drops_the_confirmed_parent(app, auth_client, held_gost_child):
    root, child, cn, key = held_gost_child
    _install(app, auth_client, child, _rsa_pem(cn, key, f'Elsewhere {_tag()}', rsa.generate_private_key(65537, 2048),
                                               serial=_serial()))
    with app.app_context():
        db.session.get(CA, root['id']).revoked = True
        db.session.commit()
        stored = db.session.get(CA, child['id'])
        assert stored.caref is None and stored.parent_confirmed_by is None and stored.parent_confirmed_at is None
        assert stored.issuing_ca() is None and stored.revoked_in_chain is False


def test_an_installed_renewal_from_a_verified_issuer_is_no_hand_confirmed_link(app, auth_client, made, held_gost_child):
    _, child, cn, key = held_gost_child
    rsa_key, rsa_cn = rsa.generate_private_key(65537, 2048), f'Rsa Root {_tag()}'
    rsa_root = _import(auth_client, _rsa_pem(rsa_cn, rsa_key, serial=_serial()))
    made.append(rsa_root['id'])
    _install(app, auth_client, child, _rsa_pem(cn, key, rsa_cn, rsa_key, serial=_serial()))
    with app.app_context():
        stored = db.session.get(CA, child['id'])
        assert stored.caref == rsa_root['refid']
        assert stored.parent_confirmed_by is None and stored.parent_confirmed_at is None
    assert auth_client.delete(ROUTE.format(child['id']), json={'confirm': True}).status_code == 409


def test_an_installed_renewal_under_the_same_unverifiable_parent_keeps_it(app, auth_client, held_gost_child):
    root, child, cn, key = held_gost_child
    with app.app_context():
        root_ski = bytes.fromhex(db.session.get(CA, root['id']).ski.replace(':', ''))
    _install(app, auth_client, child, _gost_pem(cn, root['name'], serial=_serial(), aki=root_ski, key=key))
    with app.app_context():
        stored = db.session.get(CA, child['id'])
        assert stored.caref == root['refid'] and stored.parent_confirmed_by == 'admin'


# ------------------------------------------------- withdrawal

def test_withdrawal_is_audited_and_the_candidate_comes_back(app, auth_client, gost_pair):
    root, child = gost_pair
    assert _confirm(auth_client, child['id'], root['id']).status_code == 200
    before = _audits(app, 'ca_parent_unconfirmed', child['id'])
    r = auth_client.delete(ROUTE.format(child['id']), json={'confirm': True})
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    assert data['caref'] is None and data['parent_confirmed_by'] is None
    assert data['parent_candidate']['id'] == root['id']
    assert _audits(app, 'ca_parent_unconfirmed', child['id']) == before + 1


def test_a_link_not_confirmed_by_hand_is_not_withdrawn(app, auth_client, made):
    tag = _tag()
    key, other = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
    root = _import(auth_client, _rsa_pem(f'Keep Root {tag}', key, serial=_serial()))
    made.append(root['id'])
    child = _import(auth_client, _rsa_pem(f'Keep Child {tag}', other, f'Keep Root {tag}', key, serial=_serial()))
    made.append(child['id'])
    r = auth_client.delete(ROUTE.format(child['id']), json={'confirm': True})
    assert r.status_code == 409, r.data
    with app.app_context():
        assert db.session.get(CA, child['id']).caref == root['refid']
