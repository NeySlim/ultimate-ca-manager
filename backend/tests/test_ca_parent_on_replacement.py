"""After any change of a CA's certificate, its parent is the CA whose key verifies the new
certificate, a parent confirmed by hand for it, or none: a former parent is never kept on trust.
Runs on PostgreSQL too through UCM_TEST_APP_PG_URL."""
import base64
import datetime as dt
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models import CA, db
from tests.conftest import get_json
from tests.test_ca_parent_confirmation import _audits, _gost_pem, _import, _rsa_pem, _serial, _tag

UNLINKED = 'ca_parent_unlinked'


@pytest.fixture
def made(app):
    """Ids of the CAs a test stored, deleted after it (children first)."""
    ids = []
    yield ids
    with app.app_context():
        for ca_id in sorted(ids, reverse=True):
            CA.query.filter_by(id=ca_id).delete()
        db.session.commit()


def _key():
    return rsa.generate_private_key(65537, 2048)


def _stored_pem(app, ca_id):
    with app.app_context():
        return base64.b64decode(db.session.get(CA, ca_id).crt).strip()


def _caref(app, ca_id):
    with app.app_context():
        return db.session.get(CA, ca_id).caref


@pytest.fixture
def linked(auth_client, made):
    """A root and a CA linked under it because the root's key verifies the CA's certificate."""
    tag, root_key, key = _tag(), _key(), _key()
    root_cn, cn = f'Repl Root {tag}', f'Repl Child {tag}'
    root = _import(auth_client, _rsa_pem(root_cn, root_key, serial=_serial()))
    made.append(root['id'])
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    # The CA holds its key: the install path checks the new certificate against it
    child = _import(auth_client, _rsa_pem(cn, key, root_cn, root_key, serial=_serial()) + key_pem)
    made.append(child['id'])
    assert child['caref'] == root['refid']
    return {'root': root, 'root_cn': root_cn, 'root_key': root_key, 'child': child, 'cn': cn, 'key': key}


def _with_csr(app, ca_id):
    """An outstanding renewal request: the next import of its certificate goes through the install path."""
    with app.app_context():
        db.session.get(CA, ca_id).csr = base64.b64encode(b'outstanding').decode()
        db.session.commit()


ROUTES = ['/api/v2/cas/import', '/api/v2/certificates/import', 'install']


def _replace(app, auth_client, w, pem, route):
    if route == 'install':
        _with_csr(app, w['child']['id'])
        route = '/api/v2/cas/import'
    data = _import(auth_client, pem, route=route, cross_mode='replace')
    assert data['id'] == w['child']['id']
    return data


# ------------------------------------------------- another issuer

@pytest.mark.parametrize('route', ROUTES)
def test_a_certificate_from_an_issuer_ucm_does_not_hold_unlinks_the_old_parent(app, auth_client, linked, route):
    w = linked
    before = _audits(app, UNLINKED, w['child']['id'])
    _replace(app, auth_client, w, _rsa_pem(w['cn'], w['key'], f'Elsewhere {_tag()}', _key(), serial=_serial()), route)
    assert _caref(app, w['child']['id']) is None
    assert _audits(app, UNLINKED, w['child']['id']) == before + 1
    # The chain served no longer carries the root that does not sign this certificate
    exported = auth_client.get(f"/api/v2/cas/{w['child']['id']}/export?format=pem&include_chain=true")
    assert exported.status_code == 200, exported.data
    assert _stored_pem(app, w['root']['id']) not in exported.data


@pytest.mark.parametrize('route', ROUTES)
def test_a_certificate_from_a_stored_unverifiable_issuer_is_proposed_for_confirmation(
        app, auth_client, made, linked, route):
    w, tag, ski = linked, _tag(), uuid.uuid4().bytes
    gost = _import(auth_client, _gost_pem(f'Gost Repl {tag}', serial=_serial(), ski=ski))
    made.append(gost['id'])
    _replace(app, auth_client, w, _gost_pem(w['cn'], f'Gost Repl {tag}', serial=_serial(), aki=ski, key=w['key']),
             route)
    shown = get_json(auth_client.get(f"/api/v2/cas/{w['child']['id']}"))['data']
    assert shown['caref'] is None
    assert shown['parent_candidate']['id'] == gost['id']


@pytest.mark.parametrize('route', ROUTES)
def test_a_certificate_from_another_stored_verifiable_issuer_relinks_to_it(app, auth_client, made, linked, route):
    w, other_key, other_cn = linked, _key(), f'Repl Other {_tag()}'
    other = _import(auth_client, _rsa_pem(other_cn, other_key, serial=_serial()))
    made.append(other['id'])
    before = _audits(app, UNLINKED, w['child']['id'])
    _replace(app, auth_client, w, _rsa_pem(w['cn'], w['key'], other_cn, other_key, serial=_serial()), route)
    assert _caref(app, w['child']['id']) == other['refid']
    assert _audits(app, UNLINKED, w['child']['id']) == before + 1


# ------------------------------------------------- the same issuer

@pytest.mark.parametrize('route', ROUTES)
def test_a_renewal_by_the_same_parent_keeps_the_link(app, auth_client, linked, route):
    w = linked
    before = _audits(app, UNLINKED, w['child']['id'])
    _replace(app, auth_client, w, _rsa_pem(w['cn'], w['key'], w['root_cn'], w['root_key'], serial=_serial()), route)
    assert _caref(app, w['child']['id']) == w['root']['refid']
    assert _audits(app, UNLINKED, w['child']['id']) == before


def test_a_renewal_by_the_parent_under_its_new_key_keeps_the_link(app, auth_client, linked):
    w, new_root_key = linked, _key()
    rekeyed = _import(auth_client, _rsa_pem(w['root_cn'], new_root_key, serial=_serial()), cross_mode='replace')
    assert rekeyed['id'] == w['root']['id']
    _import(auth_client, _rsa_pem(w['cn'], w['key'], w['root_cn'], new_root_key, serial=_serial()),
            cross_mode='replace')
    assert _caref(app, w['child']['id']) == w['root']['refid']


# ------------------------------------------------- one verification for every path (P3-2)

def _aki_pem(cn, key, issuer_cn, signer, signer_ski):
    name = lambda v: x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, v)])  # noqa: E731
    cert = (x509.CertificateBuilder().subject_name(name(cn)).issuer_name(name(issuer_cn))
            .public_key(key.public_key()).serial_number(_serial())
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2036, 1, 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.AuthorityKeyIdentifier(signer_ski, None, None), critical=False)
            .sign(signer, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.mark.parametrize('route', ['/api/v2/cas/import', 'install'])
def test_an_issuer_name_differing_by_case_links_on_every_path(app, auth_client, linked, route):
    """RFC 5280 7.1 compares names caselessly: the install path links what the import links."""
    w = linked
    root_cert = x509.load_pem_x509_certificate(_stored_pem(app, w['root']['id']))
    ski = x509.SubjectKeyIdentifier.from_public_key(root_cert.public_key()).digest
    with app.app_context():
        db.session.get(CA, w['root']['id']).ski = ski.hex(':').upper()
        db.session.commit()
    data = _replace(app, auth_client, w, _aki_pem(w['cn'], w['key'], w['root_cn'].upper(), w['root_key'], ski), route)
    assert _caref(app, w['child']['id']) == w['root']['refid']
    assert not [m for m in data.get('warnings', []) if 'verification failed' in m]


# ------------------------------------------------- the hourly chain repair

def test_the_chain_repair_drops_a_link_the_signature_disproves_and_relinks(app, auth_client, made, linked):
    from services.ski_aki_backfill import backfill_ski_aki
    w, stray_key = linked, _key()
    stray = _import(auth_client, _rsa_pem(f'Repl Stray {_tag()}', stray_key, serial=_serial()))
    made.append(stray['id'])
    with app.app_context():
        db.session.get(CA, w['child']['id']).caref = stray['refid']  # a link left by an earlier version
        db.session.commit()
    before = _audits(app, UNLINKED, w['child']['id'])
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, w['child']['id']) == w['root']['refid']
    assert _audits(app, UNLINKED, w['child']['id']) == before + 1


def test_the_chain_repair_keeps_a_link_it_cannot_check(app, auth_client, made):
    from services.ski_aki_backfill import backfill_ski_aki
    tag, ski = _tag(), uuid.uuid4().bytes
    gost = _import(auth_client, _gost_pem(f'Gost Keep {tag}', serial=_serial(), ski=ski))
    made.append(gost['id'])
    child = _import(auth_client, _gost_pem(f'Gost Keep Child {tag}', f'Gost Keep {tag}', serial=_serial(), aki=ski))
    made.append(child['id'])
    with app.app_context():
        db.session.get(CA, child['id']).caref = gost['refid']  # linked by name by an earlier version
        db.session.commit()
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, child['id']) == gost['refid']
