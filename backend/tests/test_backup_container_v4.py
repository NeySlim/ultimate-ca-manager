"""The v4 container: chunks authenticated one by one, read and written as a stream.

The framing tests drive `ChunkWriter` and `ChunkReader` directly, with a key
chosen here; the archive tests go through the service, password and all.
"""
import base64
import hashlib
import io
import json
import os
import struct

import pytest

from services.backup import container
from services.backup.container import ChunkAuthError, ContainerError

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
KEY = bytes(range(32))
NONCE_BASE = b'\x01' * container.NONCE_BASE_SIZE
SECTIONS = ['metadata', 'users', 'certificates']
CHUNK_MAX = container.CHUNK_MAX_RANGE[0]


def _header(sections=SECTIONS, chunk_max=CHUNK_MAX, **extra):
    metadata = {
        'format_version': 4, 'chunk_max': chunk_max, 'sections': sections,
        'nonce_base_b64': base64.b64encode(NONCE_BASE).decode(),
        'kdf': {'type': 'pbkdf2-sha256', 'iterations': 600_000, 'hash_len': 32},
        'salt_b64': base64.b64encode(b'S' * 32).decode(),
    }
    metadata.update(extra)
    return container.build_header(format_version=4, flags=container.FLAG_GZIP,
                                  kdf_id=container.KDF_PBKDF2, metadata=metadata)


def _rows(count, size=40):
    return [{'refid': f'r{index}', 'pem': 'x' * size} for index in range(count)]


def _payload():
    return [('metadata', {'schema_version': 3}),
            ('users', _rows(3)),
            ('certificates', _rows(400, size=500))]


def _write(header=None, payload=None, key=KEY, end=None):
    header = header if header is not None else _header()
    writer = container.ChunkWriter(key, header, NONCE_BASE, SECTIONS, chunk_max=CHUNK_MAX)
    chunks = [header]
    for name, value in payload if payload is not None else _payload():
        chunks.extend(writer.section(name, value))
    chunks.append(writer.finish(end if end is not None else {'key_mismatches': []}))
    return chunks


def _read(blob, key=KEY):
    stream = io.BytesIO(blob)
    metadata, header = container.read_header(stream)
    reader = container.ChunkReader(stream, key, header, metadata, NONCE_BASE)
    sections = {}
    for name, _part, rows in reader.parts():
        if isinstance(rows, dict):
            sections[name] = rows
        else:
            sections.setdefault(name, []).extend(rows)
    return sections, reader.end


def _frames(chunks):
    """The header, then each framed chunk, as written."""
    return chunks[0], chunks[1:]


class TestRoundTrip:
    def test_sections_come_back_as_written(self):
        sections, end = _read(b''.join(_write()))
        assert sections == dict(_payload())
        assert end == {'key_mismatches': []}

    def test_a_large_section_is_split_into_parts_of_whole_rows(self):
        header, frames = _frames(_write())
        # metadata, users, certificates in several parts, end record
        assert len(frames) > 4
        stream = io.BytesIO(b''.join([header] + frames))
        metadata, raw = container.read_header(stream)
        parts = [(name, part) for name, part, _rows in container.ChunkReader(
            stream, KEY, raw, metadata, NONCE_BASE).parts()]
        assert [part for name, part in parts if name == 'certificates'] == list(
            range(len(frames) - 3))

    def test_an_empty_section_is_still_one_part(self):
        payload = [('metadata', {}), ('users', []), ('certificates', iter(()))]
        sections, _end = _read(b''.join(_write(payload=payload)))
        assert sections == {'metadata': {}, 'users': [], 'certificates': []}

    def test_the_v4_header_is_recognised(self):
        blob = b''.join(_write())
        assert container.format_version_of(blob) == container.FORMAT_VERSION_V4
        metadata, header = container.read_header(io.BytesIO(blob))
        assert metadata['format_version'] == 4
        assert metadata['sections'] == SECTIONS
        assert blob.startswith(header)

    def test_a_row_larger_than_a_chunk_is_refused_at_write_time(self):
        writer = container.ChunkWriter(KEY, _header(), NONCE_BASE, SECTIONS, chunk_max=CHUNK_MAX)
        list(writer.section('metadata', {}))
        with pytest.raises(ContainerError, match="row of section 'users'"):
            list(writer.section('users', [{'pem': 'x' * (CHUNK_MAX + 1)}]))


class TestTamperingIsRefused:
    def test_a_truncated_chunk(self):
        blob = b''.join(_write())
        with pytest.raises(ContainerError, match='truncated'):
            _read(blob[:-10])

    def test_a_missing_last_chunk(self):
        header, frames = _frames(_write())
        with pytest.raises(ContainerError, match='final chunk is missing'):
            _read(b''.join([header] + frames[:-1]))

    def test_permuted_chunks(self):
        header, frames = _frames(_write())
        frames[1], frames[2] = frames[2], frames[1]
        with pytest.raises(ChunkAuthError) as refused:
            _read(b''.join([header] + frames))
        assert refused.value.counter == 1

    def test_a_skipped_counter(self):
        header, frames = _frames(_write())
        del frames[2]
        with pytest.raises(ChunkAuthError) as refused:
            _read(b''.join([header] + frames))
        assert refused.value.counter == 2

    def test_a_chunk_from_another_archive_with_the_same_key(self):
        """The header is in every chunk's additional data."""
        header, frames = _frames(_write())
        other_header, other = _frames(_write(header=_header(created_at='x')))
        frames[1] = other[1]
        with pytest.raises(ChunkAuthError):
            _read(b''.join([header] + frames))

    def test_a_flipped_ciphertext_byte(self):
        header, frames = _frames(_write())
        damaged = bytearray(frames[1])
        damaged[10] ^= 1
        frames[1] = bytes(damaged)
        with pytest.raises(ChunkAuthError, match='chunk 1 does not authenticate'):
            _read(b''.join([header] + frames))

    def test_edited_metadata_breaks_every_chunk(self):
        header, frames = _frames(_write())
        edited = _header(created_at='forged')
        with pytest.raises(ChunkAuthError) as refused:
            _read(b''.join([edited] + frames))
        assert refused.value.counter == 0

    def test_a_trailing_chunk_after_the_end_record(self):
        header, frames = _frames(_write())
        with pytest.raises(ContainerError):
            _read(b''.join([header] + frames + [frames[1]]))

    def test_an_end_record_with_a_wrong_digest(self):
        class Lying(container.ChunkWriter):
            def finish(self, metadata=None):
                self._tallies['users'].digest.update(b'not what was written')
                return super().finish(metadata)

        header = _header()
        writer = Lying(KEY, header, NONCE_BASE, SECTIONS, chunk_max=CHUNK_MAX)
        chunks = [header]
        for name, value in _payload():
            chunks.extend(writer.section(name, value))
        chunks.append(writer.finish({}))
        with pytest.raises(ContainerError, match="section 'users' does not match the digest"):
            _read(b''.join(chunks))

    def test_a_section_left_out_of_the_stream(self):
        header = _header()
        writer = container.ChunkWriter(KEY, header, NONCE_BASE, SECTIONS, chunk_max=CHUNK_MAX)
        chunks = [header] + list(writer.section('metadata', {}))
        writer._next = len(SECTIONS)     # skip the rest without writing them
        chunks.append(writer.finish({}))
        with pytest.raises(ContainerError, match="'users' is announced but missing"):
            _read(b''.join(chunks))

    def test_a_chunk_length_beyond_the_header_bound(self):
        header, frames = _frames(_write())
        frames[0] = struct.pack('>I', container.chunk_ciphertext_ceiling(CHUNK_MAX) + 1) + b'x' * 32
        with pytest.raises(ContainerError, match='outside what its header allows'):
            _read(b''.join([header] + frames))

    def test_version_five_is_refused(self):
        blob = bytearray(b''.join(_write()))
        blob[4] = 5
        with pytest.raises(ContainerError, match='Unsupported backup format version: 5'):
            container.read_header(io.BytesIO(bytes(blob)))

    @pytest.mark.parametrize('chunk_max', [1024, 2 ** 40, '8388608', True])
    def test_a_chunk_size_outside_its_range(self, chunk_max):
        blob = _header(chunk_max=chunk_max)
        metadata, header = container.read_header(io.BytesIO(blob))
        with pytest.raises(ContainerError, match='chunk size'):
            container.ChunkReader(io.BytesIO(b''), KEY, header, metadata, NONCE_BASE)

    @pytest.mark.parametrize('sections', [[], ['users', 'users'], ['../etc'], 'users',
                                          ['x'] * 300])
    def test_a_section_list_that_is_not_one(self, sections):
        blob = _header(sections=sections)
        metadata, header = container.read_header(io.BytesIO(blob))
        with pytest.raises(ContainerError, match='section list'):
            container.ChunkReader(io.BytesIO(b''), KEY, header, metadata, NONCE_BASE)


class TestThroughTheService:
    def test_archives_are_written_as_v4(self, app):
        with app.app_context():
            from services.backup_service import BackupService
            blob = BackupService().create_backup(PASSWORD)
        assert blob[:4] == container.MAGIC
        assert blob[4] == container.FORMAT_VERSION_V4
        metadata, _header = container.read_header(io.BytesIO(blob))
        assert metadata['sections'][0] == 'metadata'
        assert metadata['chunk_max'] == container.CHUNK_MAX_DEFAULT
        assert 'nonce_b64' not in metadata

    def test_every_archive_has_its_own_salt_and_nonce_base(self, app):
        with app.app_context():
            from services.backup_service import BackupService
            service = BackupService()
            first = container.read_header(io.BytesIO(service.create_backup(PASSWORD)))[0]
            second = container.read_header(io.BytesIO(service.create_backup(PASSWORD)))[0]
        assert first['salt_b64'] != second['salt_b64']
        assert first['nonce_base_b64'] != second['nonce_base_b64']

    def test_round_trip_reads_the_payload_back(self, app):
        with app.app_context():
            from services.backup_service import BackupService
            service = BackupService()
            blob = service.create_backup(PASSWORD)
            _key, payload = service._decrypt_framed(blob, PASSWORD)
        assert payload['metadata']['schema_version'] == service.SCHEMA_VERSION
        assert payload['metadata']['sections']['users'] == len(payload['users'])
        assert 'checksum' not in payload
        # The end record's digest is the v3 section digest, so both read the same way
        for name in ('users', 'configuration'):
            canonical = json.dumps(payload[name], sort_keys=True, default=str).encode()
            assert payload['metadata']['section_digests'][name] == hashlib.sha256(
                canonical).hexdigest()

    def test_a_wrong_password_is_a_decryption_failure(self, app):
        from services.backup.decrypt_mixin import BackupDecryptionError
        with app.app_context():
            from services.backup_service import BackupService
            service = BackupService()
            blob = service.create_backup(PASSWORD)
            with pytest.raises(BackupDecryptionError, match='wrong password'):
                service._decrypt_framed(blob, 'Another-Horse-Battery-7')

    def test_a_later_chunk_damaged_is_named_not_blamed_on_the_password(self, app):
        with app.app_context():
            from services.backup_service import BackupService
            service = BackupService()
            blob = bytearray(service.create_backup(PASSWORD))
            blob[-20] ^= 1
            with pytest.raises(ContainerError, match='does not authenticate'):
                service._decrypt_framed(bytes(blob), PASSWORD)

    def test_restore_from_a_path(self, app, tmp_path):
        with app.app_context():
            from services.backup_service import BackupService
            service = BackupService()
            path = tmp_path / 'archive.ucmbkp'
            path.write_bytes(service.create_backup(PASSWORD, include={
                name: False for name in container_sections()}))
            results = service.restore_backup_from_path(path, PASSWORD, mode='merge')
        assert results['sections_carried'] == []

    def test_a_restore_leaves_no_section_file_behind(self, app, tmp_path, monkeypatch):
        from services.backup import section_store
        monkeypatch.setattr(section_store, 'store_directory', lambda: str(tmp_path))
        with app.app_context():
            from services.backup_service import BackupService
            service = BackupService()
            blob = service.create_backup(PASSWORD, include={
                name: False for name in container_sections()})
            service.restore_backup(blob, PASSWORD, mode='merge')
            damaged = bytearray(blob)
            damaged[-20] ^= 1
            with pytest.raises(ContainerError):
                service.restore_backup(bytes(damaged), PASSWORD, mode='merge')
        assert os.listdir(tmp_path) == []


    def test_a_restore_runs_in_the_system_temp_dir_when_the_spool_is_unusable(
            self, app, tmp_path, monkeypatch):
        import tempfile

        from services.backup import section_store
        monkeypatch.setattr('utils.upload_spool.prepare_spool_dir', lambda _d: None)
        monkeypatch.setitem(app.config, 'UPLOAD_SPOOL_DIR', None)
        monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
        made = []
        real = tempfile.mkdtemp

        def spy(*args, **kwargs):
            path = real(*args, **kwargs)
            if kwargs.get('prefix') == section_store.STORE_PREFIX:
                made.append(path)
            return path

        monkeypatch.setattr(tempfile, 'mkdtemp', spy)
        with app.app_context():
            from services.backup_service import BackupService
            service = BackupService()
            blob = service.create_backup(PASSWORD, include={
                name: False for name in container_sections()})
            service.restore_backup(blob, PASSWORD, mode='merge')
        assert made
        assert all(path.startswith(str(tmp_path) + os.sep) for path in made)

def container_sections():
    from services.backup.manifest import SECTIONS as MANIFEST
    return list(MANIFEST)


def test_a_part_body_is_the_json_the_writer_meant():
    """Part bodies are assembled by hand: they must still parse as the writer meant."""
    body = container._part_body('users', 3, container._rows([b'{"a": 1}', b'{"b": "\\u00e9"}']))
    assert json.loads(body) == {'section': 'users', 'part': 3, 'rows': [{'a': 1}, {'b': 'é'}]}
