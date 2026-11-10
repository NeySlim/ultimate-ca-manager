"""A v4 archive larger than the memory a restore may use is read section by section.

The archive is built here row by row, never as one JSON document: a
`certificates` section of incompressible rows, over 300 MiB on disk. The
restore is followed up to the plan, where every section it applies is loaded
anyway: what is measured is decryption, verification and the checks that run
before the plan, which must not hold the section in memory.
"""
import base64
import os
import time
import tracemalloc

import pytest

from services.backup import container

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
ARCHIVE_BYTES = 300 * 1024 * 1024
PEAK_LIMIT = 100 * 1024 * 1024
ROW_RANDOM_BYTES = 3 * 1024


class _PlanReached(Exception):
    pass


def _rows(count):
    for index in range(count):
        yield {'refid': f'memory-{index}', 'descr': f'synthetic {index}',
               'crt': base64.b64encode(os.urandom(ROW_RANDOM_BYTES)).decode()}


def _write_archive(path, service):
    """A v4 archive of `metadata` and `certificates`, under the PBKDF2 floor."""
    iterations = container.KDF_PROFILES[container.KDF_PBKDF2]['bounds']['iterations'][0]
    salt = os.urandom(32)
    nonce_base = os.urandom(container.NONCE_BASE_SIZE)
    sections = ['metadata', 'certificates']
    header = container.build_header(
        format_version=4, flags=container.FLAG_GZIP, kdf_id=container.KDF_PBKDF2,
        metadata={'format_version': 4, 'backup_type': 'full',
                  'kdf': {'type': 'pbkdf2-sha256', 'iterations': iterations, 'hash_len': 32},
                  'salt_b64': base64.b64encode(salt).decode(),
                  'nonce_base_b64': base64.b64encode(nonce_base).decode(),
                  'chunk_max': container.CHUNK_MAX_DEFAULT, 'sections': sections})
    key = service._derive_pbkdf2(PASSWORD, salt, iterations)
    writer = container.ChunkWriter(key, header, nonce_base, sections, gzip_level=1)
    # base64 of random bytes deflates to about three quarters of its size
    count = int(ARCHIVE_BYTES / (ROW_RANDOM_BYTES * 4 / 3 * 0.74)) + 1
    with open(path, 'wb') as out:
        out.write(header)
        for chunk in writer.section('metadata', {'schema_version': service.SCHEMA_VERSION,
                                                 'min_reader_schema_version': 3,
                                                 'excluded_sections': []}):
            out.write(chunk)
        for chunk in writer.section('certificates', _rows(count)):
            out.write(chunk)
        out.write(writer.finish({'key_mismatches': []}))
    return count


@pytest.mark.slow
def test_a_large_v4_archive_is_read_within_bounded_memory(app, tmp_path, monkeypatch):
    from services.backup import restore_core, section_store
    from services.backup_service import BackupService

    monkeypatch.setattr(section_store, 'store_directory', lambda: str(tmp_path))
    seen = {}

    def stop_at_the_plan(cls, backup_data, pruned=frozenset()):
        seen['peak'] = tracemalloc.get_traced_memory()[1]
        seen['rows'] = section_store.section_length(backup_data, 'certificates')
        raise _PlanReached()

    monkeypatch.setattr(restore_core.RestorePlan, 'build', classmethod(stop_at_the_plan))
    service = BackupService()
    path = tmp_path / 'large.ucmbkp'
    count = _write_archive(path, service)
    assert path.stat().st_size >= ARCHIVE_BYTES

    started = time.monotonic()
    with app.app_context():
        tracemalloc.start()
        try:
            with pytest.raises(_PlanReached):
                service.restore_backup_from_path(path, PASSWORD, mode='merge')
        finally:
            tracemalloc.stop()

    assert seen['rows'] == count
    assert seen['peak'] < PEAK_LIMIT, (
        f"peak {seen['peak'] / 2 ** 20:.0f} MiB reading a "
        f"{path.stat().st_size / 2 ** 20:.0f} MiB archive")
    # The section files went with the store
    assert sorted(os.listdir(tmp_path)) == ['large.ucmbkp']
    assert time.monotonic() - started < 600
