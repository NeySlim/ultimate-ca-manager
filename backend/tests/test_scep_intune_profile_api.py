"""SCEP profile API surface for Intune SCEP challenge validation (issue #228
part 2): the auto-approve constraint, tenant/client/secret requirements, and
the unsaved-form test-intune-connection endpoint.
"""
import json

from tests.conftest import get_json
from tests.test_scep_profiles import _create_profile

CONTENT_JSON = 'application/json'


class TestIntuneProfileValidation:

    def test_create_requires_auto_approve(self, auth_client, create_ca):
        ca = create_ca(cn='Intune Reject NoApprove CA')
        r = _create_profile(
            auth_client, name='intune-no-approve', ca_id=ca['id'],
            auto_approve=False, intune_enabled=True,
            intune_tenant_id='contoso.onmicrosoft.com', intune_client_id='client-1',
            intune_client_secret='secret-1',
        )
        assert r.status_code == 400

    def test_create_requires_tenant_and_client_id(self, auth_client, create_ca):
        ca = create_ca(cn='Intune Reject NoTenant CA')
        r = _create_profile(
            auth_client, name='intune-no-tenant', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_client_secret='secret-1',
        )
        assert r.status_code == 400

    def test_create_requires_secret(self, auth_client, create_ca):
        ca = create_ca(cn='Intune Reject NoSecret CA')
        r = _create_profile(
            auth_client, name='intune-no-secret', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_tenant_id='contoso.onmicrosoft.com', intune_client_id='client-1',
        )
        assert r.status_code == 400

    def test_create_succeeds_with_full_config(self, auth_client, create_ca):
        ca = create_ca(cn='Intune Accept CA')
        r = _create_profile(
            auth_client, name='intune-full', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_tenant_id='contoso.onmicrosoft.com', intune_client_id='client-1',
            intune_client_secret='secret-1',
        )
        assert r.status_code == 200, r.data
        prof = get_json(r)['data']
        assert prof['intune_enabled'] is True
        assert prof['intune_tenant_id'] == 'contoso.onmicrosoft.com'
        assert prof['intune_client_id'] == 'client-1'
        assert prof['intune_client_secret_set'] is True
        assert 'intune_client_secret' not in prof

    def test_patch_enabling_intune_checks_existing_auto_approve(self, auth_client, create_ca):
        # A profile created WITHOUT auto_approve, then PATCHed to enable
        # Intune without also flipping auto_approve, must still be rejected
        # -- validated against the resulting state, not just this payload.
        ca = create_ca(cn='Intune Patch Guard CA')
        prof = get_json(_create_profile(
            auth_client, name='intune-patch-guard', ca_id=ca['id'], auto_approve=False,
        ))['data']
        r = auth_client.patch(
            f"/api/v2/scep/profiles/{prof['id']}",
            data=json.dumps({
                'intune_enabled': True,
                'intune_tenant_id': 'contoso.onmicrosoft.com',
                'intune_client_id': 'client-1',
                'intune_client_secret': 'secret-1',
            }),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 400

    def test_patch_enabling_intune_with_auto_approve_together_succeeds(self, auth_client, create_ca):
        ca = create_ca(cn='Intune Patch Together CA')
        prof = get_json(_create_profile(
            auth_client, name='intune-patch-together', ca_id=ca['id'], auto_approve=False,
        ))['data']
        r = auth_client.patch(
            f"/api/v2/scep/profiles/{prof['id']}",
            data=json.dumps({
                'auto_approve': True,
                'intune_enabled': True,
                'intune_tenant_id': 'contoso.onmicrosoft.com',
                'intune_client_id': 'client-1',
                'intune_client_secret': 'secret-1',
            }),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 200, r.data

    def test_patch_blank_secret_leaves_existing_secret_unchanged(self, auth_client, create_ca, app):
        ca = create_ca(cn='Intune Patch Blank Secret CA')
        prof = get_json(_create_profile(
            auth_client, name='intune-blank-secret', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_tenant_id='contoso.onmicrosoft.com', intune_client_id='client-1',
            intune_client_secret='original-secret',
        ))['data']

        r = auth_client.patch(
            f"/api/v2/scep/profiles/{prof['id']}",
            data=json.dumps({'intune_client_id': 'client-1-updated'}),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['intune_client_secret_set'] is True

        with app.app_context():
            from models import ScepProfile
            row = ScepProfile.query.filter_by(id=prof['id']).first()
            assert row.decrypted_intune_secret() == 'original-secret'

    def test_secret_encrypted_at_rest(self, auth_client, create_ca, app):
        ca = create_ca(cn='Intune Secret Encrypted CA')
        prof = get_json(_create_profile(
            auth_client, name='intune-enc-check', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_tenant_id='contoso.onmicrosoft.com', intune_client_id='client-1',
            intune_client_secret='plaintext-app-secret',
        ))['data']
        with app.app_context():
            from models import ScepProfile
            row = ScepProfile.query.filter_by(id=prof['id']).first()
            assert row.decrypted_intune_secret() == 'plaintext-app-secret'
            # utils.encryption.encrypt_value always encrypts (real key or
            # machine-id-derived) -- unlike security.encryption's challenge
            # path, there is no "encryption disabled" passthrough to allow for.
            assert row.intune_client_secret != 'plaintext-app-secret'


class TestIntuneTestConnectionEndpoint:

    def test_requires_all_fields(self, auth_client):
        r = auth_client.post(
            '/api/v2/scep/profiles/test-intune-connection',
            data=json.dumps({'intune_tenant_id': 'contoso.onmicrosoft.com'}),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 400

    def test_inline_values_used_when_no_profile_id(self, auth_client, monkeypatch):
        from services.scep.intune_client import IntuneScepClient

        captured = {}

        def fake_test_connection(self):
            captured['tenant_id'] = self.tenant_id
            captured['client_id'] = self.client_id
            captured['client_secret'] = self.client_secret

        monkeypatch.setattr(IntuneScepClient, 'test_connection', fake_test_connection)
        r = auth_client.post(
            '/api/v2/scep/profiles/test-intune-connection',
            data=json.dumps({
                'intune_tenant_id': 'contoso.onmicrosoft.com',
                'intune_client_id': 'client-1',
                'intune_client_secret': 'secret-1',
            }),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 200, r.data
        assert captured == {
            'tenant_id': 'contoso.onmicrosoft.com',
            'client_id': 'client-1',
            'client_secret': 'secret-1',
        }

    def test_blank_secret_falls_back_to_saved_profile_secret(self, auth_client, create_ca, monkeypatch):
        from services.scep.intune_client import IntuneScepClient

        ca = create_ca(cn='Intune Test Conn Fallback CA')
        prof = get_json(_create_profile(
            auth_client, name='intune-test-fallback', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_tenant_id='contoso.onmicrosoft.com', intune_client_id='client-1',
            intune_client_secret='the-real-secret',
        ))['data']

        captured = {}

        def fake_test_connection(self):
            captured['client_secret'] = self.client_secret

        monkeypatch.setattr(IntuneScepClient, 'test_connection', fake_test_connection)
        r = auth_client.post(
            '/api/v2/scep/profiles/test-intune-connection',
            data=json.dumps({
                'intune_tenant_id': 'contoso.onmicrosoft.com',
                'intune_client_id': 'client-1',
                'profile_id': prof['id'],
            }),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 200, r.data
        assert captured['client_secret'] == 'the-real-secret'

    def test_failure_reports_message_and_records_result(self, auth_client, create_ca, app, monkeypatch):
        from services.scep.intune_client import IntuneScepClient, IntuneScepError

        ca = create_ca(cn='Intune Test Conn Fail CA')
        prof = get_json(_create_profile(
            auth_client, name='intune-test-fail', ca_id=ca['id'],
            auto_approve=True, intune_enabled=True,
            intune_tenant_id='contoso.onmicrosoft.com', intune_client_id='client-1',
            intune_client_secret='the-real-secret',
        ))['data']

        def failing_test_connection(self):
            raise IntuneScepError('bad credentials')

        monkeypatch.setattr(IntuneScepClient, 'test_connection', failing_test_connection)
        r = auth_client.post(
            '/api/v2/scep/profiles/test-intune-connection',
            data=json.dumps({
                'intune_tenant_id': 'contoso.onmicrosoft.com',
                'intune_client_id': 'client-1',
                'profile_id': prof['id'],
            }),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 400
        assert 'bad credentials' in get_json(r)['message']

        with app.app_context():
            from models import ScepProfile
            row = ScepProfile.query.filter_by(id=prof['id']).first()
            assert row.intune_last_test_at is not None
            assert 'failed' in row.intune_last_test_result
