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


def _key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


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


def test_a_renewal_whose_key_identifier_names_another_stored_key_keeps_the_verified_parent(
        app, auth_client, made, linked):
    """The AKI only names a key: the former parent stays because its key still verifies the signature."""
    w, stray_key = linked, _key()
    stray_cn = f'Repl Named {_tag()}'
    stray = _import(auth_client, _rsa_pem(stray_cn, stray_key, serial=_serial()))
    made.append(stray['id'])
    ski = x509.SubjectKeyIdentifier.from_public_key(stray_key.public_key()).digest
    with app.app_context():
        db.session.get(CA, stray['id']).ski = ski.hex(':').upper()
        db.session.commit()
    _import(auth_client, _aki_pem(w['cn'], w['key'], w['root_cn'], w['root_key'], ski), cross_mode='replace')
    assert _caref(app, w['child']['id']) == w['root']['refid']


def _ed_pem(cn, key, issuer_cn=None, signer=None):
    name = lambda v: x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, v)])  # noqa: E731
    cert = (x509.CertificateBuilder().subject_name(name(cn)).issuer_name(name(issuer_cn or cn))
            .public_key(key.public_key()).serial_number(_serial())
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2036, 1, 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key((signer or key).public_key()),
                           critical=False)
            .sign(signer or key, None))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_the_chain_repair_keeps_a_link_when_the_provider_fails(app, auth_client, made, monkeypatch):
    """A verification that errors (a provider refusing the algorithm) proves nothing: no unlink, no audit."""
    from services.ski_aki_backfill import backfill_ski_aki
    from tests.fixtures.cross_pki import make_cert, pem
    from utils import cert_issuer
    tag, root_key = _tag(), _key()
    root = _import(auth_client, pem(make_cert(f'Fail Root {tag}', root_key)))
    made.append(root['id'])
    child = _import(auth_client, pem(make_cert(f'Fail Child {tag}', _key(), f'Fail Root {tag}', root_key)))
    made.append(child['id'])
    assert child['caref'] == root['refid']

    def failing(cert, key):
        raise RuntimeError('provider refused the operation')
    monkeypatch.setattr(cert_issuer, 'verify_certificate_signature', failing)
    before = _audits(app, UNLINKED, child['id'])
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, child['id']) == root['refid']
    assert _audits(app, UNLINKED, child['id']) == before


def _kid_pem(cn, key, issuer_cn, signer, named_key):
    """A CA certificate signed by *signer* whose AKI names *named_key* (the signer's, or another for a bad signature)."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    name = lambda v: x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, v)])  # noqa: E731
    cert = (x509.CertificateBuilder().subject_name(name(cn)).issuer_name(name(issuer_cn))
            .public_key(key.public_key()).serial_number(_serial())
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2036, 1, 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(named_key.public_key()),
                           critical=False)
            .sign(signer, None if isinstance(signer, ed25519.Ed25519PrivateKey) else hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _fips_root_and_child(app, auth_client, made, kind, genuine):
    """A root of *kind* and a CA linked under it, signed by the root's key when *genuine*, else by another."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    gen = {'ed25519': ed25519.Ed25519PrivateKey.generate, 'rsa-2048': _key,
           'rsa-1024': lambda: rsa.generate_private_key(65537, 1024)}[kind]
    tag, root_key, key = _tag(), gen(), _key()
    root_cn = f'Fips Root {tag}'
    root = _import(auth_client, _kid_pem(root_cn, root_key, root_cn, root_key, root_key))
    made.append(root['id'])
    child = _import(auth_client, _kid_pem(f'Fips Child {tag}', key, root_cn, root_key if genuine else gen(), root_key))
    made.append(child['id'])
    with app.app_context():
        db.session.get(CA, child['id']).caref = root['refid']  # linked by name by an earlier version
        db.session.commit()
    return root, child


@pytest.mark.parametrize('kind,genuine,kept', [
    ('ed25519', True, True),    # the module refuses Ed25519 and rejects a good signature: no proof
    ('rsa-1024', True, True),   # the module refuses a modulus under 2048 bits the same way
    ('ed25519', False, False),  # a module approving Ed25519: a bad signature is one
    ('rsa-2048', False, False),
])
def test_the_chain_repair_trusts_a_bad_signature_only_from_a_module_that_approves_the_key(
        app, auth_client, made, monkeypatch, kind, genuine, kept):
    """In FIPS mode the module answers 'invalid' for a key it does not approve: that is no proof."""
    import fips_mode
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from services.ski_aki_backfill import backfill_ski_aki
    from utils import cert_issuer
    root, child = _fips_root_and_child(app, auth_client, made, kind, genuine)
    approves_ed25519 = kind != 'ed25519' or not genuine
    real = cert_issuer.verify_certificate_signature

    def module(cert, public_key):
        if isinstance(public_key, ed25519.Ed25519PublicKey) and not approves_ed25519 or \
                isinstance(public_key, rsa.RSAPublicKey) and public_key.key_size < 2048:
            raise InvalidSignature()
        return real(cert, public_key)
    monkeypatch.setattr(cert_issuer, 'verify_certificate_signature', module)
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(fips_mode, 'module_approves', lambda algorithm: approves_ed25519)
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, child['id']) == (root['refid'] if kept else None)


# ------------------------------------------------- name chaining (RFC 5280 6.1.3(a)(4))

def _with_ski(app, ca_ids, ski):
    with app.app_context():
        for ca_id in ca_ids:
            db.session.get(CA, ca_id).ski = ski.hex(':').upper()
        db.session.commit()


@pytest.mark.parametrize('route', ['/api/v2/cas/import', 'install'])
def test_the_key_alone_does_not_pick_a_parent_of_another_name(app, auth_client, made, linked, route):
    """Two records of one key under two names: the parent is the one the issuer name designates."""
    w, renamed_cn = linked, f'Repl Renamed {_tag()}'
    renamed = _import(auth_client, _rsa_pem(renamed_cn, w['root_key'], serial=_serial()))
    made.append(renamed['id'])
    ski = x509.SubjectKeyIdentifier.from_public_key(w['root_key'].public_key()).digest
    _with_ski(app, [w['root']['id'], renamed['id']], ski)
    _replace(app, auth_client, w, _aki_pem(w['cn'], w['key'], renamed_cn, w['root_key'], ski), route)
    assert _caref(app, w['child']['id']) == renamed['refid']
    exported = auth_client.get(f"/api/v2/cas/{w['child']['id']}/export?format=pem&include_chain=true")
    assert _stored_pem(app, w['root']['id']) not in exported.data


@pytest.mark.parametrize('route', ['/api/v2/cas/import', 'install'])
def test_the_former_parent_is_dropped_when_the_issuer_name_changes(app, auth_client, linked, route):
    """The former parent's key still verifies, but the certificate names another issuer."""
    w = linked
    _replace(app, auth_client, w, _rsa_pem(w['cn'], w['key'], f'Repl Nowhere {_tag()}', w['root_key'],
                                           serial=_serial()), route)
    assert _caref(app, w['child']['id']) is None


@pytest.mark.parametrize('route', ['/api/v2/cas/import', 'install'])
def test_the_issuer_name_is_searched_when_no_key_identifier_candidate_is_retained(
        app, auth_client, made, linked, route):
    """The AKI names only a record of another name: the record of the issuer name and key still links."""
    w, renamed_cn = linked, f'Repl Alias {_tag()}'
    renamed = _import(auth_client, _rsa_pem(renamed_cn, w['root_key'], serial=_serial()))
    made.append(renamed['id'])
    ski = x509.SubjectKeyIdentifier.from_public_key(w['root_key'].public_key()).digest
    _with_ski(app, [renamed['id']], ski)
    with app.app_context():
        db.session.get(CA, w['root']['id']).ski = None  # the homonym of the issuer name, stored without a SKI
        db.session.get(CA, w['child']['id']).caref = None
        db.session.commit()
    _replace(app, auth_client, w, _aki_pem(w['cn'], w['key'], w['root_cn'], w['root_key'], ski), route)
    assert _caref(app, w['child']['id']) == w['root']['refid']


def test_a_move_to_the_root_record_of_the_same_key_is_not_audited_as_a_dropped_parent(app, auth_client, made):
    """Linked to the record of a cross-certificate of its issuer, a renewal moves the CA to the
    self-signed record of that key: the former parent still verifies it, so nothing is dropped."""
    from tests.fixtures.cross_pki import make_cert, pem
    from tests.test_cross_repair import _world
    pki, ids = _world(app)
    made.extend(ids.values())
    before = _audits(app, UNLINKED, ids['i'])
    renewed = make_cert(f'Cross Int B {pki.tag}', pki.key_int, pki.name_b, pki.key_b, days=300, path_length=0)
    assert _import(auth_client, pem(renewed), cross_mode='replace')['id'] == ids['i']
    with app.app_context():
        assert db.session.get(CA, ids['i']).caref == db.session.get(CA, ids['b']).refid
    assert _audits(app, UNLINKED, ids['i']) == before


# ------------------------------------------------- the chain repair and a re-keyed parent

@pytest.fixture
def rekeyed(app, auth_client, made):
    """A root re-keyed in place (its new certificate imported over it) and a CA its former key signed."""
    from tests.fixtures.cross_pki import make_cert, pem
    tag, old_key, key = _tag(), _key(), _key()
    root_cn, cn = f'Rekey Root {tag}', f'Rekey Child {tag}'
    root = _import(auth_client, pem(make_cert(root_cn, old_key)))
    made.append(root['id'])
    # The CA holds its key: the install path checks the certificate against it
    child = _import(auth_client, pem(make_cert(cn, key, root_cn, old_key)) + _key_pem(key))
    made.append(child['id'])
    assert child['caref'] == root['refid']
    assert _import(auth_client, pem(make_cert(root_cn, _key())), cross_mode='replace')['id'] == root['id']
    return root, child


def _revoke_by_flag(app, ca_id):
    """Revoked as a restore without the parent's revocation record leaves it: the flag alone."""
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca.revoked, ca.revoked_at, ca.revoke_reason = True, dt.datetime(2026, 2, 1), 'keyCompromise'
        db.session.commit()


def _on_crl_of(app, parent_id, child_id):
    from services.crl import CRLService
    with app.app_context():
        serial = db.session.get(CA, child_id).serial_number
        return any(str(getattr(r, 'serial_number', '')) == serial
                   for r in CRLService.get_revoked_certificates(parent_id))


def test_the_chain_repair_keeps_a_ca_signed_by_the_former_key_of_its_parent(app, auth_client, rekeyed):
    """Its AKI names the former key: the bad signature under the new one proves nothing, and the
    revocation names the re-keyed issuer."""
    from services.ca_service import CAService
    from services.ski_aki_backfill import backfill_ski_aki
    root, child = rekeyed
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, child['id']) == root['refid']
    with app.app_context(), pytest.raises(ValueError, match='re-keyed or replaced'):
        CAService.revocation_issuer(db.session.get(CA, child['id']))


def test_the_chain_repair_keeps_a_revoked_ca_on_the_crl_of_its_re_keyed_parent(app, auth_client, rekeyed):
    from services.ski_aki_backfill import backfill_ski_aki
    root, child = rekeyed
    _revoke_by_flag(app, child['id'])
    assert _on_crl_of(app, root['id'], child['id'])
    with app.app_context():
        backfill_ski_aki()
    assert _on_crl_of(app, root['id'], child['id'])
    assert _caref(app, child['id']) == root['refid']


def test_the_chain_repair_keeps_the_link_of_a_revoked_ca_under_another_name(app, auth_client, made, linked):
    """A wrong link of a revoked CA is what lists it on a CRL: the repair leaves it."""
    from services.ski_aki_backfill import backfill_ski_aki
    w = linked
    stray = _import(auth_client, _rsa_pem(f'Repl Stray {_tag()}', _key(), serial=_serial()))
    made.append(stray['id'])
    with app.app_context():
        db.session.get(CA, w['child']['id']).caref = stray['refid']  # a link left by an earlier version
        db.session.commit()
    _revoke_by_flag(app, w['child']['id'])
    with app.app_context():
        backfill_ski_aki()
    assert _on_crl_of(app, stray['id'], w['child']['id'])
    assert _caref(app, w['child']['id']) == stray['refid']


# ------------------------------------------------- one rule for the repair and a certificate change

SETTLE_ROUTES = ['/api/v2/cas/import', '/api/v2/certificates/import', 'install']


def _reimport(app, auth_client, ca_id, pem, route):
    if route == 'install':
        _with_csr(app, ca_id)
        route = '/api/v2/cas/import'
    assert _import(auth_client, pem, route=route, cross_mode='replace')['id'] == ca_id


@pytest.mark.parametrize('route', SETTLE_ROUTES)
@pytest.mark.parametrize('revoked', [True, False])
def test_the_same_certificate_imported_again_keeps_the_link_to_a_re_keyed_parent(
        app, auth_client, rekeyed, route, revoked):
    """The AKI names the former key: nothing disproves the parent, and a revoked CA stays on its CRL."""
    root, child = rekeyed
    if revoked:
        _revoke_by_flag(app, child['id'])
    before = _audits(app, UNLINKED, child['id'])
    _reimport(app, auth_client, child['id'], _stored_pem(app, child['id']).decode(), route)
    assert _caref(app, child['id']) == root['refid']
    assert _audits(app, UNLINKED, child['id']) == before
    assert _on_crl_of(app, root['id'], child['id']) is revoked


@pytest.mark.parametrize('route', ROUTES)
def test_a_new_serial_is_not_the_revoked_ca_and_follows_the_rule_of_every_certificate(
        app, auth_client, made, linked, route):
    """Revocation is per certificate (RFC 5280 5.3): a new one moves under the CA whose key verifies it."""
    w = linked
    stray = _import(auth_client, _rsa_pem(f'Repl Stray {_tag()}', _key(), serial=_serial()))
    made.append(stray['id'])
    with app.app_context():
        db.session.get(CA, w['child']['id']).caref = stray['refid']  # a link left by an earlier version
        db.session.commit()
    _revoke_by_flag(app, w['child']['id'])
    _replace(app, auth_client, w, _rsa_pem(w['cn'], w['key'], w['root_cn'], w['root_key'], serial=_serial()), route)
    assert _caref(app, w['child']['id']) == w['root']['refid']


def _case_re_keyed(app, auth_client, made):
    from tests.fixtures.cross_pki import make_cert, pem
    tag, old_key = _tag(), _key()
    root = _import(auth_client, pem(make_cert(f'Tbl Rekey {tag}', old_key)))
    made.append(root['id'])
    child = _import(auth_client, pem(make_cert(f'Tbl Rekey Child {tag}', _key(), f'Tbl Rekey {tag}', old_key)))
    made.append(child['id'])
    _import(auth_client, pem(make_cert(f'Tbl Rekey {tag}', _key())), cross_mode='replace')
    return child['id'], root['refid']


def _case_other_name(app, auth_client, made):
    tag, root_key = _tag(), _key()
    root = _import(auth_client, _rsa_pem(f'Tbl Root {tag}', root_key, serial=_serial()))
    stray = _import(auth_client, _rsa_pem(f'Tbl Stray {tag}', _key(), serial=_serial()))
    child = _import(auth_client, _rsa_pem(f'Tbl Child {tag}', _key(), f'Tbl Root {tag}', root_key, serial=_serial()))
    made.extend([root['id'], stray['id'], child['id']])
    return child['id'], stray['refid']


def _case_named_key_disproves(app, auth_client, made, *, aki=True):
    tag, root_key = _tag(), _key()
    root_cn = f'Tbl Named {tag}'
    root = _import(auth_client, _kid_pem(root_cn, root_key, root_cn, root_key, root_key))
    made.append(root['id'])
    if aki:
        pem = _kid_pem(f'Tbl Named Child {tag}', _key(), root_cn, _key(), root_key)
    else:
        pem = _rsa_pem(f'Tbl Named Child {tag}', _key(), root_cn, _key(), serial=_serial())
    child = _import(auth_client, pem)
    made.append(child['id'])
    return child['id'], root['refid']


def _case_unverifiable(app, auth_client, made):
    tag, ski = _tag(), uuid.uuid4().bytes
    gost = _import(auth_client, _gost_pem(f'Tbl Gost {tag}', serial=_serial(), ski=ski))
    made.append(gost['id'])
    child = _import(auth_client, _gost_pem(f'Tbl Gost Child {tag}', f'Tbl Gost {tag}', serial=_serial(), aki=ski))
    made.append(child['id'])
    return child['id'], gost['refid']


CASES = {
    're-keyed parent': (_case_re_keyed, True),
    'parent of another name': (_case_other_name, False),
    'bad signature under the named key': (_case_named_key_disproves, False),
    'bad signature without a key identifier': (lambda *a: _case_named_key_disproves(*a, aki=False), True),
    'signature not verifiable here': (_case_unverifiable, True),
}


def _link_kept(app, auth_client, made, case, revoked, path):
    from services.ski_aki_backfill import backfill_ski_aki
    child_id, parent_refid = CASES[case][0](app, auth_client, made)
    with app.app_context():
        db.session.get(CA, child_id).caref = parent_refid  # a link left by an earlier version
        db.session.commit()
    if revoked:
        _revoke_by_flag(app, child_id)
    if path == 'chain repair':
        with app.app_context():
            backfill_ski_aki()
    else:
        _reimport(app, auth_client, child_id, _stored_pem(app, child_id).decode(), '/api/v2/cas/import')
    return _caref(app, child_id) == parent_refid


@pytest.mark.parametrize('revoked', [False, True])
@pytest.mark.parametrize('case', sorted(CASES))
def test_the_chain_repair_and_a_certificate_change_keep_or_drop_the_same_links(
        app, auth_client, made, case, revoked):
    """Both paths ask one question, may this parent be removed: a revoked CA never loses it."""
    expected = revoked or CASES[case][1]
    kept = {path: _link_kept(app, auth_client, made, case, revoked, path)
            for path in ('chain repair', 'certificate change')}
    assert kept == {'chain repair': expected, 'certificate change': expected}


# ------------------------------------------------- a parent of another name left by an earlier version

def _last_unlinked(app, ca_id):
    from models.audit_log import AuditLog
    with app.app_context():
        row = AuditLog.query.filter_by(action=UNLINKED, resource_type='ca', resource_id=str(ca_id)) \
            .order_by(AuditLog.id.desc()).first()
        return row.details if row else None


@pytest.mark.parametrize('when', ['chain repair', 'certificate change'])
def test_a_parent_of_another_name_linked_by_an_earlier_version_is_dropped(app, auth_client, made, linked, when):
    """Its key verifies the certificate, but its subject is not the issuer name (RFC 5280 6.1.3 (a)(4))."""
    from services.ski_aki_backfill import backfill_ski_aki
    w, renamed_cn = linked, f'Repl Other Name {_tag()}'
    renamed = _import(auth_client, _rsa_pem(renamed_cn, w['root_key'], serial=_serial()))
    made.append(renamed['id'])
    with app.app_context():
        db.session.get(CA, w['child']['id']).caref = renamed['refid']
        db.session.commit()
    before = _audits(app, UNLINKED, w['child']['id'])
    if when == 'chain repair':
        with app.app_context():
            backfill_ski_aki()
    else:
        # The AKI names the key the record of the other name is stored under
        ski = x509.SubjectKeyIdentifier.from_public_key(w['root_key'].public_key()).digest
        _with_ski(app, [renamed['id']], ski)
        _replace(app, auth_client, w, _aki_pem(w['cn'], w['key'], w['root_cn'], w['root_key'], ski),
                 '/api/v2/cas/import')
    assert _caref(app, w['child']['id']) == w['root']['refid']
    assert _audits(app, UNLINKED, w['child']['id']) == before + 1
    assert 'its subject is not the issuer name' in _last_unlinked(app, w['child']['id'])


@pytest.mark.parametrize('parent_kind', ['rsa', 'ec'])
def test_the_chain_repair_drops_a_parent_whose_key_type_cannot_have_made_the_signature(
        app, auth_client, made, parent_kind):
    """An Ed25519 signature is not made by an RSA or EC key (RFC 5280 4.1.1.2): the types prove it."""
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    from services.ski_aki_backfill import backfill_ski_aki
    tag = _tag()
    root_key = _key() if parent_kind == 'rsa' else ec.generate_private_key(ec.SECP256R1())
    root_cn = f'Type Root {tag}'
    root = _import(auth_client, _kid_pem(root_cn, root_key, root_cn, root_key, root_key))
    made.append(root['id'])
    child = _import(auth_client, _kid_pem(f'Type Child {tag}', _key(), root_cn,
                                          ed25519.Ed25519PrivateKey.generate(), root_key))
    made.append(child['id'])
    with app.app_context():
        db.session.get(CA, child['id']).caref = root['refid']  # linked by name by an earlier version
        db.session.commit()
    before = _audits(app, UNLINKED, child['id'])
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, child['id']) is None
    assert _audits(app, UNLINKED, child['id']) == before + 1


# ------------------------------------------------- what an installed certificate warns

def test_an_installed_certificate_whose_issuer_name_ucm_does_not_hold_says_so(app, auth_client, linked):
    """The AKI names a stored key under another name: that record is no issuer (RFC 5280 6.1.3 (a)(4))."""
    w = linked
    ski = x509.SubjectKeyIdentifier.from_public_key(w['root_key'].public_key()).digest
    _with_ski(app, [w['root']['id']], ski)
    data = _replace(app, auth_client, w, _aki_pem(w['cn'], w['key'], f'Repl Nowhere {_tag()}', w['root_key'], ski),
                    'install')
    assert _caref(app, w['child']['id']) is None
    assert [m for m in data['warnings'] if m.startswith('Issuing CA not found in UCM')]
    assert not [m for m in data['warnings'] if 'verification failed' in m]


@pytest.mark.parametrize('revoked', [False, True])
def test_a_subject_change_on_install_warns_that_the_cas_issued_under_the_former_one_lose_it(
        app, auth_client, made, linked, revoked):
    """Their issuer name no longer is its subject (RFC 5280 6.1.3 (a)(4)): the chain repair drops the link."""
    from services.ski_aki_backfill import backfill_ski_aki
    w = linked
    sub = _import(auth_client, _rsa_pem(f'Repl Sub {_tag()}', _key(), w['cn'], w['key'], serial=_serial()))
    made.append(sub['id'])
    assert sub['caref'] == w['child']['refid']
    if revoked:
        _revoke_by_flag(app, sub['id'])
    r = auth_client.post(f"/api/v2/cas/{w['child']['id']}/certificate", content_type='multipart/form-data', data={
        'pem_content': _rsa_pem(f"{w['cn']} Renamed", w['key'], w['root_cn'], w['root_key'], serial=_serial())})
    assert r.status_code == 200, r.data
    said = [m for m in get_json(r)['data']['warnings'] if m.startswith('Certificate subject differs')]
    assert len(said) == 1
    assert ('lose this CA as their parent at the next chain repair' in said[0]) is not revoked
    with app.app_context():
        backfill_ski_aki()
    assert (_caref(app, sub['id']) == w['child']['refid']) is revoked


# ------------------------------------------------- a parent whose extensions cannot be read

def _root_pem(cn, key):
    name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(_serial())
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2036, 1, 1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _with_duplicate_extension(app, ca_id):
    """The stored certificate still loads, but its KeyUsage OID is the SKI's: its extensions do not read."""
    import ssl
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        der = x509.load_pem_x509_certificate(base64.b64decode(ca.crt)).public_bytes(serialization.Encoding.DER)
        key_usage, ski = bytes.fromhex('0603551d0f'), bytes.fromhex('0603551d0e')
        assert der.count(key_usage) == 1
        bad = der.replace(key_usage, ski)
        with pytest.raises(x509.DuplicateExtension):
            x509.load_der_x509_certificate(bad).extensions
        ca.crt = base64.b64encode(ssl.DER_cert_to_PEM_cert(bad).encode()).decode()
        db.session.commit()


@pytest.fixture
def unreadable(app, auth_client, made):
    """A CA linked under a root whose stored certificate has unreadable extensions."""
    tag, root_key, key = _tag(), _key(), _key()
    root_cn = f'Dup Root {tag}'
    root = _import(auth_client, _root_pem(root_cn, root_key))
    made.append(root['id'])
    child = _import(auth_client, _rsa_pem(f'Dup Child {tag}', key, root_cn, root_key, serial=_serial()) + _key_pem(key))
    made.append(child['id'])
    assert child['caref'] == root['refid']
    _with_duplicate_extension(app, root['id'])
    return root, child


def test_the_chain_repair_goes_on_past_a_parent_whose_extensions_cannot_be_read(app, auth_client, made, unreadable):
    """Nothing proves the link wrong: it stays, and the orphans after it are still rechained."""
    from services.ski_aki_backfill import backfill_ski_aki
    root, child = unreadable
    w = {}
    other_key, other_cn = _key(), f'Dup Other {_tag()}'
    w['other'] = _import(auth_client, _root_pem(other_cn, other_key))
    made.append(w['other']['id'])
    orphan = _import(auth_client, _aki_pem(f'Dup Orphan {_tag()}', _key(), other_cn, other_key,
                                           x509.SubjectKeyIdentifier.from_public_key(other_key.public_key()).digest))
    made.append(orphan['id'])
    with app.app_context():
        db.session.get(CA, orphan['id']).caref = None
        db.session.commit()
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, child['id']) == root['refid']
    assert _caref(app, orphan['id']) == w['other']['refid']


def test_the_chain_repair_logs_a_ca_it_cannot_settle_and_goes_on(app, auth_client, made, linked, monkeypatch):
    from services.ca import parent_confirmation
    from services.ski_aki_backfill import backfill_ski_aki
    w, other_key, other_cn = linked, _key(), f'Dup Other {_tag()}'
    other = _import(auth_client, _root_pem(other_cn, other_key))
    made.append(other['id'])
    orphan = _import(auth_client, _aki_pem(f'Dup Orphan {_tag()}', _key(), other_cn, other_key,
                                           x509.SubjectKeyIdentifier.from_public_key(other_key.public_key()).digest))
    made.append(orphan['id'])
    with app.app_context():
        db.session.get(CA, orphan['id']).caref = None
        db.session.commit()
    real = parent_confirmation.may_drop_parent

    def failing(ca, cert, parent):
        if ca.id == w['child']['id']:
            raise ValueError('unreadable')
        return real(ca, cert, parent)
    monkeypatch.setattr(parent_confirmation, 'may_drop_parent', failing)
    with app.app_context():
        backfill_ski_aki()
    assert _caref(app, w['child']['id']) == w['root']['refid']
    assert _caref(app, orphan['id']) == other['refid']


@pytest.mark.parametrize('route', SETTLE_ROUTES)
def test_the_same_certificate_imported_again_keeps_a_parent_whose_extensions_cannot_be_read(
        app, auth_client, unreadable, route):
    root, child = unreadable
    _reimport(app, auth_client, child['id'], _stored_pem(app, child['id']).decode(), route)
    assert _caref(app, child['id']) == root['refid']
    assert auth_client.get(f"/api/v2/cas/{child['id']}").status_code == 200

