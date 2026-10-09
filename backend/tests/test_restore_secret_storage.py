"""What a restore puts in a column the application keeps encrypted.

The manifest's `secrets` says a column must leave the installation in the
clear: the archive has its own encryption, and a value bound to the source's
key would be unusable anywhere else. It said nothing about the way back, and
the restore assigned the archive's cleartext straight to the column. Five
columns are plain columns rather than properties over a private one, so
nothing re-encrypted them: an ACME account key, a deployment SSH key, a SCEP
challenge, an Intune client secret and a webhook signing secret came out of a
restore readable in the database, on an installation that had them encrypted
the minute before.

Each case below writes the secret the way the application writes it, takes an
archive, removes the row, restores it, and asks two questions of the column:
what the application reads out of it, and whether the cleartext is sitting
there.
"""
import pytest

from models import db
from services.backup.manifest import SECTIONS

PASSWORD = 'secret-storage-password-0123456789'
MARK = 'secstore'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(section_name):
    """The archive carries one section: restoring a whole one would rewrite
    rows the rest of the worker is looking at."""
    return {name: name == section_name for name in SECTIONS}


def _master(value):
    from security.encryption import encrypt_text
    return encrypt_text(value)


def _database(value):
    from utils.encryption import encrypt_if_needed
    return encrypt_if_needed(value)


def _read_master(stored):
    from security.encryption import decrypt_text
    return decrypt_text(stored)


def _read_database(stored):
    from utils.encryption import decrypt_if_needed
    return decrypt_if_needed(stored)


def _acme_client_account(secret):
    from models.acme_client_account import AcmeClientAccount
    row = AcmeClientAccount(
        directory_url=f'https://{MARK}.example.test/directory',
        label=f'{MARK} account', email=f'{MARK}@example.test',
        account_key_algorithm='ES256', account_key=_master(secret))
    return AcmeClientAccount, row, AcmeClientAccount.label == f'{MARK} account'


def _scep_challenge(secret):
    from models.scep import ScepProfile
    row = ScepProfile(name=f'{MARK}-challenge', url_slug=f'{MARK}-challenge',
                      ca_refid=f'{MARK}-ca', challenge_password=_master(secret))
    return ScepProfile, row, ScepProfile.name == f'{MARK}-challenge'


def _intune_app(secret):
    from models.scep import IntuneApp
    row = IntuneApp(name=f'{MARK}-intune', tenant_id=f'{MARK}-tenant',
                    client_id=f'{MARK}-client', client_secret=_database(secret))
    return IntuneApp, row, IntuneApp.name == f'{MARK}-intune'


def _webhook(secret):
    from services.webhook_service import WebhookEndpoint
    row = WebhookEndpoint(name=f'{MARK}-hook',
                          url=f'https://{MARK}.example.test/hook',
                          events='["certificate.issued"]',
                          secret=_database(secret))
    return WebhookEndpoint, row, WebhookEndpoint.name == f'{MARK}-hook'


def _deploy_target(secret):
    from models.deploy import DeployTarget
    row = DeployTarget(name=f'{MARK}-target', host=f'{MARK}.example.test',
                       username='deploy', private_key=_master(secret))
    return DeployTarget, row, DeployTarget.name == f'{MARK}-target'


# (section, column, how the row is made, how the application reads the column)
CASES = [
    ('acme_client_accounts', 'account_key', _acme_client_account, _read_master),
    ('scep_profiles', 'challenge_password', _scep_challenge, _read_master),
    ('intune_apps', 'client_secret', _intune_app, _read_database),
    ('webhook_endpoints', 'secret', _webhook, _read_database),
    ('deploy_targets', 'private_key', _deploy_target, _read_master),
]


class TestASecretGoesBackTheWayTheColumnHoldsIt:

    @pytest.mark.parametrize('section_name, column, make, read',
                             CASES, ids=[f'{s}.{c}' for s, c, _, _ in CASES])
    def test_the_column_does_not_come_back_readable(
            self, app, encryption_enabled, section_name, column, make, read):
        # encrypt_text is a no-op without a master key, and the case is about
        # a column that was encrypted before the backup.
        cleartext = f'{MARK}-{column}-only-this-server-knows'
        with app.app_context():
            model, row, where = make(cleartext)
            model.query.filter(where).delete(synchronize_session=False)
            db.session.commit()
            db.session.add(row)
            db.session.commit()

            try:
                blob = _service().create_backup(
                    PASSWORD, include=_only(section_name))
                model.query.filter(where).delete(synchronize_session=False)
                db.session.commit()

                _service().restore_backup(blob, PASSWORD, mode='merge')
                db.session.expire_all()

                back = model.query.filter(where).one()
                stored = getattr(back, column)
                assert read(stored) == cleartext, (
                    f'{section_name}.{column} does not read back as the secret '
                    'that was there: the restore wrote something the '
                    'application cannot use')
                assert stored != cleartext, (
                    f'{section_name}.{column} holds the secret in the clear '
                    'after a restore: an installation that restored its own '
                    'archive undid its at-rest protection')
            finally:
                model.query.filter(where).delete(synchronize_session=False)
                db.session.commit()

    def test_every_column_the_manifest_names_is_covered_here(self):
        """A layer declared in the manifest and exercised by nothing is a
        layer nobody will notice going wrong."""
        declared = {(name, column) for name, section in SECTIONS.items()
                    for column in section.stored}
        covered = {(name, column) for name, column, _, _ in CASES}
        assert declared == covered, (
            'the manifest and this file disagree about which columns are '
            f'kept encrypted: {sorted(declared ^ covered)}')
