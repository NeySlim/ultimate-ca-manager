"""ACME Profiles Extension (draft-ietf-acme-profiles).

The server advertises selectable issuance profiles in the directory's
``meta.profiles``; a client picks one via ``profile`` in newOrder. Profiles are
opt-in: with none configured the directory advertises nothing and any requested
profile is refused, leaving pre-existing behaviour untouched.
"""
import json

import pytest

from models import SystemConfig, db
from models.acme_models import AcmeOrder
from services.acme import profiles as acme_profiles

from tests.test_acme_security_paths import (  # reuse the JWS/account harness
    _build_jws, _nonce, _post_jws, acme_account,  # noqa: F401
)

PROFILES = {
    'default': {
        'description': '90-day server certificate',
        'validity_days': 90,
        'digest': 'sha256',
    },
    'shortlived': {
        'description': '7-day certificate',
        'validity_days': 7,
        'digest': 'sha384',
    },
}


@pytest.fixture
def configured_profiles(app):
    """Install a profile set for the duration of a test, then remove it."""
    with app.app_context():
        row = SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first()
        if not row:
            row = SystemConfig(key=acme_profiles.CONFIG_KEY, value='')
            db.session.add(row)
        row.value = json.dumps(PROFILES)
        db.session.commit()
    yield PROFILES
    with app.app_context():
        row = SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first()
        if row:
            db.session.delete(row)
            db.session.commit()


class TestProfileConfiguration:

    def test_no_config_means_no_profiles(self, app):
        with app.app_context():
            assert acme_profiles.get_profiles() == {}
            assert acme_profiles.directory_meta() == {}
            assert acme_profiles.is_known('default') is False

    def test_invalid_json_degrades_to_none(self, app):
        with app.app_context():
            db.session.add(SystemConfig(key=acme_profiles.CONFIG_KEY, value='{not json'))
            db.session.commit()
            assert acme_profiles.get_profiles() == {}
            row = SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first()
            db.session.delete(row)
            db.session.commit()

    def test_profiles_are_sanitized(self, app):
        """Bad values fall back to defaults rather than reaching issuance."""
        with app.app_context():
            db.session.add(SystemConfig(key=acme_profiles.CONFIG_KEY, value=json.dumps({
                'weird': {'validity_days': 99999, 'digest': 'md5'},
                'negative': {'validity_days': -5},
            })))
            db.session.commit()
            profiles = acme_profiles.get_profiles()
            # Validity capped at the global 3650-day maximum, digest rejected.
            assert profiles['weird']['validity_days'] == 3650
            assert profiles['weird']['digest'] == 'sha256'
            assert profiles['negative']['validity_days'] == 90
            # Missing description falls back to the profile name.
            assert profiles['weird']['description'] == 'weird'
            row = SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first()
            db.session.delete(row)
            db.session.commit()

    def test_issuance_params_fall_back_when_profile_absent(self, app):
        """A profile removed after the order must not break finalize."""
        with app.app_context():
            params = acme_profiles.issuance_params('gone')
            assert params == {'validity_days': 90, 'digest': 'sha256'}
            assert acme_profiles.issuance_params(None)['validity_days'] == 90


class TestDirectoryAdvertisement:

    def test_directory_omits_profiles_when_unconfigured(self, client):
        meta = client.get('/acme/directory').get_json()['meta']
        assert 'profiles' not in meta

    def test_directory_advertises_configured_profiles(self, client, configured_profiles):
        meta = client.get('/acme/directory').get_json()['meta']
        assert meta['profiles'] == {
            'default': '90-day server certificate',
            'shortlived': '7-day certificate',
        }


class TestNewOrderProfileSelection:

    def _order(self, client, acme_account, payload):
        path = '/acme/new-order'
        jws = _build_jws(
            f'http://localhost{path}',
            payload,
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        return _post_jws(client, path, jws)

    def test_known_profile_is_accepted_and_recorded(
        self, app, client, acme_account, configured_profiles
    ):
        response = self._order(client, acme_account, {
            'identifiers': [{'type': 'dns', 'value': 'prof-ok.example.com'}],
            'profile': 'shortlived',
        })
        assert response.status_code == 201, response.data
        body = response.get_json()
        assert body['profile'] == 'shortlived'

        order_id = response.headers['Location'].rstrip('/').split('/')[-1]
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            assert order.profile == 'shortlived'
            # The profile drives the issuance parameters used at finalize.
            params = acme_profiles.issuance_params(order.profile)
            assert params == {'validity_days': 7, 'digest': 'sha384'}

    def test_unknown_profile_is_refused(self, client, acme_account, configured_profiles):
        response = self._order(client, acme_account, {
            'identifiers': [{'type': 'dns', 'value': 'prof-bad.example.com'}],
            'profile': 'does-not-exist',
        })
        assert response.status_code == 400
        assert response.get_json()['type'].endswith(':invalidProfile')

    def test_profile_refused_when_server_offers_none(self, client, acme_account):
        response = self._order(client, acme_account, {
            'identifiers': [{'type': 'dns', 'value': 'prof-none.example.com'}],
            'profile': 'default',
        })
        assert response.status_code == 400
        assert response.get_json()['type'].endswith(':invalidProfile')

    def test_non_string_profile_is_refused(self, client, acme_account, configured_profiles):
        response = self._order(client, acme_account, {
            'identifiers': [{'type': 'dns', 'value': 'prof-type.example.com'}],
            'profile': 42,
        })
        assert response.status_code == 400
        assert response.get_json()['type'].endswith(':invalidProfile')

    def test_order_without_profile_still_works(
        self, app, client, acme_account, configured_profiles
    ):
        """Omitting `profile` keeps the historical behaviour (no profile, defaults)."""
        response = self._order(client, acme_account, {
            'identifiers': [{'type': 'dns', 'value': 'prof-absent.example.com'}],
        })
        assert response.status_code == 201, response.data
        assert 'profile' not in response.get_json()

        order_id = response.headers['Location'].rstrip('/').split('/')[-1]
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            assert order.profile is None
            assert acme_profiles.issuance_params(order.profile)['validity_days'] == 90
