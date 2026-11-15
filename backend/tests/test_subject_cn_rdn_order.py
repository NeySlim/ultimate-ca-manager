"""Which commonName is recorded as `subject_cn`, per signing path.

Two rules, each deliberate:

* CN verified or chosen by the operator (ACME, CSR signing, SCEP, completion
  of an external certificate): the FIRST CN of the sequence, the one ACME
  finalize reads (`utils.dn_parse.subject_common_name`). Raised in #251: the
  recorder used to split `rfc4514_string()` (reverse RDN order) and stored the
  last CN while the check read the first.
* Directory subjects (EST, WSTEP via `CAService.sign_csr_from_crypto`, and the
  import): the MOST SPECIFIC CN, the LAST one (`most_specific_common_name`).
  In `CN=Roy Hagland,CN=Users,DC=...` that is the person, not the container;
  RFC 2818 s3.1 also names "the (most specific) Common Name".

Both helpers read the x509 Name, never a split of `rfc4514_string()`, which
mis-handles an escaped comma inside a value.
"""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from utils.dn_parse import most_specific_common_name, subject_common_name


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
        row = db.session.get(Certificate, csr_id)
        try:
            assert row.subject_cn == f'web-{tag}.example.com'
        finally:
            db.session.delete(row)
            db.session.commit()


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


def test_the_external_certificate_path_records_the_first_common_name(app, auth_client, key):
    """A CSR signed outside UCM, imported back: the completed row names the first CN."""
    import uuid

    from cryptography.hazmat.primitives import serialization

    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    csr = _multi_cn_csr(key, tag)
    r = auth_client.post('/api/v2/csrs/upload', json={
        'pem': csr.public_bytes(serialization.Encoding.PEM).decode(), 'name': f'rdn-ext-{tag}'})
    assert r.status_code in (200, 201), r.data
    csr_id = r.get_json()['data']['id']

    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = _subject(f'External RDN CA {tag}')
    now = datetime.datetime.now(datetime.timezone.utc)
    leaf = (x509.CertificateBuilder()
            .subject_name(csr.subject).issuer_name(issuer)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .sign(issuer_key, hashes.SHA256()))
    r = auth_client.post('/api/v2/certificates/import', data={
        'pem_content': leaf.public_bytes(serialization.Encoding.PEM).decode()},
        content_type='multipart/form-data')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['id'] == csr_id
    with app.app_context():
        row = db.session.get(Certificate, csr_id)
        try:
            assert row.subject_cn == f'web-{tag}.example.com'
        finally:
            db.session.delete(row)
            db.session.commit()


def test_the_est_path_records_the_most_specific_common_name(app, create_ca, key):
    """Directory subjects: EST (via CAService.sign_csr_from_crypto) records the LAST CN."""
    import uuid

    from models import CA, Certificate, db
    from services.ca_service import CAService

    tag = uuid.uuid4().hex[:8]
    ca_id = create_ca(cn=f'RDN order EST CA {tag}')['id']
    with app.app_context():
        pem, _serial = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, ca_id), csr=_multi_cn_csr(key, tag), validity_days=5,
            source='est', cert_type='device_cert')
        leaf = x509.load_pem_x509_certificate(pem.encode())
        row = Certificate.query.filter_by(serial_number=str(leaf.serial_number)).one()
        try:
            assert row.subject_cn == f'admin-{tag}.example.com'
        finally:
            db.session.delete(row)
            db.session.commit()


def _import_pem(auth_client, subject, key, tag, ca=False, san=None):
    """Sign `subject` (self-signed when `ca`) and run it through /import/execute."""
    import json

    from cryptography.hazmat.primitives import serialization

    issuer_key = key if ca else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder()
               .subject_name(subject)
               .issuer_name(subject if ca else _subject(f'Import RDN CA {tag}'))
               .public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - datetime.timedelta(days=1))
               .not_valid_after(now + datetime.timedelta(days=30)))
    if ca:
        builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    if san:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    cert = builder.sign(issuer_key, hashes.SHA256())
    r = auth_client.post('/api/v2/import/execute', data=json.dumps({
        'content': cert.public_bytes(serialization.Encoding.PEM).decode(),
        'options': {'import_certs': True, 'import_cas': True}}), content_type='application/json')
    assert r.status_code in (200, 201), r.data
    ids = r.get_json()['data']['imported_ids']['cas' if ca else 'certificates']
    assert len(ids) == 1, r.data
    return ids[0]


def _import_leaf(auth_client, key, tag, *cns):
    return _import_pem(auth_client, _subject(*cns), key, tag)


def _legacy_country(cn):
    """A subject real certificates carry and cryptography loads, but that
    `Name.from_rfc4514_string` refuses: a three-letter country."""
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn),
                      x509.NameAttribute(NameOID.COUNTRY_NAME, 'USA', _validate=False)])


@pytest.mark.filterwarnings('ignore:Attribute.s length')
def test_the_import_reads_the_cn_of_a_subject_rfc4514_cannot_parse_back(app, auth_client, key):
    import uuid

    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    with pytest.raises(ValueError):  # the premise
        x509.Name.from_rfc4514_string(_legacy_country('x').rfc4514_string())
    cert_id = _import_pem(auth_client, _legacy_country(f'legacy-{tag}.example'), key, tag)
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        try:
            assert row.subject_cn == f'legacy-{tag}.example'
        finally:
            db.session.delete(row)
            db.session.commit()


@pytest.mark.filterwarnings('ignore:Attribute.s length')
def test_an_imported_ca_with_such_a_subject_is_named_after_its_cn(app, auth_client):
    import uuid

    from models import CA, db

    tag = uuid.uuid4().hex[:8]
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_id = _import_pem(auth_client, _legacy_country(f'Legacy CA {tag}'), ca_key, tag, ca=True)
    with app.app_context():
        row = db.session.get(CA, ca_id)
        try:
            assert row.descr == f'Legacy CA {tag}'
        finally:
            db.session.delete(row)
            db.session.commit()


@pytest.mark.filterwarnings('ignore:Attribute.s length')
def test_an_imported_csr_is_named_after_its_parsed_cn(app, auth_client, key):
    import json
    import uuid

    from cryptography.hazmat.primitives import serialization

    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(_legacy_country(f'legacy-csr-{tag}.example'))
           .sign(key, hashes.SHA256()))
    r = auth_client.post('/api/v2/import/execute', data=json.dumps({
        'content': csr.public_bytes(serialization.Encoding.PEM).decode(),
        'options': {'import_csrs': True}}), content_type='application/json')
    assert r.status_code in (200, 201), r.data
    ids = r.get_json()['data']['imported_ids']['csrs']
    assert len(ids) == 1, r.data
    with app.app_context():
        row = db.session.get(Certificate, ids[0])
        try:
            assert (row.subject_cn, row.descr) == (f'legacy-csr-{tag}.example',) * 2
        finally:
            db.session.delete(row)
            db.session.commit()


def test_an_imported_certificate_without_a_cn_falls_back_as_before(app, auth_client, key):
    """No CN: the first DNS SAN, else no subject_cn (unchanged by this lot)."""
    import uuid

    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    org = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, f'No CN {tag}')])
    with_san = _import_pem(auth_client, org, key, tag, san=f'san-{tag}.example')
    bare = _import_pem(auth_client, org, rsa.generate_private_key(public_exponent=65537, key_size=2048), tag)
    with app.app_context():
        rows = [db.session.get(Certificate, i) for i in (with_san, bare)]
        try:
            assert rows[0].subject_cn == f'san-{tag}.example'
            assert rows[1].subject_cn is None
            assert rows[1].descr == 'Certificate'
        finally:
            for row in rows:
                db.session.delete(row)
            db.session.commit()


def test_an_imported_ca_without_a_cn_is_named_unknown_as_before(app, auth_client):
    import uuid

    from models import CA, db

    tag = uuid.uuid4().hex[:8]
    org = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, f'No CN CA {tag}')])
    ca_id = _import_pem(auth_client, org, rsa.generate_private_key(public_exponent=65537, key_size=2048),
                        tag, ca=True)
    with app.app_context():
        row = db.session.get(CA, ca_id)
        try:
            assert row.descr == 'Unknown'
        finally:
            db.session.delete(row)
            db.session.commit()


@pytest.mark.filterwarnings('ignore:Attribute.s length')
@pytest.mark.parametrize('subject, expected', [
    (_legacy_country('legacy.example'), 'legacy.example'),
    (_subject('Doe, John'), 'Doe, John'),
    (_subject('web.example.com', 'admin.example.com'), 'admin.example.com'),
    (x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'A long organisation without any CN')]),
     'O=A long organisation without ...'),
])
def test_the_validator_names_a_certificate_by_its_parsed_cn(subject, expected):
    """Validator messages: the most specific CN, else the subject cut at 30 characters."""
    from services.smart_import.parser import SmartParser
    from services.smart_import.validator import ImportValidator

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    obj = SmartParser()._parse_x509_cert(_self_signed(subject, key))
    validator = ImportValidator()
    assert validator._get_cn(obj) == expected
    assert validator._get_cn(obj, issuer=True) == expected


def test_the_smart_import_path_records_the_most_specific_common_name(app, auth_client, key):
    """Import records the LAST CN, like EST and WSTEP."""
    import uuid

    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    cert_id = _import_leaf(auth_client, key, tag, f'web-{tag}.example.com', f'admin-{tag}.example.com')
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        try:
            assert row.subject_cn == f'admin-{tag}.example.com'
        finally:
            db.session.delete(row)
            db.session.commit()


def test_the_smart_import_path_keeps_a_comma_inside_the_common_name(app, auth_client, key):
    """A CN such as 'Doe, John' is recorded whole, not cut at the escaped comma."""
    import uuid

    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    cert_id = _import_leaf(auth_client, key, tag, f'Doe, John {tag}')
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        try:
            assert row.subject_cn == f'Doe, John {tag}'
        finally:
            db.session.delete(row)
            db.session.commit()


def test_most_specific_common_name_is_the_last_one():
    assert most_specific_common_name(_subject('a.example.com', 'b.example.com')) == 'b.example.com'
    assert most_specific_common_name(_subject('Doe, John')) == 'Doe, John'
    assert most_specific_common_name(x509.Name([])) is None
