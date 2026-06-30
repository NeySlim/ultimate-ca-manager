"""Tests for the AcmeClientAccount refactor (issue: directory_url override).

Original bug: AcmeClientService(environment='staging') would silently use the
URL from SystemConfig['acme.client.directory_url'] (often production), so the
'staging' account_key was used to register against PROD. The refactor binds
the key/URL together via the AcmeClientAccount row, making drift impossible.
"""
import pytest
from models import db, AcmeClientAccount, SystemConfig
from services.acme.acme_client_service import AcmeClientService


@pytest.fixture
def clean_acme_state(app):
    """Wipe all ACME-related state before each test."""
    with app.app_context():
        AcmeClientAccount.query.delete()
        SystemConfig.query.filter(SystemConfig.key.like('acme.client.%')).delete()
        db.session.commit()
        yield
        AcmeClientAccount.query.delete()
        SystemConfig.query.filter(SystemConfig.key.like('acme.client.%')).delete()
        db.session.commit()


class TestEnvironmentResolution:
    def test_environment_staging_creates_le_staging_account(self, app, clean_acme_state):
        with app.app_context():
            svc = AcmeClientService(environment='staging')
            assert svc.directory_url == AcmeClientAccount.LE_STAGING_URL
            assert svc.environment == 'staging'
            assert svc.account.directory_url == AcmeClientAccount.LE_STAGING_URL

    def test_environment_production_creates_le_production_account(self, app, clean_acme_state):
        with app.app_context():
            svc = AcmeClientService(environment='production')
            assert svc.directory_url == AcmeClientAccount.LE_PRODUCTION_URL
            assert svc.environment == 'production'

    def test_explicit_directory_url_creates_custom_account(self, app, clean_acme_state):
        with app.app_context():
            custom = "https://acme.smallstep.example/directory"
            svc = AcmeClientService(directory_url=custom)
            assert svc.directory_url == custom
            assert svc.environment == 'custom'
            assert svc.account.directory_url == custom

    def test_no_args_uses_default_account(self, app, clean_acme_state):
        with app.app_context():
            # Seed a default account
            default = AcmeClientAccount(
                directory_url='https://my.ca/dir',
                label='Default CA',
                email='ops@example.com',
                is_default=True,
            )
            db.session.add(default)
            db.session.commit()
            svc = AcmeClientService()
            assert svc.account.id == default.id


class TestBugRegression:
    """The original bug: directory_url SystemConfig overriding environment."""

    def test_legacy_directory_url_does_not_override_environment(self, app, clean_acme_state):
        """Setting acme.client.directory_url=<prod URL> must NOT cause
        environment='staging' to use the prod URL. They are decoupled now."""
        with app.app_context():
            # Simulate the legacy polluted config
            db.session.add(SystemConfig(
                key='acme.client.directory_url',
                value=AcmeClientAccount.LE_PRODUCTION_URL,
                description='legacy'
            ))
            db.session.commit()

            svc = AcmeClientService(environment='staging')
            # Critical assertion: staging stays staging
            assert svc.directory_url == AcmeClientAccount.LE_STAGING_URL
            assert 'staging' in svc.directory_url

    def test_environment_and_url_cannot_drift_per_account(self, app, clean_acme_state):
        """Each AcmeClientAccount row binds URL ↔ key ↔ url atomically."""
        with app.app_context():
            svc_stg = AcmeClientService(environment='staging')
            svc_prod = AcmeClientService(environment='production')
            # Different rows, different URLs
            assert svc_stg.account.id != svc_prod.account.id
            assert svc_stg.directory_url != svc_prod.directory_url
            # Same env requested twice → same row reused
            svc_stg2 = AcmeClientService(environment='staging')
            assert svc_stg2.account.id == svc_stg.account.id


class TestAccountKeyBinding:
    def test_account_key_persists_to_account_row(self, app, clean_acme_state):
        """Generated keys must land on the AcmeClientAccount row, not SystemConfig."""
        with app.app_context():
            svc = AcmeClientService(environment='staging')
            key = svc._get_account_key()
            assert key is not None
            assert svc.account.account_key  # populated
            # encrypt_text returns base64(ENC:fernet_token) when enabled, raw PEM otherwise.
            from security.encryption import key_encryption
            if key_encryption.is_enabled:
                assert key_encryption.is_string_encrypted(svc.account.account_key)
            else:
                assert svc.account.account_key.startswith('-----BEGIN')
            # Legacy SystemConfig keys MUST NOT be created by the new flow
            legacy = SystemConfig.query.filter_by(
                key='acme.client.staging.account_key'
            ).first()
            assert legacy is None

    def test_account_key_reused_across_service_instances(self, app, clean_acme_state):
        """Two services for the same env must load the same persisted key."""
        with app.app_context():
            svc1 = AcmeClientService(environment='staging')
            key1 = svc1._get_account_key()
            # Force fresh load on second instance
            svc2 = AcmeClientService(environment='staging')
            svc2.account_key = None
            key2 = svc2._get_account_key()
            # Same PEM bytes
            from cryptography.hazmat.primitives import serialization
            pem1 = key1.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )
            pem2 = key2.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )
            assert pem1 == pem2


class TestMigrationBackfill:
    def test_migration_backfills_legacy_keys(self, app, clean_acme_state):
        """Migration 031 should create AcmeClientAccount rows from legacy keys."""
        with app.app_context():
            # Seed legacy state
            for k, v in [
                ('acme.client.environment', 'production'),
                ('acme.client.email', 'legacy@example.com'),
                ('acme.client.staging.account_key', '-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----'),
                ('acme.client.staging.account_url', 'https://acme-staging-v02.api.letsencrypt.org/acme/acct/123'),
                ('acme.client.production.account_key', '-----BEGIN PRIVATE KEY-----\nfake2\n-----END PRIVATE KEY-----'),
                ('acme.client.production.account_url', 'https://acme-v02.api.letsencrypt.org/acme/acct/456'),
            ]:
                db.session.add(SystemConfig(key=k, value=v, description=''))
            db.session.commit()

            # Run migration manually (uses raw sqlite conn)
            import sqlite3, importlib.util, os
            db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            if not os.path.isabs(db_path):
                # In-memory or relative — skip real-conn test
                pytest.skip("Migration test requires file-backed SQLite")
            spec = importlib.util.spec_from_file_location(
                'mig031',
                '/root/ucm-src/backend/migrations/031_acme_client_accounts.py'
            )
            mig = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mig)
            conn = sqlite3.connect(db_path)
            mig.upgrade(conn)
            conn.close()
            db.session.expire_all()

            stg = AcmeClientAccount.query.filter_by(
                directory_url=AcmeClientAccount.LE_STAGING_URL
            ).first()
            prod = AcmeClientAccount.query.filter_by(
                directory_url=AcmeClientAccount.LE_PRODUCTION_URL
            ).first()
            assert stg is not None
            assert prod is not None
            assert prod.is_default is True  # active env was 'production'
            assert stg.is_default is False
            assert stg.email == 'legacy@example.com'

class TestForIssuanceFactory:
    """Issue #147: the configured custom ACME directory + EAB must be honoured
    by the issuance / registration path, which previously only ever passed an
    environment (staging/production) and so always hit Let's Encrypt."""

    CUSTOM_DIR = "https://acme-api.actalis.example/acme/directory"

    def test_for_issuance_with_custom_directory_uses_it(self, app, clean_acme_state):
        with app.app_context():
            db.session.add(SystemConfig(
                key='acme.client.directory_url', value=self.CUSTOM_DIR,
                description='custom'))
            db.session.commit()

            svc = AcmeClientService.for_issuance(environment='production')
            assert svc.directory_url == self.CUSTOM_DIR
            assert svc.environment == 'custom'
            # The custom directory is now backed by a real account row.
            row = AcmeClientAccount.query.filter_by(directory_url=self.CUSTOM_DIR).first()
            assert row is not None
            assert svc.account.id == row.id

    def test_for_issuance_without_custom_directory_falls_back_to_le(self, app, clean_acme_state):
        with app.app_context():
            # No acme.client.directory_url configured → LE mapping
            svc = AcmeClientService.for_issuance(environment='staging')
            assert svc.directory_url == AcmeClientAccount.LE_STAGING_URL
            assert svc.environment == 'staging'

            svc2 = AcmeClientService.for_issuance(environment='production')
            assert svc2.directory_url == AcmeClientAccount.LE_PRODUCTION_URL

    def test_for_issuance_ignores_le_url_in_custom_setting(self, app, clean_acme_state):
        """A legacy acme.client.directory_url set to a LE URL must NOT redirect
        staging→production (the original regression we must keep fixed)."""
        with app.app_context():
            db.session.add(SystemConfig(
                key='acme.client.directory_url',
                value=AcmeClientAccount.LE_PRODUCTION_URL, description='legacy'))
            db.session.commit()

            svc = AcmeClientService.for_issuance(environment='staging')
            # staging stays staging — the LE URL in SystemConfig is not a custom CA
            assert svc.directory_url == AcmeClientAccount.LE_STAGING_URL

    def test_sync_legacy_eab_backfills_account_row(self, app, clean_acme_state):
        with app.app_context():
            db.session.add(SystemConfig(
                key='acme.client.directory_url', value=self.CUSTOM_DIR, description=''))
            db.session.add(SystemConfig(
                key='acme.client.eab_kid', value='kid-123', description=''))
            db.session.add(SystemConfig(
                key='acme.client.eab_hmac_key', value='aGVsbG8=', description=''))
            db.session.commit()

            svc = AcmeClientService.for_issuance(environment='production')
            assert svc.account.directory_url == self.CUSTOM_DIR
            # EAB copied from SystemConfig onto the row
            assert svc.account.eab_kid == 'kid-123'
            assert svc.account.eab_hmac_key == 'aGVsbG8='

    def test_sync_legacy_eab_does_not_overwrite_existing_eab(self, app, clean_acme_state):
        with app.app_context():
            db.session.add(SystemConfig(
                key='acme.client.directory_url', value=self.CUSTOM_DIR, description=''))
            db.session.add(SystemConfig(
                key='acme.client.eab_kid', value='LEGACY-KID', description=''))
            db.session.add(SystemConfig(
                key='acme.client.eab_hmac_key', value='bGVnYWN5', description=''))
            db.session.commit()

            svc = AcmeClientService.for_issuance(environment='production')
            assert svc.account.eab_kid == 'LEGACY-KID'  # backfilled first time

            # User now sets a NEW EAB directly on the row (e.g. via the accounts UI)
            svc.account.eab_kid = 'ROW-KID'
            svc.account.eab_hmac_key = 'cm93'
            db.session.commit()

            # A subsequent for_issuance must NOT overwrite the row-level EAB
            svc2 = AcmeClientService.for_issuance(environment='production')
            assert svc2.account.id == svc.account.id
            assert svc2.account.eab_kid == 'ROW-KID'
            assert svc2.account.eab_hmac_key == 'cm93'

    def test_for_order_preserves_custom_ca_via_account_url(self, app, clean_acme_state):
        """For an existing order, the account is resolved from account_url,
        so changing acme.client.directory_url afterwards does NOT redirect
        operations to a different CA."""
        with app.app_context():
            # Order created against the custom CA
            db.session.add(SystemConfig(
                key='acme.client.directory_url', value=self.CUSTOM_DIR, description=''))
            db.session.commit()
            svc = AcmeClientService.for_issuance(environment='production')
            svc.account.account_url = 'https://acme-api.actalis.example/acme/acct/1'
            db.session.commit()

            # Simulate an order row carrying that account_url
            from models import AcmeClientOrder
            order = AcmeClientOrder(
                domains='[]', challenge_type='dns-01', environment='custom',
                status='pending', account_url=svc.account.account_url)
            db.session.add(order)
            db.session.commit()

            # User now clears the custom directory → for_issuance would use LE
            SystemConfig.query.filter_by(key='acme.client.directory_url').delete()
            db.session.commit()

            # for_order must still reach the custom account, NOT LE
            svc2 = AcmeClientService.for_order(order)
            assert svc2.account.id == svc.account.id
            assert svc2.directory_url == self.CUSTOM_DIR

    def test_for_order_falls_back_when_account_url_missing(self, app, clean_acme_state):
        from models import AcmeClientOrder
        with app.app_context():
            order = AcmeClientOrder(
                domains='[]', challenge_type='dns-01', environment='staging',
                status='pending', account_url=None)
            db.session.add(order)
            db.session.commit()
            svc = AcmeClientService.for_order(order)
            assert svc.directory_url == AcmeClientAccount.LE_STAGING_URL


class TestMultiCaPinOrderToAccount:
    """PR #149: when an order is created via for_issuance(account_id=…),
    the resulting AcmeClientOrder row must be pinned to that account so
    renewals reuse the same CA."""

    def _make_registered_account(self, directory_url, label="Test CA"):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        acct = AcmeClientAccount(
            directory_url=directory_url, label=label, email='ops@test.example',
            account_url=f'{directory_url}/acct/1', account_key=pem,
            account_key_algorithm='ES256', is_default=True,
        )
        db.session.add(acct)
        db.session.commit()
        return acct

    def _mock_post(self, order_url, finalize_url, authz_url, challenge_type='dns-01'):

        class _Resp:
            def __init__(self, status, payload=None, location=None):
                self.status_code = status
                self._payload = payload or {}
                self.headers = {'Location': location} if location else {}

            def json(self):
                return self._payload

        def _post(url, payload, use_jwk=False):
            if url == 'https://dir.test/directory/newOrder':
                return _Resp(201, {
                    'status': 'pending',
                    'expires': '2027-01-01T00:00:00Z',
                    'finalize': finalize_url,
                    'authorizations': [authz_url],
                }, location=order_url)
            if url == authz_url:
                return _Resp(200, {
                    'identifier': {'type': 'dns', 'value': 'test.example.com'},
                    'challenges': [{'type': challenge_type, 'token': 'tok', 'url': f'{authz_url}/c0', 'status': 'pending'}],
                })
            return _Resp(404)
        return _post

    def test_create_order_pins_acme_client_account_id(self, app, clean_acme_state, monkeypatch):
        with app.app_context():
            acct = self._make_registered_account('https://dir.test/directory', 'Custom CA')
            svc = AcmeClientService(account=acct)
            # bypass network: directory + JWS POST
            monkeypatch.setattr(svc, '_fetch_directory', lambda: {
                'newNonce': 'https://dir.test/nonce',
                'newOrder': 'https://dir.test/directory/newOrder',
                'newAccount': 'https://dir.test/newAccount',
            })
            monkeypatch.setattr(svc, '_post', self._mock_post(
                'https://dir.test/order/1', 'https://dir.test/order/1/finalize',
                'https://dir.test/authz/1'))

            ok, msg, order = svc.create_order(
                ['test.example.com'], email='ops@test.example',
                challenge_type='dns-01')

            assert ok, f"create_order failed: {msg}"
            assert order is not None
            # THE pin: the order remembers which external CA account issued it.
            assert order.acme_client_account_id == acct.id
            assert order.environment == 'custom'

    def test_for_order_prefers_pinned_account_id(self, app, clean_acme_state):
        """verify/finalize/status on an existing order must reuse the pinned
        account, even after the global default changed."""
        with app.app_context():
            acct = self._make_registered_account('https://dir.test/directory', 'Custom CA')

            from models import AcmeClientOrder
            order = AcmeClientOrder(
                domains='[]', challenge_type='dns-01', environment='custom',
                status='pending', account_url=acct.account_url,
                acme_client_account_id=acct.id)
            db.session.add(order)
            db.session.commit()

            # Even with the legacy fallback stub removed, for_order must hit the
            # pinned account first.
            svc = AcmeClientService.for_order(order)
            assert svc.account.id == acct.id
            assert svc.directory_url == 'https://dir.test/directory'
