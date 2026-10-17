"""NTLM (MD4/MD5 outside the module) is refused for the WinRM channel in FIPS
mode: when configured, and when a stored NTLM connection is used."""
import pytest

import fips_mode
from tests.test_msca_admin_channel import BASE, _make_msca_cert, post_json, put_json


@pytest.fixture
def fips(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def no_winrm_call(monkeypatch):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin

    def forbidden(cfg, script):
        raise AssertionError('WinRM contacted')
    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(forbidden))


def _assert_fips_refusal(r):
    body = r.get_json()
    assert r.status_code == 400, r.data
    assert body['type'] == fips_mode.PROBLEM_TYPE
    assert body['message'] == 'NTLM for the WinRM channel not available in FIPS mode'


def test_testing_an_ntlm_channel_is_refused(app, auth_client, fips, no_winrm_call):
    msca_id, _, _ = _make_msca_cert(app, 'ntlm-test.fips.local')
    _assert_fips_refusal(post_json(auth_client, f'{BASE}/{msca_id}/admin-channel/test', {
        'winrm_transport': 'ntlm', 'winrm_username': 'officer', 'winrm_password': 'secret'}))


def test_saving_an_ntlm_channel_is_refused_and_nothing_changes(app, auth_client, fips):
    msca_id, _, _ = _make_msca_cert(app, 'ntlm-save.fips.local')
    with app.app_context():
        from models import db
        from models.msca import MicrosoftCA
        db.session.get(MicrosoftCA, msca_id).winrm_transport = 'kerberos'
        db.session.commit()
    _assert_fips_refusal(put_json(auth_client, f'{BASE}/{msca_id}', {'winrm_transport': 'ntlm'}))
    with app.app_context():
        from models import db
        from models.msca import MicrosoftCA
        assert db.session.get(MicrosoftCA, msca_id).winrm_transport == 'kerberos'


def test_a_stored_ntlm_connection_is_not_opened(app, fips):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError
    msca_id, _, _ = _make_msca_cert(app, 'ntlm-stored.fips.local')
    with app.app_context():
        from models import db
        from models.msca import MicrosoftCA
        msca = db.session.get(MicrosoftCA, msca_id)
        msca.winrm_host = 'dc.fips.local'
        with pytest.raises(MSCAAdminChannelError, match='NTLM is not available in FIPS mode'):
            MicrosoftCAAdminChannelMixin._build_session(msca)


def test_ntlm_still_works_outside_fips(app):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    msca_id, _, _ = _make_msca_cert(app, 'ntlm-standard.fips.local')
    with app.app_context():
        from models import db
        from models.msca import MicrosoftCA
        msca = db.session.get(MicrosoftCA, msca_id)
        msca.winrm_host = 'dc.fips.local'
        msca.winrm_username, msca.winrm_password = 'officer', 'secret'
        session = MicrosoftCAAdminChannelMixin._build_session(msca)
    assert session.protocol.transport.auth_method == 'ntlm'
