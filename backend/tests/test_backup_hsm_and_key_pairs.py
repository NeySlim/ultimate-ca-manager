"""What a backup does with key material it cannot simply copy.

Two cases have nothing to do with the ordinary path and everything to do with
whether a restored installation can sign:

  * a certificate authority whose private key lives in an HSM has no key of
    its own to carry. What has to survive is the link: the provider, its
    credentials, and which key of that provider is this authority's. The link
    is a numeric id on the source and means nothing on the target, so it
    travels by identity like every other relation.

  * a record whose stored private key is not its certificate's. Refusing to
    back it up would leave an administrator unable to save the state they
    need to repair, so the archive records it instead. What nobody did was
    say so on the way back in: the restore produced an authority that signs
    answers nobody can verify, and reported a clean success.
"""
import base64

import pytest

from models import db
from services.backup import manifest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    """An include map carrying just these sections.

    A full archive restored into the session database would rewrite rows the
    rest of the suite is looking at.
    """
    return {name: name in names for name in manifest.SECTIONS}


def _payload(blob):
    service = _service()
    _key, data = service._decrypt_framed(blob, PASSWORD)
    return data


@pytest.fixture
def hsm_provider(app):
    """A provider with credentials, removed again afterwards."""
    from models.hsm import HsmKey, HsmProvider

    with app.app_context():
        provider = HsmProvider(
            name='zzhsm-contract-provider',
            type='openbao',
            config='{"token": "zzhsm-secret-token"}',
        )
        db.session.add(provider)
        db.session.flush()
        key = HsmKey(
            provider_id=provider.id,
            key_identifier='zzhsm-contract-key',
            label='zzhsm-contract-label',
            algorithm='RSA-2048',
            key_type='RSA',
            purpose='ca-signing',
        )
        db.session.add(key)
        db.session.commit()
        identifiers = (provider.id, key.id, provider.name, key.key_identifier)

    yield identifiers

    with app.app_context():
        HsmKey.query.filter(
            HsmKey.key_identifier.like('zzhsm-contract%')).delete(
                synchronize_session=False)
        HsmProvider.query.filter(
            HsmProvider.name.like('zzhsm-contract%')).delete(
                synchronize_session=False)
        db.session.commit()


class TestAnHsmBackedAuthorityKeepsItsLink:
    def test_the_authority_carries_the_identity_of_its_hsm_key(
            self, app, create_ca, hsm_provider):
        """`hsm_key_id` is a number on the source. On another installation it
        points at whatever happens to hold that number, which is why the
        archive carries the identity of the key beside it."""
        from models import CA

        _provider_id, key_id, provider_name, key_identifier = hsm_provider
        created = create_ca(cn='HSM Linked CA')
        with app.app_context():
            row = db.session.get(CA, created['id'])
            row.hsm_key_id = key_id
            db.session.commit()
            refid = row.refid

            blob = _service().create_backup(
                PASSWORD,
                include=_only('certificate_authorities', 'hsm_keys',
                              'hsm_providers'))
            archived = next(
                item for item in _payload(blob)['certificate_authorities']
                if item['refid'] == refid)

            row.hsm_key_id = None
            db.session.commit()

        assert archived['hsm_key_id'] == key_id
        reference = archived.get('hsm_key_id_ref')
        assert reference, 'the link travels as a number alone'
        assert reference.get('key_identifier') == key_identifier

    def test_the_provider_credentials_travel_readable(
            self, app, hsm_provider):
        """The archive has to be restorable on an installation with another
        database key, so the provider's configuration leaves in the clear
        inside the container rather than as ciphertext bound to this one."""
        from security.encryption import key_encryption

        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('hsm_providers'))
            archived = next(
                item for item in _payload(blob)['hsm_providers']
                if item['name'] == 'zzhsm-contract-provider')

        config = archived['config']
        assert 'zzhsm-secret-token' in config
        assert not key_encryption.is_string_encrypted(config)

    def test_the_key_is_identified_by_its_provider_and_name(self, app,
                                                            hsm_provider):
        """`hsm_keys` is identified by (provider, key identifier): the pair is
        what names the same key on another installation."""
        assert manifest.SECTIONS['hsm_keys'].identity == (
            'provider_id', 'key_identifier')

        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('hsm_keys', 'hsm_providers'))
            archived = next(
                item for item in _payload(blob)['hsm_keys']
                if item['key_identifier'] == 'zzhsm-contract-key')

        assert archived.get('provider_id_ref', {}).get('name') == \
            'zzhsm-contract-provider'


@pytest.fixture
def broken_pair(app, create_ca):
    """An authority whose stored key is another authority's, taken back out.

    Left behind, it would be in every later archive of this file and of every
    other file on this worker, which is exactly the kind of leak the suite
    spent this campaign removing.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from models import CA
    from utils.key_codec import store_pem_bytes

    created = create_ca(cn='Mismatched Pair CA')
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = stranger.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with app.app_context():
        row = db.session.get(CA, created['id'])
        row.prv = store_pem_bytes(pem)
        db.session.commit()
        refid = row.refid

    yield refid

    from models.crl import CRLMetadata
    with app.app_context():
        # A CRL signed meanwhile (restore, scheduler) holds a foreign key to the CA
        CRLMetadata.query.filter_by(ca_id=created['id']).delete(synchronize_session=False)
        CA.query.filter_by(refid=refid).delete(synchronize_session=False)
        db.session.commit()


class TestAMismatchedPairIsNeverSilent:
    def test_the_archive_records_it(self, app, broken_pair):
        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('certificate_authorities'))
            payload = _payload(blob)

        recorded = payload['metadata'].get('key_mismatches') or []
        assert any(broken_pair in str(item) for item in recorded), (
            f'the archive says nothing about {broken_pair}: {recorded}')

    def test_the_restore_repeats_it_instead_of_reporting_a_clean_success(
            self, app, broken_pair):
        """The restore knew: the archive told it. It said nothing, and the
        operator was left with an authority that cannot sign for them."""
        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('certificate_authorities'))
            results = _service().restore_backup(blob, PASSWORD, mode='merge')

        reported = results.get('key_mismatches') or []
        assert any(broken_pair in str(item) for item in reported), (
            f'the restore reported no mismatch: {reported}')

    def test_a_sound_archive_reports_nothing(self, app, create_ca):
        """Nothing in this instance has a key that is not its certificate's,
        so the restore has nothing to report: the warning means something."""
        create_ca(cn='Sound Pair CA')

        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('certificate_authorities'))
            results = _service().restore_backup(blob, PASSWORD, mode='merge')

        assert results.get('key_mismatches') == []

    def test_an_archive_without_the_metadata_is_still_read(self, app):
        """An archive written before the list was carried in the metadata
        still has the flag on the row, and is reported from there."""
        found = _service()._archived_key_mismatches({
            'metadata': {},
            'certificate_authorities': [
                {'refid': 'zz-old-archive', '_key_mismatch': True},
                {'refid': 'zz-sound'},
            ],
        })

        assert found == ['certificate_authorities:zz-old-archive']


class TestTheRouteSaysItToo:
    def test_the_answer_names_the_records_that_cannot_sign(
            self, app, auth_client, broken_pair):
        """The service reports it; an operator restoring through the API has
        to read it without going through the JSON."""
        import io
        import json

        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('certificate_authorities'))

        response = auth_client.post(
            '/api/v2/system/restore',
            data={'password': PASSWORD, 'mode': 'merge',
                  'file': (io.BytesIO(blob), 'b.ucmbkp')},
            content_type='multipart/form-data')

        assert response.status_code == 200, response.data
        body = json.loads(response.data)
        assert broken_pair in json.dumps(body['data']['key_mismatches'])
        assert 'cannot sign' in body['message']


class TestAnArchiveThatRestoresNothing:
    """An archive of metadata alone used to come back as "restored
    successfully", and the route then revoked every session and asked for a
    restart over a file that changed not one row."""

    def test_the_answer_says_nothing_was_restored(self, app, auth_client):
        import io
        import json

        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include={name: False for name in manifest.SECTIONS})

        response = auth_client.post(
            '/api/v2/system/restore',
            data={'password': PASSWORD, 'mode': 'merge',
                  'file': (io.BytesIO(blob), 'b.ucmbkp')},
            content_type='multipart/form-data')

        assert response.status_code == 200, response.data
        body = json.loads(response.data)
        assert 'carried no data' in body['message']
        assert body['data']['sections_carried'] == []
        # The session that made the call is still the session that made it.
        assert body['data'].get('invalidated') is None
        assert body['data'].get('restart_requested') is None

    def test_an_archive_with_a_section_still_says_what_it_carried(
            self, app, create_ca):
        create_ca(cn='Carried Sections CA')

        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('certificate_authorities'))
            results = _service().restore_backup(blob, PASSWORD, mode='merge')

        assert results['sections_carried'] == ['certificate_authorities']
