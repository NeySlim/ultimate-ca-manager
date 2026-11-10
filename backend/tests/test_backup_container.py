"""The container and its reader, on bytes a caller chose.

Every test here feeds the reader something a well-formed archive would never
contain, and pins what it must refuse — before deriving a key, before
expanding a payload, and before the first write to the database.
"""
import base64
import gzip
import hashlib
import json
import struct
import zlib

import pytest

from services.backup import container
from services.backup.container import ContainerError

from tests.backup_v3 import as_v3
from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


def _service():
    from services.backup_service import BackupService
    return BackupService()


PASSWORD = 'Correct-Horse-Battery-9'


@pytest.fixture(scope='module')
def written(app):
    """A real archive of the test instance, as written today."""
    with app.app_context():
        return _service().create_backup(PASSWORD)


@pytest.fixture(scope='module')
def archive(app, written):
    """A real v3 archive of the test instance: v3 is still read, no longer written."""
    with app.app_context():
        return as_v3(written, PASSWORD)


def _split(blob):
    metadata_len = struct.unpack('>H', blob[8:10])[0]
    header_end = 10 + metadata_len
    return blob[:header_end], blob[header_end:]


def _rebuild(blob: bytes, metadata: dict, ciphertext: bytes, *, version=None):
    """Reframe an archive, keeping the bytes the writer chose unless asked."""
    body = json.dumps(metadata, separators=(',', ':'), sort_keys=True).encode()
    return (container.MAGIC
            + bytes([version if version is not None else blob[4], blob[5], blob[6], 0])
            + struct.pack('>H', len(body)) + body + ciphertext)


class TestWhatIsWritten:
    def test_archives_are_written_as_v4(self, written):
        assert written[:4] == container.MAGIC
        assert written[4] == container.FORMAT_VERSION_V4

    def test_the_whole_header_is_authenticated(self, app, archive):
        """Editing any header byte must break the tag, not just the magic."""
        header, ciphertext = _split(archive)
        metadata = json.loads(header[10:].decode())

        for field, value in (
            ('backup_type', 'databases'),      # same length, different meaning
            ('ucm_version', '9.999'),
            ('created_at', '1999-01-01T00:00:00.000000Z'),
        ):
            tampered = dict(metadata)
            tampered[field] = value
            blob = _rebuild(archive, tampered, ciphertext)
            with app.app_context():
                with pytest.raises(Exception) as exc:
                    _service()._decrypt_framed(blob, PASSWORD)
            assert 'Decryption failed' in str(exc.value), field

    def test_a_v2_archive_still_opens(self, app, archive):
        """Old archives authenticated only the magic; they must still read."""
        header, ciphertext = _split(archive)
        metadata = json.loads(header[10:].decode())
        with app.app_context():
            svc = _service()
            # Re-encrypt the same payload the way v2 did
            master_key, payload = svc._decrypt_framed(archive, PASSWORD)
            plaintext = gzip.compress(json.dumps(payload, indent=2, sort_keys=True).encode())
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            nonce = base64.b64decode(metadata['nonce_b64'])
            v2_ciphertext = AESGCM(master_key).encrypt(nonce, plaintext, container.MAGIC)
            v2_metadata = dict(metadata, format_version=2)
            blob = _rebuild(archive, v2_metadata, v2_ciphertext, version=2)

            _key, restored = svc._decrypt_framed(blob, PASSWORD)
            assert restored['metadata']['ucm_version'] == payload['metadata']['ucm_version']


class TestArgon2Path:
    """The production environment ships argon2-cffi; the test one may not."""

    def test_round_trip_under_argon2(self, app):
        from services.backup.decrypt_mixin import _ARGON2_AVAILABLE
        if not _ARGON2_AVAILABLE:
            pytest.skip('argon2-cffi is not installed in this environment')
        with app.app_context():
            svc = _service()
            blob = svc.create_backup(PASSWORD)
            assert blob[6] == container.KDF_ARGON2ID
            _key, payload = svc._decrypt_framed(blob, PASSWORD)
            assert payload['metadata']['schema_version'] == svc.SCHEMA_VERSION


class TestFramingIsRefusedEarly:
    @pytest.mark.parametrize('blob, expected', [
        (b'UCMB' + bytes([9, 1, 2, 0]) + struct.pack('>H', 2) + b'{}' + b'x' * 16,
         'Unsupported backup format version'),
        (b'UCMB' + bytes([3, 0x80, 2, 0]) + struct.pack('>H', 2) + b'{}' + b'x' * 16,
         'unknown container flags'),
        (b'UCMB' + bytes([3, 1, 7, 0]) + struct.pack('>H', 2) + b'{}' + b'x' * 16,
         'Unknown KDF id'),
        (b'UCMB' + bytes([3, 1, 2, 5]) + struct.pack('>H', 2) + b'{}' + b'x' * 16,
         'reserved byte is set'),
        (b'UCMB' + bytes([3, 1, 2, 0]) + struct.pack('>H', 0) + b'x' * 16,
         'empty header metadata'),
        (b'UCMB' + bytes([3, 1, 2, 0]) + struct.pack('>H', 9000) + b'{}',
         'header metadata is too large'),
        (b'UCMB' + bytes([3, 1, 2, 0]) + struct.pack('>H', 2) + b'{}',
         'truncated'),
        (b'NOPE' + bytes([3, 1, 2, 0]) + struct.pack('>H', 2) + b'{}' + b'x' * 16,
         'bad magic bytes'),
        (b'UCM', 'truncated header'),
    ])
    def test_bad_framing_is_named(self, blob, expected):
        with pytest.raises(ContainerError) as exc:
            container.parse_header(blob)
        assert expected in str(exc.value)

    def test_an_oversized_container_is_refused_before_parsing(self, monkeypatch):
        from services.backup import storage
        monkeypatch.setattr(storage, 'restore_upload_limit', lambda: 4096)
        with pytest.raises(ContainerError, match='too large') as refused:
            container.parse_header(b'UCMB' + b'\x00' * 4096)
        assert 'BACKUP_MAX_UPLOAD_MB' in str(refused.value)

    def test_the_ceilings_follow_the_restore_upload_setting(self, monkeypatch):
        """What a restore route accepts, the reader reads: no second, smaller ceiling."""
        from services.backup import storage
        monkeypatch.setattr(storage, 'restore_upload_limit', lambda: 300 * 1024 * 1024)
        assert container.max_container_bytes() == 300 * 1024 * 1024
        assert container.max_plaintext_bytes() == (
            container.PLAINTEXT_PER_ARCHIVE_BYTE * 300 * 1024 * 1024)
        with pytest.raises(ContainerError) as refused:
            container.parse_header(b'UCMB' + b'\x00' * 64)
        assert 'too large' not in str(refused.value)

    def test_a_payload_past_the_decompressed_ceiling_names_the_setting(self, monkeypatch):
        import gzip
        import os
        from services.backup import storage
        monkeypatch.setattr(storage, 'restore_upload_limit', lambda: 1024)
        payload = gzip.compress(os.urandom(4000).hex().encode())
        with pytest.raises(ContainerError) as refused:
            container.decompress_bounded(payload)
        assert 'BACKUP_MAX_UPLOAD_MB' in str(refused.value)


class TestKdfProfilesAreBounded:
    """A header chooses these numbers and both KDFs spend what they are given,
    so they are checked before a key is derived, not while one is."""

    def _metadata(self, **overrides):
        kdf = {'type': 'argon2id', 'time_cost': 3, 'memory_cost': 65536,
               'parallelism': 4, 'hash_len': 32}
        kdf.update(overrides.pop('kdf', {}))
        metadata = {
            'kdf': kdf,
            'salt_b64': base64.b64encode(b'S' * 16).decode(),
            'nonce_b64': base64.b64encode(b'N' * 12).decode(),
        }
        metadata.update(overrides)
        return metadata

    @pytest.mark.parametrize('field, value', [
        ('memory_cost', 2 ** 31),      # terabytes of RAM
        ('memory_cost', 1024),         # below the floor
        ('time_cost', 10_000_000),     # hours of hashing
        ('parallelism', 4096),
        ('hash_len', 1024 * 1024),
    ])
    def test_argon2_outside_its_range_is_refused(self, field, value):
        metadata = self._metadata(kdf={field: value})
        with pytest.raises(ContainerError, match='outside the accepted range'):
            container.validate_kdf(container.KDF_ARGON2ID, metadata)

    def test_pbkdf2_iteration_bomb_is_refused(self):
        metadata = self._metadata(
            kdf={'type': 'pbkdf2-sha256', 'iterations': 2_000_000_000, 'hash_len': 32},
            salt_b64=base64.b64encode(b'S' * 32).decode())
        with pytest.raises(ContainerError, match='outside the accepted range'):
            container.validate_kdf(container.KDF_PBKDF2, metadata)

    def test_a_non_integer_parameter_is_refused(self):
        metadata = self._metadata(kdf={'memory_cost': '65536'})
        with pytest.raises(ContainerError, match='not an integer'):
            container.validate_kdf(container.KDF_ARGON2ID, metadata)

    def test_the_kdf_type_must_match_the_container_id(self):
        metadata = self._metadata(kdf={'type': 'pbkdf2-sha256'})
        with pytest.raises(ContainerError, match='does not match'):
            container.validate_kdf(container.KDF_ARGON2ID, metadata)

    @pytest.mark.parametrize('field, raw', [
        ('salt_b64', base64.b64encode(b'S' * 8).decode()),
        ('nonce_b64', base64.b64encode(b'N' * 24).decode()),
    ])
    def test_wrong_salt_or_nonce_size_is_refused(self, field, raw):
        metadata = self._metadata(**{field: raw})
        with pytest.raises(ContainerError, match='expected'):
            container.validate_kdf(container.KDF_ARGON2ID, metadata)

    def test_unparsable_base64_is_refused(self):
        metadata = self._metadata(salt_b64='not base64!!')
        with pytest.raises(ContainerError, match='not valid base64'):
            container.validate_kdf(container.KDF_ARGON2ID, metadata)

    def test_the_accepted_profile_is_the_one_we_emit(self):
        salt, nonce, params = container.validate_kdf(
            container.KDF_ARGON2ID, self._metadata())
        assert len(salt) == 16 and len(nonce) == 12
        assert params == {'time_cost': 3, 'memory_cost': 65536,
                          'parallelism': 4, 'hash_len': 32}


class TestPayloadBombsAreRefused:
    def test_a_gzip_bomb_is_refused_instead_of_materialised(self):
        """A few kilobytes that expand to gigabytes stop at the ceiling."""
        bomb = gzip.compress(b'\x00' * (64 * 1024 * 1024))
        assert len(bomb) < 128 * 1024
        with pytest.raises(ContainerError, match='expands beyond'):
            container.decompress_bounded(bomb)

    def test_an_ordinary_payload_still_decompresses(self):
        payload = json.dumps({'rows': list(range(1000))}).encode()
        assert container.decompress_bounded(gzip.compress(payload)) == payload

    def test_a_truncated_member_is_refused(self):
        blob = gzip.compress(b'x' * 10_000)
        with pytest.raises(ContainerError, match='truncated compressed payload'):
            container.decompress_bounded(blob[:len(blob) // 2])

    def test_garbage_is_not_mistaken_for_a_member(self):
        with pytest.raises(ContainerError, match='gzip decompression failed'):
            container.decompress_bounded(b'not gzip at all')

    def test_deeply_nested_json_is_refused_before_parsing(self):
        payload = ('[' * 5000 + ']' * 5000).encode()
        with pytest.raises(ContainerError, match='nests deeper'):
            container.json_loads_bounded(payload)

    def test_too_many_objects_are_refused_naming_the_setting(self, monkeypatch):
        from services.backup import storage
        monkeypatch.setattr(storage, 'restore_upload_limit',
                            lambda: 100 * container.ARCHIVE_BYTES_PER_JSON_CONTAINER)
        assert container.max_json_containers() == 100
        payload = json.dumps([{} for _ in range(200)]).encode()
        with pytest.raises(ContainerError, match='more than 100 objects') as refused:
            container.json_loads_bounded(payload)
        assert 'BACKUP_MAX_UPLOAD_MB' in str(refused.value)

    def test_objects_are_counted_as_the_reader_counts_them(self):
        payload = {'a': [{}, {'b': []}], 'c': 'x'}
        text = json.dumps(payload).encode()
        assert container.count_containers(payload) == text.count(b'{') + text.count(b'[')

    def test_braces_inside_strings_do_not_count(self):
        payload = json.dumps({'descr': '{' * 200, 'note': '\\"[[['}).encode()
        assert container.json_loads_bounded(payload)['descr'] == '{' * 200

    def test_a_non_utf8_payload_is_refused(self):
        with pytest.raises(ContainerError, match='not UTF-8'):
            container.json_loads_bounded(b'\xff\xfe\x00')


class TestSchemaIsCheckedBeforeAnyWrite:
    def test_a_future_schema_is_refused(self, app):
        with app.app_context():
            svc = _service()
            with pytest.raises(ValueError, match='newer than'):
                svc._check_payload_schema(
                    {'metadata': {'schema_version': svc.SCHEMA_VERSION + 1}})

    def test_a_reader_requirement_we_cannot_meet_is_refused(self, app):
        with app.app_context():
            svc = _service()
            with pytest.raises(ValueError, match='requires a reader'):
                svc._check_payload_schema(
                    {'metadata': {'min_reader_schema_version': svc.SCHEMA_VERSION + 5}})

    def test_a_section_short_of_its_announced_count_is_refused(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match='holds 1 entries, 4 were written'):
                _service()._check_payload_schema({
                    'metadata': {'schema_version': 3, 'sections': {'users': 4}},
                    'users': [{'username': 'admin'}],
                })

    def test_an_announced_section_that_is_missing_is_refused(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match="announced but missing"):
                _service()._check_payload_schema({
                    'metadata': {'schema_version': 3, 'sections': {'cas': 2}},
                })

    def test_an_archive_without_schema_metadata_is_still_read(self, app):
        """Archives written before the schema was versioned stay restorable."""
        with app.app_context():
            _service()._check_payload_schema({'metadata': {'version': '1.0'}})

    def test_a_real_archive_carries_its_schema_and_dialect(self, app, archive):
        with app.app_context():
            svc = _service()
            _key, payload = svc._decrypt_framed(archive, PASSWORD)
            metadata = payload['metadata']
            assert metadata['schema_version'] == svc.SCHEMA_VERSION
            assert metadata['database_dialect'] in ('sqlite', 'postgresql')
            assert metadata['sections']['users'] == len(payload['users'])
            assert 'audit_logs' in metadata['excluded_sections']
            svc._check_payload_schema(payload)


class TestRestoreRefusesBeforeMutating:
    def test_a_future_archive_changes_nothing(self, app, archive, auth_client):
        """The refusal must land before the first write, not during it."""
        from models import db, User
        with app.app_context():
            svc = _service()
            _key, payload = svc._decrypt_framed(archive, PASSWORD)
            payload['metadata']['schema_version'] = svc.SCHEMA_VERSION + 1
            before = {u.username for u in User.query.all()}

            with pytest.raises(ValueError, match='newer than'):
                svc._check_payload_schema(payload)

            db.session.rollback()
            assert {u.username for u in User.query.all()} == before


class TestReviewOfTheReader:
    """Findings of the adversarial pass over this reader, each pinned."""

    def test_concatenated_gzip_members_are_all_read(self):
        """gzip.decompress read them; a reader that stopped at the first
        would hand back a truncated payload instead of refusing it."""
        multi = gzip.compress(b'{"a":1}') + gzip.compress(b'{"b":2}')
        assert container.decompress_bounded(multi) == b'{"a":1}{"b":2}'

    def test_a_bomb_in_a_later_member_is_still_refused(self):
        multi = gzip.compress(b'x' * 100) + gzip.compress(b'\x00' * (64 * 1024 * 1024))
        with pytest.raises(ContainerError, match='expands beyond'):
            container.decompress_bounded(multi)

    def test_the_announced_version_must_match_the_framing(self):
        """An archive must not describe itself as something it is not."""
        metadata = {'format_version': 2, 'kdf': {'type': 'pbkdf2-sha256'},
                    'salt_b64': '', 'nonce_b64': ''}
        body = json.dumps(metadata, separators=(',', ':')).encode()
        blob = (container.MAGIC + bytes([3, 1, 1, 0])
                + struct.pack('>H', len(body)) + body + b'x' * 16)
        with pytest.raises(ContainerError, match='announces format version 2'):
            container.parse_header(blob)

    def test_a_deeply_nested_header_is_refused_before_parsing(self):
        """A v2 header may be 64 KiB, and json.loads recurses."""
        deep = ('[' * 500 + ']' * 500).encode()
        blob = (container.MAGIC + bytes([2, 1, 1, 0])
                + struct.pack('>H', len(deep)) + deep + b'x' * 16)
        with pytest.raises(ContainerError, match='Invalid backup metadata'):
            container.parse_header(blob)

    def test_a_refusal_tells_the_administrator_what_happened(self, app, auth_client,
                                                             archive):
        """An archive from a newer UCM used to come back as 'invalid restore
        parameters', which says nothing about what to do next."""
        import io
        from services.backup import storage  # noqa: F401  (route import parity)
        with app.app_context():
            svc = _service()
            _key, payload = svc._decrypt_framed(archive, PASSWORD)
            payload['metadata']['schema_version'] = svc.SCHEMA_VERSION + 1
            # Recompute the checksum the way a real writer would, so the
            # refusal under test is the schema one and not a corrupt payload
            payload.pop('checksum', None)
            digest = hashlib.sha256(
                json.dumps(payload, indent=2, sort_keys=True).encode()).hexdigest()
            payload['checksum'] = {'algorithm': 'SHA256', 'value': digest}

        # Rebuild an archive carrying the future schema, with a valid tag
        with app.app_context():
            import gzip as _gzip
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            header, _ = _split(archive)
            metadata = json.loads(header[10:].decode())
            salt = base64.b64decode(metadata['salt_b64'])
            nonce = base64.b64decode(metadata['nonce_b64'])
            svc = _service()
            if metadata['kdf']['type'] == 'argon2id':
                key = svc._derive_argon2id(
                    PASSWORD, salt,
                    time_cost=metadata['kdf']['time_cost'],
                    memory_cost=metadata['kdf']['memory_cost'],
                    parallelism=metadata['kdf']['parallelism'],
                    hash_len=metadata['kdf']['hash_len'])
            else:
                key = svc._derive_pbkdf2(PASSWORD, salt, metadata['kdf']['iterations'])
            plaintext = _gzip.compress(
                json.dumps(payload, indent=2, sort_keys=True).encode())
            blob = header + AESGCM(key).encrypt(nonce, plaintext, header)

        response = auth_client.post(
            '/api/v2/system/restore',
            data={'password': PASSWORD, 'file': (io.BytesIO(blob), 'future.ucmbkp')},
            content_type='multipart/form-data')

        assert response.status_code == 400, response.data
        message = json.loads(response.data)['message']
        assert 'schema version' in message and 'nothing has been changed' in message.lower()

    @pytest.mark.parametrize('offset, value, what', [
        (4, 2, 'the format version byte'),
        (5, 0, 'the gzip flag'),
        (6, 1, 'the KDF id'),
    ])
    def test_editing_a_framing_byte_is_caught(self, app, archive, offset, value, what):
        """v3 signs these bytes, so flipping one must not open the archive."""
        if archive[offset] == value:
            pytest.skip(f'{what} already holds the tested value')
        blob = bytearray(archive)
        blob[offset] = value
        from services.backup.decrypt_mixin import BackupDecryptionError
        with app.app_context():
            with pytest.raises((BackupDecryptionError, ContainerError)) as exc:
                _service()._decrypt_framed(bytes(blob), PASSWORD)
        assert 'Decryption failed' in str(exc.value) or 'Invalid' in str(exc.value), what

    def test_a_v3_archive_cannot_be_downgraded_to_v2(self, app, archive):
        """Claiming v2 would move the authenticated data back to the magic
        alone, which is the weakness v3 exists to close. Flipping the byte
        alone contradicts the header's own JSON; rewriting both to agree
        still fails, because the tag covers the header that was written."""
        from services.backup.decrypt_mixin import BackupDecryptionError

        byte_only = bytearray(archive)
        byte_only[4] = container.FORMAT_VERSION_V2
        with app.app_context():
            with pytest.raises(ContainerError, match='announces format version 3'):
                _service()._decrypt_framed(bytes(byte_only), PASSWORD)

        header, ciphertext = _split(archive)
        metadata = json.loads(header[10:].decode())
        consistent = _rebuild(archive, dict(metadata, format_version=2),
                              ciphertext, version=2)
        with app.app_context():
            with pytest.raises(BackupDecryptionError):
                _service()._decrypt_framed(consistent, PASSWORD)

    def test_the_writer_and_the_reader_share_one_kdf_table(self, app):
        """What is written must be inside what is accepted."""
        for kdf_id, profile in container.KDF_PROFILES.items():
            metadata = {
                'kdf': {'type': profile['type'], **profile['emitted']},
                'salt_b64': base64.b64encode(b'S' * profile['salt_size']).decode(),
                'nonce_b64': base64.b64encode(b'N' * container.NONCE_SIZE).decode(),
            }
            salt, nonce, params = container.validate_kdf(kdf_id, metadata)
            assert params == profile['emitted']

    def test_a_stream_that_cannot_progress_is_refused(self):
        """A member whose stream stalls must be refused, not spun on."""
        stalled = gzip.compress(b'payload' * 100)[:12]
        with pytest.raises(ContainerError):
            container.decompress_bounded(stalled)
