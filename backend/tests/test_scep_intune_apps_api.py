"""Intune app registrations (issue #358): defined once, picked per profile.

The pre-092 profile fields keep working for one release: they find or create
the app, and on an existing profile they edit the app it is bound to.
"""
import json

from tests.conftest import get_json
from tests.test_scep_profiles import _create_profile

CONTENT_JSON = 'application/json'


def _post(client, path, **payload):
    return client.post(path, data=json.dumps(payload), content_type=CONTENT_JSON)


def _patch(client, path, **payload):
    return client.patch(path, data=json.dumps(payload), content_type=CONTENT_JSON)


def _create_app(client, name, tenant='apps.onmicrosoft.com', client_id=None,
                secret='the-secret'):
    # Tenant and client are unique per registration: one client per name
    r = _post(client, '/api/v2/scep/intune-apps', name=name, tenant_id=tenant,
              client_id=client_id or f'{name}-client', client_secret=secret)
    assert r.status_code == 200, r.data
    return get_json(r)['data']


def _apps(client):
    return {a['name']: a for a in get_json(client.get('/api/v2/scep/intune-apps'))['data']}


class TestAppRegistrations:

    def test_create_list_update_delete(self, auth_client):
        app = _create_app(auth_client, 'apps-crud')
        assert app['client_secret_set'] is True
        assert 'client_secret' not in app
        assert app['profile_count'] == 0
        assert _apps(auth_client)['apps-crud']['tenant_id'] == 'apps.onmicrosoft.com'

        r = _patch(auth_client, f"/api/v2/scep/intune-apps/{app['id']}",
                   name='apps-crud', client_secret='')
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['client_secret_set'] is True   # blank leaves it
        r = _patch(auth_client, f"/api/v2/scep/intune-apps/{app['id']}",
                   client_id='client-2', client_secret='new-secret')
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['client_id'] == 'client-2'

        r = auth_client.delete(f"/api/v2/scep/intune-apps/{app['id']}")
        assert r.status_code == 200
        assert 'apps-crud' not in _apps(auth_client)

    def test_create_requires_name_tenant_client_and_secret(self, auth_client):
        base = dict(name='apps-incomplete', tenant_id='t', client_id='c', client_secret='s')
        for missing in base:
            payload = {k: v for k, v in base.items() if k != missing}
            r = _post(auth_client, '/api/v2/scep/intune-apps', **payload)
            assert r.status_code == 400, missing

    def test_names_are_unique(self, auth_client):
        _create_app(auth_client, 'apps-unique')
        r = _post(auth_client, '/api/v2/scep/intune-apps', name='apps-unique',
                  tenant_id='t', client_id='c', client_secret='s')
        assert r.status_code == 409

    def test_unknown_app_is_404(self, auth_client):
        assert _patch(auth_client, '/api/v2/scep/intune-apps/987654', name='x').status_code == 404
        assert auth_client.delete('/api/v2/scep/intune-apps/987654').status_code == 404

    def test_an_app_in_use_is_not_deleted(self, auth_client, create_ca):
        app = _create_app(auth_client, 'apps-in-use')
        ca = create_ca(cn='Intune App In Use CA')
        r = _create_profile(auth_client, name='apps-in-use-profile', ca_id=ca['id'],
                            auto_approve=True, intune_enabled=True, intune_app_id=app['id'])
        assert r.status_code == 200, r.data
        r = auth_client.delete(f"/api/v2/scep/intune-apps/{app['id']}")
        assert r.status_code == 409
        assert 'apps-in-use-profile' in get_json(r)['message']
        assert _apps(auth_client)['apps-in-use']['profile_names'] == ['apps-in-use-profile']


class TestProfilesPickAnApp:

    def test_profile_bound_by_app_id_echoes_the_app(self, auth_client, create_ca):
        app = _create_app(auth_client, 'apps-pick', client_id='client-pick')
        ca = create_ca(cn='Intune App Pick CA')
        prof = get_json(_create_profile(
            auth_client, name='apps-pick-profile', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True, intune_app_id=app['id']))['data']
        assert prof['intune_app_id'] == app['id']
        assert prof['intune_app_name'] == 'apps-pick'
        assert prof['intune_client_id'] == 'client-pick'      # pre-092 shape, echoed
        assert prof['intune_client_secret_set'] is True

    def test_intune_needs_an_app(self, auth_client, create_ca):
        ca = create_ca(cn='Intune App Missing CA')
        r = _create_profile(auth_client, name='apps-missing-profile', ca_id=ca['id'],
                            auto_approve=True, intune_enabled=True, intune_app_id=None)
        assert r.status_code == 400
        r = _create_profile(auth_client, name='apps-missing-profile', ca_id=ca['id'],
                            auto_approve=True, intune_enabled=True, intune_app_id=987654)
        assert r.status_code == 400

    def test_two_profiles_share_one_app(self, auth_client, create_ca):
        app = _create_app(auth_client, 'apps-shared', client_id='client-shared')
        ca = create_ca(cn='Intune App Shared CA')
        for name in ('apps-shared-windows', 'apps-shared-ios'):
            r = _create_profile(auth_client, name=name, ca_id=ca['id'], url_slug=name,
                                auto_approve=True, intune_enabled=True, intune_app_id=app['id'])
            assert r.status_code == 200, r.data
        assert _apps(auth_client)['apps-shared']['profile_count'] == 2

    def test_switching_intune_off_may_unbind(self, auth_client, create_ca):
        app = _create_app(auth_client, 'apps-unbind')
        ca = create_ca(cn='Intune App Unbind CA')
        prof = get_json(_create_profile(
            auth_client, name='apps-unbind-profile', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True, intune_app_id=app['id']))['data']
        r = _patch(auth_client, f"/api/v2/scep/profiles/{prof['id']}",
                   intune_enabled=False, intune_app_id=None)
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['intune_app_id'] is None
        assert auth_client.delete(f"/api/v2/scep/intune-apps/{app['id']}").status_code == 200


class TestThePre092FieldsStillWork:

    def test_the_trio_creates_an_app_named_after_the_profile(self, auth_client, create_ca):
        ca = create_ca(cn='Intune Legacy Create CA')
        prof = get_json(_create_profile(
            auth_client, name='apps-legacy-create', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_tenant_id='apps-legacy.onmicrosoft.com', intune_client_id='apps-legacy-client',
            intune_client_secret='legacy-secret'))['data']
        app = _apps(auth_client)['apps-legacy-create']
        assert prof['intune_app_id'] == app['id']
        assert (app['tenant_id'], app['client_id']) == ('apps-legacy.onmicrosoft.com', 'apps-legacy-client')

    def test_the_same_trio_reuses_the_app(self, auth_client, create_ca):
        ca = create_ca(cn='Intune Legacy Reuse CA')
        ids = []
        for name in ('apps-legacy-reuse-a', 'apps-legacy-reuse-b'):
            prof = get_json(_create_profile(
                auth_client, name=name, ca_id=ca['id'], url_slug=name,
                auto_approve=True, intune_enabled=True,
                intune_tenant_id='reuse.onmicrosoft.com', intune_client_id='reuse-client',
                intune_client_secret='reuse-secret'))['data']
            ids.append(prof['intune_app_id'])
        assert ids[0] == ids[1]
        assert 'apps-legacy-reuse-b' not in _apps(auth_client)

    def test_a_patch_with_the_trio_edits_the_bound_app(self, auth_client, create_ca, app):
        registration = _create_app(auth_client, 'apps-legacy-patch', client_id='before')
        ca = create_ca(cn='Intune Legacy Patch CA')
        prof = get_json(_create_profile(
            auth_client, name='apps-legacy-patch-profile', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True, intune_app_id=registration['id']))['data']
        r = _patch(auth_client, f"/api/v2/scep/profiles/{prof['id']}",
                   intune_client_id='after', intune_client_secret='rotated')
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['intune_client_id'] == 'after'
        assert _apps(auth_client)['apps-legacy-patch']['client_id'] == 'after'
        with app.app_context():
            from models import IntuneApp
            assert IntuneApp.query.get(registration['id']).decrypted_secret() == 'rotated'


class TestTheConnectionTest:

    def test_unsaved_values_are_tested_as_given(self, auth_client, monkeypatch):
        from services.scep.intune_client import IntuneScepClient
        seen = {}

        def fake(self):
            seen.update(tenant=self.tenant_id, client=self.client_id, secret=self.client_secret)

        monkeypatch.setattr(IntuneScepClient, 'test_connection', fake)
        r = _post(auth_client, '/api/v2/scep/intune-apps/test',
                  tenant_id='t', client_id='c', client_secret='s')
        assert r.status_code == 200, r.data
        assert seen == {'tenant': 't', 'client': 'c', 'secret': 's'}

    def test_a_saved_app_lends_its_secret_and_records_the_result(self, auth_client, monkeypatch):
        from services.scep.intune_client import IntuneScepClient, IntuneScepError
        registration = _create_app(auth_client, 'apps-test-saved', secret='kept-secret')
        seen = {}

        def failing(self):
            seen['secret'] = self.client_secret
            raise IntuneScepError('bad credentials')

        monkeypatch.setattr(IntuneScepClient, 'test_connection', failing)
        r = _post(auth_client, '/api/v2/scep/intune-apps/test', app_id=registration['id'])
        assert r.status_code == 400
        assert 'bad credentials' in get_json(r)['message']
        assert seen == {'secret': 'kept-secret'}
        assert 'failed' in _apps(auth_client)['apps-test-saved']['last_test_result']

    def test_requires_all_fields(self, auth_client):
        assert _post(auth_client, '/api/v2/scep/intune-apps/test',
                     tenant_id='t').status_code == 400
        assert _post(auth_client, '/api/v2/scep/intune-apps/test',
                     app_id=987654).status_code == 404


class TestTheEndpointValidatesWithTheApp:

    def test_the_client_is_built_from_the_bound_app(self, app, client, auth_client, create_ca,
                                                    monkeypatch):
        """GetCACaps on an Intune profile builds the validation client: its
        credentials are the app's, not the frozen profile columns."""
        from models import SystemConfig, db
        from services.scep.intune_client import IntuneScepClient
        registration = _create_app(auth_client, 'apps-endpoint', tenant='endpoint.onmicrosoft.com',
                                   client_id='endpoint-client', secret='endpoint-secret')
        ca = create_ca(cn='Intune App Endpoint CA')
        r = _create_profile(auth_client, name='apps-endpoint-profile', ca_id=ca['id'],
                            url_slug='apps-endpoint', auto_approve=True,
                            intune_enabled=True, intune_app_id=registration['id'])
        assert r.status_code == 200, r.data
        with app.app_context():
            row = SystemConfig.query.filter_by(key='scep_enabled').first()
            saved = row.value if row else None
            if row is None:
                db.session.add(SystemConfig(key='scep_enabled', value='true'))
            else:
                row.value = 'true'
            db.session.commit()
        built = {}
        original = IntuneScepClient.__init__

        def recording(self, tenant_id, client_id, client_secret, provider_name=None):
            built.update(tenant=tenant_id, client=client_id, secret=client_secret)
            original(self, tenant_id, client_id, client_secret, provider_name)

        monkeypatch.setattr(IntuneScepClient, '__init__', recording)
        try:
            r = client.get('/scep/apps-endpoint/pkiclient.exe?operation=GetCACaps')
            assert r.status_code == 200, r.data
        finally:
            with app.app_context():
                row = SystemConfig.query.filter_by(key='scep_enabled').first()
                if saved is None:
                    db.session.delete(row)
                else:
                    row.value = saved
                db.session.commit()
        assert built == {'tenant': 'endpoint.onmicrosoft.com', 'client': 'endpoint-client',
                         'secret': 'endpoint-secret'}


class TestTenantAndClientAreUnique:

    def test_an_explicit_duplicate_is_refused(self, auth_client):
        first = _create_app(auth_client, 'apps-twin-a', tenant='twin.onmicrosoft.com', client_id='twin')
        r = _post(auth_client, '/api/v2/scep/intune-apps', name='apps-twin-b',
                  tenant_id='twin.onmicrosoft.com', client_id='twin', client_secret='other')
        assert r.status_code == 409
        assert 'apps-twin-a' in get_json(r)['message']
        other = _create_app(auth_client, 'apps-twin-c', tenant='twin.onmicrosoft.com', client_id='twin-c')
        r = _patch(auth_client, f"/api/v2/scep/intune-apps/{other['id']}", client_id='twin')
        assert r.status_code == 409
        # Editing a registration without moving it onto another pair stays allowed
        r = _patch(auth_client, f"/api/v2/scep/intune-apps/{first['id']}", name='apps-twin-a2')
        assert r.status_code == 200, r.data

    def test_the_trio_with_another_secret_is_refused_not_merged(self, auth_client, create_ca):
        _create_app(auth_client, 'apps-trio-clash', tenant='clash.onmicrosoft.com',
                    client_id='clash', secret='current')
        ca = create_ca(cn='Intune Trio Clash CA')
        r = _create_profile(auth_client, name='apps-trio-clash-profile', ca_id=ca['id'],
                            auto_approve=True, intune_enabled=True,
                            intune_tenant_id='clash.onmicrosoft.com', intune_client_id='clash',
                            intune_client_secret='rotated')
        assert r.status_code == 409, r.data
        assert 'apps-trio-clash' in get_json(r)['message']
        assert len([a for a in _apps(auth_client).values()
                    if a['tenant_id'] == 'clash.onmicrosoft.com']) == 1

    def test_the_trio_without_a_secret_needs_one_candidate(self, auth_client, create_ca, app):
        with app.app_context():
            from models import IntuneApp, db
            from utils.encryption import encrypt_value
            for name, secret in (('apps-dup-old', 'old'), ('apps-dup-new', 'new')):
                db.session.add(IntuneApp(name=name, tenant_id='dup.onmicrosoft.com',
                                         client_id='dup', client_secret=encrypt_value(secret)))
            db.session.commit()
        ca = create_ca(cn='Intune Dup CA')
        r = _create_profile(auth_client, name='apps-dup-profile', ca_id=ca['id'],
                            auto_approve=True, intune_enabled=True,
                            intune_tenant_id='dup.onmicrosoft.com', intune_client_id='dup')
        assert r.status_code == 409
        assert 'Several' in get_json(r)['message']
        # With the secret, the matching registration is picked
        r = _create_profile(auth_client, name='apps-dup-profile', ca_id=ca['id'],
                            auto_approve=True, intune_enabled=True,
                            intune_tenant_id='dup.onmicrosoft.com', intune_client_id='dup',
                            intune_client_secret='new')
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['intune_app_name'] == 'apps-dup-new'
