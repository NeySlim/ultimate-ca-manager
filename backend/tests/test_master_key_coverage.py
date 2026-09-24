"""Every secret stored under the master key is counted, encrypted by
encrypt-all-keys and decrypted before the key is removed, not only the CA and
certificate keys."""
import base64
import uuid

import pytest
from cryptography.fernet import Fernet

from models import db, SystemConfig


SSH_KEY = base64.b64encode(
    b'-----BEGIN OPENSSH PRIVATE KEY-----\nssh\n-----END OPENSSH PRIVATE KEY-----\n'
).decode()
PEM = '-----BEGIN PRIVATE KEY-----\ntext\n-----END PRIVATE KEY-----\n'


@pytest.fixture
def secrets(app, create_ca):
    """One plaintext secret in each place the master key protects."""
    from models import AcmeClientAccount, ScepProfile
    from models.deploy import DeployTarget
    from models.ssh import SSHCertificateAuthority
    from models.sso import SSOProvider

    ca_refid = create_ca()['refid']
    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        # A fixed key: set aside what the shared database holds under it
        existing = SystemConfig.query.filter_by(key='acme.proxy.account_key').first()
        kept = None if existing is None else existing.value
        if existing is not None:
            db.session.delete(existing)
            db.session.commit()
        ssh = SSHCertificateAuthority(
            descr=f'ssh {tag}', ca_type='user', public_key='ssh-ed25519 AAAA',
            private_key=SSH_KEY, key_type='ed25519', fingerprint=f'SHA256:{tag}')
        target = DeployTarget(name=f'target {tag}', host='host.example',
                              username='deploy', private_key=PEM)
        account = AcmeClientAccount(
            directory_url=f'https://{tag}-test.example/directory',
            label='coverage', email='ops@example.com', account_key=PEM)
        account._eab_hmac_key = 'eab-hmac-secret'
        profile = ScepProfile(name=f'scep {tag}', url_slug=f'scep-{tag}',
                              ca_refid=ca_refid,
                              challenge_password='challenge-secret')
        provider = SSOProvider(name=f'ldap {tag}', provider_type='ldap')
        provider.ldap_bind_password = 'bind-secret'
        config = SystemConfig(key=f'acme.account.{tag}.private_key', value=PEM)
        # Written before migration 031 and never removed since
        legacy = SystemConfig(key=f'acme.client.{tag}.account_key', value=PEM)
        proxy = SystemConfig(key='acme.proxy.account_key', value=PEM)
        rows = [ssh, target, account, profile, provider, config, legacy, proxy]
        db.session.add_all(rows)
        db.session.commit()
        ids = [(type(row), row.id) for row in rows]
    yield {
        'ssh': ids[0], 'target': ids[1], 'account': ids[2],
        'profile': ids[3], 'provider': ids[4], 'config': ids[5],
        'legacy': ids[6], 'proxy': ids[7],
    }
    with app.app_context():
        for model, row_id in ids:
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()
        if kept is not None:
            db.session.add(SystemConfig(key='acme.proxy.account_key', value=kept))
            db.session.commit()


def _stored(secrets):
    """What each place holds under the master key, keyed by its name."""
    get = lambda name: db.session.get(*secrets[name])
    account = get('account')
    return {
        'ssh': get('ssh').private_key,
        'target': get('target').private_key,
        'account_key': account.account_key,
        'eab_hmac': account._eab_hmac_key,
        'challenge': get('profile').challenge_password,
        # The database layer wraps it; the property takes that layer off
        'bind': get('provider').ldap_bind_password,
        'config': get('config').value,
        'legacy': get('legacy').value,
        'proxy': get('proxy').value,
    }


PLAINTEXT = {
    'ssh': SSH_KEY, 'target': PEM, 'account_key': PEM,
    'eab_hmac': 'eab-hmac-secret', 'challenge': 'challenge-secret',
    'bind': 'bind-secret', 'config': PEM, 'legacy': PEM, 'proxy': PEM,
}


@pytest.fixture
def only_these(secrets, encryption_enabled, monkeypatch):
    """Limit the bulk operations to this test's rows: the shared database holds
    other tests' keys, some under a key this test does not have."""
    every = encryption_enabled.master_key_values
    mine = set(secrets.values())
    monkeypatch.setattr(
        encryption_enabled, 'master_key_values',
        lambda: (v for v in every() if (type(v[1]), v[1].id) in mine))
    return encryption_enabled


def test_the_status_and_encrypt_all_count_every_secret(
        app, auth_client, secrets, encryption_enabled):
    from security.encryption import encrypt_private_key, encrypt_text

    def counts():
        status = auth_client.get('/api/v2/system/security/encryption-status')
        run = auth_client.post('/api/v2/system/security/encrypt-all-keys',
                               json={'dry_run': True})
        return (status.get_json()['data']['unencrypted_count'],
                run.get_json()['data']['encrypted'])

    before = counts()
    with app.app_context():
        get = lambda name: db.session.get(*secrets[name])
        get('ssh').private_key = encrypt_private_key(SSH_KEY)
        get('target').private_key = encrypt_text(PEM)
        get('account').account_key = encrypt_text(PEM)
        get('account')._eab_hmac_key = encrypt_text('eab-hmac-secret')
        get('profile').challenge_password = encrypt_text('challenge-secret')
        get('provider').ldap_bind_password = encrypt_text('bind-secret')
        get('config').value = encrypt_text(PEM)
        get('legacy').value = encrypt_text(PEM)
        get('proxy').value = encrypt_text(PEM)
        db.session.commit()

    after = counts()
    assert before[0] - after[0] == len(PLAINTEXT)
    assert before[1] - after[1] == len(PLAINTEXT)


def test_everything_is_encrypted_then_decrypted(app, secrets, only_these):
    from security.encryption import (
        decrypt_all_keys, decrypt_text, encrypt_all_keys,
        has_encrypted_keys_in_db, key_encryption,
    )

    with app.app_context():
        encrypted, _, errors = encrypt_all_keys(dry_run=False)
        assert not errors and encrypted == len(PLAINTEXT)
        stored = _stored(secrets)
        for name, value in stored.items():
            assert key_encryption.is_encrypted(value), name
        assert key_encryption.decrypt(stored['ssh']) == SSH_KEY
        assert all(decrypt_text(stored[name]) == PLAINTEXT[name]
                   for name in PLAINTEXT if name != 'ssh')
        assert has_encrypted_keys_in_db()

        # What disabling encryption runs before it removes the key
        decrypted, _, errors = decrypt_all_keys(dry_run=False)
        assert not errors and decrypted == len(PLAINTEXT)
        db.session.expire_all()
        assert _stored(secrets) == PLAINTEXT
        assert not has_encrypted_keys_in_db()


def test_an_encrypted_secret_outside_ca_and_certificates_is_detected(
        app, secrets, only_these):
    from security.encryption import encrypt_text, has_encrypted_keys_in_db

    with app.app_context():
        assert not has_encrypted_keys_in_db()
        db.session.get(*secrets['target']).private_key = encrypt_text(PEM)
        db.session.commit()
        # Without it, a lost master key goes unnoticed at startup
        assert has_encrypted_keys_in_db()


def test_decrypting_is_all_or_nothing(app, secrets, only_these):
    from security.encryption import (
        ENCRYPTED_MARKER, decrypt_all_keys, encrypt_text, key_encryption,
    )

    foreign = base64.b64encode(
        ENCRYPTED_MARKER + Fernet(Fernet.generate_key()).encrypt(b'x')).decode()
    with app.app_context():
        db.session.get(*secrets['target']).private_key = encrypt_text(PEM)
        db.session.get(*secrets['profile']).challenge_password = foreign
        db.session.commit()

        _, _, errors = decrypt_all_keys(dry_run=False)
        assert len(errors) == 1 and errors[0].startswith('ScepProfile')
        db.session.expire_all()
        # The key is kept when anything fails, so nothing may be left decrypted
        assert key_encryption.is_encrypted(db.session.get(*secrets['target']).private_key)


def test_disabling_is_refused_while_the_key_comes_from_the_environment(
        app, auth_client, secrets, only_these):
    from security.encryption import encrypt_text, key_encryption

    assert key_encryption.key_source == 'env'
    with app.app_context():
        db.session.get(*secrets['target']).private_key = encrypt_text(PEM)
        db.session.commit()

    response = auth_client.post('/api/v2/system/security/disable-encryption')
    # The key would be reloaded from the environment: nothing to disable
    assert response.status_code == 409, response.data
    assert key_encryption.is_enabled
    with app.app_context():
        assert key_encryption.is_encrypted(db.session.get(*secrets['target']).private_key)


def test_disabling_is_refused_while_the_environment_would_supply_a_key(
        app, auth_client, secrets, only_these):
    from security import encryption
    from security.encryption import KeyEncryption, encrypt_text, key_encryption

    # The key file wins over the variable; removing the file reloads the variable
    KeyEncryption.write_key_file(Fernet.generate_key().decode())
    key_encryption.reload()
    assert key_encryption.key_source == 'file'
    with app.app_context():
        db.session.get(*secrets['target']).private_key = encrypt_text(PEM)
        db.session.commit()

    response = auth_client.post('/api/v2/system/security/disable-encryption')
    assert response.status_code == 409, response.data
    assert encryption.MASTER_KEY_PATH.exists()
    with app.app_context():
        assert key_encryption.is_encrypted(db.session.get(*secrets['target']).private_key)
