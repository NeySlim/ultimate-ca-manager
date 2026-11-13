"""The default Windows enrollment profile in the running application (SQLite, and PostgreSQL
with UCM_TEST_APP_PG_URL): GetPolicies byte for byte after migration 155, a 2.x archive
restored as the same profile, the settings it replaced read nowhere, deletion refused while
a profile uses a row, and the A1 cases served or refused."""
import ast
import importlib
from pathlib import Path

import pytest
from lxml import etree

from tests.ad_connector_support import connector_row as lowest_connector_row
from models import (CA, ADConnectorConfig, Certificate, CATemplatePin, CertificateTemplate, SystemConfig,
                    WindowsEnrollmentProfile, WindowsProfileTemplate, db)
from services.backup import manifest
from services.kerberos import negotiate_auth
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS
from services.windows_profiles.legacy import MIGRATED_KEYS, profile_from_2x
from tests.fixtures.templates import delete_templates
from tests.windows_profile_support import upload_keytab

XCEP_URL = '/ADPolicyProvider_CEP_UsernamePassword/service.svc'
XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
USER, PASSWORD = 'c01-cep-user', 'c01-cep-password'
MESSAGE_ID = 'urn:uuid:5e3c01aa-0000-4000-8000-000000000155'
BACKUP_PASSWORD = 'C01-backup-password-155'
PROFILE_COLUMNS = ('name', 'realm', 'is_default', 'enabled', 'connector_id', 'issuing_ca_refid',
                   'policy_ca_refid', 'validity_days', 'xcep_username', 'xcep_password',
                   'wstep_username', 'wstep_password')
BACKEND = Path(__file__).resolve().parents[1]
# The CAs two_cas makes are this file's: the leak guard sees the session's tables unchanged
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


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
    migration = importlib.import_module('migrations._from_2_254.155_windows_enrollment_profiles')
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
        connector = lowest_connector_row()
        connector_state = (connector.enabled, connector.base_dn) if connector is not None else None
        connectors = {c.id for c in ADConnectorConfig.query.all()}
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
        # A connector left enabled serves its realm to the next file's Kerberos tests
        added = [c.id for c in ADConnectorConfig.query.all() if c.id not in connectors]
        WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.connector_id.in_(added)).update(
            {'connector_id': None}, synchronize_session=False)
        ADConnectorConfig.query.filter(ADConnectorConfig.id.in_(added)).delete(synchronize_session=False)
        connector = lowest_connector_row()
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
        from services.windows_profiles import serving_profile
        with app.test_request_context('/'):
            assert _resolve_wstep_ca(serving_profile())[0].refid == issuing['refid'] and _validity_days(serving_profile()) == 42
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


def _2x_archive(app, settings, base_dn='DC=c01,DC=example', connector_enabled=True,
                sections=('configuration', 'ad_connector', 'certificates')):
    """An archive as 2.x wrote it: *settings* in the configuration, the connector unnamed,
    the WSTEP certificate ``c01-wstep-cert`` without a profile, no profile sections."""
    from services.backup_service import BackupService
    from tests.backup_v3 import as_v3
    with app.app_context():
        connector = lowest_connector_row()
        if connector is None:
            connector = ADConnectorConfig(name='default', server='dc.c01.example')
            db.session.add(connector)
        connector.enabled, connector.base_dn = connector_enabled, base_dn
        caref = settings.get('wstep_ca_refid')
        cert = Certificate(refid='c01-wstep-cert', descr='c01 wstep', caref=caref, source='wstep')
        db.session.add(cert)
        db.session.commit()
        connector_row = {'id': connector.id, 'enabled': connector_enabled, 'base_dn': base_dn}
        include = {name: name in sections for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)
        Certificate.query.filter_by(refid='c01-wstep-cert').delete()
        db.session.commit()

    def as_2x(payload):
        payload['configuration']['settings'].update(settings)
        for row in payload['ad_connector']:
            row.pop('name', None)
            row.pop('domain_sid', None)
        if 'certificates' in payload:
            payload['certificates'] = [r for r in payload['certificates'] if r['refid'] == 'c01-wstep-cert']
        for row in payload.get('certificates', ()):
            row.pop('windows_profile_id', None)
            row.pop('windows_profile_id_ref', None)
        payload.pop('windows_enrollment_profiles', None)
        payload.pop('windows_profile_templates', None)
        # What 2.x announced: the counts of its own sections, no digests of these
        payload['metadata'].pop('section_digests', None)
        payload['metadata']['sections'] = {name: len(rows) for name, rows in payload.items()
                                           if name in manifest.SECTIONS and isinstance(rows, (list, dict))}
    return as_v3(blob, BACKUP_PASSWORD, edit=as_2x), connector_row


def test_a_2x_archive_restores_as_the_profile_the_migration_makes(app, clean_slate, no_shared_keytab, two_cas):
    """Same conversion: the default profile from a 2.x archive equals the one migration 155
    makes of the same settings, and its WSTEP certificate is attached to it."""
    from services.backup_service import BackupService
    issuing, policy, _template = two_cas
    settings = _settings_2x(issuing, policy)
    archive, connector_row = _2x_archive(app, settings)
    try:
        with app.app_context():
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


@pytest.mark.parametrize('xcep_ca', ['', None], ids=['empty', 'absent'])
@pytest.mark.parametrize('route', ['migration', 'restore'])
def test_xcep_without_its_own_ca_is_switched_off(app, client, auth_client, clean_slate, no_shared_keytab,
                                                 two_cas,
                                                 monkeypatch, xcep_ca, route):
    """2.x answered GetPolicies 503 without an XCEP CA; the profile would serve the issuing CA's
    policy (A4): the switch goes off, the client still gets a 503 and no policy."""
    from services.backup_service import BackupService
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: False)
    issuing, policy, _template = two_cas
    settings = _settings_2x(issuing, policy)
    if xcep_ca is None:
        del settings['xcep_ca_refid']
    else:
        settings['xcep_ca_refid'] = xcep_ca
    with app.app_context():
        _set('xcep_enabled', 'true')
        SystemConfig.query.filter_by(key='xcep_ca_refid').delete()
        db.session.commit()
    if route == 'migration':
        with app.app_context():
            for key, value in settings.items():
                _set(key, value)
            db.session.commit()
            _migrate_app_db()
    else:
        archive, _connector = _2x_archive(app, settings)
        try:
            with app.app_context():
                BackupService().restore_backup(archive, BACKUP_PASSWORD, mode='merge')
        finally:
            with app.app_context():
                Certificate.query.filter_by(refid='c01-wstep-cert').delete()
                db.session.commit()
    r = client.post(XCEP_URL, data=_envelope())
    assert r.status_code == 503 and r.data == b'XCEP disabled'
    with app.app_context():
        from services import windows_profiles
        profile = windows_profiles.default_profile()
        assert not profile.policy_ca_refid
        assert windows_profiles.policy_ca(profile).refid == issuing['refid']
    # The operator who wants the issuing CA's policy switches XCEP on (A4)
    assert auth_client.patch('/api/v2/windows-profiles/settings', json={'xcep_enabled': True}).status_code == 200
    assert client.post(XCEP_URL, data=_envelope()).status_code == 200


def test_a_30_archive_round_trip_keeps_the_profile(app, clean_slate, no_shared_keytab, two_cas):
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
    connector = lowest_connector_row()
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
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    from api.wstep_protocol import _check_credentials, _resolve_wstep_ca, _validity_days
    from services.windows_profiles import kerberos_refusal, serving_profile
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
            assert _resolve_wstep_ca(serving_profile())[0].refid == issuing['refid'] and _validity_days(serving_profile()) == 42
        assert kerberos_refusal() is not None
    # 2.x also advertised the Kerberos CES when it served it: the only byte that differs
    r = client.post(XCEP_URL, data=_envelope())
    assert r.status_code == 200 and r.data == before
    with app.app_context():
        reason = negotiate_auth.not_configured_reason() or auth_client.get(
            f'/api/v2/windows-profiles/{_default().id}').get_json()['data']['kerberos_refusal']
    assert reason == ('default profile has no realm: Kerberos refused until one is set'
                      if served_by_2x else 'no SPN set')


def test_the_realm_of_the_default_profile_is_set_through_the_profile_api(
        app, auth_client, clean_slate, two_cas, no_shared_keytab, monkeypatch, tmp_path):
    """The way out of A1's refusal: an explicit realm, in capitals, one the keytab names."""
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
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
    with app.app_context():
        default_id = _default().id
        _default().set_keytab(TWO_REALMS)
        db.session.commit()
    url = f'/api/v2/windows-profiles/{default_id}'
    # A realm the keytab does not name, or none at all, leaves the profile without one
    for bad in ('THREE.EXAMPLE', ''):
        r = auth_client.put(url, json={'realm': bad})
        assert r.status_code == 400, (bad, r.data)
    with app.app_context():
        from services.windows_profiles import kerberos_refusal
        assert _default().realm is None and kerberos_refusal() is not None
    assert auth_client.put(url, json={'realm': 'two.example'}).status_code == 200
    data = auth_client.get(url).get_json()['data']
    assert (data['realm'], data['kerberos_refusal']) == ('TWO.EXAMPLE', None)


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


@pytest.mark.parametrize('keytab, realm', [('absent', 'CORP.EXAMPLE'), ('absent-in-ha', None),
                                           ('unread', None), ('read', None)])
def test_a_disabled_connector_names_the_realm_once_no_keytab_is_established(
        app, clean_slate, two_cas, no_shared_keytab, monkeypatch, tmp_path, keytab, realm):
    """The migration reads no keytab: the realm waits for the start, which takes the DN of the
    disabled connector only when no keytab exists; one it cannot take or that lacks it: none."""
    from config.settings import Config
    from tests.test_windows_profile_migration import TWO_REALMS
    issuing, policy, _template = two_cas
    path = tmp_path / 'kerberos.keytab'
    if not keytab.startswith('absent'):
        path.write_bytes(TWO_REALMS)
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    # A node's own file is not taken in HA, and a node without one cannot speak for the others
    monkeypatch.setattr(Config, 'HA_MODE', keytab in ('unread', 'absent-in-ha'))
    with app.app_context():
        _connector_as({'enabled': False, 'base_dn': 'DC=corp,DC=example'})
        for key, value in {**_settings_2x(issuing, policy), 'kerberos_enabled': 'true',
                           'kerberos_spn': 'HTTP/ucm.example'}.items():
            _set(key, value)
        db.session.commit()
        _migrate_app_db(keytab=b'')
        assert _default().realm is None
    negotiate_auth.restore_keytab_at_start(app)
    with app.app_context():
        assert _default().realm == realm


def test_an_uploaded_keytab_names_the_realm_before_a_disabled_connector(
        app, auth_client, clean_slate, no_shared_keytab, monkeypatch, tmp_path):
    """The upload reads the keytab it brings, as the migration does: its single realm wins over
    the DN of a disabled connector."""
    from tests.test_windows_profile_migration import ONE_REALM
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', tmp_path / 'kerberos.keytab')
    # GSSAPI is not what names the realm: the entries are read from the bytes
    monkeypatch.setattr(negotiate_auth, 'inspect_keytab', lambda *a, **k: {
        'valid': True, 'principal': 'HTTP/ucm.example@EXAMPLE.TEST', 'error': None})
    with app.app_context():
        _connector_as({'enabled': False, 'base_dn': 'DC=corp,DC=example'})
        _set('kerberos_spn', 'HTTP/testhost.example.test')
        db.session.commit()
    r = upload_keytab(auth_client, ONE_REALM, filename='k.keytab')
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _default().realm == 'EXAMPLE.TEST'


ARCHIVED_KEYTAB, TARGET_KEYTAB = b'\x05\x02keytab-of-the-archive', b'\x05\x02keytab-of-the-target'


@pytest.mark.parametrize('target', ['other-keytab', 'fresh'])
def test_the_keytab_of_a_restored_profile_is_served(app, clean_slate, no_shared_keytab, monkeypatch,
                                                    tmp_path, target):
    """The profile is the source (A7): its restored keytab becomes the shared file, this node's
    file, and a reload for the other nodes."""
    from config.settings import Config
    from models import ClusterCommand
    from services import cluster_commands, shared_files
    from services.backup_service import BackupService
    path = tmp_path / 'kerberos.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='KT.EXAMPLE')
        profile.set_keytab(ARCHIVED_KEYTAB)
        db.session.add(profile)
        db.session.commit()
        include = {name: name == 'windows_enrollment_profiles' for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)
        if target == 'fresh':
            db.session.delete(profile)
        else:
            profile.set_keytab(TARGET_KEYTAB)
            shared_files.store_file(shared_files.KERBEROS_KEYTAB, TARGET_KEYTAB)
            path.write_bytes(TARGET_KEYTAB)
        ClusterCommand.query.filter_by(kind=cluster_commands.RELOAD_KEYTAB).delete()
        db.session.commit()
    monkeypatch.setattr(Config, 'HA_MODE', True)
    try:
        with app.app_context():
            BackupService().restore_backup(blob, BACKUP_PASSWORD, mode='merge')
        with app.app_context():
            assert _default().keytab_bytes() == ARCHIVED_KEYTAB
            assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == ARCHIVED_KEYTAB
            assert ClusterCommand.query.filter_by(kind=cluster_commands.RELOAD_KEYTAB).count() == 1
        assert path.read_bytes() == ARCHIVED_KEYTAB
    finally:
        with app.app_context():
            ClusterCommand.query.filter_by(kind=cluster_commands.RELOAD_KEYTAB).delete()
            db.session.commit()


def test_a_keytab_that_cannot_be_served_is_in_the_report_and_the_log(app, clean_slate, no_shared_keytab,
                                                                    monkeypatch, tmp_path, caplog):
    from services import windows_profiles
    from services.backup_service import BackupService
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', tmp_path / 'kerberos.keytab')
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='KT.EXAMPLE')
        profile.set_keytab(ARCHIVED_KEYTAB)
        db.session.add(profile)
        db.session.commit()
        include = {name: name == 'windows_enrollment_profiles' for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)

    def undecryptable(actor='system'):
        raise ValueError('c01 keytab cannot be decrypted')
    monkeypatch.setattr(windows_profiles, 'publish_keytab', undecryptable)
    with app.app_context(), caplog.at_level('WARNING'):
        results = BackupService().restore_backup(blob, BACKUP_PASSWORD, mode='merge')
    expected = 'windows_enrollment_profiles: the keytab is not served: c01 keytab cannot be decrypted'
    assert expected in results['warnings']
    assert expected in caplog.text


def test_startup_rebuilds_a_shared_keytab_the_profile_does_not_hold(app, clean_slate, no_shared_keytab,
                                                                     monkeypatch, tmp_path):
    from config.settings import Config
    from services import shared_files
    monkeypatch.setattr(Config, 'HA_MODE', False)
    path = tmp_path / 'kerberos.keytab'
    path.write_bytes(TARGET_KEYTAB)
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='KT.EXAMPLE')
        profile.set_keytab(ARCHIVED_KEYTAB)
        db.session.add(profile)
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, TARGET_KEYTAB)
        db.session.commit()
    negotiate_auth.restore_keytab_at_start(app)
    with app.app_context():
        assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == ARCHIVED_KEYTAB
    assert path.read_bytes() == ARCHIVED_KEYTAB


def _another_node_created_the_default(monkeypatch, misses):
    """The default profile, committed by a concurrent writer after the first *misses* reads here."""
    from services import windows_profiles
    real = windows_profiles.default_profile
    calls = []

    def racing():
        calls.append(1)
        return None if len(calls) <= misses else real()
    monkeypatch.setattr(windows_profiles, 'default_profile', racing)


def test_a_concurrent_default_profile_is_the_one_written(app, auth_client, clean_slate, monkeypatch):
    with app.app_context():
        db.session.add(WindowsEnrollmentProfile(name='default', is_default=True, xcep_username='first'))
        db.session.commit()
    _another_node_created_the_default(monkeypatch, misses=1)
    with app.app_context():
        from services import windows_profiles
        windows_profiles.default_for_write('test').xcep_username = 'second'
        db.session.commit()
    with app.app_context():
        assert [p.xcep_username for p in WindowsEnrollmentProfile.query.filter_by(is_default=True)] == ['second']


def test_the_node_that_loses_the_race_writes_its_keytab_file(app, clean_slate, no_shared_keytab,
                                                              monkeypatch, tmp_path):
    from config.settings import Config
    from services import shared_files
    monkeypatch.setattr(Config, 'HA_MODE', False)
    path = tmp_path / 'kerberos.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        db.session.add(WindowsEnrollmentProfile(name='default', is_default=True))
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, TARGET_KEYTAB)
        db.session.commit()
    _another_node_created_the_default(monkeypatch, misses=2)
    negotiate_auth.restore_keytab_at_start(app)
    assert path.read_bytes() == TARGET_KEYTAB
    with app.app_context():
        assert _default().keytab_bytes() == TARGET_KEYTAB


def _committed_elsewhere(content, insert):
    """Another node's transaction on shared_files, committed outside this session."""
    from sqlalchemy import insert as sql_insert, update
    from models import SharedFile
    from services import shared_files
    from utils.key_codec import store_pem_bytes
    table = SharedFile.__table__
    with db.engine.begin() as conn:
        if insert:
            conn.execute(sql_insert(table).values(name=shared_files.KERBEROS_KEYTAB,
                                                  content=store_pem_bytes(content), updated_by='other-node'))
        else:
            conn.execute(update(table).where(table.c.name == shared_files.KERBEROS_KEYTAB).values(
                content=store_pem_bytes(content), updated_by='other-node'))


def test_the_node_that_loses_the_keytab_insert_writes_its_file(app, clean_slate, no_shared_keytab,
                                                                monkeypatch, tmp_path, caplog):
    """Two nodes rebuild the missing shared keytab at once: the one whose insert collides keeps
    the other's row and still writes its own file."""
    from config.settings import Config
    from models import SharedFile
    from services import shared_files
    from utils.key_codec import store_pem_bytes
    monkeypatch.setattr(Config, 'HA_MODE', False)
    path = tmp_path / 'kerberos.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='KT.EXAMPLE')
        profile.set_keytab(ARCHIVED_KEYTAB)
        db.session.add(profile)
        db.session.commit()
    real, raced = shared_files.store_file, []

    def colliding(name, data, actor=None):
        if raced:
            return real(name, data, actor)
        # This node looked and found no row; the other node's insert commits before its own
        raced.append(1)
        _committed_elsewhere(data, insert=True)
        row = SharedFile(name=name, content=store_pem_bytes(data))
        db.session.add(row)
        return row
    monkeypatch.setattr(shared_files, 'store_file', colliding)
    with caplog.at_level('ERROR'):
        negotiate_auth.restore_keytab_at_start(app)
    assert raced and path.read_bytes() == ARCHIVED_KEYTAB
    assert 'not restored' not in caplog.text
    with app.app_context():
        assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == ARCHIVED_KEYTAB


@pytest.mark.parametrize('raced, reloads', [(False, 1), (True, 0)], ids=['alone', 'other-node-first'])
def test_a_start_queues_a_reload_only_when_it_changed_the_keytab(app, clean_slate, no_shared_keytab,
                                                                 monkeypatch, tmp_path, raced, reloads):
    """HA: a node starting with a stale shared keytab rebuilds it and asks the others to reload;
    when another node rebuilt it in the meantime, the content is unchanged and nothing is queued."""
    from config.settings import Config
    from models import ClusterCommand
    from services import cluster_commands, shared_files
    monkeypatch.setattr(Config, 'HA_MODE', True)
    path = tmp_path / 'kerberos.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='KT.EXAMPLE')
        profile.set_keytab(ARCHIVED_KEYTAB)
        db.session.add(profile)
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, TARGET_KEYTAB)
        ClusterCommand.query.filter_by(kind=cluster_commands.RELOAD_KEYTAB).delete()
        db.session.commit()
    from services import windows_profiles
    real, holders, reads = shared_files.read_file, windows_profiles.keytab_holders, []

    def stale_then_rebuilt():
        value = holders()
        if raced and not reads:
            # This node read the profiles; the other node's rebuild commits right after
            _committed_elsewhere(ARCHIVED_KEYTAB, insert=False)
        reads.append(1)
        return value
    monkeypatch.setattr(windows_profiles, 'keytab_holders', stale_then_rebuilt)
    try:
        negotiate_auth.restore_keytab_at_start(app)
        with app.app_context():
            assert real(shared_files.KERBEROS_KEYTAB) == ARCHIVED_KEYTAB
            assert ClusterCommand.query.filter_by(kind=cluster_commands.RELOAD_KEYTAB).count() == reloads
        assert path.read_bytes() == ARCHIVED_KEYTAB
    finally:
        with app.app_context():
            ClusterCommand.query.filter_by(kind=cluster_commands.RELOAD_KEYTAB).delete()
            db.session.commit()


def test_a_failed_rebuild_still_writes_the_stored_keytab_file(app, clean_slate, no_shared_keytab,
                                                              monkeypatch, tmp_path):
    from config.settings import Config
    from services import shared_files
    monkeypatch.setattr(Config, 'HA_MODE', False)
    path = tmp_path / 'kerberos.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', path)
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='KT.EXAMPLE')
        profile.set_keytab(ARCHIVED_KEYTAB)
        db.session.add(profile)
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, TARGET_KEYTAB)
        db.session.commit()

    def failing():
        raise RuntimeError('c01 rebuild failed')
    monkeypatch.setattr(negotiate_auth, '_rebuild_shared_keytab', failing)
    negotiate_auth.restore_keytab_at_start(app)
    assert path.read_bytes() == TARGET_KEYTAB


def _restore(app, archive, mode='merge'):
    from services.backup_service import BackupService
    try:
        with app.app_context():
            return BackupService().restore_backup(archive, BACKUP_PASSWORD, mode=mode)
    finally:
        with app.app_context():
            Certificate.query.filter_by(refid='c01-wstep-cert').delete()
            db.session.commit()


def test_a_2x_archive_with_only_kerberos_gets_the_profile_the_migration_makes(app, clean_slate, no_shared_keytab):
    """One criterion on both sides: an SPN alone was a Windows configuration to carry."""
    settings = {'kerberos_enabled': 'true', 'kerberos_spn': 'HTTP/ucm.c01.example@C01.EXAMPLE'}
    archive, _connector = _2x_archive(app, settings)
    _restore(app, archive)
    with app.app_context():
        restored = _default()
        assert restored is not None
        restored = _columns(restored)
        WindowsEnrollmentProfile.query.filter_by(is_default=True).delete()
        for key, value in settings.items():
            _set(key, value)
        db.session.commit()
        _migrate_app_db()
        assert _columns(_default()) == restored
    assert restored['realm'] == 'C01.EXAMPLE' and restored['enabled']


def test_a_30_archive_without_the_profiles_section_creates_none(app, clean_slate, no_shared_keytab):
    from services.backup_service import BackupService
    with app.app_context():
        _set('kerberos_spn', 'HTTP/ucm.c01.example@C01.EXAMPLE')
        db.session.commit()
        include = {name: name == 'configuration' for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)
    _restore(app, blob)
    with app.app_context():
        assert _default() is None


def test_a_converted_realm_the_keytab_here_lacks_is_reported(app, clean_slate, no_shared_keytab, two_cas):
    from tests.test_windows_profile_migration import ONE_REALM
    issuing, policy, _template = two_cas
    with app.app_context():
        # This installation's keytab, kept by the profile that the restore converts again
        profile = WindowsEnrollmentProfile(name='default', is_default=True)
        profile.set_keytab(ONE_REALM)
        db.session.add(profile)
        db.session.commit()
    archive, _connector = _2x_archive(app, _settings_2x(issuing, policy))
    results = _restore(app, archive)
    assert any('C01.EXAMPLE' in w and 'EXAMPLE.TEST' in w for w in results['warnings']), results['warnings']


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_a_2x_archive_without_windows_settings_leaves_the_profile_here(app, clean_slate, two_cas,
                                                                       no_shared_keytab, mode):
    """The archive alone decides whether it carries a configuration: the keytab of this installation
    does not, so no profile section is made and neither mode touches the profile here."""
    from tests.test_windows_profile_migration import ONE_REALM
    issuing, policy, _template = two_cas
    archive, connector_row = _2x_archive(app, {'kerberos_spn': ''}, sections=('configuration', 'ad_connector'))
    with app.app_context():
        profile = WindowsEnrollmentProfile(
            name='default', is_default=True, realm='EXAMPLE.TEST', connector_id=connector_row['id'],
            issuing_ca_refid=issuing['refid'], policy_ca_refid=policy['refid'], validity_days=42,
            xcep_username=USER, xcep_password='hashed-cep', wstep_username='c01-ces-user',
            wstep_password='hashed-ces')
        profile.set_keytab(ONE_REALM)
        db.session.add(profile)
        db.session.commit()
        before = _columns(profile)
    _restore(app, archive, mode=mode)
    with app.app_context():
        assert WindowsEnrollmentProfile.query.filter_by(name='default').count() == 1
        assert _columns(_default()) == before and _default().keytab_bytes() == ONE_REALM


@pytest.fixture
def own_connector(app):
    """A connector of this test and the default profile using it; the shared row is untouched."""
    with app.app_context():
        connector = ADConnectorConfig(name='c01-replace-connector', server='dc.replace.example',
                                      base_dn='DC=replace,DC=example', enabled=True)
        db.session.add(connector)
        db.session.flush()
        db.session.add(WindowsEnrollmentProfile(name='default', is_default=True, realm='REPLACE.EXAMPLE',
                                                connector_id=connector.id))
        db.session.commit()
        connector_id = connector.id
    yield connector_id
    with app.app_context():
        WindowsEnrollmentProfile.query.filter_by(connector_id=connector_id).update({'connector_id': None})
        ADConnectorConfig.query.filter_by(id=connector_id).delete()
        db.session.commit()


def _replace_with(app, sections, edit):
    """A replacing restore of an archive of *sections* from here, *edit* applied to its payload."""
    from services.backup_service import BackupService
    from tests.backup_v3 import as_v3
    with app.app_context():
        include = {name: name in sections for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)
    archive = as_v3(blob, BACKUP_PASSWORD, edit=edit)
    with app.app_context():
        return BackupService().restore_backup(archive, BACKUP_PASSWORD, mode='replace')


def _without_connector(name):
    def edit(payload):
        payload['ad_connector'] = [r for r in payload['ad_connector'] if r.get('name') != name]
        payload['metadata'].pop('section_digests', None)
        payload['metadata']['sections']['ad_connector'] = len(payload['ad_connector'])
    return edit


@pytest.mark.parametrize('sections', [('ad_connector',), ('ad_connector', 'windows_enrollment_profiles')],
                         ids=['profiles-not-carried', 'profiles-carried'])
def test_a_replacing_restore_keeps_a_connector_a_profile_still_uses(app, clean_slate, no_shared_keytab,
                                                                    own_connector, sections):
    """A connector the restore would remove while a profile it keeps or restores still names it:
    refused, never a profile with a dangling connector nor one that silently lost it."""
    from services.backup.restore.conflict import RestoreConflictError
    with pytest.raises(RestoreConflictError) as refused:
        _replace_with(app, sections, _without_connector('c01-replace-connector'))
    assert 'removes ad_connector name=c01-replace-connector' in str(refused.value)
    with app.app_context():
        assert db.session.get(ADConnectorConfig, own_connector) is not None
        assert _default().connector_id == own_connector


def test_a_replacing_restore_removes_a_connector_no_profile_uses(app, clean_slate, no_shared_keytab, own_connector):
    def edit(payload):
        _without_connector('c01-replace-connector')(payload)
        for row in payload['windows_enrollment_profiles']:
            row['connector_id'] = None
            row.pop('connector_id_ref', None)
    _replace_with(app, ('ad_connector', 'windows_enrollment_profiles'), edit)
    with app.app_context():
        assert db.session.get(ADConnectorConfig, own_connector) is None
        assert _default().connector_id is None


def test_a_2x_archive_takes_the_realm_of_its_own_connector(app, clean_slate, no_shared_keytab, two_cas):
    """No realm in the SPN, no keytab: only the archive's connector names it."""
    issuing, policy, _template = two_cas
    settings = {**_settings_2x(issuing, policy), 'kerberos_spn': 'HTTP/ucm.c01.example'}
    archive, _connector = _2x_archive(app, settings, base_dn='DC=archived,DC=example')
    with app.app_context():
        lowest_connector_row().base_dn = 'DC=target,DC=example'
        db.session.commit()
    _restore(app, archive)
    with app.app_context():
        assert _default().realm == 'ARCHIVED.EXAMPLE'


def _raw_keytab(profile_id):
    from sqlalchemy import text
    return db.session.execute(text("SELECT keytab FROM windows_enrollment_profiles WHERE id = :i"),
                              {'i': profile_id}).scalar()


def test_the_keytab_column_is_stored_under_the_master_key(app, clean_slate, no_shared_keytab, encryption_enabled):
    import base64
    from services.backup_service import BackupService
    is_encrypted = encryption_enabled.key_encryption.is_encrypted
    plain = base64.b64encode(ARCHIVED_KEYTAB).decode()
    with app.app_context():
        profile = WindowsEnrollmentProfile(name='default', is_default=True, realm='KT.EXAMPLE')
        profile.set_keytab(ARCHIVED_KEYTAB)
        db.session.add(profile)
        db.session.commit()
        raw = _raw_keytab(profile.id)
        assert raw != plain and is_encrypted(raw)
        include = {name: name == 'windows_enrollment_profiles' for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)
        db.session.delete(profile)
        db.session.commit()
        BackupService().restore_backup(blob, BACKUP_PASSWORD, mode='merge')
        db.session.expire_all()
        raw = _raw_keytab(_default().id)
        assert raw != plain and is_encrypted(raw)
        assert _default().keytab_bytes() == ARCHIVED_KEYTAB


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_a_restore_of_the_connectors_alone_gives_them_to_a_default_profile_without_one(
        app, clean_slate, no_shared_keytab, mode):
    """As a created connector does: the protocols must not be left without the connector the screen shows."""
    from services import windows_profiles
    from services.backup_service import BackupService
    with app.app_context():
        db.session.add(ADConnectorConfig(name='c02b-restored', server='dc.restored.example',
                                         base_dn='DC=restored,DC=example'))
        db.session.commit()
        include = {name: name == 'ad_connector' for name in manifest.SECTIONS}
        blob = BackupService().create_backup(BACKUP_PASSWORD, include=include)
        ADConnectorConfig.query.filter_by(name='c02b-restored').delete()
        db.session.add(WindowsEnrollmentProfile(name='default', is_default=True, realm='RESTORED.EXAMPLE'))
        db.session.commit()
    _restore(app, blob, mode=mode)
    with app.app_context():
        lowest = windows_profiles.lowest_connector()
        assert lowest is not None and _default().connector_id == lowest.id
