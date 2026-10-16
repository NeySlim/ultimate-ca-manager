"""A template's key type is stored under its registry label.

The API accepted legacy spellings ('ec:p384') and stored them as given: XCEP
then announced the template as RSA 2048, so Windows generated an RSA key,
and issuance from the template failed with 'Unsupported key type'.
"""
import base64
import importlib.util
import json
import os
import sqlite3
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from lxml import etree

from models import CA, CATemplatePin, Certificate, CertificateTemplate, db
from models.system_config import SystemConfig
from tests.conftest import get_json

CONTENT_JSON = 'application/json'
XCEP_URL = '/ADPolicyProvider_CEP_UsernamePassword/service.svc'
XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
XSI_NIL = '{http://www.w3.org/2001/XMLSchema-instance}nil'
XCEP_USER = 'xcep-canonical'
XCEP_PASSWORD = 'xcep-canonical-password'


def _name(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:8]}'


def _create_template(auth_client, key_type, **extra):
    data = {'name': _name('kt-canon'), 'template_type': 'custom', 'key_type': key_type,
            'validity_days': 90,
            'extensions_template': {'key_usage': ['digitalSignature'],
                                    'extended_key_usage': ['clientAuth']}}
    data.update(extra)
    return auth_client.post('/api/v2/templates', data=json.dumps(data),
                            content_type=CONTENT_JSON)


def _stored_key_type(app, template_id):
    with app.app_context():
        return db.session.get(CertificateTemplate, template_id).key_type


class TestWritesStoreTheRegistryLabel:
    def test_create_stores_the_canonical_label(self, app, auth_client):
        r = _create_template(auth_client, 'ec:p384')
        assert r.status_code in (200, 201), r.data
        tpl = get_json(r)['data']
        assert tpl['key_type'] == 'EC-P384'
        assert _stored_key_type(app, tpl['id']) == 'EC-P384'

    def test_update_stores_the_canonical_label(self, app, auth_client):
        tpl = get_json(_create_template(auth_client, 'RSA-2048'))['data']
        r = auth_client.put(f"/api/v2/templates/{tpl['id']}",
                            data=json.dumps({'key_type': 'rsa:4096'}),
                            content_type=CONTENT_JSON)
        assert r.status_code == 200, r.data
        assert _stored_key_type(app, tpl['id']) == 'RSA-4096'

    def test_an_empty_key_type_on_update_keeps_the_current_one(self, app, auth_client):
        tpl = get_json(_create_template(auth_client, 'EC-P256'))['data']
        r = auth_client.put(f"/api/v2/templates/{tpl['id']}",
                            data=json.dumps({'key_type': ''}), content_type=CONTENT_JSON)
        assert r.status_code == 200, r.data
        assert _stored_key_type(app, tpl['id']) == 'EC-P256'

    def test_import_stores_the_canonical_label_on_create_and_update(self, app, auth_client):
        name = _name('kt-import')

        def _import(key_type, update):
            return auth_client.post('/api/v2/templates/import', data={
                'json_content': json.dumps([{'name': name, 'template_type': 'custom',
                                             'key_type': key_type}]),
                'update_existing': 'true' if update else 'false',
            })

        r = _import('ec:p521', update=False)
        assert r.status_code == 200, r.data
        with app.app_context():
            assert CertificateTemplate.query.filter_by(name=name).one().key_type == 'EC-P521'
        r = _import('rsa:3072', update=True)
        assert r.status_code == 200, r.data
        with app.app_context():
            assert CertificateTemplate.query.filter_by(name=name).one().key_type == 'RSA-3072'

    @pytest.mark.parametrize('key_type', ['dsa:1024', 'rsa:1024', 'ED25519', 'nonsense'])
    def test_an_unusable_key_type_is_refused(self, auth_client, key_type):
        r = _create_template(auth_client, key_type)
        assert r.status_code == 400, r.data
        tpl = get_json(_create_template(auth_client, 'RSA-2048'))['data']
        r = auth_client.put(f"/api/v2/templates/{tpl['id']}",
                            data=json.dumps({'key_type': key_type}), content_type=CONTENT_JSON)
        assert r.status_code == 400, r.data

    def test_the_service_stores_the_canonical_label(self, app):
        from services.template_service import TemplateService
        with app.app_context():
            tpl = TemplateService.create_template(
                {'name': _name('kt-svc'), 'key_type': 'ec:p256'}, 'tester')
            assert tpl.key_type == 'EC-P256'
            tpl = TemplateService.update_template(tpl.id, {'key_type': 'rsa:4096'}, 'tester')
            assert tpl.key_type == 'RSA-4096'
            with pytest.raises(ValueError):
                TemplateService.update_template(tpl.id, {'key_type': 'dsa:1024'}, 'tester')
            assert db.session.get(CertificateTemplate, tpl.id).key_type == 'RSA-4096'


def test_issuance_from_a_legacy_spelled_template_works(app, auth_client, create_ca):
    ca = create_ca(cn='Key Type Canonical CA')
    tpl = get_json(_create_template(auth_client, 'ec:p384'))['data']
    r = auth_client.post('/api/v2/certificates', data=json.dumps({
        'cn': 'kt-canon.example.com', 'ca_id': ca['id'], 'template_id': tpl['id']}),
        content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    with app.app_context():
        row = db.session.get(Certificate, get_json(r)['data']['id'])
        key = x509.load_pem_x509_certificate(base64.b64decode(row.crt)).public_key()
    assert isinstance(key, ec.EllipticCurvePublicKey) and key.curve.name == 'secp384r1'


# ---------------------------------------------------------------- XCEP

def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row is not None:
            db.session.delete(row)
    elif row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def xcep_ca(app, create_ca):
    """An XCEP-enabled CA; yields a function pinning template ids to it."""
    ca_data = create_ca(cn=_name('XCEP KeyType CA'))
    keys = ('xcep_enabled', 'xcep_ca_refid', 'xcep_username', 'xcep_password')
    pinned = []
    with app.app_context():
        previous = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None)
                    for k in keys}
        ca = db.session.get(CA, ca_data['id'])
        for key, value in zip(keys, ('true', ca.refid, XCEP_USER, XCEP_PASSWORD)):
            _set_config(key, value)

    def _pin(template_id):
        with app.app_context():
            pin = CATemplatePin(ca_id=ca_data['id'], template_id=template_id)
            db.session.add(pin)
            db.session.commit()
            pinned.append(pin.id)

    yield _pin
    with app.app_context():
        for pin_id in pinned:
            row = db.session.get(CATemplatePin, pin_id)
            if row:
                db.session.delete(row)
        db.session.commit()
        for key, value in previous.items():
            _set_config(key, value)


def _raw_template(app, key_type):
    """A row written straight to the database, as an older version could leave it."""
    with app.app_context():
        tpl = CertificateTemplate(name=_name('kt-raw'), template_type='custom',
                                  key_type=key_type, validity_days=90, digest='sha256',
                                  extensions_template='{}', is_active=True)
        db.session.add(tpl)
        db.session.commit()
        return tpl.id, tpl.name


def _policies(client):
    token = base64.b64encode(f'{XCEP_USER}:{XCEP_PASSWORD}'.encode()).decode()
    r = client.post(XCEP_URL, data=b'<GetPolicies/>',
                    headers={'Authorization': f'Basic {token}'})
    assert r.status_code == 200, r.data
    root = etree.fromstring(r.data)
    return {p.find(f'.//{{{XCEP_NS}}}commonName').text: p
            for p in root.findall(f'.//{{{XCEP_NS}}}policy')}


def _assert_ecdsa_p384(policy):
    attrs = policy.find(f'.//{{{XCEP_NS}}}privateKeyAttributes')
    assert attrs.find(f'{{{XCEP_NS}}}minimalKeyLength').text == '384'
    assert attrs.find(f'{{{XCEP_NS}}}keySpec').get(XSI_NIL) == 'true'
    providers = [p.text for p in attrs.findall(f'.//{{{XCEP_NS}}}provider')]
    assert providers == ['Microsoft Software Key Storage Provider']


class TestXcepAnnouncesTheTemplateKeyType:
    def test_a_template_created_as_ec_p384_is_announced_ecdsa_p384(
            self, client, auth_client, xcep_ca):
        tpl = get_json(_create_template(auth_client, 'ec:p384'))['data']
        xcep_ca(tpl['id'])
        _assert_ecdsa_p384(_policies(client)[tpl['name']])

    def test_a_legacy_row_is_read_through_the_registry(self, app, client, xcep_ca):
        tpl_id, name = _raw_template(app, 'ec:p384')
        xcep_ca(tpl_id)
        _assert_ecdsa_p384(_policies(client)[name])

    def test_an_unknown_key_type_is_not_announced(self, app, client, auth_client, xcep_ca):
        known = get_json(_create_template(auth_client, 'RSA-3072'))['data']
        unknown_id, unknown_name = _raw_template(app, 'dsa:1024')
        xcep_ca(known['id'])
        xcep_ca(unknown_id)
        policies = _policies(client)
        assert unknown_name not in policies
        assert policies[known['name']].find(f'.//{{{XCEP_NS}}}minimalKeyLength').text == '3072'


# ----------------------------------------------------------- migration

def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'migrations', '096_template_key_type_canonical.py')
    spec = importlib.util.spec_from_file_location('m096', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_normalizes_known_spellings_and_keeps_the_rest():
    migration = _migration()
    assert migration.pg_compatible is True
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE certificate_templates (id INTEGER PRIMARY KEY, key_type VARCHAR(20))')
    rows = [(1, 'ec:p384'), (2, 'rsa:4096'), (3, 'dsa:1024'), (4, 'EC-P256'), (5, None)]
    conn.executemany('INSERT INTO certificate_templates VALUES (?, ?)', rows)
    expected = {1: 'EC-P384', 2: 'RSA-4096', 3: 'dsa:1024', 4: 'EC-P256', 5: None}

    for _ in range(2):  # idempotent
        migration.upgrade(conn)
        assert dict(conn.execute('SELECT id, key_type FROM certificate_templates')) == expected


def test_migration_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_migration_on_postgresql():
    from sqlalchemy import create_engine, text
    # A schema of its own: the bench is one database shared by other files.
    schema = f"m096_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    engine = create_engine(os.environ['UCM_TEST_PG_URL'])
    migration = _migration()
    expected = {1: 'EC-P384', 2: 'RSA-4096', 3: 'dsa:1024', 4: 'EC-P256', 5: None}
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET search_path TO {schema}'))
            migration.upgrade(conn)     # no table yet
            conn.execute(text('CREATE TABLE certificate_templates '
                              '(id INTEGER PRIMARY KEY, key_type VARCHAR(20))'))
            conn.execute(text("INSERT INTO certificate_templates VALUES (1, 'ec:p384'), "
                              "(2, 'rsa:4096'), (3, 'dsa:1024'), (4, 'EC-P256'), (5, NULL)"))
        for _ in range(2):
            with engine.begin() as conn:
                conn.execute(text(f'SET search_path TO {schema}'))
                migration.upgrade(conn)
                rows = dict(conn.execute(text('SELECT id, key_type FROM certificate_templates')).fetchall())
            assert rows == expected
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
