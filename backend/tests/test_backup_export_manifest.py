"""What the manifest-driven export puts in an archive.

The export used to be twenty-seven hand-written dictionaries: a column added
to a model never reached an archive, and a secret encrypted with the source's
database key travelled as ciphertext nobody else could read. These tests pin
the two properties that fixes: everything is carried, and what is carried is
readable somewhere else.
"""
import base64
import json

import pytest

from models import db
from services.backup import manifest
from services.backup.export_generic import IdentityIndex, export_section

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


@pytest.fixture(scope='module')
def payload(app):
    with app.app_context():
        svc = _service()
        blob = svc.create_backup(PASSWORD)
        _key, data = svc._decrypt_framed(blob, PASSWORD)
        return data


class TestSectionsNoArchiveUsedToCarry:
    @pytest.mark.parametrize('section', [
        'acme_client_accounts',   # upstream account key and EAB
        'ad_connector',
        'webhook_endpoints',
        'deploy_targets',
        'deploy_bindings',
        'scep_profiles',
        'ca_template_pins',
        'role_permissions',       # a custom role without them grants nothing
        'group_members',
        'webauthn_credentials',
    ])
    def test_the_section_is_present(self, payload, section):
        assert section in payload, f"{section} is still missing from the archive"


class TestFieldsNoArchiveUsedToCarry:
    def test_users_carry_their_authentication_state(self, payload):
        user = payload['users'][0]
        for field in ('totp_secret', 'totp_confirmed', 'totp_exempt', 'backup_codes',
                      'sso_provider_id', 'sso_external_id', 'custom_role_id',
                      'auth_source', 'preferences', 'force_password_change'):
            assert field in user, f"users.{field} is missing"

    def test_authorities_carry_their_recent_pki_settings(self, app, create_ca, payload):
        create_ca(cn='Manifest Fields CA')
        with app.app_context():
            rows = export_section('certificate_authorities', IdentityIndex())
        assert rows
        ca = rows[0]
        for field in ('url_slug', 'hsm_key_id', 'path_length', 'name_constraints_permitted',
                      'name_constraints_excluded', 'policy_constraints_require',
                      'policy_constraints_inhibit', 'inhibit_any_policy', 'sia_enabled',
                      'sia_urls', 'delta_crl_enabled', 'crl_publish_interval_hours',
                      'crl_digest', 'owner_group_id', 'created_by'):
            assert field in ca, f"certificate_authorities.{field} is missing"

    def test_certificates_carry_their_identifiers_and_renewal_history(
            self, app, create_ca, create_cert):
        ca = create_ca(cn='Manifest Cert Fields CA')
        issued = create_cert(cn='manifest-fields.example.com', ca_id=ca['id'])
        with app.app_context():
            rows = export_section('certificates', IdentityIndex())
        cert = next(r for r in rows if r['refid'] == issued['refid']) \
            if any('refid' in r for r in rows) else rows[0]
        for field in ('aki', 'ski', 'san_upn', 'renewed_at', 'renewed_times',
                      'template_overrides', 'subject_cn'):
            assert field in cert, f"certificates.{field} is missing"

    def test_smtp_carries_its_oauth2_credentials(self, app):
        from models.email_notification import SMTPConfig
        with app.app_context():
            created = False
            config = SMTPConfig.query.first()
            if config is None:
                config = SMTPConfig(smtp_host='smtp.example.test', smtp_port=587)
                db.session.add(config)
                db.session.commit()
                created = True
            try:
                rows = export_section('smtp_config', IdentityIndex())
            finally:
                if created:
                    db.session.delete(config)
                    db.session.commit()
        assert rows
        for field in ('smtp_auth_method', 'smtp_oauth_provider', 'smtp_oauth_client_id',
                      'smtp_oauth_client_secret', 'smtp_oauth_refresh_token',
                      'smtp_oauth_token_url', 'smtp_oauth_tenant_id'):
            assert field in rows[0], f"smtp_config.{field} is missing"


class TestRelationsTravelByIdentity:
    """A numeric id means nothing on the target; the identity beside it does."""

    def test_every_declared_reference_is_exported_with_its_identity(
            self, app, auth_client, create_ca, create_cert):
        from tests.test_backup_contract_matrix import _remove, _seed_all
        # The factory hangs its rows off a CA and certificates; a revoked one fills
        # the revocation sections. SSH material is the one thing nothing can invent.
        ca = create_ca(cn='Manifest Reference CA')
        create_cert(cn='manifest-issued.example.com', ca_id=ca['id'])
        revoked = create_cert(cn='manifest-revoked.example.com', ca_id=ca['id'])
        r = auth_client.post(f"/api/v2/certificates/{revoked['id']}/revoke", json={'reason': 'superseded'})
        assert r.status_code == 200, r.get_json()
        exempt = {'ssh_cas', 'ssh_certificates'}
        with app.app_context():
            # A row in every section the factory can build, so none is skipped as empty.
            _seeded, _failures, order, _secrets = _seed_all()
            try:
                index = IdentityIndex()
                checked = set()
                for name, section in manifest.SECTIONS.items():
                    if not section.references or section.optional:
                        continue
                    rows = export_section(name, index)
                    if not rows:
                        continue
                    checked.add(name)
                    for column in section.references:
                        assert f'{column}_ref' in rows[0], \
                            f"{name}.{column} travels as a number only"
                wanted = {n for n, s in manifest.SECTIONS.items()
                          if s.references and not s.optional} - exempt
                assert checked == wanted, sorted(wanted - checked)
            finally:
                _remove(order)

    def test_the_identity_is_the_target_row_not_its_primary_key(self, app, create_user):
        create_user(username='manifest_identity_user', role='operator')
        with app.app_context():
            from models import User
            from models.group import Group, GroupMember
            group = Group(name='manifest-identity-group')
            db.session.add(group)
            db.session.commit()
            user = User.query.filter_by(username='manifest_identity_user').first()
            db.session.add(GroupMember(group_id=group.id, user_id=user.id, role='member'))
            db.session.commit()
            try:
                rows = export_section('group_members', IdentityIndex())
                mine = [r for r in rows if r['group_id'] == group.id]
                assert mine, 'the membership was not exported'
                assert mine[0]['user_id_ref'] == {'username': 'manifest_identity_user'}
                assert mine[0]['group_id_ref'] == {'name': 'manifest-identity-group'}
            finally:
                GroupMember.query.filter_by(group_id=group.id).delete()
                db.session.delete(group)
                db.session.commit()


class TestSecretsLeaveWithTheArchive:
    """The gate of this lot: an archive must open on an installation that
    never had the source's database key."""

    def test_a_secret_is_carried_in_the_clear_inside_the_container(self, app, monkeypatch):
        from cryptography.fernet import Fernet
        from models.acme_models import DnsProvider
        import utils.encryption as enc

        with app.app_context():
            provider = DnsProvider(name='portable-dns', provider_type='cloudflare')
            provider.credentials = json.dumps({'api_token': 'portable-secret-token'})
            db.session.add(provider)
            db.session.commit()
            try:
                rows = export_section('dns_providers', IdentityIndex())
                mine = [r for r in rows if r['name'] == 'portable-dns'][0]
                assert 'portable-secret-token' in mine['credentials'], \
                    'the archive carries ciphertext instead of the credential'

                # The source's database key is gone: the archive must still
                # hold something usable, since it no longer depends on it.
                monkeypatch.setenv('UCM_DB_ENCRYPTION_KEY', Fernet.generate_key().decode())
                enc._cipher = None if hasattr(enc, '_cipher') else None
                assert 'portable-secret-token' in mine['credentials']
            finally:
                db.session.delete(provider)
                db.session.commit()

    def test_an_unreadable_secret_stops_the_backup(self, app, monkeypatch):
        from services.backup.errors import BackupExportError
        from models.acme_models import DnsProvider
        import utils.encryption as enc

        with app.app_context():
            provider = DnsProvider(name='unreadable-dns', provider_type='cloudflare')
            provider.credentials = json.dumps({'api_token': 'x'})
            db.session.add(provider)
            db.session.commit()
            stored = provider._credentials
            try:
                real = enc.decrypt_value
                monkeypatch.setattr(
                    enc, 'decrypt_value',
                    lambda value: None if value == stored else real(value))
                with pytest.raises(BackupExportError, match='could not be decrypted'):
                    export_section('dns_providers', IdentityIndex())
            finally:
                db.session.delete(provider)
                db.session.commit()


class TestKeyAndCertificateAreCheckedAtExport:
    """A mismatched pair is a fact of the source, recorded rather than
    refused: a backup must stay possible precisely when something is wrong,
    and the restore is where the pair is turned away."""

    def test_a_mismatch_is_recorded_in_the_archive(self, app, create_ca, monkeypatch):
        """Only a pair that could be compared and did not match is recorded:
        a record whose certificate or key cannot be read has not been shown to
        be anyone else's."""
        authority = create_ca(cn='Recorded Mismatch CA')
        with app.app_context():
            import utils.cert_issuer as issuer
            monkeypatch.setattr(issuer, 'private_key_matches', lambda key, cert: False)

            svc = _service()
            mine = next(row for row in svc._export_cas(True)
                        if row['refid'] == authority['refid'])
            assert mine.get('_key_mismatch'), 'the mismatch was not recorded on the row'

            blob = svc.create_backup(PASSWORD)
            _key, data = svc._decrypt_framed(blob, PASSWORD)
            recorded = data['metadata']['key_mismatches']
            assert f"certificate_authorities:{authority['refid']}" in recorded

    def test_a_matching_pair_records_nothing(self, app, create_ca):
        authority = create_ca(cn='Matching Pair CA')
        with app.app_context():
            svc = _service()
            blob = svc.create_backup(PASSWORD)
            _key, data = svc._decrypt_framed(blob, PASSWORD)
            assert f"certificate_authorities:{authority['refid']}" not in \
                data['metadata']['key_mismatches']


class TestSectionAccounting:
    def test_counts_and_digests_cover_every_section(self, payload):
        metadata = payload['metadata']
        sections = set(metadata['sections'])
        digests = set(metadata['section_digests'])
        carried = {k for k in payload if k not in ('metadata', 'checksum')}
        assert carried == sections, f"counts miss {sorted(carried - sections)}"
        assert carried == digests, f"digests miss {sorted(carried - digests)}"

    def test_a_modified_section_is_named(self, app, payload):
        from services.backup.errors import BackupSchemaError
        altered = json.loads(json.dumps(payload))
        altered['groups'].append({'name': 'ghost-group'})
        altered['metadata']['sections']['groups'] += 1   # hide it from the count
        with app.app_context():
            with pytest.raises(BackupSchemaError, match="section 'groups'"):
                _service()._check_payload_schema(altered)


class TestTheRestoreSaysWhatItLeavesBehind:
    """Every section the manifest declares is applied now; what remains is an
    archive from a version that carries more than this one knows about."""

    def test_an_unknown_section_is_reported_rather_than_dropped(self, app):
        with app.app_context():
            svc = _service()
            blob = svc.create_backup(PASSWORD)
            _key, data = svc._decrypt_framed(blob, PASSWORD)

            data['a_section_from_a_later_version'] = [{'anything': 1}]
            data.pop('checksum', None)
            forged = _reseal(svc, blob, data)

            results = svc.restore_backup(forged, PASSWORD)
            assert 'a_section_from_a_later_version' in results['sections_not_restored']


class TestSectionsTheOldRestoreIgnored:
    """The sixteen sections the export learned to carry are now put back."""

    def test_a_webhook_endpoint_comes_back_with_a_usable_secret(self, app):
        from services.webhook_service import WebhookEndpoint
        from utils.encryption import decrypt_if_needed, encrypt_if_needed
        with app.app_context():
            endpoint = WebhookEndpoint(name='restored-hook',
                                       url='https://hook.example.test/z',
                                       events='["certificate.issued"]')
            endpoint.secret = encrypt_if_needed('a-secret-only-this-server-knows')
            db.session.add(endpoint)
            db.session.commit()

            # Only the section under test: restoring a whole archive into the
            # session database would rewrite rows other tests are looking at.
            blob = _service().create_backup(PASSWORD, include=_only('webhook_endpoints'))
            WebhookEndpoint.query.filter_by(name='restored-hook').delete()
            db.session.commit()
            assert WebhookEndpoint.query.filter_by(name='restored-hook').first() is None

            try:
                _service().restore_backup(blob, PASSWORD)
                back = WebhookEndpoint.query.filter_by(name='restored-hook').first()
                assert back is not None, 'the endpoint was not restored'
                assert back.url == 'https://hook.example.test/z'
                # `secret` is a plain column the application keeps encrypted,
                # so what matters is what the delivery path reads out of it
                # and that the column is not holding the secret in the clear:
                # the archive carries it that way so it can be restored under
                # another key, and the restore is where it goes back under
                # this one.
                assert decrypt_if_needed(back.secret) == (
                    'a-secret-only-this-server-knows')
                assert back.secret != 'a-secret-only-this-server-knows', (
                    'the restore left the signing secret readable in the '
                    'database')
            finally:
                WebhookEndpoint.query.filter_by(name='restored-hook').delete()
                db.session.commit()

    def test_a_membership_follows_the_user_not_the_number(self, app, create_user):
        """The source's ids mean nothing here: the membership must land on the
        user with that username, whatever id it happens to have."""
        from models import User
        from models.group import Group, GroupMember
        create_user(username='membership_follows_identity', role='operator')
        with app.app_context():
            group = Group(name='membership-identity-group')
            db.session.add(group)
            db.session.commit()
            user = User.query.filter_by(username='membership_follows_identity').first()
            db.session.add(GroupMember(group_id=group.id, user_id=user.id, role='member'))
            db.session.commit()

            blob = _service().create_backup(
                PASSWORD, include=_only('group_members', 'groups', 'users'))
            GroupMember.query.filter_by(group_id=group.id).delete()
            db.session.commit()

            try:
                _service().restore_backup(blob, PASSWORD)
                back = GroupMember.query.filter_by(group_id=group.id).first()
                assert back is not None, 'the membership was not restored'
                assert back.user_id == user.id
            finally:
                GroupMember.query.filter_by(group_id=group.id).delete()
                db.session.delete(group)
                db.session.commit()


def _only(*names):
    """An include map that carries just these sections."""
    return {name: name in names for name in manifest.SECTIONS}


def _reseal(svc, original_blob, data):
    """Rewrite an archive's payload, keeping its container and password."""
    import gzip
    import hashlib
    import struct
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from services.backup import container

    metadata_len = struct.unpack('>H', original_blob[8:10])[0]
    header = original_blob[:10 + metadata_len]
    metadata = json.loads(header[10:].decode())
    salt = base64.b64decode(metadata['salt_b64'])
    nonce = base64.b64decode(metadata['nonce_b64'])

    if metadata['kdf']['type'] == 'argon2id':
        key = svc._derive_argon2id(
            PASSWORD, salt,
            time_cost=metadata['kdf']['time_cost'],
            memory_cost=metadata['kdf']['memory_cost'],
            parallelism=metadata['kdf']['parallelism'],
            hash_len=metadata['kdf']['hash_len'])
    else:
        key = svc._derive_pbkdf2(PASSWORD, salt, metadata['kdf']['iterations'])

    digest = hashlib.sha256(
        json.dumps(data, indent=2, sort_keys=True).encode()).hexdigest()
    data['checksum'] = {'algorithm': 'SHA256', 'value': digest}
    plaintext = gzip.compress(json.dumps(data, indent=2, sort_keys=True).encode())
    return header + AESGCM(key).encrypt(nonce, plaintext, header)
