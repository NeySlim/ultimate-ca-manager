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


class TestForIssuanceCustomDirectory:
    """for_issuance() must route to a configured custom CA (e.g. Actalis) instead
    of silently falling back to Let's Encrypt — the original report's bug."""

    def test_for_issuance_honors_custom_directory_over_environment(self, app, clean_acme_state):
        with app.app_context():
            custom = "https://acme-api.actalis.com/acme/directory"
            db.session.add(SystemConfig(
                key='acme.client.directory_url', value=custom, description='custom CA'
            ))
            db.session.commit()

            svc = AcmeClientService.for_issuance(environment='production')
            # Must NOT be Let's Encrypt despite environment='production'
            assert svc.directory_url == custom
            assert svc.account.directory_url == custom
            assert svc.environment == 'custom'

    def test_for_issuance_falls_back_to_letsencrypt_without_custom(self, app, clean_acme_state):
        with app.app_context():
            svc = AcmeClientService.for_issuance(environment='staging')
            assert svc.directory_url == AcmeClientAccount.LE_STAGING_URL

    def test_for_issuance_ignores_letsencrypt_url_as_custom(self, app, clean_acme_state):
        """A custom directory_url that happens to be a Let's Encrypt URL is not
        treated as a custom CA (avoids creating a duplicate path)."""
        with app.app_context():
            db.session.add(SystemConfig(
                key='acme.client.directory_url',
                value=AcmeClientAccount.LE_PRODUCTION_URL, description='legacy'
            ))
            db.session.commit()
            svc = AcmeClientService.for_issuance(environment='staging')
            # environment wins → staging, not the prod URL from config
            assert svc.directory_url == AcmeClientAccount.LE_STAGING_URL

    def test_for_issuance_syncs_legacy_eab_to_account_row(self, app, clean_acme_state):
        """EAB set via Settings (SystemConfig) must reach the custom account row."""
        with app.app_context():
            custom = "https://acme-api.actalis.com/acme/directory"
            for k, v in [
                ('acme.client.directory_url', custom),
                ('acme.client.eab_kid', 'kid-actalis-123'),
                ('acme.client.eab_hmac_key', 'c2VjcmV0LWhtYWMta2V5'),
            ]:
                db.session.add(SystemConfig(key=k, value=v, description=''))
            db.session.commit()

            svc = AcmeClientService.for_issuance(environment='production')
            kid, hmac_key = svc._get_eab_credentials()
            assert kid == 'kid-actalis-123'
            assert hmac_key == 'c2VjcmV0LWhtYWMta2V5'
            assert svc.account.eab_kid == 'kid-actalis-123'


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