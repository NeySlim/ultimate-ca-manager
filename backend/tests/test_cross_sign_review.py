"""Cross-signing review fixes: revoked subjects, copied constraints, SKI, rollover, notices, degenerate pairs."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from models.policy import CertificatePolicy
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import key_pem, new_key, openssl_verify, pem
from tests.test_cross_sign import _cert_of, _sign
from utils.key_codec import store_pem_bytes


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _mk(cn, key, issuer_cn=None, issuer_key=None, *, ca=True, days=365, path_length=None, extras=(),
        ski=None, aki=None, san=None):
    now = datetime.now(timezone.utc)
    signer = issuer_key or key
    b = (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(_name(issuer_cn or cn))
         .public_key(key.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=path_length if ca else None), critical=True)
         .add_extension(ski or x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
         .add_extension(aki or x509.AuthorityKeyIdentifier.from_issuer_public_key(signer.public_key()),
                        critical=False))
    if ca:
        b = b.add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
    else:
        b = b.add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
    if san:
        b = b.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    for ext, critical in extras:
        b = b.add_extension(ext, critical=critical)
    return b.sign(signer, hashes.SHA256())


def _import(app, certs, keyed=()):
    """Import *certs* (PEM objects); *keyed* maps a description to the key to attach. Returns {descr: id}."""
    ids = {}
    with app.app_context():
        for cert in certs:
            SmartImporter().execute(pem(cert))
        for cert in certs:
            cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            for ca in CA.query.filter_by(descr=cn).all():
                ids.setdefault(cn, []).append(ca.id)
        for cn, key in keyed:
            for ca_id in ids[cn]:
                db.session.get(CA, ca_id).prv = store_pem_bytes(key_pem(key).encode())
        db.session.commit()
    return ids


def _tag():
    return uuid.uuid4().hex[:8]


def test_revoked_subject_cannot_be_cross_signed(app, auth_client):
    tag, ka, kb = _tag(), new_key(), new_key()
    ids = _import(app, [_mk(f'RA {tag}', ka), _mk(f'RB {tag}', kb)], keyed=[(f'RA {tag}', ka)])
    a, b = ids[f'RA {tag}'][0], ids[f'RB {tag}'][0]
    with app.app_context():
        db.session.get(CA, b).revoked = True
        db.session.commit()
    r = _sign(auth_client, a, b)
    assert r.status_code == 409 and r.get_json()['details']['code'] == 'subject_revoked'
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 0


def test_subject_constraints_are_copied_into_the_cross_certificate(app, auth_client):
    tag, ka, kb, ki, kl, ke = _tag(), new_key(), new_key(), new_key(), new_key(), new_key()
    nc = x509.NameConstraints(permitted_subtrees=[x509.DNSName('good.example')], excluded_subtrees=None)
    eku = x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION])
    root_b = _mk(f'RB {tag}', kb, extras=[(nc, True), (eku, False)])
    int_b = _mk(f'IB {tag}', ki, f'RB {tag}', kb, path_length=0)
    good = _mk(f'good.good.example', kl, f'IB {tag}', ki, ca=False, san='good.good.example')
    evil = _mk('evil.example.org', ke, f'IB {tag}', ki, ca=False, san=f'evil-{tag}.org')
    ids = _import(app, [_mk(f'RA {tag}', ka), root_b, int_b], keyed=[(f'RA {tag}', ka)])
    ok, out = openssl_verify(evil, [root_b], untrusted=[int_b])
    assert not ok, 'precondition: B alone refuses the evil name'
    r = _sign(auth_client, ids[f'RA {tag}'][0], ids[f'RB {tag}'][0])
    assert r.status_code == 201, r.data
    cross = _cert_of(r)
    got = cross.extensions.get_extension_for_class(x509.NameConstraints)
    assert got.critical and [g.value for g in got.value.permitted_subtrees] == ['good.example']
    assert cross.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value == eku
    root_a = x509.load_pem_x509_certificate(
        db_pem(app, ids[f'RA {tag}'][0]))
    ok, out = openssl_verify(evil, [root_a], untrusted=[int_b, cross])
    assert not ok, out
    ok, out = openssl_verify(good, [root_a], untrusted=[int_b, cross])
    assert ok, out


def db_pem(app, ca_id):
    import base64
    with app.app_context():
        return base64.b64decode(db.session.get(CA, ca_id).crt)


def test_cross_certificate_keeps_the_subject_key_identifier(app, auth_client):
    tag, ka, kb, ki = _tag(), new_key(), new_key(), new_key()
    odd = x509.SubjectKeyIdentifier(os.urandom(20))
    root_a, root_b = _mk(f'RA {tag}', ka), _mk(f'RB {tag}', kb, ski=odd, aki=x509.AuthorityKeyIdentifier(odd.digest, None, None))
    int_b = _mk(f'IB {tag}', ki, f'RB {tag}', kb, path_length=0, aki=x509.AuthorityKeyIdentifier(odd.digest, None, None))
    leaf = _mk(f'l-{tag}.example', new_key(), f'IB {tag}', ki, ca=False, san=f'l-{tag}.example',
               aki=x509.AuthorityKeyIdentifier.from_issuer_public_key(ki.public_key()))
    ids = _import(app, [root_a, root_b, int_b], keyed=[(f'RA {tag}', ka)])
    ok, out = openssl_verify(leaf, [root_b], untrusted=[int_b])
    assert ok, out
    r = _sign(auth_client, ids[f'RA {tag}'][0], ids[f'RB {tag}'][0])
    assert r.status_code == 201, r.data
    cross = _cert_of(r)
    assert cross.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value == odd
    ok, out = openssl_verify(leaf, [root_a], untrusted=[int_b, cross])
    assert ok, out


def test_key_rollover_cross_certificate_carries_an_authority_key_identifier(app, auth_client):
    tag, k_old, k_new = _tag(), new_key(), new_key()
    name = f'Rollover {tag}'
    old, new = _mk(name, k_old), _mk(name, k_new)
    leaf = _mk(f'l-{tag}.example', new_key(), name, k_new, ca=False, san=f'l-{tag}.example')
    with app.app_context():
        for cert in (old, new):
            SmartImporter().execute(pem(cert))
        rows = CA.query.filter_by(descr=name).order_by(CA.id).all()
        assert len(rows) == 2, 'two rows are expected for two keys under one name'
        by_spki = {}
        for row in rows:
            by_spki[row.id] = x509.load_pem_x509_certificate(__import__('base64').b64decode(row.crt))
        old_row = next(r for r in rows if by_spki[r.id].public_key().public_numbers() == old.public_key().public_numbers())
        new_row = next(r for r in rows if r is not old_row)
        old_row.prv = store_pem_bytes(key_pem(k_old).encode())
        db.session.commit()
        old_id, new_id = old_row.id, new_row.id
    r = _sign(auth_client, old_id, new_id)
    assert r.status_code == 201, r.data
    cross = _cert_of(r)
    aki = cross.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
    assert aki.key_identifier == old.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    ok, out = openssl_verify(leaf, [old], untrusted=[cross])
    assert ok, out


def _policy(app, a, rules):
    with app.app_context():
        pol = CertificatePolicy(name=f'p-{uuid.uuid4().hex[:8]}', policy_type='issuance', ca_id=a,
                                requires_approval=False, min_approvers=1, is_active=True, priority=100)
        pol.set_rules(rules)
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop(app, pid):
    with app.app_context():
        CertificatePolicy.query.filter_by(id=pid).delete()
        db.session.commit()


def _pair(app, days_a=3650):
    tag, ka, kb = _tag(), new_key(), new_key()
    ids = _import(app, [_mk(f'RA {tag}', ka, days=days_a), _mk(f'RB {tag}', kb)], keyed=[(f'RA {tag}', ka)])
    return ids[f'RA {tag}'][0], ids[f'RB {tag}'][0]


def test_policy_cap_is_reported_in_the_warnings(app, auth_client):
    a, b = _pair(app)
    pid = _policy(app, a, {'max_validity_days': 30})
    try:
        r = _sign(auth_client, a, b, validity_days=300)
        assert r.status_code == 201, r.data
        warnings = r.get_json()['data']['warnings']
        assert any('30 day' in w and 'policy' in w for w in warnings), warnings
    finally:
        _drop(app, pid)


def test_issuer_window_clamp_is_reported_in_the_warnings(app, auth_client):
    a, b = _pair(app, days_a=200)
    r = _sign(auth_client, a, b, validity_days=3000)
    assert r.status_code == 201, r.data
    assert any('expires on' in w for w in r.get_json()['data']['warnings'])
    a2, b2 = _pair(app)
    r = _sign(auth_client, a2, b2, validity_days=100)
    assert r.get_json()['data']['warnings'] == []


def test_a_refusal_notifies_policy_recipients_once(app, auth_client):
    a, b = _pair(app)
    pid = _policy(app, a, {'allowed_key_types': ['RSA-4096']})
    try:
        with mock.patch('services.policy_notifications.violation') as notify:
            assert _sign(auth_client, a, b).status_code == 400
        assert notify.call_count == 1
    finally:
        _drop(app, pid)


def test_parent_cannot_cross_sign_its_own_child_nor_a_child_its_ancestor(app, auth_client):
    tag, kb, ki = _tag(), new_key(), new_key()
    root, child = _mk(f'RB {tag}', kb), _mk(f'IB {tag}', ki, f'RB {tag}', kb, path_length=0)
    ids = _import(app, [root, child], keyed=[(f'RB {tag}', kb), (f'IB {tag}', ki)])
    rb, ib = ids[f'RB {tag}'][0], ids[f'IB {tag}'][0]
    r = _sign(auth_client, rb, ib)
    assert r.status_code == 409 and r.get_json()['details']['code'] == 'issuer_is_ancestor'
    r = _sign(auth_client, ib, rb)
    assert r.status_code == 409 and r.get_json()['details']['code'] == 'subject_is_ancestor'
    with app.app_context():
        assert CACrossCertificate.query.filter(CACrossCertificate.ca_id.in_([rb, ib])).count() == 0
