"""Custom X.509 extensions (#437): validation and templates; shared helpers."""
import base64
import itertools
import json

import pytest
from cryptography import x509

from models import Certificate, CertificateTemplate, db
from tests.test_acme_profile_template import _drop_template
from utils.custom_extensions import (MAX_EXTENSIONS, MAX_VALUE_BYTES, merge_custom_extensions,
                                     validate_custom_extensions)

_SEQ = itertools.count(1)
OID_A = '1.3.6.1.4.1.55555.1.1'
OID_B = '1.3.6.1.4.1.55555.1.2'
DER_A = '0c0568656c6c6f'          # UTF8String "hello"
DER_B = '020101'                  # INTEGER 1
TPL_EXT = [{'oid': OID_A, 'critical': False, 'value': DER_A}]


def _ext(cert, oid):
    try:
        return cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(oid))
    except x509.ExtensionNotFound:
        return None


def _value(cert, oid):
    ext = _ext(cert, oid)
    return None if ext is None else (ext.value.value.hex(), ext.critical)


def _cert(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


@pytest.fixture
def make_template(app):
    made = []

    def make(custom=TPL_EXT, **cols):
        with app.app_context():
            tpl = CertificateTemplate(
                name=f'custom-ext-tpl-{next(_SEQ)}', template_type='custom', key_type='RSA-2048',
                validity_days=30, digest='sha256', dn_template='{}',
                extensions_template=json.dumps({'extended_key_usage': ['serverAuth']}),
                custom_extensions=json.dumps(custom) if custom is not None else None, **cols)
            db.session.add(tpl)
            db.session.commit()
            made.append(tpl.id)
            return tpl.id
    yield make
    for tpl_id in made:
        _drop_template(app, tpl_id)


def _set_template_extensions(app, tpl_id, custom):
    with app.app_context():
        db.session.get(CertificateTemplate, tpl_id).custom_extensions = json.dumps(custom)
        db.session.commit()


# ── validation ──────────────────────────────────────────────────────────────

class TestValidation:
    def test_hex_is_normalised(self):
        entries, err = validate_custom_extensions(
            [{'oid': f' {OID_A} ', 'value': '0C:05 68:65:6C 6C:6F'}])
        assert err is None
        assert entries == [{'oid': OID_A, 'critical': False, 'value': DER_A}]

    def test_base64_gives_the_same_entry(self):
        b64 = base64.b64encode(bytes.fromhex(DER_A)).decode()
        entries, err = validate_custom_extensions([{'oid': OID_A, 'critical': True, 'value_base64': b64}])
        assert err is None and entries == [{'oid': OID_A, 'critical': True, 'value': DER_A}]

    def test_json_text_and_empty(self):
        assert validate_custom_extensions(None) == ([], None)
        assert validate_custom_extensions([]) == ([], None)
        assert validate_custom_extensions(json.dumps(TPL_EXT)) == (TPL_EXT, None)

    @pytest.mark.parametrize('oid,name', [
        ('2.5.29.19', 'basicConstraints'), ('2.5.29.15', 'keyUsage'), ('2.5.29.37', 'extendedKeyUsage'),
        ('2.5.29.17', 'subjectAltName'), ('2.5.29.14', 'subjectKeyIdentifier'),
        ('2.5.29.35', 'authorityKeyIdentifier'), ('2.5.29.31', 'cRLDistributionPoints'),
        ('1.3.6.1.5.5.7.1.1', 'authorityInfoAccess'), ('2.5.29.32', 'certificatePolicies'),
        ('2.5.29.30', 'nameConstraints'), ('1.3.6.1.4.1.11129.2.4.2', 'signedCertificateTimestampList'),
        ('1.3.6.1.5.5.7.1.24', 'TLSFeature'), ('1.3.6.1.5.5.7.48.1.5', 'OCSPNoCheck'),
        ('1.3.6.1.5.5.7.1.36', 'relatedCertificate'), ('1.3.6.1.4.1.311.21.7', 'msCertificateTemplate'),
        ('1.3.6.1.4.1.311.25.2', 'ntdsCaSecurityExt'), ('1.3.6.1.5.5.7.1.3', 'qcStatements'),
    ])
    def test_extensions_ucm_sets_are_refused_by_name(self, oid, name):
        entries, err = validate_custom_extensions([{'oid': oid, 'value': DER_B}])
        assert entries is None
        assert f'{oid} is the {name} extension' in err and 'dedicated setting' in err

    @pytest.mark.parametrize('oid', ['abc', '1', '3.1', '1.40', '1.2.03', '1.2.', '1..2', 7, None,
                                     '1.2.' + '9' * 130])
    def test_oid_must_be_dotted_and_valid(self, oid):
        entries, err = validate_custom_extensions([{'oid': oid, 'value': DER_B}])
        assert entries is None and 'OID' in err

    def test_size_cap(self):
        at_cap = [{'oid': OID_A, 'value': '00' * MAX_VALUE_BYTES}]
        assert validate_custom_extensions(at_cap)[1] is None
        entries, err = validate_custom_extensions([{'oid': OID_A, 'value': '00' * (MAX_VALUE_BYTES + 1)}])
        assert entries is None and f'{MAX_VALUE_BYTES} bytes' in err
        b64 = base64.b64encode(b'\0' * (MAX_VALUE_BYTES + 1)).decode()
        assert validate_custom_extensions([{'oid': OID_A, 'value_base64': b64}])[0] is None

    @pytest.mark.parametrize('entry,needle', [
        ({'oid': OID_A, 'value': ''}, 'empty'),
        ({'oid': OID_A, 'value': '  '}, 'empty'),
        ({'oid': OID_A, 'value': 'abc'}, 'even number of hex'),
        ({'oid': OID_A, 'value': 'zz'}, 'even number of hex'),
        ({'oid': OID_A, 'value': 1234}, 'string'),
        ({'oid': OID_A, 'value_base64': '!!'}, 'base64'),
        ({'oid': OID_A}, 'give the value'),
        ({'oid': OID_A, 'value': DER_A, 'value_base64': 'AQ=='}, 'give the value'),
        ({'oid': OID_A, 'value': DER_A, 'critical': 'yes'}, 'critical'),
        ({'oid': OID_A, 'value': DER_A, 'extra': 1}, 'unknown key extra'),
    ])
    def test_bad_entries(self, entry, needle):
        entries, err = validate_custom_extensions([entry])
        assert entries is None and needle in err

    def test_shape_count_and_duplicates(self):
        assert 'must be a list' in validate_custom_extensions({'oid': OID_A})[1]
        assert 'must be an object' in validate_custom_extensions(['x'])[1]
        assert 'not valid JSON' in validate_custom_extensions('[')[1]
        many = [{'oid': f'1.3.6.1.4.1.55555.9.{i}', 'value': DER_B} for i in range(MAX_EXTENSIONS + 1)]
        assert f'at most {MAX_EXTENSIONS}' in validate_custom_extensions(many)[1]
        assert validate_custom_extensions(many[:MAX_EXTENSIONS])[1] is None
        dup = [{'oid': OID_A, 'value': DER_A}, {'oid': OID_A, 'value': DER_B}]
        assert 'appears more than once' in validate_custom_extensions(dup)[1]

    def test_merge_the_later_list_wins_in_place(self):
        tpl = [{'oid': OID_A, 'critical': False, 'value': DER_A},
               {'oid': OID_B, 'critical': False, 'value': DER_B}]
        req = [{'oid': OID_A, 'critical': True, 'value': '0500'}]
        assert merge_custom_extensions(tpl, req) == [req[0], tpl[1]]


# ── templates ───────────────────────────────────────────────────────────────

def _tpl_payload(**extra):
    return {'name': f'custom-ext-api-{next(_SEQ)}', 'template_type': 'custom',
            'extensions_template': {'key_usage': ['digitalSignature']}, **extra}


class TestTemplateApi:
    def test_create_update_clear(self, app, auth_client):
        r = auth_client.post('/api/v2/templates', json=_tpl_payload(
            custom_extensions=[{'oid': OID_A, 'critical': True, 'value': '0C:05:68:65:6C:6C:6F'}]))
        assert r.status_code == 201, r.get_json()
        tpl = r.get_json()['data']
        try:
            assert tpl['custom_extensions'] == [{'oid': OID_A, 'critical': True, 'value': DER_A}]
            r = auth_client.put(f"/api/v2/templates/{tpl['id']}", json={
                'custom_extensions': [{'oid': OID_B, 'value': DER_B}]})
            assert r.status_code == 200
            assert r.get_json()['data']['custom_extensions'] == [
                {'oid': OID_B, 'critical': False, 'value': DER_B}]
            r = auth_client.put(f"/api/v2/templates/{tpl['id']}", json={'custom_extensions': []})
            assert r.get_json()['data']['custom_extensions'] == []
            with app.app_context():
                assert db.session.get(CertificateTemplate, tpl['id']).custom_extensions is None
        finally:
            _drop_template(app, tpl['id'])

    def test_refusals_are_400_and_named(self, app, auth_client):
        r = auth_client.post('/api/v2/templates', json=_tpl_payload(
            custom_extensions=[{'oid': '2.5.29.17', 'value': DER_B}]))
        assert r.status_code == 400
        assert 'subjectAltName extension' in r.get_json()['message']
        r = auth_client.post('/api/v2/templates', json=_tpl_payload(
            custom_extensions=[{'oid': OID_A, 'value': 'abc'}]))
        assert r.status_code == 400 and 'hex' in r.get_json()['message']

    def test_update_refusal_keeps_the_stored_list(self, app, auth_client, make_template):
        tpl_id = make_template()
        r = auth_client.put(f'/api/v2/templates/{tpl_id}', json={
            'custom_extensions': [{'oid': '2.5.29.19', 'value': DER_B}]})
        assert r.status_code == 400
        with app.app_context():
            assert json.loads(db.session.get(CertificateTemplate, tpl_id).custom_extensions) == TPL_EXT

    def test_duplicate_export_import(self, app, auth_client, make_template):
        tpl_id = make_template()
        r = auth_client.post(f'/api/v2/templates/{tpl_id}/duplicate')
        clone = r.get_json()['data']
        try:
            assert clone['custom_extensions'] == TPL_EXT
            exported = json.loads(auth_client.get(f'/api/v2/templates/{tpl_id}/export').data)
            assert exported['custom_extensions'] == TPL_EXT
            exported['name'] = f'custom-ext-imported-{next(_SEQ)}'
            r = auth_client.post('/api/v2/templates/import', data={'json_content': json.dumps(exported)},
                                 content_type='multipart/form-data')
            assert r.status_code == 200 and r.get_json()['data']['imported'] == 1, r.get_json()
            with app.app_context():
                imported = CertificateTemplate.query.filter_by(name=exported['name']).first()
                assert imported.custom_extensions_list() == TPL_EXT
                imported_id = imported.id
            _drop_template(app, imported_id)
            exported['name'] = f'custom-ext-bad-{next(_SEQ)}'
            exported['custom_extensions'] = [{'oid': '2.5.29.15', 'value': DER_B}]
            r = auth_client.post('/api/v2/templates/import', data={'json_content': json.dumps(exported)},
                                 content_type='multipart/form-data')
            assert r.get_json()['data']['imported'] == 0
            assert 'keyUsage extension' in r.get_json()['data']['skipped_items'][0]
        finally:
            _drop_template(app, clone['id'])

    def test_backup_carries_the_column(self, app, make_template):
        from services.backup.export_generic import IdentityIndex, export_section
        tpl_id = make_template()
        with app.app_context():
            name = db.session.get(CertificateTemplate, tpl_id).name
            rows = export_section('certificate_templates', IdentityIndex())
        row = next(r for r in rows if r['name'] == name)
        assert json.loads(row['custom_extensions']) == TPL_EXT

    def test_writing_needs_write_templates(self, app, create_user):
        user = create_user(role='viewer')
        client = app.test_client()
        r = client.post('/api/v2/auth/login', json={'username': user['username'], 'password': 'TestPass123!'})
        assert r.status_code == 200
        r = client.post('/api/v2/templates', json=_tpl_payload(custom_extensions=TPL_EXT))
        assert r.status_code == 403
