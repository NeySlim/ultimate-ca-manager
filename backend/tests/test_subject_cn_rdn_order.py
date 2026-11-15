"""The recorded subject_cn must be the subject's FIRST commonName.

Raised by NeySlim reviewing #251: the CN was derived by splitting
`subject.rfc4514_string()` on ',' and taking the first `CN=` token. RFC 4514
s2.1 emits RDNs in REVERSE order, so that token is the LAST commonName. For
`CN=web.example.com, CN=admin.example.com` the recorder stored
`admin.example.com` -- while ACME finalize validates
`get_attributes_for_oid(COMMON_NAME)[0]`, i.e. `web.example.com`. The name
CHECKED and the name RECORDED disagreed exactly when a subject carried more
than one CN, which is the case an attacker controls.

#251 closed the ACME route by rejecting a multi-CN subject at finalize, so it
is no longer reachable there -- but the same derivation fed every other
signing path, so the defect outlived its most dangerous caller.

These tests drive the REAL helper (`utils.dn_parse.subject_common_name`) that
both recorders now call, and pin the agreement against the same cryptography
API ACME finalize uses. An earlier draft of this module defined its own copy
of the derivation and asserted against that -- which would have passed no
matter what the production code did.
"""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from utils.dn_parse import subject_common_name


@pytest.fixture(scope='module')
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _subject(*cns, org=None):
    parts = [x509.NameAttribute(NameOID.COMMON_NAME, c) for c in cns]
    if org:
        parts.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))
    return x509.Name(parts)


def _self_signed(subject, key):
    now = datetime.datetime.now(datetime.timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )


def _the_old_way(subject):
    """The derivation both recorders used before the fix, kept ONLY to prove
    the two disagree -- never as the expected value."""
    for part in subject.rfc4514_string().split(','):
        if part.strip().upper().startswith('CN='):
            return part.strip()[3:]
    return None


def test_rfc4514_really_does_reverse_rdn_order():
    """Pin the premise. If cryptography ever stopped reversing, the rest of
    this module would still pass but would no longer be testing anything."""
    subject = _subject('web.example.com', 'admin.example.com')
    assert subject.rfc4514_string().startswith('CN=admin.example.com')
    assert subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'web.example.com'


def test_multi_cn_subject_resolves_to_the_first_common_name():
    subject = _subject('web.example.com', 'admin.example.com')
    assert subject_common_name(subject) == 'web.example.com'
    # The exact inversion that made a smuggled name the displayed identity.
    assert _the_old_way(subject) == 'admin.example.com'
    assert subject_common_name(subject) != _the_old_way(subject)


def test_it_reads_a_real_certificates_subject(key):
    cert = _self_signed(_subject('web.example.com', 'admin.example.com'), key)
    assert subject_common_name(cert.subject) == 'web.example.com'


def test_a_comma_inside_another_value_does_not_split_the_cn():
    r"""RFC 4514 escapes a comma in a value as '\,'; the old split ignored
    that, so an O= containing a comma could truncate or mis-pick the CN."""
    subject = _subject('host.example.com', org='Example, Inc.')
    assert subject_common_name(subject) == 'host.example.com'


@pytest.mark.parametrize('cns', [
    ('single.example.com',),
    ('first.example.com', 'second.example.com'),
    ('a.example.com', 'b.example.com', 'c.example.com'),
])
def test_recorder_agrees_with_the_name_acme_finalize_validates(cns):
    """The invariant that matters: the name UCM records is the name ACME
    finalize checks. Compared against the cryptography API directly, so a
    change to the helper that broke the agreement fails here."""
    subject = _subject(*cns)
    validated = subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    assert subject_common_name(subject) == validated == cns[0]


def test_subject_without_a_common_name_is_none_not_a_crash():
    subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Example')])
    assert subject_common_name(subject) is None


def _multi_cn_csr(key, tag):
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(_subject(f'web-{tag}.example.com', f'admin-{tag}.example.com'))
            .sign(key, hashes.SHA256()))


def test_the_csr_signing_path_records_the_first_common_name(app, auth_client, create_ca, key):
    """Uploaded then signed through the API: the row names the first CN."""
    import uuid

    from cryptography.hazmat.primitives import serialization

    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    pem = _multi_cn_csr(key, tag).public_bytes(serialization.Encoding.PEM).decode()
    ca_id = create_ca(cn=f'RDN order CA {tag}')['id']
    r = auth_client.post('/api/v2/csrs/upload', json={'pem': pem, 'name': f'rdn-{tag}'})
    assert r.status_code in (200, 201), r.data
    csr_id = r.get_json()['data']['id']
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca_id})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(Certificate, csr_id).subject_cn == f'web-{tag}.example.com'


def test_the_scep_path_records_the_first_common_name(app, create_ca, key):
    """Issued by the SCEP service: the row names the first CN too."""
    import base64
    import uuid

    from cryptography.hazmat.primitives import serialization

    from models import CA, Certificate, SCEPRequest, db
    from services.scep.scep_service import SCEPService

    tag = uuid.uuid4().hex[:8]
    csr = _multi_cn_csr(key, tag)
    ca_id = create_ca(cn=f'RDN order SCEP CA {tag}')['id']
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        req = SCEPRequest(transaction_id=f'rdn-{tag}', ca_refid=ca.refid, status='pending',
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode(),
                          subject=csr.subject.rfc4514_string())
        db.session.add(req)
        db.session.flush()
        refid = SCEPService(ca_refid=ca.refid, auto_approve=True)._auto_approve_request(req, csr)
        db.session.commit()
        row = Certificate.query.filter_by(refid=refid).one()
        try:
            assert row.subject_cn == f'web-{tag}.example.com'
        finally:
            db.session.delete(row)
            db.session.delete(req)
            db.session.commit()
