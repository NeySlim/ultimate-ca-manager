"""An archive taken here has to be restorable somewhere else.

That is what the whole export is shaped for, and the one thing nothing
proved end to end: an archive is carried to a *different* installation, whose
numeric ids belong to its own history and whose encryption keys are not the
ones the archive was written under. Both of those used to be fatal in
silence.

The ids first. The restore wrote the source's numbers into the target, so a
group membership, an API key or a client certificate landed on whichever row
happened to hold that number here -- a restore reported as a success that
had handed someone's key to someone else's account. The manifest now carries,
beside every foreign key, the stable identity of the row it pointed at, and
the restore is supposed to resolve that identity against the target. These
tests walk the manifest's `references` rather than three relations picked by
hand: every relation is either exercised here or named, with its reason, in
one of the tables below.

The keys second. Secrets and private keys travel in the clear *inside* the
archive -- which is itself encrypted under the backup password -- precisely
so they can be written back under the target's key. An archive carrying the
source's at-rest ciphertext restores into credentials nothing can read and
authorities that cannot sign, and says so only on the day someone uses them.
So the target here runs with a database key and a key-encryption key the
source never held, and a restored authority is asked to actually sign.

Several of the tables below record what a restore onto another installation
does *not* do today: sections it refuses outright, rows it writes and then
takes away, links it drops, and the difference between SQLite, which lets a
wrong reference through long enough to be repaired, and PostgreSQL, which
does not. They are pinned rather than accepted -- each has a test that fails
the day the behaviour changes, in either direction, so that a fix is as
visible as a regression.

Neither installation is the suite's shared database. Each round trip runs
against throwaway databases of its own, bound to the application in turn, so
the archive holds nothing but the rows these tests write and the shared
database is never touched -- which matters, because every other file of this
worker reads it.
"""
import base64
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, inspect as sa_inspect, text

from models import db
from services.backup import manifest
from services.backup.export_generic import REFERENCE_SUFFIX, load_model

PASSWORD = 'Correct-Horse-Battery-9'

# The source writes its rows with primary keys no fresh installation reaches,
# so a restore that carried a number over instead of resolving an identity
# points at nothing at all rather than at something plausible.
SOURCE_ID_BASE = 900_000

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_needs_pg = pytest.mark.skipif(
    not _PG_URL, reason='UCM_TEST_PG_URL not set; skipping the PostgreSQL target')


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _model(section_name):
    return load_model(manifest.SECTIONS[section_name])


def _only(*names):
    """An include map carrying just these sections, historical ones too."""
    return {name: name in names for name in manifest.SECTIONS}


# ---------------------------------------------------------------------------
# Two installations, neither of them the suite's shared database
# ---------------------------------------------------------------------------


class Keys:
    """The two keys an installation stores its secrets under.

    They are two independent layers, and a second installation shares
    neither: `utils.encryption` holds the database key the manifest's
    `secrets` columns are encrypted with, and `security.encryption` holds the
    key-encryption key that wraps the private keys.
    """

    def __init__(self, directory, name):
        self.database = Fernet.generate_key().decode('ascii')
        self.master = Fernet.generate_key().decode('ascii')
        # A path that is never written, as `tests/conftest.py` does: a
        # master.key file takes priority over the environment, and the
        # machine running the suite may well have one of its own.
        self.master_path = directory / f'{name}-master.key'


@contextmanager
def _keys_of(keys):
    """Run under one installation's keys, and put back what was there.

    The patching is this context's own, so leaving it restores the suite's
    environment exactly, whatever else is going on around it.
    """
    from security import encryption as key_layer
    from utils import encryption as db_layer

    patch = pytest.MonkeyPatch()
    try:
        patch.setattr(key_layer, 'MASTER_KEY_PATH', keys.master_path)
        patch.setenv('KEY_ENCRYPTION_KEY', keys.master)
        patch.delenv('KEY_ENCRYPTION_KEY_FILE', raising=False)
        patch.setenv('UCM_DB_ENCRYPTION_KEY', keys.database)
        db_layer.get_cipher.cache_clear()
        key_layer.key_encryption.reload()
        assert key_layer.key_encryption.is_enabled, \
            'an installation under test stores its private keys encrypted'
        yield
    finally:
        patch.undo()
        db_layer.get_cipher.cache_clear()
        key_layer.key_encryption.reload()


@contextmanager
def _bound_to(app, url, is_postgresql=False, create_schema=True):
    """Point the application at a database of its own.

    The engine is swapped the way `tests/test_database_migration_matrix.py`
    does it, and put back whatever happens: every later file of this worker
    reaches the shared database through the same mapping.
    """
    from services.database_admin.helpers import _force_register_all_models
    from services.database_admin.migration import _create_target_schema

    _force_register_all_models()
    engine = create_engine(url, pool_pre_ping=True)
    if create_schema:
        _create_target_schema(engine, is_postgresql)

    engines = db._app_engines[app]
    original = engines[None]
    with app.app_context():
        engines[None] = engine
        db.session.remove()
    try:
        yield engine
    finally:
        with app.app_context():
            engines[None] = original
            db.session.remove()
        engine.dispose()


@contextmanager
def _installation(app, url, keys, is_postgresql=False, create_schema=True):
    """One installation: its database and the keys it reads it with."""
    with _keys_of(keys), _bound_to(app, url, is_postgresql, create_schema):
        yield


# ---------------------------------------------------------------------------
# Key material that can actually be used
# ---------------------------------------------------------------------------


def _authority(common_name):
    """A real self-signed authority: the restored one has to sign with it."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                       critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _leaf(common_name, issuer_key, issuer_certificate):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(issuer_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(issuer_key, hashes.SHA256())
    )
    return key, certificate


def _pem(material):
    if isinstance(material, x509.Certificate):
        return material.public_bytes(serialization.Encoding.PEM)
    return material.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _stored_certificate(certificate):
    """What `CA.crt` and `Certificate.crt` hold: base64 of the PEM."""
    return base64.b64encode(_pem(certificate)).decode('ascii')


def _stored_key(private_key):
    """What `.prv` holds: base64 of the PEM, wrapped with the current key."""
    from utils.key_codec import store_pem_bytes
    return store_pem_bytes(_pem(private_key))


# ---------------------------------------------------------------------------
# The source installation
# ---------------------------------------------------------------------------

# Every secret the manifest declares, with the value written on the source.
# Read back on the target, under a key the source never had.
SECRET_VALUES = {
    ('users', 'totp_secret'): 'xinst-totp-JBSWY3DPEHPK3PXP',
    ('users', 'backup_codes'): '["xinst-backup-code-1", "xinst-backup-code-2"]',
    ('sso_providers', 'oauth2_client_secret'): 'xinst-oauth2-client-secret',
    ('sso_providers', 'ldap_bind_password'): 'xinst-ldap-bind-password',
    ('hsm_providers', 'config'): '{"url": "http://bao.test", "token": "xinst-hsm"}',
    ('smtp_config', 'smtp_password'): 'xinst-smtp-password',
    ('smtp_config', 'smtp_oauth_client_secret'): 'xinst-smtp-oauth-secret',
    ('smtp_config', 'smtp_oauth_refresh_token'): 'xinst-smtp-refresh-token',
    ('dns_providers', 'credentials'): '{"api_token": "xinst-dns-token"}',
    ('acme_eab_credentials', 'hmac_key_b64'): 'eGluc3QtZWFiLWhtYWMta2V5',
    ('acme_client_accounts', 'account_key'): 'xinst-acme-client-account-key',
    ('acme_client_accounts', 'eab_hmac_key'): 'xinst-acme-client-eab-key',
    # Standard base64 of bytes(range(32)): what a TSIG key file holds.
    ('acme_dns_update_keys', 'secret'): 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=',
    ('microsoft_cas', 'password'): 'xinst-msca-password',
    ('microsoft_cas', 'winrm_password'): 'xinst-winrm-password',
    ('microsoft_cas', 'client_key_pem'): (
        '-----BEGIN PRIVATE KEY-----\nxinst-msca-mtls\n'
        '-----END PRIVATE KEY-----\n'),
    ('scep_profiles', 'challenge_password'): 'xinst-scep-challenge',
    ('intune_apps', 'client_secret'): 'xinst-intune-secret',
    ('ad_connector', 'bind_password'): 'xinst-ad-bind-password',
    ('webhook_endpoints', 'secret'): 'xinst-webhook-secret',
    ('webhook_endpoints', 'auth_token'): 'xinst-webhook-auth-token',
    ('deploy_targets', 'private_key'): 'xinst-deploy-private-key',
}

# The row each section's secrets were written on, as this installation names
# it; a singleton section has no name to give.
SECRET_ROW = {
    'users': {'username': 'xinst-user-b'},
    'sso_providers': {'name': 'xinst-sso-b'},
    'hsm_providers': {'name': 'xinst-hsm-b'},
    'smtp_config': {},
    'dns_providers': {'name': 'xinst-dns-b'},
    'acme_eab_credentials': {'kid': 'xinst-eab-kid'},
    'acme_client_accounts': {'label': 'xinst-client-b'},
    'acme_dns_update_keys': {'name': 'xinst-tsig.'},
    'microsoft_cas': {'name': 'xinst-msca-b'},
    'intune_apps': {'name': 'xinst-intune'},
    'scep_profiles': {'name': 'xinst-scep'},
    'ad_connector': {},
    'webhook_endpoints': {'name': 'xinst-webhook'},
    'deploy_targets': {'name': 'xinst-deploy-b'},
}


def _secret_attribute(model, column):
    """The mapped attribute holding a secret column, `_secret` and all.

    The same two steps the export takes: the attribute the column is mapped
    to, and failing that the underscored name, since a model whose column is
    named differently from the manifest's secret hides it behind one.
    """
    for prop in sa_inspect(model).column_attrs:
        for stored in prop.columns:
            if stored.key == column:
                return prop.key
    return f'_{column}' if hasattr(model, f'_{column}') else column


def _has_encrypting_property(model, column):
    """Whether the model re-encrypts this column when it is assigned."""
    return isinstance(getattr(model, column, None), property)


# Secrets the product stores through `security.encryption` (the master key)
# rather than through `utils.encryption` (the database key), which is the
# layer the manifest's `secrets` contract is written against.
WRAPPED_WITH_THE_MASTER_KEY = {
    ('acme_client_accounts', 'account_key'),
    ('acme_client_accounts', 'eab_hmac_key'),
}


def _write_secret(row, section_name, column, value):
    """Write a secret the way an installation in use holds it.

    A model that exposes the column as a property encrypts on assignment; one
    that does not is encrypted by whichever route writes it, which is what is
    reproduced here. Either way the value reaches the database as ciphertext
    of the *source's* key, which is the whole point: an archive carrying that
    ciphertext restores into a credential the target cannot read.
    """
    from security.encryption import encrypt_text
    from utils.encryption import encrypt_value

    model = type(row)
    if _has_encrypting_property(model, column):
        setattr(row, column, value)          # the property encrypts, its way
    elif (section_name, column) in WRAPPED_WITH_THE_MASTER_KEY:
        setattr(row, _secret_attribute(model, column), encrypt_text(value))
    else:
        setattr(row, _secret_attribute(model, column), encrypt_value(value))


def _stored_secret(row, column):
    """The bytes the database holds for a secret column, encrypted or not."""
    return getattr(row, _secret_attribute(type(row), column), None)


def _readable_secret(row, column, section_name=None):
    """The secret as this installation reads it back.

    Through the property when there is one, since that is what every caller
    uses. Otherwise through the column, opened with the layer the manifest
    says the application keeps it under: `decrypt_if_needed` alone read an
    ACME account key, a deployment key and a SCEP challenge as the ciphertext
    they are, because those three are written with the key-encryption key and
    not with the database key.
    """
    from security.encryption import decrypt_text
    from utils.encryption import decrypt_if_needed

    if _has_encrypting_property(type(row), column):
        return getattr(row, column)
    stored = _stored_secret(row, column)
    layer = (manifest.SECTIONS[section_name].stored.get(column)
             if section_name else None)
    if layer == 'master':
        return decrypt_text(stored) if stored else stored
    return decrypt_if_needed(stored)


class _Ids:
    """Primary keys from a range a fresh installation never reaches."""

    def __init__(self):
        self._next = SOURCE_ID_BASE

    def __call__(self):
        self._next += 1
        return self._next


def _seed_source():
    """One installation's worth of rows, with every declared reference set.

    Two rows in every section something points at, so "the reference landed
    on the right row" is a statement about identity and not about being the
    only candidate left. Everything is written through the ORM rather than
    through the API: this database is not the suite's, and it holds no admin
    account to call the routes with.
    """
    from utils.datetime_utils import utc_now

    identifier = _Ids()
    now = utc_now()
    made = {}

    def add(section_name, **columns):
        row = _model(section_name)(id=identifier(), **columns)
        db.session.add(row)
        made.setdefault(section_name, []).append(row)
        return row

    def secret(row, section_name, column):
        _write_secret(row, section_name, column,
                      SECRET_VALUES[(section_name, column)])

    # -- the rows other rows point at --------------------------------------
    groups = [add('groups', name=f'xinst-group-{suffix}') for suffix in 'ab']
    roles = [add('custom_roles', name=f'xinst-role-{suffix}') for suffix in 'ab']
    templates = [add('certificate_templates', name=f'xinst-template-{suffix}',
                     template_type='server', extensions_template='{}')
                 for suffix in 'ab']

    providers = [add('sso_providers', name=f'xinst-sso-{suffix}',
                     provider_type='oauth2') for suffix in 'ab']
    for column in ('oauth2_client_secret', 'ldap_bind_password'):
        secret(providers[1], 'sso_providers', column)

    hsm_providers = [add('hsm_providers', name=f'xinst-hsm-{suffix}',
                         type='openbao', config='{}') for suffix in 'ab']
    secret(hsm_providers[1], 'hsm_providers', 'config')
    db.session.flush()

    hsm_keys = [add('hsm_keys', provider_id=hsm_providers[1].id,
                    key_identifier=f'xinst-key-{suffix}', label=f'xinst-{suffix}',
                    algorithm='rsa', key_type='rsa', purpose='sign')
                for suffix in 'ab']

    users = [add('users', username=f'xinst-user-{suffix}',
                 email=f'xinst-{suffix}@example.test', password_hash='x' * 32,
                 role='operator', active=True) for suffix in 'ab']
    users[1].custom_role_id = roles[1].id
    users[1].sso_provider_id = providers[1].id
    # A role built on another role, and a provider recording who added it:
    # two numbers that named a different row on every other installation.
    roles[1].inherits_from = roles[0].id
    hsm_providers[1].created_by = users[1].id
    for column in ('totp_secret', 'backup_codes'):
        secret(users[1], 'users', column)

    # -- authorities and certificates, with usable key material ------------
    authorities, keys, issued = [], {}, {}
    for suffix in 'ab':
        key, certificate = _authority(f'xinst CA {suffix}')
        refid = f'xinst-ca-{suffix}'
        authorities.append(add(
            'certificate_authorities', refid=refid, descr=f'xinst CA {suffix}',
            url_slug=refid, crt=_stored_certificate(certificate),
            prv=_stored_key(key), subject=certificate.subject.rfc4514_string(),
            issuer=certificate.issuer.rfc4514_string(),
            serial_number=format(certificate.serial_number, 'x'),
            valid_from=certificate.not_valid_before,
            valid_to=certificate.not_valid_after))
        keys[refid], issued[refid] = key, certificate
    authorities[1].owner_group_id = groups[1].id
    authorities[1].hsm_key_id = hsm_keys[1].id

    leaves = []
    for suffix in 'ab':
        key, certificate = _leaf(f'xinst-{suffix}.example.test',
                                 keys['xinst-ca-b'], issued['xinst-ca-b'])
        refid = f'xinst-cert-{suffix}'
        leaves.append(add(
            'certificates', refid=refid, descr=f'xinst cert {suffix}',
            caref='xinst-ca-b', crt=_stored_certificate(certificate),
            prv=_stored_key(key), subject_cn=f'xinst-{suffix}.example.test',
            serial_number=format(certificate.serial_number, 'x'),
            valid_from=certificate.not_valid_before,
            valid_to=certificate.not_valid_after))
        keys[refid], issued[refid] = key, certificate
    leaves[1].template_id = templates[1].id
    leaves[1].owner_group_id = groups[1].id
    db.session.flush()

    # -- the rows that point at them ---------------------------------------
    add('role_permissions', role_id=roles[1].id, permission='read:certificates')
    add('ca_template_pins', ca_id=authorities[1].id, template_id=templates[1].id)
    add('group_members', group_id=groups[1].id, user_id=users[1].id, role='member')
    add('api_keys', user_id=users[1].id, key_hash='xinst-api-key-hash',
        name='xinst-api-key', permissions='[]')
    add('auth_certificates', user_id=users[1].id, cert_serial='xinst-auth-serial',
        cert_subject='CN=xinst-auth', cert_fingerprint='xinst-auth-fingerprint')
    add('webauthn_credentials', user_id=users[1].id,
        credential_id=b'xinst-credential-id', public_key=b'xinst-public-key',
        name='xinst-webauthn')
    add('revoked_serials', caref='xinst-ca-b', serial_number='xinst-revoked-serial',
        certificate_id=leaves[1].id, valid_to=now + timedelta(days=30),
        revoked_at=now)

    policies = [add('certificate_policies', name=f'xinst-policy-{suffix}')
                for suffix in 'ab']
    policies[1].ca_id = authorities[1].id
    policies[1].template_id = templates[1].id
    policies[1].approval_group_id = groups[1].id
    db.session.flush()

    # The request names the policy that governs it: a link that used to take
    # the restore down, because resolving it queried the session while a
    # half-built request was pending and the autoflush wrote the row before
    # its required columns were set. The restorer builds the row whole now.
    add('approval_requests', certificate_id=leaves[1].id,
        requester_id=users[1].id, request_type='issue', status='pending',
        policy_id=policies[1].id, created_at=now)

    dns_providers = [add('dns_providers', name=f'xinst-dns-{suffix}',
                         provider_type='cloudflare') for suffix in 'ab']
    secret(dns_providers[1], 'dns_providers', 'credentials')

    acme_accounts = [add('acme_accounts', account_id=f'xinst-acct-{suffix}',
                         jwk='{}', jwk_thumbprint=f'xinst-thumbprint-{suffix}')
                     for suffix in 'ab']
    db.session.flush()

    # used_by_account_id is the ACME account id as a string, which is what
    # the product writes there; the manifest calls it a reference all the
    # same. See NOT_EXERCISED and TestReferencesTheManifestCannotResolve.
    eab = add('acme_eab_credentials', kid='xinst-eab-kid',
              created_by_user_id=users[1].id,
              used_by_account_id=acme_accounts[1].account_id,
              revoked_by_user_id=users[1].id)
    secret(eab, 'acme_eab_credentials', 'hmac_key_b64')

    add('acme_domains', domain='xinst-domain.example.test',
        dns_provider_id=dns_providers[1].id, issuing_ca_id=authorities[1].id)

    # The authority a locally-served zone is signed by: a column that cannot
    # be empty, so the source's number was written into it and PostgreSQL
    # refused the row outright.
    add('acme_local_domains', domain='xinst-local.example.test',
        issuing_ca_id=authorities[1].id, auto_approve=True,
        created_by='xinst-user-b')

    client_accounts = [
        add('acme_client_accounts',
            directory_url=f'https://acme-{suffix}.example.test/directory',
            label=f'xinst-client-{suffix}', email=f'acme-{suffix}@example.test',
            account_key_algorithm='ec256', proxy_slug=f'xinst-proxy-{suffix}')
        for suffix in 'ab']
    # A second account at the same authority, under the same mailbox, told
    # apart only by its label: what migration 077 made possible (#276), and
    # what an identity of (directory_url, email) alone could not tell from
    # the account above.
    client_accounts.append(add(
        'acme_client_accounts',
        directory_url='https://acme-b.example.test/directory',
        label='xinst-client-b-second', email='acme-b@example.test',
        account_key_algorithm='ec256', proxy_slug='xinst-proxy-b-second'))
    for column in ('account_key', 'eab_hmac_key'):
        secret(client_accounts[1], 'acme_client_accounts', column)
    db.session.flush()

    # A TSIG key of the DNS UPDATE listener: bound to a proxy account and to
    # the EAB credential, and recording the user who made it.
    tsig = add('acme_dns_update_keys', name='xinst-tsig.', algorithm='hmac-sha256',
               status='active', acme_client_account_id=client_accounts[1].id,
               eab_credential_id=eab.id, created_by_user_id=users[1].id)
    secret(tsig, 'acme_dns_update_keys', 'secret')
    db.session.flush()

    add('acme_client_orders', order_url='https://acme-b.example.test/order/1',
        domains='["xinst-order.example.test"]', challenge_type='http-01',
        environment='production', key_source='generate', status='valid',
        account_id=acme_accounts[1].account_id,
        acme_client_account_id=client_accounts[1].id,
        dns_provider_id=dns_providers[1].id,
        certificate_id=leaves[1].id, source_certificate_id=leaves[0].id)

    ssh_authorities = [
        add('ssh_cas', refid=f'xinst-sshca-{suffix}',
            descr=f'xinst ssh ca {suffix}', ca_type='user',
            public_key='ssh-ed25519 AAAA xinst',
            private_key=_stored_key(ec.generate_private_key(ec.SECP256R1())),
            key_type='ed25519', fingerprint=f'SHA256:xinst{suffix}')
        for suffix in 'ab']
    ssh_authorities[1].owner_group_id = groups[1].id
    db.session.flush()

    add('ssh_certificates', refid='xinst-sshcert', ssh_ca_id=ssh_authorities[1].id,
        cert_type='user', key_id='xinst-key-id', public_key='ssh-ed25519 AAAA xinst',
        certificate='ssh-ed25519-cert-v01@openssh.com AAAA', principals='["xinst"]',
        serial=17, valid_from=now, valid_to=now + timedelta(days=30),
        key_type='ed25519', fingerprint='SHA256:xinstcert',
        owner_group_id=groups[1].id)

    microsoft = [add('microsoft_cas', name=f'xinst-msca-{suffix}',
                     server=f'ca-{suffix}.example.test') for suffix in 'ab']
    for column in ('password', 'winrm_password', 'client_key_pem'):
        secret(microsoft[1], 'microsoft_cas', column)
    db.session.flush()

    add('msca_requests', msca_id=microsoft[1].id, request_id=42,
        template='WebServer', status='issued',
        cert_id=leaves[1].id, csr_id=leaves[0].id)

    intune = add('intune_apps', name='xinst-intune', tenant_id='xinst.onmicrosoft.com',
                 client_id='xinst-client', client_secret='x')
    secret(intune, 'intune_apps', 'client_secret')
    db.session.flush()
    scep = add('scep_profiles', name='xinst-scep', url_slug='xinst-scep',
               ca_refid='xinst-ca-b', template_id=templates[1].id,
               intune_enabled=True, intune_app_id=intune.id)
    secret(scep, 'scep_profiles', 'challenge_password')

    deploy_targets = [add('deploy_targets', name=f'xinst-deploy-{suffix}',
                          host=f'deploy-{suffix}.example.test', username='ucm',
                          private_key='x') for suffix in 'ab']
    secret(deploy_targets[1], 'deploy_targets', 'private_key')
    db.session.flush()

    add('deploy_bindings', target_id=deploy_targets[1].id,
        certificate_id=leaves[1].id)
    add('crl_deploy_bindings', target_id=deploy_targets[1].id,
        ca_id=authorities[1].id, crl_path='/etc/ucm/xinst.crl',
        format='pem', include_parent_crls=True,
        reload_command='systemctl reload nginx')

    scan_profiles = [add('scan_profiles', name=f'xinst-scan-{suffix}')
                     for suffix in 'ab']
    db.session.flush()
    add('scan_runs', scan_profile_id=scan_profiles[1].id, started_at=now,
        status='completed')
    add('discovered_certificates', target='xinst-discovered.example.test', port=443,
        fingerprint_sha256='xinst-discovered-fingerprint',
        scan_profile_id=scan_profiles[1].id, ucm_certificate_id=leaves[1].id)

    add('key_recovery_requests', cert_id=leaves[1].id, cert_refid='xinst-cert-b',
        reason='xinst', requested_by='xinst-user-b', requested_at=now,
        status='pending')

    # -- the sections that carry only secrets -------------------------------
    smtp = add('smtp_config', smtp_host='smtp.example.test', smtp_port=587,
               smtp_user='xinst', smtp_from='ucm@example.test')
    for column in ('smtp_password', 'smtp_oauth_client_secret',
                   'smtp_oauth_refresh_token'):
        secret(smtp, 'smtp_config', column)

    connector = add('ad_connector', enabled=False, server='ad.example.test',
                    bind_dn='CN=ucm', base_dn='DC=example,DC=test')
    secret(connector, 'ad_connector', 'bind_password')

    endpoint = add('webhook_endpoints', name='xinst-webhook',
                   url='https://hook.example.test/xinst', auth_type='bearer')
    for column in ('secret', 'auth_token'):
        secret(endpoint, 'webhook_endpoints', column)

    db.session.commit()

    # What the source's database actually holds for every secret, so the
    # target can be shown to hold something else.
    stored = {}
    for (section_name, column) in SECRET_VALUES:
        row = _model(section_name).query.filter_by(**SECRET_ROW[section_name]).one()
        stored[(section_name, column)] = _stored_secret(row, column)

    return {
        'keys': keys,
        'certificates': issued,
        'stored_secrets': stored,
        'ids': {name: [row.id for row in rows] for name, rows in made.items()},
    }


def _seed_target_history():
    """The rows the target installation already had of its own.

    An installation being restored onto is not an empty database: it has its
    own groups, users and templates, numbered by its own history. They are
    here so the ids the restore hands out are the target's rather than a
    mirror of the archive's.
    """
    from models import User
    from models.certificate_template import CertificateTemplate
    from models.group import Group

    for index in range(3):
        db.session.add(Group(name=f'other-installation-group-{index}'))
    for index in range(2):
        db.session.add(User(username=f'other-installation-user-{index}',
                            email=f'other-{index}@example.test',
                            password_hash='x' * 32, role='viewer'))
        db.session.add(CertificateTemplate(
            name=f'other-installation-template-{index}', template_type='server',
            extensions_template='{}'))
    db.session.commit()


# ---------------------------------------------------------------------------
# What a restore onto another installation can and cannot place
# ---------------------------------------------------------------------------

# Sections whose references a manifest-driven restore could not resolve on an
# installation that does not already hold the rows they point at: the plan was
# indexed before the first write, the columns are NOT NULL, and the whole
# restore aborted rather than writing an unlinked row. `apply_section` now
# refreshes the index of the sections it points at before resolving, so the
# list is empty and `TestSectionsARestorePlacesOnAFreshInstallation` keeps it
# that way.
ABORTS_THE_RESTORE = ()

# Sections a restore wrote with the source's numeric id, repairing them at
# the very end in `relink_references`. SQLite enforces no foreign key, so the
# repair arrived in time and nobody was any the wiser; PostgreSQL refused the
# insert as it happened and took the whole restore with it, so an archive
# that restored on one backend did not restore on the other.
#
# Empty: every one of them resolves its references where the row is written
# now. `tests/test_restore_reference_resolution_pg.py` is the proof on a real
# PostgreSQL, and `TestWhatPostgreSQLUsedToRefuse` keeps the list at zero.
RESTORED_ONLY_ON_SQLITE: dict = {}

RESTORABLE_SECTIONS = tuple(
    name for name in (
        'users', 'groups', 'custom_roles', 'sso_providers',
        'certificate_templates', 'certificate_authorities', 'certificates',
        'revoked_serials', 'hsm_providers', 'hsm_keys', 'api_keys',
        'auth_certificates', 'certificate_policies', 'approval_requests',
        'dns_providers', 'acme_accounts', 'acme_eab_credentials',
        'acme_domains', 'acme_local_domains', 'acme_client_accounts',
        'acme_client_orders', 'acme_dns_update_keys',
        'ssh_cas', 'ssh_certificates', 'microsoft_cas', 'msca_requests',
        'scep_profiles', 'deploy_targets', 'scan_profiles', 'scan_runs',
        'intune_apps',
        'discovered_certificates', 'smtp_config', 'ad_connector',
        'webhook_endpoints',
        # These six used to abort the restore outright: their references
        # point at rows the same restore creates, and the plan was indexed
        # before the first write. `apply_section` now rebuilds the index of
        # the sections it points at, so they are ordinary sections of the
        # round trip like any other.
        'role_permissions', 'group_members', 'webauthn_credentials',
        'deploy_bindings', 'crl_deploy_bindings', 'ca_template_pins',
        'key_recovery_requests',
    ) if name not in ABORTS_THE_RESTORE
)

# What a PostgreSQL installation will take from the same archive.
RESTORABLE_ON_POSTGRESQL = tuple(name for name in RESTORABLE_SECTIONS
                                 if name not in RESTORED_ONLY_ON_SQLITE)


class Source:
    """The installation the archive was taken from, kept for the module."""

    def __init__(self, app, directory):
        self.app = app
        self.directory = directory
        self.keys = Keys(directory, 'source')
        self.url = f"sqlite:///{directory / 'source.db'}"
        self.seeded = None

    @contextmanager
    def bound(self):
        with _installation(self.app, self.url, self.keys):
            yield

    def archive_of(self, *sections):
        """An archive of these sections, written under the source's keys."""
        with self.bound(), self.app.app_context():
            blob = _service().create_backup(PASSWORD, include=_only(*sections))
            _master, payload = _service()._decrypt_framed(blob, PASSWORD)
        return blob, payload


class Restored:
    """What one cross-installation round trip left behind.

    The installation is not left bound to the application: a test that wants
    to read it says so, so that two round trips in the same file cannot end
    up reading each other's database.
    """

    def __init__(self, source, keys, url, is_postgresql, archive, results):
        self.source = source
        self.keys = keys
        self.url = url
        self.is_postgresql = is_postgresql
        self.archive = archive
        self.results = results

    @contextmanager
    def open(self, app):
        """Read the target installation, under the keys it was restored with."""
        with _installation(app, self.url, self.keys, self.is_postgresql,
                           create_schema=False), app.app_context():
            yield

    def archived(self, section_name):
        return self.archive.get(section_name) or []

    def archived_row(self, section_name, **identity):
        for row in self.archived(section_name):
            if all(row.get(field) == value for field, value in identity.items()):
                return row
        raise AssertionError(
            f"the archive carries no {section_name} row matching {identity}")


@pytest.fixture(scope='module')
def source(app, tmp_path_factory):
    """An installation holding one scenario, written under its own keys."""
    installation = Source(app, tmp_path_factory.mktemp('cross-installation'))
    with installation.bound(), app.app_context():
        installation.seeded = _seed_source()
    return installation


def _restore_onto(app, source, url, sections, is_postgresql=False):
    """Restore the source's archive onto a second installation."""
    blob, archive = source.archive_of(*sections)

    keys = Keys(source.directory, f'target-{"pg" if is_postgresql else "sqlite"}')
    with _installation(app, url, keys, is_postgresql), app.app_context():
        _seed_target_history()
        results = _service().restore_backup(blob, PASSWORD)
    return Restored(source, keys, url, is_postgresql, archive, results)


@pytest.fixture(scope='module')
def restored_on_sqlite(app, source):
    """One round trip onto a SQLite installation, shared by the whole file."""
    return _restore_onto(app, source,
                         f"sqlite:///{source.directory / 'target.db'}",
                         RESTORABLE_SECTIONS)


@pytest.fixture
def restored_on_postgresql(app, source):
    """The same round trip onto a PostgreSQL installation (opt-in).

    One bench, one schema, and the tests that pin what PostgreSQL refuses
    empty it as they go, so this is done again for each test that asks for
    it rather than shared and quietly wiped halfway through.

    A restore that resolves a reference wrongly on SQLite still writes the
    row; only a backend that enforces foreign keys says so out loud. It also
    crosses dialects, which is what an administrator moving to PostgreSQL
    actually does.
    """
    if not _PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set; skipping the PostgreSQL target')

    # The bench is one database; another file resets the same schema.
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _empty_the_postgresql_bench()
        try:
            yield _restore_onto(app, source, _PG_URL, RESTORABLE_ON_POSTGRESQL,
                                is_postgresql=True)
        finally:
            _empty_the_postgresql_bench()


def _empty_the_postgresql_bench():
    engine = create_engine(_PG_URL, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text('DROP SCHEMA public CASCADE'))
            connection.execute(text('CREATE SCHEMA public'))
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Walking the manifest's references
# ---------------------------------------------------------------------------


def _attribute_of(model, column):
    for prop in sa_inspect(model).column_attrs:
        for stored in prop.columns:
            if stored.key == column:
                return prop.key
    return column


def _stable_identity(section_name, values):
    """The part of a section's identity that means anything elsewhere.

    Several sections identify a row by a foreign key and a column -- an HSM
    key by its provider and its identifier, a pin by its authority and its
    template. The number is the source's; only the rest can be looked up
    here.
    """
    section = manifest.SECTIONS[section_name]
    return {field: values.get(field) for field in section.identity
            if field not in section.references and field != 'id'}


def _as_column_value(model, field, value):
    """An archived identity value, back in the shape its column holds.

    Identities travel serialised -- a date as an ISO string, a credential id
    as base64 -- and a query filtered with the serialised form matches
    nothing at all, which reads as "the row was not restored".
    """
    from sqlalchemy.types import Date, DateTime, LargeBinary

    column = sa_inspect(model).columns.get(field)
    if column is None or value is None:
        return value
    if isinstance(column.type, LargeBinary) and isinstance(value, str):
        return base64.b64decode(value)
    if isinstance(column.type, (DateTime, Date)) and isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed.date() if not isinstance(column.type, DateTime) else parsed
    return value


def _row_named_by(section_name, values):
    """The row on this installation that these archived values name."""
    model = _model(section_name)
    stable = {field: _as_column_value(model, field, value)
              for field, value in _stable_identity(section_name, values).items()}
    if not stable:
        # Identified by nothing but foreign keys: this file writes exactly
        # one such row, so there is no ambiguity left to resolve.
        rows = model.query.all()
        assert len(rows) == 1, (
            f"section '{section_name}' is identified only by foreign keys and "
            f"holds {len(rows)} rows here, so no row of it can be named")
        return rows[0]
    found = model.query.filter_by(**stable).all()
    assert len(found) == 1, (
        f"the archive names a {section_name} row by {stable} and this "
        f"installation holds {len(found)} of them")
    return found[0]


def _references_carried_by(archive):
    """Every (section, column) the archive actually carries a reference for."""
    carried = {}
    for section_name, section in manifest.SECTIONS.items():
        for row in archive.get(section_name) or []:
            for column in section.references:
                if row.get(f'{column}{REFERENCE_SUFFIX}'):
                    carried.setdefault((section_name, column), []).append(row)
    return carried


def _where_the_reference_landed(section_name, column, row):
    """Nothing when the reference found the row the archive names, and a
    sentence naming what it found instead otherwise."""
    section = manifest.SECTIONS[section_name]
    try:
        child = _row_named_by(section_name, row)
        parent = _row_named_by(section.references[column],
                               row[f'{column}{REFERENCE_SUFFIX}'])
    except AssertionError as missing:
        # The row itself, or the row it points at, is not on the target: a
        # reference cannot be checked, and the reason is the answer.
        return f'{section_name}.{column}: {missing}'
    landed = getattr(child, _attribute_of(type(child), column), None)

    if landed != parent.id:
        return (f"{section_name}.{column} points at {landed!r}; the row the "
                f"archive names is {parent.id!r} here")
    if landed == row.get(column):
        return (f"{section_name}.{column} kept the source's own id {landed!r}, "
                "so nothing here proves an identity was resolved")
    return None


# References the manifest declares that no round trip in this file puts to
# the test, each with the reason. A reference that is neither exercised nor
# named here fails `test_every_declared_reference_is_accounted_for`.
NOT_EXERCISED = {
}

# Relations a restore places wrongly on another installation. Pinned, not
# accepted: each is a link that quietly points at nothing once the ids are
# not the source's, and this table is what makes a fix visible. It is empty,
# and `_assert_every_reference_landed` fails in both directions -- when a
# relation stops landing and when one listed here starts landing again.
#
# What used to be in it, and what closed it:
#  - msca_requests, scan_runs, discovered_certificates were named in
#    RESTORED_SECTIONS with no restorer behind them: exported, announced as
#    restored, never written. They go through the manifest-driven path now.
#  - approval_requests was written and then removed by the replacing pass:
#    its identity holds foreign keys, so the identity the archive carries
#    (the source's numbers) was not the identity the row has here, and it
#    read as a row the archive does not carry. The pass translates the
#    archived identity through the plan before comparing.
KNOWN_TO_NOT_SURVIVE: dict = {}


def _assert_every_reference_landed(restored):
    carried = _references_carried_by(restored.archive)
    failures, unexpectedly_fine = [], []
    for (section_name, column), rows in sorted(carried.items()):
        if not restored.archived(manifest.SECTIONS[section_name].references[column]):
            # This archive does not carry the section the reference points
            # at, so there is no row here it could have landed on.
            continue
        for row in rows:
            problem = _where_the_reference_landed(section_name, column, row)
            known = (section_name, column) in KNOWN_TO_NOT_SURVIVE
            if problem and not known:
                failures.append(problem)
            if not problem and known:
                unexpectedly_fine.append(f'{section_name}.{column}')
    assert not failures, (
        'references that did not land on the row the archive names:\n  '
        + '\n  '.join(failures))
    assert not unexpectedly_fine, (
        'these relations survive a change of installation now and are still '
        f'listed as known not to: {sorted(unexpectedly_fine)} -- take them out '
        'of KNOWN_TO_NOT_SURVIVE')


def _declared_references():
    return {(name, column) for name, section in manifest.SECTIONS.items()
            for column in section.references}


class TestEveryReferenceLandsOnTheRowTheArchiveNames:
    """The restore used to write the source's numbers into the target."""

    def test_on_sqlite(self, app, restored_on_sqlite):
        with restored_on_sqlite.open(app):
            _assert_every_reference_landed(restored_on_sqlite)

    @_needs_pg
    def test_on_postgresql(self, app, restored_on_postgresql):
        with restored_on_postgresql.open(app):
            _assert_every_reference_landed(restored_on_postgresql)

    def test_the_target_numbered_its_own_rows(self, app, restored_on_sqlite):
        """Nothing here may carry a primary key from the source's range.

        The point of the source's ids being what they are: a row holding one
        of them is a row the restore copied rather than created, and every
        reference "landing correctly" would then prove nothing at all.
        """
        with restored_on_sqlite.open(app):
            carried_over = []
            for section_name in RESTORABLE_SECTIONS:
                model = _model(section_name)
                mapper = sa_inspect(model)
                primary = [column.key for column in mapper.primary_key]
                if len(primary) != 1:
                    continue
                for row in model.query.all():
                    if (getattr(row, primary[0]) or 0) >= SOURCE_ID_BASE:
                        carried_over.append(
                            f'{section_name} #{getattr(row, primary[0])}')
            assert not carried_over, (
                f"the target kept the source's primary keys: {carried_over}")

    def test_every_declared_reference_is_accounted_for(self, restored_on_sqlite):
        """A reference added to the manifest and to no scenario fails here.

        Picking a few relations by hand is how the quiet ones get through:
        the reference nobody thought of is exactly the one that breaks.
        """
        aborting = {(name, column) for name in ABORTS_THE_RESTORE
                    for column in manifest.SECTIONS[name].references}
        accounted = (set(_references_carried_by(restored_on_sqlite.archive))
                     | aborting | set(NOT_EXERCISED))
        unaccounted = _declared_references() - accounted
        assert not unaccounted, (
            'these references are declared by the manifest and nothing in this '
            f'file covers them: {sorted(unaccounted)}')

    def test_the_reasons_given_still_name_a_reference(self):
        """A reason written for a reference the manifest no longer declares is
        a reason nobody will re-read; it goes when the reference goes."""
        stale = (set(NOT_EXERCISED) | set(KNOWN_TO_NOT_SURVIVE)) - _declared_references()
        assert not stale, f'these reasons no longer name a reference: {sorted(stale)}'


class TestALinkTheProtocolNamesComesBackAsItself:
    """The two links that were dropped *because* they had been declared.

    An EAB credential and an ACME client order name the account they belong
    to by its account id: the string the protocol itself uses, the same on
    every installation that holds the account. The manifest declared both
    columns as references to `acme_accounts`, which is indexed by primary
    key, so no identity was ever written beside them, and the restore,
    finding none, cleared a link that needed no translation at all.

    The companion of this class says it on PostgreSQL, where the order's
    column is a foreign key and a wrong value cannot even be written. It is
    said here as well because that file is opt-in: without a PostgreSQL
    server to run against, nothing at all asserted this.
    """

    @pytest.mark.parametrize('section_name, column, identity', [
        ('acme_eab_credentials', 'used_by_account_id', {'kid': 'xinst-eab-kid'}),
        ('acme_client_orders', 'account_id',
         {'order_url': 'https://acme-b.example.test/order/1'}),
    ])
    def test_the_account_the_archive_names_is_still_named(
            self, app, restored_on_sqlite, section_name, column, identity):
        archived = restored_on_sqlite.archived_row(section_name, **identity)
        assert archived[column] == 'xinst-acct-b', \
            'the archive carries the account id, as text and unambiguous'

        with restored_on_sqlite.open(app):
            row = _model(section_name).query.filter_by(**identity).one()
            assert getattr(row, column) == 'xinst-acct-b', (
                f'{section_name}.{column} no longer names the account the '
                'archive named')
            assert _model('acme_accounts').query.filter_by(
                account_id=getattr(row, column)).one(), \
                'and the account it names is one this installation holds'


class TestTwoRowsAnIdentityCouldNotTellApart:
    """An identity that is not unique loses rows without a word.

    Two accounts at the same authority, under the same shared mailbox, are
    what migration 077 made possible on purpose (#276). Identified by the
    pair (directory_url, email) they were one entry in the index: the second
    archived row was applied over the first, the section came out of the
    restore one row short, and the order pointing at the account that
    disappeared was attached to the one that remained.
    """

    def test_both_accounts_of_the_shared_mailbox_arrive(self, app,
                                                        restored_on_sqlite):
        from models.acme_client_account import AcmeClientAccount

        with restored_on_sqlite.open(app):
            same_mailbox = AcmeClientAccount.query.filter_by(
                directory_url='https://acme-b.example.test/directory',
                email='acme-b@example.test').all()
            labels = sorted(account.label for account in same_mailbox)
            assert labels == ['xinst-client-b', 'xinst-client-b-second'], (
                'the two accounts an identity of (directory_url, email) could '
                f'not tell apart came back as {labels}')


class TestACertificateFindsItsAuthority:
    """The one link that is not a number, and has to keep working anyway."""

    def test_the_certificate_still_names_the_authority_that_signed_it(
            self, app, restored_on_sqlite):
        """A certificate points at its authority by refid, not by id, which is
        what lets the pair survive the move. What it must not survive is the
        pair coming apart: a certificate whose caref names an authority this
        installation does not hold has no chain, no CRL and no revocation."""
        from models import CA, Certificate

        with restored_on_sqlite.open(app):
            certificate = Certificate.query.filter_by(refid='xinst-cert-b').one()
            authority = CA.query.filter_by(refid=certificate.caref).one()
            assert authority.refid == 'xinst-ca-b'

            signed = x509.load_pem_x509_certificate(
                base64.b64decode(certificate.crt))
            issuer = x509.load_pem_x509_certificate(base64.b64decode(authority.crt))
            assert signed.issuer == issuer.subject
            issuer.public_key().verify(
                signed.signature, signed.tbs_certificate_bytes,
                ec.ECDSA(signed.signature_hash_algorithm))


class TestWhatPostgreSQLUsedToRefuse:
    """The same archive, onto an installation that enforces its own schema.

    Several restorers wrote the source's numeric id and counted on
    `relink_references`, at the very end of the restore, to point the column
    at the right row. On SQLite, which enforces no foreign key, the repair
    arrived in time and nobody was any the wiser. PostgreSQL refused the
    insert as it happened: the transaction died, the restore was announced as
    failed, and an archive that restored on one backend did not restore on
    the other.

    They resolve the reference where the row is written now.
    """

    def test_no_section_is_left_to_postgresql_to_refuse(self):
        """Every one of them resolves its references where the row is
        written now, so none is left writing a number that belongs to another
        installation. An entry coming back means a section went back to
        relying on the repair at the end -- which PostgreSQL never reaches."""
        assert RESTORED_ONLY_ON_SQLITE == {}

    def test_they_all_restore_on_sqlite_too(self, app, restored_on_sqlite):
        """The seven that used to be in the list, by name: what was quiet on
        SQLite and fatal on PostgreSQL now works on both."""
        with restored_on_sqlite.open(app):
            for section_name in ('api_keys', 'auth_certificates',
                                 'certificate_policies', 'acme_domains',
                                 'ssh_cas', 'ssh_certificates', 'hsm_keys'):
                assert _model(section_name).query.count() > 0, (
                    f"'{section_name}' no longer restores on SQLite either")


class TestWhatARestoreUsedToDropWithoutSayingSo:
    """Rows the archive carried, the restore reported, and nobody wrote.

    `restore_backup` names the sections it did not apply, so an administrator
    is never told a restore is complete while part of the archive was passed
    over. These sections were on the list of what it *does* apply and nothing
    applied them: the count came back silent, the row never arrived, and the
    only way to find out was to go looking for the history it held.

    They go through the manifest-driven path now, and `approval_requests`,
    which was written and then deleted by the pass that makes a restore a
    replacement, survives it: the archived identity is translated through the
    plan before being compared, so a row identified by what it points at is
    no longer read as a row the archive does not carry.
    """

    @pytest.mark.parametrize('section_name',
                             ['msca_requests', 'scan_runs',
                              'discovered_certificates'])
    def test_the_section_is_restored_and_not_merely_announced(
            self, app, restored_on_sqlite, section_name):
        assert len(restored_on_sqlite.archived(section_name)) == 1, \
            'the archive should carry the row this scenario wrote'
        assert section_name not in restored_on_sqlite.results['sections_not_restored']
        with restored_on_sqlite.open(app):
            assert _model(section_name).query.count() == 1, (
                f"'{section_name}' is announced as restored and is not")

    def test_an_approval_request_survives_the_replacing_pass(
            self, app, restored_on_sqlite):
        """`approval_requests` is identified by (certificate_id, created_at),
        and the certificate_id the archive carries is the source's. The row
        the restore had just written held this installation's, so it read as
        a row the archive does not carry and the replacement deleted it."""
        assert len(restored_on_sqlite.archived('approval_requests')) == 1
        assert restored_on_sqlite.results.get('approval_requests') == 1
        with restored_on_sqlite.open(app):
            assert _model('approval_requests').query.count() == 1, \
                'the approval request was written and then taken away again'


class TestNothingAbortsARestoreAnyMore:
    """Six sections used to make a restore onto a fresh installation
    impossible: their references point at rows the same restore creates, the
    plan was indexed before the first write, and every one of those columns is
    NOT NULL, so the restore died after having written everything before it.

    They are part of the ordinary round trip above now, which is the real
    proof; what is left here is the guard that keeps the list empty.
    """

    def test_the_list_of_sections_that_abort_is_empty(self):
        assert ABORTS_THE_RESTORE == (), (
            'a section aborts a restore again: its references resolve to '
            'nothing on an installation that does not already hold them')

    def test_nothing_else_was_left_out_of_the_round_trip(self):
        """The sections this file restores, and the ones it cannot, together
        account for every section the scenario writes a row in."""
        covered = set(RESTORABLE_SECTIONS) | set(ABORTS_THE_RESTORE)
        assert set(SECRET_ROW) <= covered
        assert not (set(ABORTS_THE_RESTORE) & set(RESTORABLE_SECTIONS))


# ---------------------------------------------------------------------------
# The secrets, under a key the source never had
# ---------------------------------------------------------------------------

# Where a secret ends up on the target, measured rather than assumed:
#
#   'database key'        re-encrypted here, with this installation's key --
#                         what the whole design is for;
#   'key-encryption key'  encrypted with the master key rather than the
#                         database key;
#   'the clear'           held readable in the column, which for some of them
#                         is where the application reads it from
#                         (`pyotp.TOTP(user.totp_secret)`,
#                         `json.loads(provider.config)`): putting a ciphertext
#                         there would restore an account whose MFA can no
#                         longer be verified;
#   'nothing'             not restored at all: the section's restorer writes a
#                         hand-picked list of columns and this is not on it.
#
# 'nothing' is always a gap. 'the clear' is a gap only where the model has a
# property that encrypts and the restorer went around it; where the column is
# what the application itself reads, it is the right answer. They are pinned
# here so that moving a column between them is something somebody chose.
AT_REST_AFTER_A_RESTORE = {
    # Put back under the target's database key, as the design intends.
    ('acme_eab_credentials', 'hmac_key_b64'): 'database key',
    ('acme_dns_update_keys', 'secret'): 'database key',
    ('ad_connector', 'bind_password'): 'database key',
    ('dns_providers', 'credentials'): 'database key',
    ('microsoft_cas', 'password'): 'database key',

    # Put back under the target's database key now that their restorers go
    # through the manifest-driven path instead of assigning the private
    # column behind the property, or -- for winrm_password -- instead of not
    # being written at all.
    ('microsoft_cas', 'winrm_password'): 'database key',
    ('microsoft_cas', 'client_key_pem'): 'database key',
    ('smtp_config', 'smtp_password'): 'database key',
    ('sso_providers', 'ldap_bind_password'): 'database key',
    ('sso_providers', 'oauth2_client_secret'): 'database key',
    # And these two were on no restorer's list at all.
    ('smtp_config', 'smtp_oauth_client_secret'): 'database key',
    ('smtp_config', 'smtp_oauth_refresh_token'): 'database key',

    # Readable in the column, which is where the application reads them: the
    # MFA secret is handed straight to pyotp, the HSM configuration straight
    # to json.loads. The restore puts back what the source held.
    ('users', 'backup_codes'): 'the clear',
    ('users', 'totp_secret'): 'the clear',

    # Readable in the column, which is where the application reads it: the
    # HSM configuration goes straight to json.loads.
    ('hsm_providers', 'config'): 'the clear',

    # Plain columns, so no property re-encrypted them, and the restore wrote
    # the archive's cleartext into each: a deployment SSH key, a SCEP
    # challenge, an Intune client secret and a webhook signing secret sat
    # readable in the database of an installation that had them encrypted
    # the minute before it restored its own archive. The manifest now names
    # the layer each column is kept under and the restore puts them back
    # under it.
    ('deploy_targets', 'private_key'): 'key-encryption key',
    ('scep_profiles', 'challenge_password'): 'key-encryption key',
    ('intune_apps', 'client_secret'): 'database key',
    ('webhook_endpoints', 'secret'): 'database key',

    # Never written by the restore at all:
    #  - _restore_microsoft_cas writes a hand-picked list of columns;
    #  - webhook_endpoints.auth_token is applied by the manifest-driven path,
    #    which drops it before it reaches the branch that writes secrets:
    #    the column is named `_auth_token`, so `columns.get('auth_token')` is
    #    None and the row is skipped as "a column this version does not have".
    ('webhook_endpoints', 'auth_token'): 'nothing',

    # Both arrived as the source's own ciphertext until the export learned to
    # read the key-encryption layer as well: the product writes them through
    # `security.encryption` and the export decrypted only through
    # `utils.encryption`, so they opened on no installation but the one that
    # wrote the archive. The account key is a plain column and went back in
    # the clear once the export was fixed; it goes back under the key the
    # product writes it with.
    ('acme_client_accounts', 'account_key'): 'key-encryption key',
    ('acme_client_accounts', 'eab_hmac_key'): 'key-encryption key',
}

# Secrets the archive carried as the source's own ciphertext: the export
# decrypted with one module and the model stored with the other, so nothing
# was decrypted at all and the value only opened on the installation that
# wrote it. Empty: the export now tries both, and refuses the backup when
# neither reads.
CARRIED_AS_SOURCE_CIPHERTEXT: set = set()

# Secrets the restore never writes; there is nothing on the target to read.
NOT_RESTORED_AT_ALL = {key for key, state in AT_REST_AFTER_A_RESTORE.items()
                       if state == 'nothing'}


def _secrets_under_test():
    return sorted(key for key in SECRET_VALUES
                  if key[0] in RESTORABLE_SECTIONS)


def _at_rest(stored):
    """How the database is holding this value: under which key, or not."""
    from security.encryption import key_encryption
    from utils.encryption import is_encrypted as under_the_database_key

    if not stored:
        return 'nothing'
    if under_the_database_key(stored):
        return 'database key'
    if key_encryption.is_string_encrypted(stored):
        return 'key-encryption key'
    return 'the clear'


@pytest.fixture(scope='module')
def secrets_on_the_target(app, restored_on_sqlite):
    """Every declared secret as the target now holds it, read once.

    Measured in one pass so a test can name every column that moved rather
    than the first one, which is what makes this readable when the restore
    changes.
    """
    measured = {}
    with restored_on_sqlite.open(app):
        for section_name, column in _secrets_under_test():
            row = _model(section_name).query.filter_by(
                **SECRET_ROW[section_name]).one()
            stored = _stored_secret(row, column)
            measured[(section_name, column)] = {
                'stored': stored,
                'at_rest': _at_rest(stored),
                'readable': _readable_secret(row, column, section_name),
            }
    return measured


class TestEverySecretSurvivesAChangeOfDatabaseKey:
    """The reason secrets are decrypted at export time and not before.

    An exporter that carried the stored ciphertext produced an archive that
    restored perfectly onto the machine it came from and nowhere else: every
    integration came back with a credential that decrypts to nothing under
    the target's key, and each one only said so the next time it was used.
    """

    def test_the_archive_carries_them_in_the_clear(self, restored_on_sqlite):
        carried_as_ciphertext = []
        for section_name, column in _secrets_under_test():
            row = restored_on_sqlite.archived_row(
                section_name, **SECRET_ROW[section_name])
            if row.get(column) != SECRET_VALUES[(section_name, column)]:
                carried_as_ciphertext.append((section_name, column))
        assert set(carried_as_ciphertext) == CARRIED_AS_SOURCE_CIPHERTEXT, (
            'what the archive carries in the clear changed: now ciphertext '
            f'{sorted(set(carried_as_ciphertext) - CARRIED_AS_SOURCE_CIPHERTEXT)}, '
            'now in the clear '
            f'{sorted(CARRIED_AS_SOURCE_CIPHERTEXT - set(carried_as_ciphertext))}')

    def test_they_are_readable_on_the_target(self, secrets_on_the_target):
        unreadable = []
        for key, measured in sorted(secrets_on_the_target.items()):
            if key in NOT_RESTORED_AT_ALL or key in CARRIED_AS_SOURCE_CIPHERTEXT:
                continue
            if measured['readable'] != SECRET_VALUES[key]:
                unreadable.append(key)
        assert not unreadable, (
            'these secrets cannot be read on an installation whose database '
            f'key is not the source\'s: {unreadable}')

    def test_the_target_does_not_hold_the_source_ciphertext(
            self, restored_on_sqlite, secrets_on_the_target):
        """The strongest of the three: whatever the target holds, it is not
        the bytes the source held, which no key of the target's opens."""
        source_values = restored_on_sqlite.source.seeded['stored_secrets']
        carried_over = []
        for key, measured in sorted(secrets_on_the_target.items()):
            if key in NOT_RESTORED_AT_ALL:
                continue
            if measured['stored'] == source_values[key]:
                carried_over.append(key)
        assert set(carried_over) == CARRIED_AS_SOURCE_CIPHERTEXT, (
            'secrets still holding the bytes the source stored changed: '
            f'{sorted(set(carried_over) ^ CARRIED_AS_SOURCE_CIPHERTEXT)}')

    def test_where_each_secret_ends_up(self, secrets_on_the_target):
        """A restore must not be a way to strip at-rest encryption.

        `restore/apply.py` says secrets go back through the model's property,
        which is what re-encrypts them here. Several restorers assign the
        column underneath instead, and several columns have no such property
        at all, so the value lands in the clear.
        """
        measured = {key: state['at_rest']
                    for key, state in secrets_on_the_target.items()}
        differences = {key: (AT_REST_AFTER_A_RESTORE.get(key), value)
                       for key, value in measured.items()
                       if AT_REST_AFTER_A_RESTORE.get(key) != value}
        assert not differences, (
            'where a restore leaves these secrets changed (pinned, measured): '
            f'{differences}')
        assert set(measured) == set(AT_REST_AFTER_A_RESTORE), \
            'the table and the secrets under test no longer line up'
        assert 'database key' in measured.values(), \
            'no secret at all came back encrypted with the target\'s key'

    def test_the_re_encrypted_ones_use_the_target_key(
            self, restored_on_sqlite, secrets_on_the_target):
        """Encrypted with *this* installation's key, not carried over."""
        from utils.encryption import decrypt_value

        source_key = Fernet(restored_on_sqlite.source.keys.database.encode())
        for key, measured in sorted(secrets_on_the_target.items()):
            if measured['at_rest'] != 'database key':
                continue
            with _keys_of(restored_on_sqlite.keys):
                assert decrypt_value(measured['stored']) == SECRET_VALUES[key], \
                    f'{key} does not open with the target\'s database key'
            with pytest.raises(InvalidToken):
                source_key.decrypt(measured['stored'].encode())

    def test_every_declared_secret_is_accounted_for(self):
        """A secret added to the manifest and to no scenario fails here."""
        declared = {(name, column) for name, section in manifest.SECTIONS.items()
                    for column in section.secrets}
        assert declared == set(SECRET_VALUES), (
            'the manifest and this file disagree about what a secret is: '
            f'not written here {sorted(declared - set(SECRET_VALUES))}, '
            f'no longer declared {sorted(set(SECRET_VALUES) - declared)}')


# ---------------------------------------------------------------------------

# The private keys, under a key-encryption key the source never had
# ---------------------------------------------------------------------------


def _wrapped_with(stored, key):
    """Whether this stored key material opens with that master key."""
    from security.encryption import ENCRYPTED_MARKER

    marked = base64.b64decode(stored)
    assert marked.startswith(ENCRYPTED_MARKER), \
        'the restored key material is not encrypted at rest at all'
    Fernet(key.encode()).decrypt(marked[len(ENCRYPTED_MARKER):])


class TestARestoredAuthorityCanStillSign:
    """Comparing bytes proves nothing: the key has to work.

    The exporters used to fall back to the stored value when they could not
    decrypt it, so the archive carried the at-rest ciphertext in the field a
    restore reads as a PEM. Restoring produced an authority holding something
    that is not a key, on an installation that cannot tell -- until the day it
    is asked to sign or to publish a CRL.
    """

    def test_the_authority_signs_a_new_certificate(self, app,
                                                   restored_on_sqlite):
        from models import CA
        from utils.key_codec import load_pem_bytes

        with restored_on_sqlite.open(app):
            authority = CA.query.filter_by(refid='xinst-ca-b').one()
            certificate = x509.load_pem_x509_certificate(
                base64.b64decode(authority.crt))
            key = serialization.load_pem_private_key(
                load_pem_bytes(authority.prv, context='xinst-ca-b'),
                password=None)

        _key, issued = _leaf('signed-after-the-restore.example.test', key,
                             certificate)
        certificate.public_key().verify(
            issued.signature, issued.tbs_certificate_bytes,
            ec.ECDSA(issued.signature_hash_algorithm))

    def test_the_certificate_keeps_a_key_that_matches_it(self, app,
                                                         restored_on_sqlite):
        from models import Certificate
        from utils.key_codec import load_pem_bytes

        with restored_on_sqlite.open(app):
            row = Certificate.query.filter_by(refid='xinst-cert-b').one()
            certificate = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
            key = serialization.load_pem_private_key(
                load_pem_bytes(row.prv, context='xinst-cert-b'), password=None)

        signature = key.sign(b'restored on another installation',
                             ec.ECDSA(hashes.SHA256()))
        certificate.public_key().verify(
            signature, b'restored on another installation',
            ec.ECDSA(hashes.SHA256()))

    def test_the_key_is_wrapped_with_the_target_key_and_not_the_source(
            self, app, restored_on_sqlite):
        """What makes the archive portable is that the key material is
        rewritten here, not copied: the source's key-encryption key must not
        open what the target now holds, or the archive only ever worked
        because both installations shared a master.key."""
        from models import CA, Certificate

        with restored_on_sqlite.open(app):
            stored = [CA.query.filter_by(refid='xinst-ca-b').one().prv,
                      Certificate.query.filter_by(refid='xinst-cert-b').one().prv]
            ssh_authority = _model('ssh_cas').query.filter_by(
                refid='xinst-sshca-b').one()
            stored.append(ssh_authority.private_key)

        for material in stored:
            _wrapped_with(material, restored_on_sqlite.keys.master)
            with pytest.raises(InvalidToken):
                _wrapped_with(material, restored_on_sqlite.source.keys.master)

    @_needs_pg
    def test_the_authority_signs_on_postgresql_too(self, app,
                                                   restored_on_postgresql):
        from models import CA
        from utils.key_codec import load_pem_bytes

        with restored_on_postgresql.open(app):
            authority = CA.query.filter_by(refid='xinst-ca-b').one()
            certificate = x509.load_pem_x509_certificate(
                base64.b64decode(authority.crt))
            key = serialization.load_pem_private_key(
                load_pem_bytes(authority.prv, context='xinst-ca-b'),
                password=None)

        _key, issued = _leaf('signed-on-postgresql.example.test', key, certificate)
        certificate.public_key().verify(
            issued.signature, issued.tbs_certificate_bytes,
            ec.ECDSA(issued.signature_hash_algorithm))


class TestThisFileLeavesTheSuiteAlone:
    """The database every other file of this worker reads.

    It is shared, there is no rollback between tests, and a row left behind
    with a dangling foreign key fails files nobody has looked at yet. Nothing
    here writes to it: the scenario, the archive and both installations live
    in databases of their own. This is the test that says so.
    """

    def test_no_row_of_the_scenario_reached_it(self, app, restored_on_sqlite):
        from models import CA, Certificate, User
        from models.group import Group

        with app.app_context():
            strays = []
            for model, column in ((Group, Group.name), (User, User.username),
                                  (CA, CA.refid), (Certificate, Certificate.refid)):
                for prefix in ('xinst-%', 'other-installation-%'):
                    found = model.query.filter(column.like(prefix)).count()
                    if found:
                        strays.append(f'{model.__name__}: {found} like {prefix}')
            assert not strays, (
                f'this file wrote to the suite\'s own database: {strays}')
