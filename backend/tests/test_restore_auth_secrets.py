"""What a restore leaves in the database for the sections restored by hand.

The export was rebuilt from a manifest; the restore stayed a set of
hand-written functions, each applying the columns somebody listed once. Two
things followed, and both are pinned here:

* a secret was assigned to the *column underneath* the property that encrypts
  it (`sso._oauth2_client_secret = ...`, `smtp._smtp_password = ...`), so
  restoring a backup wrote the SSO client secret, the LDAP bind password and
  the mail password into the database readable, and quietly undid the at-rest
  encryption of the installation that took the backup;
* a column nobody had listed was never written at all: an installation using
  OAuth2 for its mail server came back with neither
  `smtp_oauth_client_secret` nor `smtp_oauth_refresh_token`, and found out the
  next time a notification failed to leave.

The secrets are read here from the raw column (SQL, and the mapped attribute
that is the column rather than the property), because the property decrypts
and would report a value in the clear as perfectly fine.

The last test is the contract itself: every column the archive carries for
these sections is in the database afterwards. It walks the manifest rather
than a hand-written list, which is the whole point -- a list is what let these
columns go missing in the first place.

Each archive is limited to the sections under test (`_only`), and every row
this file creates is removed again: the database is shared by every test file
of a worker and there is no rollback between them.
"""
import base64
from datetime import date, datetime

import json

import pytest
from sqlalchemy import inspect as sa_inspect, text as sa_text
from sqlalchemy.types import (
    Boolean,
    Date,
    DateTime,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)

from models import db, User
from services.backup import manifest
from services.backup.export_generic import IdentityIndex, export_section, load_model

PASSWORD = 'Correct-Horse-Battery-9'
MARK = 'restore-secrets'

# The sections applied by the three restorers under test.
SECTIONS_UNDER_TEST = (
    'sso_providers',
    'hsm_providers',
    'api_keys',
    'auth_certificates',
    'groups',
    'custom_roles',
    'certificate_templates',
    'trusted_certificates',
    'smtp_config',
    'notification_config',
)

# What the archive is made to carry, per (section, column).
ARCHIVED_SECRETS = {
    ('sso_providers', 'oauth2_client_secret'): f'{MARK}-oauth2-client-secret',
    ('sso_providers', 'ldap_bind_password'): f'{MARK}-ldap-bind-password',
    ('smtp_config', 'smtp_password'): f'{MARK}-smtp-password',
    ('smtp_config', 'smtp_oauth_client_secret'): f'{MARK}-oauth-client-secret',
    ('smtp_config', 'smtp_oauth_refresh_token'): f'{MARK}-oauth-refresh-token',
    ('hsm_providers', 'config'): '{"url": "https://vault.test", "token": "%s-hsm"}' % MARK,
}

# Secrets emptied rather than changed before the restore: these are the two
# the restore never wrote, so "it came back" has to mean "it came back from
# nothing", not "nobody touched it".
EMPTIED_BEFORE_RESTORE = {
    ('smtp_config', 'smtp_oauth_client_secret'),
    ('smtp_config', 'smtp_oauth_refresh_token'),
}

# The secrets whose model exposes a property that encrypts: these are the ones
# a restore must not be able to leave in the clear. `hsm_providers.config` is
# encrypted field by field, without such a property: not here.
SECRETS_WITH_A_PROPERTY = (
    ('sso_providers', 'oauth2_client_secret'),
    ('sso_providers', 'ldap_bind_password'),
    ('smtp_config', 'smtp_password'),
    ('smtp_config', 'smtp_oauth_client_secret'),
    ('smtp_config', 'smtp_oauth_refresh_token'),
)

DRIFTED = f'{MARK}-was-here-before'
_DRIFTED_AT = datetime(2001, 2, 3, 4, 5, 6)

_CERTIFICATE_PEM = (
    '-----BEGIN CERTIFICATE-----\n'
    'MIIBkTCB+wIJAJ' + 'A' * 40 + '\n'
    '-----END CERTIFICATE-----\n'
)


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    """An include map that carries just these sections."""
    return {name: name in names for name in manifest.SECTIONS}


def _model(section_name):
    return load_model(manifest.SECTIONS[section_name])


def _columns_of(model):
    """(Column by archive name, mapped attribute by archive name)."""
    mapper = sa_inspect(model)
    columns = {column.key: column for column in mapper.columns}
    attribute_of = {}
    for prop in mapper.column_attrs:
        for column in prop.columns:
            attribute_of[column.key] = prop.key
    return columns, attribute_of


def _stored_attribute(model, column_name):
    """The mapped attribute holding the column itself, never the property."""
    return _columns_of(model)[1][column_name]


def _write_secret(instance, section_name, column, value):
    """Set a secret the way the application does: through the property when
    the model has one, straight onto the column when it does not."""
    if isinstance(getattr(type(instance), column, None), property):
        setattr(instance, column, value)
    else:
        setattr(instance, _stored_attribute(type(instance), column), value)


def _raw_secret(instance, column):
    """What the database column holds, read by SQL rather than by the
    property: the property decrypts, so it answers the same thing whether the
    value is encrypted at rest or lying there in the clear."""
    model = type(instance)
    column_object = _columns_of(model)[0][column]
    primary = list(sa_inspect(model).primary_key)[0]
    statement = sa_text(
        f'SELECT "{column_object.name}" FROM "{model.__tablename__}" '
        f'WHERE "{primary.name}" = :key')
    return db.session.execute(statement, {'key': getattr(instance, primary.key)}).scalar()


# ---------------------------------------------------------------------------
# One row per section, and the drift a restore has to undo
# ---------------------------------------------------------------------------

def _seed():
    """One row in every section the three restorers apply."""
    from models.api_key import APIKey
    from models.auth_certificate import AuthCertificate
    from models.certificate_template import CertificateTemplate
    from models.email_notification import NotificationConfig, SMTPConfig
    from models.group import Group
    from models.hsm import HsmProvider
    from models.rbac import CustomRole
    from models.sso import SSOProvider
    from models.truststore import TrustedCertificate

    owner = User.query.order_by(User.id).first()
    assert owner is not None, 'the suite always has at least one user'

    rows = {}

    rows['sso_providers'] = SSOProvider(
        name=f'{MARK}-sso', provider_type='oauth2', enabled=False,
        display_name='Restore Secrets IdP', oauth2_client_id='client-id',
        oauth2_issuer='https://idp.test/realms/ucm',
        oauth2_jwks_uri='https://idp.test/realms/ucm/jwks',
        ldap_server='ldaps://directory.test', ldap_bind_dn='cn=readonly',
        ldap_base_dn='dc=ucm,dc=test')

    rows['hsm_providers'] = HsmProvider(
        name=f'{MARK}-hsm', type='openbao', config='{}', status='connected')

    # A list, as the product writes it: JSON text is the shape migration 104 repairs
    rows['groups'] = Group(name=f'{MARK}-group', description='seeded',
                           permissions=['read:certificates'])

    rows['custom_roles'] = CustomRole(
        name=f'{MARK}-role', description='seeded',
        permissions='["read:certificates"]', is_system=False)

    rows['certificate_templates'] = CertificateTemplate(
        name=f'{MARK}-template', description='seeded', template_type='custom',
        key_type='rsa', validity_days=365, digest='sha256',
        extensions_template='{}', is_system=False, is_active=True)

    rows['trusted_certificates'] = TrustedCertificate(
        name=f'{MARK}-trusted', certificate_pem=_CERTIFICATE_PEM,
        fingerprint_sha256=f'{MARK}-fingerprint-256',
        fingerprint_sha1=f'{MARK}-fingerprint-1', subject='CN=Restore Secrets',
        issuer='CN=Restore Secrets', serial_number='01', purpose='root_ca')

    rows['api_keys'] = APIKey(
        user_id=owner.id, key_hash=f'{MARK}-key-hash', key_prefix='ucm_ak_RS',
        name=f'{MARK}-key', permissions='["read:certificates"]', is_active=True)

    rows['auth_certificates'] = AuthCertificate(
        user_id=owner.id, cert_pem=_CERTIFICATE_PEM.encode(),
        cert_serial=f'{MARK}-cert-serial', cert_subject='CN=Restore Secrets',
        cert_issuer='CN=Restore Secrets',
        cert_fingerprint=f'{MARK}-cert-fingerprint',
        name=f'{MARK}-auth-cert', enabled=True)

    rows['notification_config'] = NotificationConfig(
        type=f'{MARK}-alert', enabled=True, days_before=30,
        alert_days='[30, 7]', include_revoked=False,
        recipients='["ops@ucm.test"]', subject_template='Seeded',
        description='seeded', cooldown_hours=12)

    for instance in rows.values():
        db.session.add(instance)

    smtp = SMTPConfig.query.first()
    if smtp is None:
        smtp = SMTPConfig()
        db.session.add(smtp)
    smtp.smtp_host = 'smtp.ucm.test'
    smtp.smtp_port = 587
    smtp.smtp_user = 'notifier@ucm.test'
    smtp.smtp_from = 'notifier@ucm.test'
    smtp.smtp_auth_method = 'oauth2'
    smtp.smtp_oauth_provider = 'microsoft'
    smtp.smtp_oauth_client_id = 'oauth-client-id'
    smtp.enabled = False
    rows['smtp_config'] = smtp

    for (section_name, column), value in ARCHIVED_SECRETS.items():
        _write_secret(rows[section_name], section_name, column, value)

    db.session.flush()
    return rows


def _drift(rows):
    """Change everything a restore is supposed to put back.

    Without this, comparing the archive to the database afterwards would pass
    on a restore that writes nothing at all.
    """
    for section_name, instance in rows.items():
        section = manifest.SECTIONS[section_name]
        columns, attribute_of = _columns_of(type(instance))

        for column_name, column in columns.items():
            if column.primary_key or column_name == 'id':
                continue
            if column_name in section.identity or column_name in section.secrets:
                continue
            if column_name in section.exclude or column_name in section.handled:
                continue
            if column.unique or column.foreign_keys:
                # Identity and links: drifting them would move the row rather
                # than change it, and a foreign key pointing nowhere is a
                # different test than this one.
                continue
            drifted = _drifted_value(column, getattr(instance, attribute_of[column_name]))
            if drifted is not _UNCHANGED:
                setattr(instance, attribute_of[column_name], drifted)

        for column in section.secrets:
            if (section_name, column) in EMPTIED_BEFORE_RESTORE:
                setattr(instance, _stored_attribute(type(instance), column), None)
            else:
                _write_secret(instance, section_name, column,
                              f'{DRIFTED}-{column}')

    db.session.flush()


_UNCHANGED = object()


def _drifted_value(column, current):
    kind = column.type
    if isinstance(kind, Boolean):
        return not bool(current)
    if isinstance(kind, LargeBinary):
        return b'drifted'
    if isinstance(kind, DateTime):
        return _DRIFTED_AT
    if isinstance(kind, Date):
        return date(2001, 2, 3)
    if isinstance(kind, Integer):
        return (current or 0) + 7
    if isinstance(kind, Numeric):
        return (current or 0) + 1
    if isinstance(kind, (String, Text)):
        length = getattr(kind, 'length', None)
        return DRIFTED[:length] if length else DRIFTED
    return _UNCHANGED


def _export_of(section_names):
    index = IdentityIndex()
    return {name: export_section(name, index) for name in section_names}


# How this file finds its own row again, where the manifest identifies one by
# its primary key: the id says nothing about which row it is, and
# `notification_config` holds one row per notification type, not one row.
_FOUND_BY = {'notification_config': ('type',)}


def _identity_fields(section_name):
    return _FOUND_BY.get(section_name,
                         manifest.SECTIONS[section_name].identity)


def _mine(section_name, row):
    """The row this file created, among everything the section holds."""
    if section_name == 'smtp_config':
        return True      # a singleton: the installation has exactly one
    return all(str(row.get(field) or '').startswith(MARK)
               for field in _identity_fields(section_name))


def _rows_of_mine(payload, section_name):
    return [row for row in payload.get(section_name) or []
            if _mine(section_name, row)]


# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def restored(app):
    """Seed, archive, drift, restore -- measured once, then cleaned away."""
    from models.email_notification import SMTPConfig

    with app.app_context():
        service = _service()
        smtp_before = _snapshot_smtp()
        rows = _seed()
        db.session.commit()

        blob = service.create_backup(
            PASSWORD, include=_only(*SECTIONS_UNDER_TEST))
        _master, archive = service._decrypt_framed(blob, PASSWORD)

        _drift(rows)
        db.session.commit()

        before = {}
        for section_name, column in ARCHIVED_SECRETS:
            before[(section_name, column)] = _raw_secret(rows[section_name], column)

        service.restore_backup(blob, PASSWORD)
        db.session.expire_all()

        measured = {}
        for section_name, column in ARCHIVED_SECRETS:
            instance = _reload(section_name, rows)
            measured[(section_name, column)] = {
                'raw': _raw_secret(instance, column),
                'column': getattr(instance, _stored_attribute(type(instance), column)),
                'readable': (json.dumps(instance.get_config()) if section_name == 'hsm_providers'
                             else getattr(instance, column)),
                'before': before[(section_name, column)],
            }

        after = _export_of(SECTIONS_UNDER_TEST)

        yield {'archive': archive, 'after': after, 'secrets': measured}

        _cleanup(smtp_before)


def _reload(section_name, rows):
    """The row as the database holds it now, found by its own identity."""
    from models.email_notification import SMTPConfig
    if section_name == 'smtp_config':
        return SMTPConfig.query.first()
    model = _model(section_name)
    original = rows[section_name]
    criteria = {field: getattr(original, field)
                for field in _identity_fields(section_name)}
    return model.query.filter_by(**criteria).one()


def _snapshot_smtp():
    """Every column of the singleton SMTP row, or None when there is none."""
    from models.email_notification import SMTPConfig
    row = SMTPConfig.query.first()
    if row is None:
        return None
    _columns, attribute_of = _columns_of(SMTPConfig)
    return {attribute: getattr(row, attribute)
            for attribute in set(attribute_of.values())}


def _cleanup(smtp_before):
    """Put the database back exactly as this module found it."""
    from models.api_key import APIKey
    from models.auth_certificate import AuthCertificate
    from models.certificate_template import CertificateTemplate
    from models.email_notification import NotificationConfig, SMTPConfig
    from models.group import Group
    from models.hsm import HsmProvider
    from models.rbac import CustomRole
    from models.sso import SSOProvider
    from models.truststore import TrustedCertificate

    db.session.rollback()
    for model, criteria in (
        (SSOProvider, {'name': f'{MARK}-sso'}),
        (HsmProvider, {'name': f'{MARK}-hsm'}),
        (Group, {'name': f'{MARK}-group'}),
        (CustomRole, {'name': f'{MARK}-role'}),
        (CertificateTemplate, {'name': f'{MARK}-template'}),
        (TrustedCertificate, {'fingerprint_sha256': f'{MARK}-fingerprint-256'}),
        (APIKey, {'key_hash': f'{MARK}-key-hash'}),
        (AuthCertificate, {'cert_serial': f'{MARK}-cert-serial'}),
        (NotificationConfig, {'type': f'{MARK}-alert'}),
    ):
        model.query.filter_by(**criteria).delete()

    row = SMTPConfig.query.first()
    if smtp_before is None:
        if row is not None:
            db.session.delete(row)
    elif row is not None:
        for attribute, value in smtp_before.items():
            setattr(row, attribute, value)
    db.session.commit()


class TestASecretComesBackEncrypted:
    """A restore must not be a way to strip at-rest encryption.

    `restore/apply.py` writes a secret through the model's property, which is
    what re-encrypts it with this installation's key. The restorers assigned
    the column underneath instead, and the value landed readable.
    """

    @pytest.mark.parametrize('section_name, column', SECRETS_WITH_A_PROPERTY)
    def test_the_column_holds_ciphertext(self, restored, section_name, column):
        from utils.encryption import is_encrypted

        measured = restored['secrets'][(section_name, column)]
        assert measured['raw'], f'{section_name}.{column} came back empty'
        assert is_encrypted(measured['raw']), (
            f'{section_name}.{column} is in the database in the clear after a '
            f'restore: {measured["raw"]!r}')
        assert measured['raw'] != ARCHIVED_SECRETS[(section_name, column)], \
            'the ciphertext cannot be the secret itself'
        assert measured['column'] == measured['raw'], (
            'the mapped attribute and the column disagree; this test is not '
            'reading what the database holds')

    @pytest.mark.parametrize('section_name, column', SECRETS_WITH_A_PROPERTY)
    def test_the_property_reads_it_back(self, restored, section_name, column):
        measured = restored['secrets'][(section_name, column)]
        assert measured['readable'] == ARCHIVED_SECRETS[(section_name, column)]

    @pytest.mark.parametrize('section_name, column',
                             sorted(ARCHIVED_SECRETS))
    def test_it_is_the_archives_value_and_not_the_one_that_was_there(
            self, restored, section_name, column):
        """The restore writes the archive over what the target held.

        Told apart on purpose: a restorer that skips the column entirely
        leaves the drifted value in place and reads back as "fine" against a
        test that only checks the value is readable.
        """
        measured = restored['secrets'][(section_name, column)]
        assert measured['readable'] == ARCHIVED_SECRETS[(section_name, column)]
        assert measured['raw'] != measured['before'], (
            f'{section_name}.{column} still holds what was in the database '
            'before the restore')

    def test_the_archive_carries_them_in_the_clear(self, restored):
        """The premise of the three tests above: what the archive holds is the
        secret itself, decrypted at export time, so a restore that copied the
        column verbatim would be storing plaintext rather than re-encrypting."""
        for (section_name, column), value in sorted(ARCHIVED_SECRETS.items()):
            row = _rows_of_mine(restored['archive'], section_name)[0]
            assert row.get(column) == value


class TestAColumnNoRestorerWroteComesBack:
    """`smtp_oauth_client_secret` and `smtp_oauth_refresh_token` are declared
    by the manifest, carried by every archive, and were written by nobody: an
    installation authenticating to its mail server with OAuth2 was restored
    with no credential at all, and said nothing about it."""

    @pytest.mark.parametrize('section_name, column',
                             sorted(EMPTIED_BEFORE_RESTORE))
    def test_it_is_written_even_though_the_row_had_nothing(
            self, restored, section_name, column):
        measured = restored['secrets'][(section_name, column)]
        assert measured['before'] is None, \
            'the point of this test is that there was nothing to keep'
        assert measured['readable'] == ARCHIVED_SECRETS[(section_name, column)]


class TestEveryColumnTheArchiveCarriesIsPutBack:
    """The contract, walked from the manifest rather than from a list.

    A hand-written list of columns is what let `smtp_oauth_client_secret` and
    a dozen others go missing; checking against one here would reproduce the
    bug in the test. Every column the export wrote -- which is every column
    the manifest neither excludes nor marks `handled` -- has to be back in the
    database after the restore, and the comparison is made by exporting the
    sections again and reading the two side by side.
    """

    @pytest.mark.parametrize('section_name', SECTIONS_UNDER_TEST)
    def test_the_section_reads_back_as_it_was_archived(self, restored,
                                                       section_name):
        archived = _rows_of_mine(restored['archive'], section_name)
        assert len(archived) == 1, \
            f"this file seeds exactly one row in '{section_name}'"
        now = _rows_of_mine(restored['after'], section_name)
        assert len(now) == 1, (
            f"'{section_name}' no longer holds the row the archive carries")

        missing = {column: (value, now[0].get(column))
                   for column, value in archived[0].items()
                   if column != 'id' and now[0].get(column) != value}
        assert not missing, (
            f"'{section_name}' came back missing what the archive carries "
            f'(archived, restored): {missing}')

    def test_the_drift_was_real(self, restored):
        """The other half: if nothing had been changed between the archive and
        the restore, the comparison above would pass on a restore that writes
        nothing at all."""
        for (section_name, column), measured in sorted(
                restored['secrets'].items()):
            if (section_name, column) in EMPTIED_BEFORE_RESTORE:
                assert measured['before'] is None
            else:
                assert measured['before'], (
                    f'{section_name}.{column} held nothing before the restore, '
                    'so restoring it proves nothing')

    def test_the_sections_are_the_ones_these_restorers_apply(self):
        """A section added to one of the three restorers and not here would
        never be covered; the list is small enough to be checked by reading."""
        for section_name in SECTIONS_UNDER_TEST:
            assert section_name in manifest.SECTIONS
