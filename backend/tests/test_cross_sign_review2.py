"""Cross-signing review fixes: policy chain, both validity notices, unlinked children, subject limits."""
from cryptography import x509
from cryptography.x509.oid import ObjectIdentifier

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from tests.fixtures.cross_pki import new_key, openssl_verify
from tests.test_cross_sign import _cert_of, _sign
from tests.test_cross_sign_review import _drop, _import, _mk, _pair, _policy, _tag, db_pem

POLICY = ObjectIdentifier('1.3.6.1.4.1.99999.1')


def _policies():
    return x509.CertificatePolicies([x509.PolicyInformation(POLICY, None)])


def test_cross_certificate_keeps_the_policy_chain_valid_under_explicit_policy(app, auth_client):
    tag, ka, kb, ki = _tag(), new_key(), new_key(), new_key()
    pc = x509.PolicyConstraints(require_explicit_policy=0, inhibit_policy_mapping=None)
    root_b = _mk(f'RB {tag}', kb, extras=[(pc, True), (_policies(), False)])
    int_b = _mk(f'IB {tag}', ki, f'RB {tag}', kb, path_length=0, extras=[(_policies(), False)])
    leaf = _mk(f'l-{tag}.example', new_key(), f'IB {tag}', ki, ca=False, san=f'l-{tag}.example',
               extras=[(_policies(), False)])
    ids = _import(app, [_mk(f'RA {tag}', ka), root_b, int_b], keyed=[(f'RA {tag}', ka)])
    r = _sign(auth_client, ids[f'RA {tag}'][0], ids[f'RB {tag}'][0])
    assert r.status_code == 201, r.data
    cross = _cert_of(r)
    root_a = x509.load_pem_x509_certificate(db_pem(app, ids[f'RA {tag}'][0]))
    import subprocess, tempfile, pathlib
    from tests.fixtures.cross_pki import pem
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / 'leaf.pem').write_text(pem(leaf))
        (t / 'root.pem').write_text(pem(root_a))
        (t / 'un.pem').write_text(pem(int_b) + pem(cross))
        done = subprocess.run(['openssl', 'verify', '-policy_check', '-policy', POLICY.dotted_string, '-no-CApath',
                               '-no-CAstore', '-CAfile', str(t / 'root.pem'), '-untrusted', str(t / 'un.pem'),
                               str(t / 'leaf.pem')], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stdout + done.stderr


def test_both_validity_notices_are_reported_when_policy_and_issuer_expiry_shorten(app, auth_client):
    a, b = _pair(app, days_a=100)
    pid = _policy(app, a, {'max_validity_days': 1000})
    try:
        r = _sign(auth_client, a, b, validity_days=3000)
        assert r.status_code == 201, r.data
        warnings = r.get_json()['data']['warnings']
        assert any('policy' in w for w in warnings), warnings
        assert any('expires on' in w for w in warnings), warnings
    finally:
        _drop(app, pid)


def test_child_without_caref_cannot_be_recertified_by_its_parent(app, auth_client):
    tag, kr, kc = _tag(), new_key(), new_key()
    root, child = _mk(f'RB {tag}', kr), _mk(f'IB {tag}', kc, f'RB {tag}', kr, path_length=0)
    ids = _import(app, [child, root], keyed=[(f'RB {tag}', kr)])
    rb, ib = ids[f'RB {tag}'][0], ids[f'IB {tag}'][0]
    with app.app_context():
        assert not db.session.get(CA, ib).caref, 'precondition: child is unlinked'
    r = _sign(auth_client, rb, ib)
    assert r.status_code == 409 and r.get_json()['details']['code'] == 'issuer_is_ancestor'
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=ib).count() == 0


def _b_pair(app, ski_ku_extras=(), path_length=None):
    tag, ka, kb = _tag(), new_key(), new_key()
    ids = _import(app, [_mk(f'RA {tag}', ka, path_length=5), _mk(f'RB {tag}', kb, path_length=path_length)],
                  keyed=[(f'RA {tag}', ka)])
    return ids[f'RA {tag}'][0], ids[f'RB {tag}'][0]


def test_cross_certificate_copies_the_subject_key_usage(app, auth_client):
    a, b = _b_pair(app)  # subject KU is keyCertSign + cRLSign only
    r = _sign(auth_client, a, b)
    assert r.status_code == 201, r.data
    ku = _cert_of(r).extensions.get_extension_for_class(x509.KeyUsage).value
    assert ku.key_cert_sign and ku.crl_sign and not ku.digital_signature


def test_explicit_path_length_never_exceeds_the_subjects_own(app, auth_client):
    a, b = _b_pair(app, path_length=0)

    def length(**extra):
        r = _sign(auth_client, a, b, **extra)
        assert r.status_code == 201, r.data
        return _cert_of(r).extensions.get_extension_for_class(x509.BasicConstraints).value.path_length
    assert length(path_length=5) == 0
    assert length(path_length=None) == 0
    assert length() == 0
