"""An archive older than a repair migration is repaired again once restored.

Restores run after the migrations, so an archive from before 101 to 105 put
back what they had cleaned: the legacy EAB blob, dead settings and a bind
password, SAML providers signing requests UCM never signed, group permissions
stored as text. Each repair touches only what the restore wrote.
"""
import json
import uuid

import pytest

from models import SystemConfig, db
from models.acme_models import AcmeEabCredential
from models.certificate_template import CertificateTemplate
from models.group import Group
from models.policy import CertificatePolicy
from models.sso import SSOProvider
from services.backup.restore.repairs import REPAIRS
from tests.test_backup_restore_failfast import _reseal
from tests.test_restore_replace_dependents import PASSWORD, _only, _service, _target

SECTIONS = ('configuration', 'certificate_templates', 'certificate_policies',
            'sso_providers', 'groups')


@pytest.fixture
def target(app, tmp_path):
    with _target(app, 'sqlite', tmp_path, f'repairs_{uuid.uuid4().hex[:8]}'):
        yield


def _seed():
    db.session.add_all([
        CertificateTemplate(name='VPN Client', template_type='vpn_client', is_system=True,
                            extensions_template=json.dumps({'san_types': ['email']})),
        CertificatePolicy(name='lot7-policy',
                          rules=json.dumps({'required_extensions': ['x'], 'max_validity_days': 30})),
        SSOProvider(name='lot7-saml', provider_type='saml', saml_sign_requests=True),
        Group(name='lot7-group', permissions=['read:certificates', 'admin:system']),
    ])
    db.session.commit()


def _archive(older):
    """An archive of this installation, in the shape a pre-101..105 one has when `older`."""
    svc = _service()
    blob = svc.create_backup(PASSWORD, include=_only(*SECTIONS))
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    if older:
        data['configuration']['settings'].update({
            'acme_eab_keys': json.dumps({'lot7-kid': 'bG90Ny1rZXk='}),
            'site_name': 'Old PKI', 'scep_url': 'http://old.example.test/scep',
            'ldap_bind_password': 'lot7-bind-secret'})
        for row in data['certificate_templates']:
            row.pop('enforce_san_types', None)
        for row in data['sso_providers']:
            row.pop('saml_allow_idp_initiated', None)
        for row in data['groups']:
            row['permissions'] = json.dumps(row['permissions'])
    return _reseal(blob, data)


def _state():
    settings = {row.key: row.value for row in SystemConfig.query.all()}
    template = CertificateTemplate.query.filter_by(name='VPN Client').one()
    provider = SSOProvider.query.filter_by(name='lot7-saml').one()
    return {
        '101_acme_eab_keys_import': (AcmeEabCredential.query.filter_by(kid='lot7-kid').count(),
                                     'acme_eab_keys' in settings),
        '102_dead_settings': (settings.get('system_name'), 'site_name' in settings,
                              'scep_url' in settings,
                              json.loads(template.extensions_template)['san_types'],
                              'required_extensions' in json.loads(
                                  CertificatePolicy.query.filter_by(name='lot7-policy').one().rules)),
        '103_saml_strict': (provider.saml_allow_idp_initiated, provider.saml_sign_requests),
        '104_group_permissions_lists': Group.query.filter_by(name='lot7-group').one().permissions,
        '105_legacy_ldap_settings': 'ldap_bind_password' in settings,
    }


REPAIRED = {
    '101_acme_eab_keys_import': (1, False),
    '102_dead_settings': ('Old PKI', False, False, ['dns', 'email', 'upn'], False),
    '103_saml_strict': (True, False),
    '104_group_permissions_lists': ['read:certificates'],
    '105_legacy_ldap_settings': False,
}


@pytest.mark.parametrize('migration', sorted(REPAIRED))
def test_an_older_archive_is_repaired_once_restored(target, migration):
    _seed()
    _service().restore_backup(_archive(older=True), PASSWORD, mode='merge')
    db.session.expire_all()
    assert _state()[migration] == REPAIRED[migration]


def test_a_current_archive_is_left_as_it_is(target):
    _seed()
    before = _state()
    results = _service().restore_backup(_archive(older=False), PASSWORD, mode='merge')
    db.session.expire_all()
    # Policy rules lose dead keys whatever the archive's age: nothing reads them
    before['102_dead_settings'] = before['102_dead_settings'][:4] + (False,)
    assert _state() == before
    assert set(results['repairs']) == {'102_dead_settings'}


def test_every_declared_repair_is_characterised():
    # 121 is characterised in test_backup_acme_orders_and_requests (doubled renewals restored)
    assert {repair.migration for repair in REPAIRS} == set(REPAIRED) | {'121_acme_renewal_order_duplicates'}
