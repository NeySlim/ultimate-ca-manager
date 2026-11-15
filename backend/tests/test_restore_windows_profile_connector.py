"""A merge whose default Windows profile names no connector keeps the link the target holds
when the archive does not say there is none (a 2.x archive written without its connectors);
an archive that carries its connectors, or a 3.0 profile without one, is restored as written."""
import pytest

from models import ADConnectorConfig, WindowsEnrollmentProfile, db
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_backup_hostile_corpus import PASSWORD, _forged, _service

SETTINGS_2X = {
    'xcep_enabled': 'true', 'wstep_enabled': 'true', 'wstep_validity_days': '30',
    'kerberos_enabled': 'true', 'kerberos_spn': 'HTTP/ucm.corp.example',
}


@pytest.fixture
def here(app, tmp_path):
    """An installation whose default profile is linked to its connector."""
    with _installation(app, f"sqlite:///{tmp_path / 'merge.db'}", Keys(tmp_path, 'merge')), \
            app.app_context():
        connector = ADConnectorConfig(name='target-dc', base_dn='DC=corp,DC=example', enabled=True)
        db.session.add(connector)
        db.session.flush()
        profile = WindowsEnrollmentProfile.query.filter_by(is_default=True).first()
        if profile is None:
            profile = WindowsEnrollmentProfile(name='default', is_default=True, enabled=True)
            db.session.add(profile)
        profile.connector_id, profile.realm = connector.id, 'CORP.EXAMPLE'
        db.session.commit()
        yield connector.id
        db.session.rollback()


def _as_2x(data, connectors=None):
    """The archive as 2.x wrote it: Windows settings in the configuration, no profiles."""
    data.pop('windows_enrollment_profiles', None)
    settings = data.setdefault('configuration', {}).setdefault('settings', {})
    settings.update(SETTINGS_2X)
    if connectors is not None:
        data['ad_connector'] = connectors
        excluded = data.get('metadata', {}).get('excluded_sections', [])
        if 'ad_connector' in excluded:
            excluded.remove('ad_connector')


def _default_connector():
    db.session.expire_all()
    return WindowsEnrollmentProfile.query.filter_by(is_default=True).one().connector_id


def test_a_2x_archive_without_its_connectors_keeps_the_targets_link(here):
    blob = _forged(['configuration'], mutate=_as_2x)
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _default_connector() == here


def test_a_2x_archive_saying_it_has_no_connector_is_restored_as_written(here):
    blob = _forged(['configuration'], mutate=lambda data: _as_2x(data, connectors=[]))
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _default_connector() is None


def test_a_30_profile_without_connector_is_merged_as_written(here):
    profile = WindowsEnrollmentProfile.query.filter_by(is_default=True).one()
    profile.connector_id = None
    db.session.commit()
    blob = _forged(['windows_enrollment_profiles'])
    profile.connector_id = here
    db.session.commit()
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _default_connector() is None
