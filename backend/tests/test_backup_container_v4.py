"""The v4 container: chunks authenticated one by one, read and written as a stream.

The framing tests drive `ChunkWriter` and `ChunkReader` directly, with a key
chosen here; the archive tests go through the service, password and all.
"""
import base64
import io
import json
import struct

import pytest

from services.backup import container
from services.backup.container import ChunkAuthError, ContainerError

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


def test_the_end_record_is_valid_json_for_any_section_name():
    """Part bodies are assembled by hand: they must still parse as the writer meant."""
    body = container._part_body('users', 3, [b'{"a":1}', b'{"b":"\\u00e9"}'])
    assert json.loads(body) == {'section': 'users', 'part': 3, 'rows': [{'a': 1}, {'b': 'é'}]}
