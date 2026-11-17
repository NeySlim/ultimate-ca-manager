"""Restoring a 2.x archive whose TSA signs with its CA keeps that signer, as migration 162 does;
a 3.0 archive, or any other 2.x TSA, is restored without the compatibility setting."""
import os
import uuid
from contextlib import contextmanager

import pytest

from models import CA, SystemConfig, db
from services.backup.restore.tsa_signer import upgrade_archived_tsa_signer
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_backup_hostile_corpus import PASSWORD, _forged, _service

KEY = 'tsa_require_dedicated_cert'
CA_REFID = 'archived-tsa-ca'


def _archive(settings, cas=(CA_REFID,), v30=False):
    data = {'configuration': {'settings': dict(settings)},
            'certificate_authorities': [{'refid': r} for r in cas]}
    if v30:
        data['windows_enrollment_profiles'] = []
    return data


@pytest.mark.parametrize('settings,cas,v30,written', [
    ({'tsa_ca_refid': CA_REFID}, (CA_REFID,), False, True),
    ({'tsa_enabled': 'true', 'tsa_ca_refid': CA_REFID, 'tsa_signer_cert_refid': ''}, (CA_REFID,), False, True),
    ({'tsa_ca_refid': CA_REFID}, (CA_REFID,), True, False),
    ({'tsa_ca_refid': CA_REFID, 'tsa_signer_cert_refid': 'cert-1'}, (CA_REFID,), False, False),
    ({'tsa_enabled': 'false', 'tsa_ca_refid': CA_REFID}, (CA_REFID,), False, False),
    ({'tsa_ca_refid': CA_REFID, KEY: 'true'}, (CA_REFID,), False, False),
    ({'tsa_ca_refid': ''}, (CA_REFID,), False, False),
    ({'tsa_ca_refid': CA_REFID}, (), False, False),
    ({'tsa_enabled': None, 'tsa_ca_refid': CA_REFID}, (CA_REFID,), False, False),
    ({'tsa_enabled': ' true', 'tsa_ca_refid': CA_REFID}, (CA_REFID,), False, False),
    ({'tsa_enabled': 'TRUE', 'tsa_ca_refid': CA_REFID}, (CA_REFID,), False, True),
    ({'tsa_ca_refid': CA_REFID, KEY: ''}, (CA_REFID,), False, True),
    ({'tsa_ca_refid': CA_REFID, KEY: None}, (CA_REFID,), False, True),
    ({'tsa_ca_refid': CA_REFID, KEY: 'no'}, (CA_REFID,), False, True),
    ({'tsa_ca_refid': CA_REFID, KEY: ' true'}, (CA_REFID,), False, True),
    ({'tsa_ca_refid': CA_REFID, KEY: 'TRUE'}, (CA_REFID,), False, False),
    ({'tsa_enabled': 'false', 'tsa_ca_refid': CA_REFID, KEY: 'no'}, (CA_REFID,), False, False),
], ids=['default_on', 'explicit', 'v30_archive', 'dedicated', 'disabled', 'key_set', 'no_ca', 'ca_unknown',
        'enabled_null', 'enabled_padded', 'enabled_upper', 'key_empty', 'key_null', 'key_no', 'key_padded',
        'key_upper_true', 'key_no_disabled'])
def test_the_rule_on_the_archived_settings(app, settings, cas, v30, written):
    data = _archive(settings, cas, v30)
    with app.app_context():
        assert upgrade_archived_tsa_signer(data) is written
    expected = {**settings, KEY: 'false'} if written else settings
    assert data['configuration']['settings'] == expected


def test_a_ca_of_this_installation_counts(app, create_ca):
    ca = create_ca(cn='restore-tsa-here')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
        data = _archive({'tsa_ca_refid': refid}, cas=())
        assert upgrade_archived_tsa_signer(data) is True


_PG_URL = os.environ.get('UCM_TEST_PG_URL')
ENGINES = ['sqlite', pytest.param('postgresql', marks=[
    pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')])]


@contextmanager
def _database(engine, tmp_path):
    if engine == 'sqlite':
        yield f"sqlite:///{tmp_path / 'tsa-restore.db'}"
        return
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'tsa_restore_{uuid.uuid4().hex[:6]}') as url:
        yield url


@pytest.fixture(params=ENGINES)
def here(app, tmp_path, request):
    """A separate installation holding the CA the archived TSA names."""
    with _database(request.param, tmp_path) as url, \
            _installation(app, url, Keys(tmp_path, 'tsa'), is_postgresql=request.param != 'sqlite'), \
            app.app_context():
        db.session.add(CA(refid=CA_REFID, descr='archived TSA CA', crt='', subject='CN=archived TSA CA'))
        SystemConfig.query.filter(SystemConfig.key.in_(
            ['tsa_enabled', 'tsa_ca_refid', 'tsa_signer_cert_refid', KEY])).delete(synchronize_session=False)
        db.session.commit()
        yield
        db.session.rollback()


def _as_2x_tsa(data):
    data.pop('windows_enrollment_profiles', None)
    settings = data.setdefault('configuration', {}).setdefault('settings', {})
    settings.pop(KEY, None)
    settings.update({'tsa_enabled': 'true', 'tsa_ca_refid': CA_REFID, 'tsa_signer_cert_refid': ''})


def _stored():
    db.session.expire_all()
    row = SystemConfig.query.filter_by(key=KEY).first()
    return row.value if row else None


def test_a_2x_archive_keeps_its_ca_signer(here):
    blob = _forged(['configuration'], mutate=_as_2x_tsa)
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _stored() == 'false'


def test_a_30_archive_is_restored_without_the_setting(here):
    def as_30(data):
        _as_2x_tsa(data)
        data['windows_enrollment_profiles'] = []
    blob = _forged(['configuration'], mutate=as_30)
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _stored() is None


def test_a_2x_archive_with_a_windows_configuration_keeps_its_ca_signer(here):
    """The Windows conversion adds the section that marks a 3.0 archive: the TSA rule runs first."""
    def with_windows(data):
        _as_2x_tsa(data)
        data['configuration']['settings']['kerberos_spn'] = 'HTTP/ucm.example.test@EXAMPLE.TEST'
    blob = _forged(['configuration'], mutate=with_windows)
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _stored() == 'false'


@pytest.mark.parametrize('archived,stored', [('', 'false'), ('no', 'false'), ('true', 'true')])
def test_a_2x_archive_whose_key_read_as_no_keeps_its_ca_signer(here, archived, stored):
    """2.x read the key as lower() == 'true': any other row signed with the CA, so it is restored as false."""
    def with_key(data):
        _as_2x_tsa(data)
        data['configuration']['settings'][KEY] = archived
    blob = _forged(['configuration'], mutate=with_key)
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _stored() == stored


@pytest.mark.parametrize('enabled', [None, ' true'])
def test_a_2x_archive_whose_tsa_was_off_is_restored_without_the_setting(here, enabled):
    def with_enabled(data):
        _as_2x_tsa(data)
        data['configuration']['settings']['tsa_enabled'] = enabled
    blob = _forged(['configuration'], mutate=with_enabled)
    _service().restore_backup(blob, PASSWORD, mode='merge')
    assert _stored() is None
