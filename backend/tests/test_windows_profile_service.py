"""The default Windows enrollment profile in the running application (SQLite, and PostgreSQL
with UCM_TEST_APP_PG_URL): GetPolicies byte for byte after migration 155, a 2.x archive
restored as the same profile, the settings it replaced read nowhere, deletion refused while
a profile uses a row, and the A1 cases served or refused."""
import ast
import importlib
from pathlib import Path

import pytest
from lxml import etree

from models import (CA, ADConnectorConfig, Certificate, CATemplatePin, CertificateTemplate, SystemConfig,
                    WindowsEnrollmentProfile, WindowsProfileTemplate, db)
from services.backup import manifest
from services.kerberos import negotiate_auth
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS
from services.windows_profiles.legacy import MIGRATED_KEYS, profile_from_2x
from tests.fixtures.templates import delete_templates

XCEP_URL = '/ADPolicyProvider_CEP_UsernamePassword/service.svc'
XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
USER, PASSWORD = 'c01-cep-user', 'c01-cep-password'
MESSAGE_ID = 'urn:uuid:5e3c01aa-0000-4000-8000-000000000155'
BACKUP_PASSWORD = 'C01-backup-password-155'
PROFILE_COLUMNS = ('name', 'realm', 'is_default', 'enabled', 'connector_id', 'issuing_ca_refid',
                   'policy_ca_refid', 'validity_days', 'xcep_username', 'xcep_password',
                   'wstep_username', 'wstep_password')
BACKEND = Path(__file__).resolve().parents[1]


def _envelope(username=USER, password=PASSWORD):
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap={'s': SOAP_NS, 'a': ADDRESSING_NS, 'wsse': WSSE_NS})
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = MESSAGE_ID
    token = etree.SubElement(etree.SubElement(header, '{%s}Security' % WSSE_NS), '{%s}UsernameToken' % WSSE_NS)
    etree.SubElement(token, '{%s}Username' % WSSE_NS).text = username
    etree.SubElement(token, '{%s}Password' % WSSE_NS).text = password
    etree.SubElement(etree.SubElement(envelope, '{%s}Body' % SOAP_NS), '{%s}GetPolicies' % XCEP_NS)
    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def _migrate_app_db(keytab=b''):
    """Migration 155 on the application's own database, as a 2.x upgrade runs it."""
    migration = importlib.import_module('migrations.155_windows_enrollment_profiles')
    db.session.commit()
    if db.engine.dialect.name == 'sqlite':
        raw = db.engine.raw_connection()
        try:
            migration.upgrade_sqlite(raw.driver_connection, keytab=keytab)
        finally:
            raw.close()
    else:
        with db.engine.begin() as conn:
            migration.upgrade_pg(conn, keytab=keytab)
    db.session.expire_all()


def _default():
    return WindowsEnrollmentProfile.query.filter_by(is_default=True).first()


def _columns(profile):
    return {c: getattr(profile, c) for c in PROFILE_COLUMNS}


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


@pytest.fixture
def clean_slate(app):
    """No default profile and none of the 2.x settings during the test; put back afterwards."""
    keys = MIGRATED_KEYS + ('xcep_enabled', 'wstep_enabled', 'kerberos_enabled', 'kerberos_spn')
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}
        parked = _default()
        parked_state = None
        if parked is not None:
            parked_state = (parked.id, parked.name, parked.realm)
            parked.is_default, parked.name, parked.realm = False, f'parked-{parked.id}', None
        SystemConfig.query.filter(SystemConfig.key.in_(MIGRATED_KEYS)).delete(synchronize_session=False)
        connector = ADConnectorConfig.get_singleton()
        connector_state = (connector.enabled, connector.base_dn) if connector is not None else None
        db.session.commit()
    yield
    with app.app_context():
        mine = WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.name.notlike('parked-%')).all()
        mine_ids = [p.id for p in mine if parked_state is None or p.id != parked_state[0]]
        Certificate.query.filter(Certificate.windows_profile_id.in_(mine_ids)).update(
            {'windows_profile_id': None}, synchronize_session=False)
        WindowsProfileTemplate.query.filter(WindowsProfileTemplate.profile_id.in_(mine_ids)).delete(
            synchronize_session=False)
        WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.id.in_(mine_ids)).delete(
            synchronize_session=False)
        db.session.flush()
        if parked_state is not None:
            parked = db.session.get(WindowsEnrollmentProfile, parked_state[0])
            parked.is_default, parked.name, parked.realm = True, parked_state[1], parked_state[2]
        for key, value in saved.items():
            if value is None:
                SystemConfig.query.filter_by(key=key).delete()
            else:
                _set(key, value)
        connector = ADConnectorConfig.get_singleton()
        if connector is not None and connector_state is not None:
            connector.enabled, connector.base_dn = connector_state
        db.session.commit()


@pytest.fixture
def two_cas(app, create_ca):
    """An issuing CA and a policy CA, a template pinned to the policy CA."""
    issuing, policy = create_ca(cn='C01 issuing CA'), create_ca(cn='C01 policy CA')
    with app.app_context():
        template = CertificateTemplate(name='C01 pinned template', template_type='client_auth',
                                       key_type='RSA-2048', validity_days=90, digest='sha256',
                                       extensions_template='{"extended_key_usage": ["clientAuth"]}',
                                       is_active=True)
        db.session.add(template)
        db.session.commit()
        db.session.add(CATemplatePin(ca_id=policy['id'], template_id=template.id))
        db.session.commit()
        template_id = template.id
    yield issuing, policy, template_id
    with app.app_context():
        CATemplatePin.query.filter_by(template_id=template_id).delete()
        WindowsProfileTemplate.query.filter_by(template_id=template_id).delete()
        delete_templates([template_id])
        db.session.commit()


def _settings_2x(issuing, policy):
    from utils.password_hash import hash_password
    return {'xcep_enabled': 'true', 'xcep_ca_refid': policy['refid'], 'xcep_username': USER,
            'xcep_password': hash_password(PASSWORD), 'wstep_enabled': 'true',
            'wstep_ca_refid': issuing['refid'], 'wstep_username': 'c01-ces-user',
            'wstep_password': hash_password('c01-ces-password'), 'wstep_validity_days': '42',
            'kerberos_enabled': 'false', 'kerberos_spn': 'HTTP/ucm.c01.example@C01.EXAMPLE'}


def _get_policies_as_2x(app):
    """GetPolicies as 2.x answered it from its settings (api/xcep_protocol.py at 2.253)."""
    from services.wstep import CES_CERTIFICATE_PATH, CES_USERNAME_PASSWORD_PATH
    from services.xcep.policy_builder import (AUTH_CLIENT_CERTIFICATE, AUTH_USERNAME_PASSWORD,
                                              build_get_policies_response)
    with app.test_request_context(XCEP_URL, base_url='http://localhost'):
        from flask import request
        ca = CA.query.filter_by(refid=SystemConfig.query.filter_by(key='xcep_ca_refid').one().value).one()
        base = request.url_root.rstrip('/')
        uris = [(AUTH_USERNAME_PASSWORD, f'{base}{CES_USERNAME_PASSWORD_PATH}', False),
                (AUTH_CLIENT_CERTIFICATE, f'{base}{CES_CERTIFICATE_PATH}', True)]
        return build_get_policies_response(ca, CertificateTemplate.query.filter_by(is_active=True).all(),
                                           enrollment_uris=uris, message_id=MESSAGE_ID, ad_identity=False)


def test_get_policies_is_byte_identical_after_the_migration(app, client, clean_slate, two_cas, monkeypatch):
    """Same policyID, same template OIDs, same bytes: the clients keep the policy they cached."""
    import types
    import uuid
    from services.wstep import soap_envelope
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: False)
    # The response's own MessageID is random: the same one before and after
    fixed = uuid.UUID('00000000-0000-4000-8000-000000000155')
    monkeypatch.setattr(soap_envelope, 'uuid', types.SimpleNamespace(uuid4=lambda: fixed))
    issuing, policy, _template = two_cas
    with app.app_context():
        for key, value in _settings_2x(issuing, policy).items():
            _set(key, value)
        db.session.commit()
        before = _get_policies_as_2x(app)
        _migrate_app_db()
        assert _default().policy_ca_refid == policy['refid']
    r = client.post(XCEP_URL, data=_envelope())
    assert r.status_code == 200, r.data
    assert r.data == before


def test_a_setting_the_profile_replaced_has_no_effect(app, client, clean_slate, two_cas, monkeypatch):
    """An old key written by hand is read by nothing: the policy and the account stay the profile's."""
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: False)
    issuing, policy, _template = two_cas
    with app.app_context():
        for key, value in _settings_2x(issuing, policy).items():
            _set(key, value)
        db.session.commit()
        _migrate_app_db()
        from utils.password_hash import hash_password
        for key, value in {'xcep_ca_refid': issuing['refid'], 'xcep_username': 'intruder',
                           'xcep_password': hash_password('intruder-pw'),
                           'wstep_ca_refid': policy['refid'], 'wstep_validity_days': '1'}.items():
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()
    r = client.post(XCEP_URL, data=_envelope())
    assert r.status_code == 200, r.data
    policy_id = etree.fromstring(r.data).find(f'.//{{{XCEP_NS}}}policyID').text
    from services.xcep.policy_builder import _policy_id_for_ca
    with app.app_context():
        assert policy_id == _policy_id_for_ca(CA.query.filter_by(refid=policy['refid']).one())
        from api.wstep_protocol import _resolve_wstep_ca, _validity_days
        with app.test_request_context('/'):
            assert _resolve_wstep_ca()[0].refid == issuing['refid'] and _validity_days() == 42
        SystemConfig.query.filter(SystemConfig.key.in_(MIGRATED_KEYS)).delete(synchronize_session=False)
        db.session.commit()
    assert client.post(XCEP_URL, data=_envelope('intruder', 'intruder-pw')).status_code == 400


def _string_constants(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def test_no_code_names_a_setting_the_profile_replaced():
    """Only the conversion from 2.x and the migration name them; nothing else can read them."""
    allowed = {BACKEND / 'services' / 'windows_profiles' / 'legacy.py'}
    found = []
    for path in BACKEND.rglob('*.py'):
        relative = path.relative_to(BACKEND).parts
        if relative[0] in ('tests', 'migrations') or '.venv' in relative or path in allowed:
            continue
        named = _string_constants(path) & set(MIGRATED_KEYS)
        if named:
            found.append(f'{"/".join(relative)}: {sorted(named)}')
    assert not found, found


def test_a_2x_archive_restores_as_the_profile_the_migration_makes(app, clean_slate, two_cas):
    """Same conversion: the default profile from a 2.x archive equals the one migration 155
    makes of the same settings, and its WSTEP certificate is attached to it."""
    from services.backup_service import BackupService
    from tests.backup_v3 import as_v3
    issuing, policy, _template = two_cas
    settings = _settings_2x(issuing, policy)
    with app.app_context():
        connector = ADConnectorConfig.get_singleton()
        if connector is None:
            connector = ADConnectorConfig(name='default', server='dc.c01.example')
            db.session.add(connector)
        connector.enabled, connector.base_dn = True, 'DC=c01,DC=example'
        cert = Certificate(refid='c01-wstep-cert', descr='c01 wstep', caref=issuing['refid'], source='wstep')
        db.session.add(cert)
        db.session.commit()
        connector_row = {'id': connector.id, 'enabled': True, 'base_dn': connector.base_dn}
        include = {name: name in ('configuration', 'ad_connector', 'certificates') for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)

    def as_2x(payload):
        payload['configuration']['settings'].update(settings)
        for row in payload['ad_connector']:
            row.pop('name', None)
            row.pop('domain_sid', None)
        payload['certificates'] = [r for r in payload['certificates'] if r['refid'] == 'c01-wstep-cert']
        for row in payload['certificates']:
            row.pop('windows_profile_id', None)
            row.pop('windows_profile_id_ref', None)
        payload.pop('windows_enrollment_profiles', None)
        payload.pop('windows_profile_templates', None)
        # What 2.x announced: the counts of its own sections, no digests of these
        payload['metadata'].pop('section_digests', None)
        payload['metadata']['sections'] = {name: len(rows) for name, rows in payload.items()
                                           if name in manifest.SECTIONS and isinstance(rows, (list, dict))}
    archive = as_v3(blob, BACKUP_PASSWORD, edit=as_2x)

    try:
        with app.app_context():
            Certificate.query.filter_by(refid='c01-wstep-cert').delete()
            db.session.commit()
            BackupService().restore_backup(archive, BACKUP_PASSWORD, mode='merge')
            db.session.expire_all()
            restored = _columns(_default())
            restored_cert = Certificate.query.filter_by(refid='c01-wstep-cert').one().windows_profile_id
            assert restored_cert == _default().id
            assert not SystemConfig.query.filter(SystemConfig.key.in_(MIGRATED_KEYS)).count()

            # The same settings on the same base, through the migration
            WindowsEnrollmentProfile.query.filter_by(id=_default().id).delete()
            for key, value in settings.items():
                _set(key, value)
            db.session.commit()
            _migrate_app_db()
            migrated = _columns(_default())
    finally:
        with app.app_context():
            Certificate.query.filter_by(refid='c01-wstep-cert').delete()
            db.session.commit()
    direct = profile_from_2x(settings, connector_row, None)
    assert restored == migrated == {c: direct[c] for c in PROFILE_COLUMNS}
    assert restored['realm'] == 'C01.EXAMPLE'


def test_a_30_archive_round_trip_keeps_the_profile(app, clean_slate, two_cas):
    from services.backup_service import BackupService
    issuing, policy, template_id = two_cas
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='ROUND.TRIP',
                                           issuing_ca_refid=issuing['refid'], policy_ca_refid=policy['refid'],
                                           validity_days=77, xcep_username='rt', allowed_ad_group='RT Group',
                                           pinned_subject_fields='{"O": "Round Trip"}')
        profile.set_keytab(b'\x05\x02round-trip-keytab')
        db.session.add(profile)
        db.session.flush()
        db.session.add(WindowsProfileTemplate(profile_id=profile.id, template_id=template_id))
        db.session.commit()
        before = _columns(profile)
        include = {name: name in ('windows_enrollment_profiles', 'windows_profile_templates')
                   for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)
        WindowsProfileTemplate.query.filter_by(profile_id=profile.id).delete()
        WindowsEnrollmentProfile.query.filter_by(id=profile.id).delete()
        db.session.commit()
        BackupService().restore_backup(blob, BACKUP_PASSWORD, mode='merge')
        db.session.expire_all()
        back = _default()
        assert _columns(back) | {'connector_id': None} == before | {'connector_id': None}
        assert (back.allowed_ad_group, back.pinned_subject_fields) == ('RT Group', '{"O": "Round Trip"}')
        assert back.keytab_bytes() == b'\x05\x02round-trip-keytab'
        assert [link.template_id for link in WindowsProfileTemplate.query.filter_by(profile_id=back.id)] == [template_id]


def test_a_ca_a_template_or_a_connector_used_by_a_profile_is_not_deleted(app, clean_slate, two_cas):
    from services.deletion_blockers import (ca_deletion_blockers, connector_deletion_blockers,
                                            first_blocker, template_deletion_blockers)
    issuing, policy, template_id = two_cas
    with app.app_context():
        # A connector of its own: a profile parked by the fixture may use the shared one
        connector = ADConnectorConfig(name='c01-blocker-connector')
        db.session.add(connector)
        db.session.flush()
        profile = WindowsEnrollmentProfile(name='default', is_default=True, connector_id=connector.id,
                                           issuing_ca_refid=issuing['refid'], policy_ca_refid=policy['refid'])
        db.session.add(profile)
        db.session.flush()
        db.session.add(WindowsProfileTemplate(profile_id=profile.id, template_id=template_id))
        db.session.commit()
        for ca in (issuing, policy):
            blocker = first_blocker(ca_deletion_blockers(db.session.get(CA, ca['id'])))
            assert blocker is not None and 'Windows enrollment profile' in blocker.message
        blocker = first_blocker(template_deletion_blockers(db.session.get(CertificateTemplate, template_id)))
        assert blocker is not None and 'Windows enrollment profile' in blocker.message
        assert first_blocker(connector_deletion_blockers(connector)) is not None
        profile.connector_id = None
        db.session.commit()
        assert first_blocker(connector_deletion_blockers(connector)) is None
        db.session.delete(connector)
        db.session.commit()


@pytest.fixture
def no_shared_keytab(app):
    """No keytab in shared_files during the test; the one there before is put back."""
    from models import SharedFile
    from services import shared_files
    with app.app_context():
        row = db.session.get(SharedFile, shared_files.KERBEROS_KEYTAB)
        saved = (row.content, row.updated_at, row.updated_by) if row is not None else None
        if row is not None:
            db.session.delete(row)
        db.session.commit()
    yield
    with app.app_context():
        SharedFile.query.filter_by(name=shared_files.KERBEROS_KEYTAB).delete()
        if saved is not None:
            db.session.add(SharedFile(name=shared_files.KERBEROS_KEYTAB, content=saved[0],
                                      updated_at=saved[1], updated_by=saved[2]))
        db.session.commit()


def _connector_as(state):
    """The shared connector row as a 2.x case wants it; None: as good as absent."""
    connector = ADConnectorConfig.get_singleton()
    if connector is None:
        connector = ADConnectorConfig(name='default', server='dc.c01.example')
        db.session.add(connector)
    connector.enabled, connector.base_dn = (state['enabled'], state['base_dn']) if state else (False, None)


def _fixed_message_id(monkeypatch):
    import types
    import uuid
    from services.wstep import soap_envelope
    fixed = uuid.UUID('00000000-0000-4000-8000-000000000155')
    monkeypatch.setattr(soap_envelope, 'uuid', types.SimpleNamespace(uuid4=lambda: fixed))


def _undeterminable():
    from tests.test_windows_profile_migration import UNDETERMINABLE
    return UNDETERMINABLE


@pytest.mark.parametrize('settings, connector, keytab', _undeterminable())
def test_an_undeterminable_realm_refuses_kerberos_only(app, client, auth_client, clean_slate, two_cas,
                                                       no_shared_keytab, monkeypatch, tmp_path,
                                                       settings, connector, keytab):
    """A1, the 2.x settings the review replayed: UsernamePassword (XCEP, WSTEP) and the renewal by
    certificate answer as 2.x did; Kerberos, which 2.x served with an SPN, is refused with its reason."""
    from api.wstep_protocol import _check_credentials, _resolve_wstep_ca, _validity_days
    _fixed_message_id(monkeypatch)
    issuing, policy, _template = two_cas
    path = tmp_path / 'kerberos.keytab'
    path.write_bytes(keytab)
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        _connector_as(connector)
        values = {**_settings_2x(issuing, policy), 'kerberos_enabled': 'true',
                  'kerberos_spn': settings['kerberos_spn']}
        for key, value in values.items():
            _set(key, value)
        db.session.commit()
        served_by_2x = bool(negotiate_auth.is_enabled() and negotiate_auth.get_spn() and path.exists())
        before = _get_policies_as_2x(app)
        _migrate_app_db(keytab=keytab)
        profile = _default()
        assert profile.realm is None and profile.enabled
        with app.test_request_context('/'):
            assert _check_credentials('c01-ces-user', 'c01-ces-password')
            assert _resolve_wstep_ca()[0].refid == issuing['refid'] and _validity_days() == 42
        assert negotiate_auth.is_configured() is False
    # 2.x also advertised the Kerberos CES when it served it: the only byte that differs
    r = client.post(XCEP_URL, data=_envelope())
    assert r.status_code == 200 and r.data == before
    reason = auth_client.get('/api/v2/kerberos/config').get_json()['data']['reason']
    assert reason == ('default profile has no realm: Kerberos refused until one is set'
                      if served_by_2x else 'no SPN set')


def test_the_realm_of_the_default_profile_is_set_through_the_kerberos_route(
        app, auth_client, clean_slate, two_cas, no_shared_keytab, monkeypatch, tmp_path):
    """The way out of A1's refusal: an explicit realm, in capitals, one the keytab names."""
    from tests.test_windows_profile_migration import TWO_REALMS
    issuing, policy, _template = two_cas
    path = tmp_path / 'kerberos.keytab'
    path.write_bytes(TWO_REALMS)
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        _connector_as(None)
        for key, value in {**_settings_2x(issuing, policy), 'kerberos_enabled': 'true',
                           'kerberos_spn': 'HTTP/ucm.example'}.items():
            _set(key, value)
        db.session.commit()
        _migrate_app_db(keytab=TWO_REALMS)
    # Capitals, keytab or not
    assert auth_client.patch('/api/v2/kerberos/config', json={'realm': 'two.example'}).status_code == 400
    with app.app_context():
        _default().set_keytab(TWO_REALMS)
        db.session.commit()
    for bad, status in (('two.example', 400), ('THREE.EXAMPLE', 400), ('', 400), (None, 400)):
        r = auth_client.patch('/api/v2/kerberos/config', json={'realm': bad})
        assert r.status_code == status, (bad, r.data)
    with app.app_context():
        assert _default().realm is None and negotiate_auth.is_configured() is False
    assert auth_client.patch('/api/v2/kerberos/config', json={'realm': 'TWO.EXAMPLE'}).status_code == 200
    data = auth_client.get('/api/v2/kerberos/config').get_json()['data']
    assert (data['realm'], data['configured'], data['reason']) == ('TWO.EXAMPLE', True, None)


@pytest.mark.parametrize('keytab, realm', [('ONE_REALM', 'EXAMPLE.TEST'), ('TWO_REALMS', None)],
                         ids=['one-realm', 'two-realms'])
def test_the_profile_is_the_same_whether_the_migration_reads_the_keytab_or_not(
        app, clean_slate, two_cas, no_shared_keytab, monkeypatch, tmp_path, caplog, keytab, realm):
    """Unread by the migration, the keytab is taken at startup with the same realm and warning."""
    from tests import test_windows_profile_migration as fixtures
    keytab = getattr(fixtures, keytab)
    issuing, policy, _template = two_cas
    path = tmp_path / 'kerberos.keytab'
    path.write_bytes(keytab)
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    settings = {**_settings_2x(issuing, policy), 'kerberos_enabled': 'true', 'kerberos_spn': 'HTTP/ucm.example'}
    seen = []
    for read in (True, False):
        with app.app_context():
            _connector_as(None)
            for key, value in settings.items():
                _set(key, value)
            db.session.commit()
            caplog.clear()
            with caplog.at_level('WARNING'):
                _migrate_app_db(keytab=keytab if read else b'')
        with caplog.at_level('WARNING'):
            negotiate_auth.restore_keytab_at_start(app)
        with app.app_context():
            profile = _default()
            seen.append((_columns(profile), profile.keytab_bytes(), 'has no realm' in caplog.text))
            WindowsEnrollmentProfile.query.filter_by(id=profile.id).delete()
            db.session.commit()
    assert seen[0] == seen[1]
    assert seen[0][0]['realm'] == realm and seen[0][0]['enabled'] and seen[0][1] == keytab
    assert seen[0][2] == (realm is None)
