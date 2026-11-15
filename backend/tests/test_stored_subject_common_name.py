"""The CN read from a subject kept as TEXT (search, enrolled user certificates,
the system trust store sync).

These paths hold no x509.Name, only the stored `rfc4514_string()`, so they read
it with `utils.dn_parse.stored_dn_common_name`: an escaped comma stays inside
the value. On a subject with several CNs they keep the one they returned before,
the FIRST in the string, which RFC 4514 order makes the most specific.
"""
import datetime
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tests.conftest import assert_success, get_json
from utils.dn_parse import get_dn_attribute, stored_dn_common_name


@pytest.mark.parametrize('dn, expected', [
    (r'CN=Doe\, John', 'Doe, John'),
    ('CN=admin.example.com,CN=web.example.com', 'admin.example.com'),
    ('CN=x,O="Acme, Inc"', 'x'),
    ('cn=lower', 'lower'),
    ('O=No common name', None),
    ('', None),
    (None, None),
])
def test_it_reads_what_get_dn_attribute_reads(dn, expected):
    assert stored_dn_common_name(dn) == expected
    if dn:
        assert get_dn_attribute(dn, 'CN') == expected


@pytest.mark.filterwarnings('ignore:Attribute.s length')
@pytest.mark.parametrize('attrs, expected', [
    # cryptography writes emailAddress as a numeric OID, which ldap3 refuses
    ([(NameOID.COMMON_NAME, 'a.example'), (NameOID.EMAIL_ADDRESS, 'u@example.com')], 'a.example'),
    ([(NameOID.COMMON_NAME, 'q"uote+plus=eq#h <x>;')], 'q"uote+plus=eq#h <x>;'),
    ([(NameOID.COMMON_NAME, ' lead and trail ')], ' lead and trail '),
    ([(NameOID.COMMON_NAME, '')], ''),
])
def test_it_reads_subjects_cryptography_writes_and_ldap3_refuses(attrs, expected):
    """RFC 4514 allows a numeric OID type, an unescaped '=' and an empty value."""
    dn = x509.Name([x509.NameAttribute(oid, v, _validate=False) for oid, v in attrs]).rfc4514_string()
    assert stored_dn_common_name(dn) == expected


def test_an_escaped_comma_cannot_smuggle_a_cn():
    assert stored_dn_common_name(r'O=Evil\, CN=fake,CN=real') == 'real'


def post_json(client, url, data):
    import json
    return client.post(url, data=json.dumps(data), content_type='application/json')


def _comma_subject(tag):
    return rf'CN=Doe\, John {tag},O=Example'


def test_search_names_a_certificate_by_its_whole_cn(app, auth_client):
    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        row = Certificate(refid=f'cn-{tag}', descr=f'descr-{tag}', subject=_comma_subject(tag),
                          cert_type='server_cert', serial_number=str(uuid.uuid4().int)[:30])
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    try:
        r = auth_client.get(f'/api/v2/search?q=John {tag}&limit=5')
        found = [c for c in assert_success(r)['certificates'] if c['id'] == row_id]
        assert [c['name'] for c in found] == [f'Doe, John {tag}']
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()


def test_search_names_a_multi_cn_certificate_by_the_first_cn_in_the_string(app, auth_client):
    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        row = Certificate(refid=f'cn-{tag}', descr=f'descr-{tag}',
                          subject=f'CN=admin-{tag}.example,CN=web-{tag}.example',
                          cert_type='server_cert', serial_number=str(uuid.uuid4().int)[:30])
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    try:
        r = auth_client.get(f'/api/v2/search?q=web-{tag}&limit=5')
        found = [c for c in assert_success(r)['certificates'] if c['id'] == row_id]
        assert [c['name'] for c in found] == [f'admin-{tag}.example']
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()


@pytest.mark.parametrize('subject, expected', [
    (_comma_subject('u'), 'Doe, John u'),
    ('CN=admin.example,CN=web.example', 'admin.example'),
])
def test_an_enrolled_user_certificate_is_named_by_its_whole_cn(app, subject, expected):
    from api.v2.user_certificates import _build_cert_response
    from models import Certificate
    from models.auth_certificate import AuthCertificate

    with app.app_context():
        enrolment = AuthCertificate(user_id=1, cert_serial='1', cert_subject=subject,
                                    name='enrolment name', enabled=True)
        certificate = Certificate(refid='x', descr='descr', subject=subject, cert_type='usr_cert')
        assert _build_cert_response(enrolment, certificate)['common_name'] == expected


def _ca_pem(subject):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_the_system_trust_store_sync_names_a_ca_by_its_whole_cn(app, auth_client, monkeypatch):
    import io
    import os

    import api.v2.truststore as truststore
    from models import TrustedCertificate, db

    tag = uuid.uuid4().hex[:8]
    bundle = _ca_pem(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Doe, John {tag}')]))
    path = '/etc/ssl/certs/ca-certificates.crt'
    real_exists, real_open = os.path.exists, open
    monkeypatch.setattr(truststore.os.path, 'exists', lambda p: p == path or real_exists(p))
    monkeypatch.setattr(truststore, 'open',
                        lambda p, *a, **k: io.StringIO(bundle) if p == path else real_open(p, *a, **k),
                        raising=False)
    r = post_json(auth_client, '/api/v2/truststore/sync', {'limit': 1})
    assert assert_success(r)['new_count'] == 1, get_json(r)
    with app.app_context():
        rows = TrustedCertificate.query.filter(TrustedCertificate.subject.like(f'%{tag}%')).all()
        try:
            assert [row.name for row in rows] == [f'Doe, John {tag}']
        finally:
            for row in rows:
                db.session.delete(row)
            db.session.commit()


# The models read a stored subject as text too: CN, issuer CN and the other
# fields keep an escaped comma, and with several values of one attribute they
# keep the one they returned before, the FIRST in the stored string.
def test_a_certificate_row_reads_its_whole_cn_and_issuer_cn():
    from models import Certificate

    row = Certificate(subject=r'CN=Doe\, John,O=Acme\, Inc,OU=Ops',
                      issuer=r'CN=Issuer\, CA,O=Example')
    assert row.common_name == 'Doe, John'
    assert row.organization == 'Acme, Inc'
    assert row.organizational_unit == 'Ops'
    assert row.issuer_name == 'Issuer, CA'


def test_a_ca_row_reads_its_whole_cn():
    from models import CA

    row = CA(subject=r'CN=Doe\, John,O=Acme\, Inc')
    assert (row.common_name, row.organization) == ('Doe, John', 'Acme, Inc')


@pytest.mark.parametrize('model', ['Certificate', 'CA'])
def test_with_several_values_the_first_in_the_stored_string_is_kept(model):
    import models

    row = getattr(models, model)(subject='CN=admin.example,CN=web.example,OU=b,OU=a')
    assert (row.common_name, row.organizational_unit) == ('admin.example', 'b')


@pytest.mark.parametrize('model', ['Certificate', 'CA'])
def test_a_multivalued_rdn_does_not_leak_into_the_value(model):
    import models

    row = getattr(models, model)(subject='CN=host+O=Org,C=FR')
    assert (row.common_name, row.organization, row.country) == ('host', 'Org', 'FR')


def test_an_escaped_comma_cannot_smuggle_a_field():
    from models import Certificate

    assert Certificate(subject=r'O=Evil\, CN=fake', descr='d').common_name == 'd'


def _import(auth_client, pem, kind):
    import json

    r = auth_client.post('/api/v2/import/execute', data=json.dumps({
        'content': pem, 'options': {'import_certs': True, 'import_cas': True}}),
        content_type='application/json')
    assert r.status_code in (200, 201), r.data
    ids = r.get_json()['data']['imported_ids'][kind]
    assert len(ids) == 1, r.data
    return ids[0]


def _leaf_pem(subject, issuer):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _cn(value):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, value)])


def test_the_certificate_list_shows_the_whole_cn_and_issuer_cn(app, auth_client):
    from models import Certificate, db

    tag = uuid.uuid4().hex[:8]
    cert_id = _import(auth_client, _leaf_pem(_cn(f'Doe, John {tag}'), _cn(f'Issuer, CA {tag}')),
                      'certificates')
    try:
        r = auth_client.get(f'/api/v2/certificates?search={tag}&per_page=5')
        found = [c for c in assert_success(r) if c['id'] == cert_id]
        assert [(c['common_name'], c['cn'], c['issuer_name']) for c in found] == [
            (f'Doe, John {tag}', f'Doe, John {tag}', f'Issuer, CA {tag}')]
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, cert_id))
            db.session.commit()


def test_the_ca_list_shows_the_whole_cn_and_counts_by_it(app, auth_client):
    """The issuer-CN fallback of the certificate count still finds the CA's certificates."""
    from models import CA, Certificate, db

    tag = uuid.uuid4().hex[:8]
    ca_id = _import(auth_client, _ca_pem(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f'Doe, John {tag}'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Example')])), 'cas')
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        orphan = Certificate(refid=f'cn-{tag}', descr=f'descr-{tag}', subject=f'CN=leaf-{tag}',
                             issuer=ca.subject, cert_type='server_cert',
                             serial_number=str(uuid.uuid4().int)[:30])
        db.session.add(orphan)
        db.session.commit()
        orphan_id = orphan.id
    try:
        listed = [c for c in assert_success(auth_client.get('/api/v2/cas')) if c['id'] == ca_id]
        assert [(c['common_name'], c['certs']) for c in listed] == [(f'Doe, John {tag}', 1)]
        detail = assert_success(auth_client.get(f'/api/v2/cas/{ca_id}'))
        assert (detail['common_name'], detail['certs']) == (f'Doe, John {tag}', 1)
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, orphan_id))
            db.session.delete(db.session.get(CA, ca_id))
            db.session.commit()
