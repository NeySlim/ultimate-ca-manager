"""
Tests for the ADConnectorConfig model -- encrypted-at-rest bind password
(same mechanism/pattern as models/msca.py's MicrosoftCA.password), and
fail-closed behavior when encryption is unavailable -- plus the settings
route's validation of the domain controller list.
"""
import json

import pytest

from models import db, ADConnectorConfig


def test_bind_password_encrypted_at_rest(app):
    with app.app_context():
        ADConnectorConfig.query.delete()
        db.session.commit()

        config = ADConnectorConfig(
            server='dc1.hagland.domain',
            base_dn='DC=hagland,DC=domain',
            bind_dn='CN=svc-ucm,CN=Users,DC=hagland,DC=domain',
            enabled=True,
        )
        config.bind_password = 'super-secret-bind-password'
        db.session.add(config)
        db.session.commit()

        # Raw column must not contain the plaintext value.
        assert config._bind_password is not None
        assert 'super-secret-bind-password' not in config._bind_password

        # Property getter must decrypt it back correctly.
        assert config.bind_password == 'super-secret-bind-password'

        # to_dict() masks by default, reveals only with include_secrets=True.
        assert config.to_dict()['bind_password'] == '***'
        assert config.to_dict(include_secrets=True)['bind_password'] == 'super-secret-bind-password'

        db.session.delete(config)
        db.session.commit()


def test_bind_password_setter_fails_closed_when_encryption_unavailable(app, monkeypatch):
    """If the encryption cipher can't be obtained, saving must raise -- not
    silently persist the credential in plaintext."""
    import utils.encryption as enc_mod

    def _broken_cipher():
        raise RuntimeError('encryption key unavailable')

    monkeypatch.setattr(enc_mod, 'get_cipher', _broken_cipher)

    with app.app_context():
        config = ADConnectorConfig(server='dc1.hagland.domain')
        with pytest.raises(RuntimeError):
            config.bind_password = 'super-secret-bind-password'
        # The setter must not have stored anything, plaintext or otherwise.
        assert config._bind_password is None


def test_get_singleton_returns_none_when_unconfigured(app):
    with app.app_context():
        ADConnectorConfig.query.delete()
        db.session.commit()
        assert ADConnectorConfig.get_singleton() is None


class TestServerListValidation:
    """The list reaches the route straight off the wire. split_servers is
    deliberately forgiving (it also reads a column that could have been
    hand-edited), so the shapes it skips have to be refused here -- with a
    400, never an AttributeError or a TypeError turning into a 500, and
    never a silent 200 that stored fewer servers than the client sent."""

    @staticmethod
    def _put(auth_client, payload):
        return auth_client.put('/api/v2/ad-connector', data=json.dumps(payload),
                               content_type='application/json')

    def test_a_number_in_the_list_is_rejected(self, auth_client):
        assert self._put(auth_client, {'servers': [123]}).status_code == 400

    def test_a_bare_number_is_rejected(self, auth_client):
        assert self._put(auth_client, {'servers': 5}).status_code == 400

    def test_a_dict_is_rejected(self, auth_client):
        assert self._put(auth_client, {'servers': {'a': 1}}).status_code == 400

    def test_more_servers_than_the_cap_are_rejected(self, auth_client):
        """Each one costs the probe a connect timeout on the scheduler's
        single thread, ahead of CRL generation, backups and discovery."""
        from api.v2.ad_connector import MAX_SERVERS
        servers = [f'dc{i}.corp.local' for i in range(MAX_SERVERS + 1)]
        assert self._put(auth_client, {'servers': servers}).status_code == 400

    def test_a_normal_list_is_accepted(self, auth_client, app):
        response = self._put(auth_client, {
            'servers': ['dc1.corp.local', 'dc2.corp.local'],
            'base_dn': 'DC=corp,DC=local',
            'bind_dn': 'CN=svc-ucm,DC=corp,DC=local',
            'bind_password': 'svc-password',
        })
        assert response.status_code == 200, response.data
        with app.app_context():
            assert ADConnectorConfig.get_singleton().servers == \
                ['dc1.corp.local', 'dc2.corp.local']


class TestSavedTestDoesNotRecordForADisabledConnector:
    """A disabled connector serves no lookup: recording a verdict for it
    would put a Degraded badge on something that is off and log "Kerberos
    autoenrollment will fail" for enrollments that are not happening."""

    def test_disabled_connector_keeps_its_health_untouched(self, app, auth_client, monkeypatch):
        from services.ad_connector import lookup as lookup_mod

        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.add(ADConnectorConfig(
                server='dc1.corp.local', base_dn='DC=corp,DC=local', enabled=False))
            db.session.commit()

        monkeypatch.setattr(lookup_mod, 'test_connection', lambda cfg: {
            'success': False, 'partial': False, 'message': 'Connection failed',
            'servers': [{'server': 'dc1.corp.local', 'success': False,
                         'message': 'timed out'}],
        })

        response = auth_client.post('/api/v2/ad-connector/test-saved')
        assert response.status_code == 400
        with app.app_context():
            config = ADConnectorConfig.get_singleton()
            assert config.health == {}
            # The test itself is still recorded -- only the health verdict
            # (which drives the badge and the skip list) is withheld.
            assert config.last_test_result.startswith('failed:')


class TestBindCredentialIsRequired:
    """An empty bind DN or password is an anonymous bind. ldap3 makes one
    whenever either half is missing, and this connector reads the computer
    and user objects that become the subject of a certificate UCM is about
    to issue: a directory that permits the anonymous read makes that
    identity attacker-influenced, and one that does not turns every lookup
    into a silent failure. The form has always asked for both; the API now
    enforces it, so it cannot be skipped by calling the route directly."""

    @staticmethod
    def _put(auth_client, payload):
        return auth_client.put('/api/v2/ad-connector', data=json.dumps(payload),
                               content_type='application/json')

    def test_first_save_without_one_is_refused(self, app, auth_client):
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
        response = self._put(auth_client, {
            'servers': ['dc1.corp.local'], 'base_dn': 'DC=corp,DC=local',
            'bind_dn': 'CN=svc-ucm,DC=corp,DC=local',
        })
        assert response.status_code == 400
        with app.app_context():
            # Refused, not half-applied: the partial mutation is rolled back.
            assert ADConnectorConfig.get_singleton() is None

    def test_a_later_save_keeps_the_stored_one(self, app, auth_client):
        """The form never re-sends a saved password, so a blank field means
        "unchanged" -- editing the port must not demand the credential
        again, and must not clear it."""
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
        assert self._put(auth_client, {
            'servers': ['dc1.corp.local'], 'base_dn': 'DC=corp,DC=local',
            'bind_dn': 'CN=svc-ucm,DC=corp,DC=local',
            'bind_password': 'svc-password',
        }).status_code == 200

        assert self._put(auth_client, {'port': 636}).status_code == 200
        with app.app_context():
            config = ADConnectorConfig.get_singleton()
            assert (config.port, config.bind_password) == (636, 'svc-password')

    def test_clearing_it_is_refused(self, app, auth_client):
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(server='dc1.corp.local', base_dn='DC=corp,DC=local')
            config.bind_password = 'svc-password'
            db.session.add(config)
            db.session.commit()

        assert self._put(auth_client, {'bind_password': ''}).status_code == 400
        with app.app_context():
            assert ADConnectorConfig.get_singleton().bind_password == 'svc-password'

    def test_first_save_without_a_bind_dn_is_refused(self, app, auth_client):
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
        response = self._put(auth_client, {
            'servers': ['dc1.corp.local'], 'base_dn': 'DC=corp,DC=local',
            'bind_password': 'svc-password',
        })
        assert response.status_code == 400
        with app.app_context():
            assert ADConnectorConfig.get_singleton() is None

    def test_clearing_the_bind_dn_is_refused(self, app, auth_client):
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(
                server='dc1.corp.local', base_dn='DC=corp,DC=local',
                bind_dn='CN=svc-ucm,DC=corp,DC=local')
            config.bind_password = 'svc-password'
            db.session.add(config)
            db.session.commit()

        assert self._put(auth_client, {'bind_dn': ''}).status_code == 400
        with app.app_context():
            assert ADConnectorConfig.get_singleton().bind_dn == 'CN=svc-ucm,DC=corp,DC=local'

    def test_the_inline_test_will_not_bind_anonymously(self, app, auth_client):
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
        response = auth_client.post(
            '/api/v2/ad-connector/test', content_type='application/json',
            data=json.dumps({'servers': ['dc1.corp.local'],
                             'bind_dn': 'CN=svc-ucm,DC=corp,DC=local'}))
        assert response.status_code == 400

        no_dn = auth_client.post(
            '/api/v2/ad-connector/test', content_type='application/json',
            data=json.dumps({'servers': ['dc1.corp.local'],
                             'bind_password': 'svc-password'}))
        assert no_dn.status_code == 400
