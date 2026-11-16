"""A start moves or removes the files the OPNsense import left under the code tree."""
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

from config.settings import Config
from models import CA, Certificate, db
from tests.fixtures.cross_pki import key_pem, pem
from tests.test_opnsense_import_data_dir import _b64, _forget_rows, _pair, plaintext_mirrors  # noqa: F401
from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path
from utils.key_codec import store_pem_bytes


@pytest.fixture
def legacy(monkeypatch, tmp_path):
    from services import file_regen_service
    root = tmp_path / 'backend-data'
    for sub in ('ca', 'certs', 'private'):
        (root / sub).mkdir(parents=True)
    monkeypatch.setattr(file_regen_service, 'LEGACY_DATA_DIR', root)
    file_regen_service._LEGACY_WARNED.clear()
    return root


def _rows(app, tag):
    """A CA and a certificate as an OPNsense import stores them; returns their refids and bytes."""
    ca, ca_key, leaf, leaf_key = _pair(tag)
    ca_refid, cert_refid = uuid.uuid4().hex[:13], uuid.uuid4().hex[:13]
    with app.app_context():
        db.session.add(CA(refid=ca_refid, descr=f'legacy ca {tag}', crt=_b64(pem(ca)),
                          prv=store_pem_bytes(key_pem(ca_key).encode()),
                          subject=ca.subject.rfc4514_string(), imported_from='opnsense'))
        db.session.add(Certificate(refid=cert_refid, descr=f'legacy leaf {tag}', crt=_b64(pem(leaf)),
                                   prv=store_pem_bytes(key_pem(leaf_key).encode()),
                                   subject=leaf.subject.rfc4514_string(),
                                   imported_from='opnsense'))
        db.session.commit()
    return {'ca': (ca_refid, pem(ca).encode(), key_pem(ca_key).encode()),
            'cert': (cert_refid, pem(leaf).encode(), key_pem(leaf_key).encode())}


def _plant(root, rows):
    ca_refid, ca_crt, ca_prv = rows['ca']
    cert_refid, cert_crt, cert_prv = rows['cert']
    planted = {
        'ca': root / 'ca' / f'{ca_refid}.crt', 'ca_key': root / 'private' / f'{ca_refid}.key',
        'cert': root / 'certs' / f'{cert_refid}.crt', 'cert_key': root / 'private' / f'{cert_refid}.key',
    }
    for name, data in (('ca', ca_crt), ('ca_key', ca_prv), ('cert', cert_crt), ('cert_key', cert_prv)):
        planted[name].write_bytes(data)
        planted[name].chmod(0o644)
    return planted


def _canonical(app, rows):
    with app.app_context():
        ca = CA.query.filter_by(refid=rows['ca'][0]).one()
        cert = Certificate.query.filter_by(refid=rows['cert'][0]).one()
        return {'ca': ca_cert_path(ca), 'ca_key': ca_key_path(ca),
                'cert': cert_cert_path(cert), 'cert_key': cert_key_path(cert)}


def _reconcile(app):
    from services.file_regen_service import reconcile_files
    with app.app_context():
        return reconcile_files()


def test_files_left_in_code_tree_are_moved_when_destination_is_missing(app, legacy, plaintext_mirrors):
    rows = _rows(app, uuid.uuid4().hex[:8])
    planted = _plant(legacy, rows)
    canonical = _canonical(app, rows)
    for path in canonical.values():
        path.unlink(missing_ok=True)
    expected = {k: planted[k].read_bytes() for k in planted}

    stats = _reconcile(app)

    assert stats['legacy_moved'] == 4
    for name, path in canonical.items():
        assert path.read_bytes() == expected[name]
        assert not planted[name].exists()
    assert canonical['ca_key'].stat().st_mode & 0o777 == 0o600
    assert canonical['cert_key'].stat().st_mode & 0o777 == 0o600


def test_identical_copies_are_removed_and_the_pass_is_idempotent(app, legacy, plaintext_mirrors):
    rows = _rows(app, uuid.uuid4().hex[:8])
    planted = _plant(legacy, rows)
    canonical = _canonical(app, rows)
    assert all(path.exists() for path in canonical.values())  # written at insert

    stats = _reconcile(app)
    assert stats['legacy_removed'] == 4 and stats['legacy_moved'] == 0
    assert not any(path.exists() for path in planted.values())
    again = _reconcile(app)
    assert again['legacy_removed'] == again['legacy_moved'] == again['legacy_kept'] == 0
    assert all(path.exists() for path in canonical.values())


def test_plaintext_key_mirrors_are_removed_while_keys_are_encrypted(app, legacy, encryption_enabled):
    rows = _rows(app, uuid.uuid4().hex[:8])
    planted = _plant(legacy, rows)
    canonical = _canonical(app, rows)

    stats = _reconcile(app)

    assert not planted['ca_key'].exists() and not planted['cert_key'].exists()
    assert not canonical['ca_key'].exists() and not canonical['cert_key'].exists()
    assert canonical['ca'].exists() and not planted['ca'].exists()
    assert stats['legacy_removed'] + stats['legacy_moved'] == 4


def test_unmatched_files_are_kept_and_reported_once_without_content(
        app, legacy, plaintext_mirrors, caplog):
    rows = _rows(app, uuid.uuid4().hex[:8])
    secret = b'-----BEGIN PRIVATE KEY-----\nNOT-IN-THE-DATABASE\n-----END PRIVATE KEY-----\n'
    orphan = legacy / 'private' / f'{uuid.uuid4().hex[:13]}.key'
    orphan.write_bytes(secret)
    # The refid of a row, but not its content: not a copy of what the database holds
    differs = legacy / 'ca' / f"{rows['ca'][0]}.crt"
    differs.write_bytes(b'something else')

    with caplog.at_level(logging.WARNING, logger='services.file_regen_service'):
        first = _reconcile(app)
        second = _reconcile(app)

    assert orphan.read_bytes() == secret and differs.read_bytes() == b'something else'
    assert first['legacy_kept'] == 2 and second['legacy_kept'] == 2
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert sum(str(orphan) in m for m in warnings) == 1
    assert sum(str(differs) in m for m in warnings) == 1
    assert not any('NOT-IN-THE-DATABASE' in m for m in warnings)


def test_no_repair_when_data_dir_is_the_code_tree_directory(app, monkeypatch, plaintext_mirrors):
    from services import file_regen_service
    rows = _rows(app, uuid.uuid4().hex[:8])
    monkeypatch.setattr(file_regen_service, 'LEGACY_DATA_DIR', Path(Config.DATA_DIR))
    file_regen_service._LEGACY_WARNED.clear()
    named = Path(Config.CA_DIR) / f"{rows['ca'][0]}.crt"
    named.write_bytes(rows['ca'][1])
    try:
        stats = _reconcile(app)
        assert named.read_bytes() == rows['ca'][1]
        assert stats['legacy_removed'] == stats['legacy_moved'] == stats['legacy_kept'] == 0
    finally:
        named.unlink(missing_ok=True)


def test_repair_runs_only_under_the_reconciliation_lock(app, legacy, monkeypatch, plaintext_mirrors):
    from services import file_regen_service
    rows = _rows(app, uuid.uuid4().hex[:8])
    planted = _plant(legacy, rows)

    @contextmanager
    def held_elsewhere(_dirs, _wait=0.0):
        yield False

    monkeypatch.setattr(file_regen_service, '_exclusive', held_elsewhere)
    assert _reconcile(app)['status'] == 'busy'
    assert all(path.exists() for path in planted.values())


def test_a_namesake_with_other_content_is_not_moved_into_data_dir(app, legacy, plaintext_mirrors):
    rows = _rows(app, uuid.uuid4().hex[:8])
    canonical = _canonical(app, rows)
    canonical['ca'].unlink()
    namesake = legacy / 'ca' / f"{rows['ca'][0]}.crt"
    namesake.write_bytes(b'not the stored certificate')

    stats = _reconcile(app)

    assert namesake.read_bytes() == b'not the stored certificate'
    assert canonical['ca'].read_bytes() == rows['ca'][1]  # written from the row
    assert stats['legacy_kept'] == 1 and stats['legacy_moved'] == 0


def test_a_copy_is_kept_when_its_destination_holds_other_content(app, legacy, plaintext_mirrors, caplog):
    rows = _rows(app, uuid.uuid4().hex[:8])
    planted = _plant(legacy, rows)
    canonical = _canonical(app, rows)
    canonical['ca'].write_bytes(b'edited by an operator')

    with caplog.at_level(logging.WARNING, logger='services.file_regen_service'):
        stats = _reconcile(app)

    assert planted['ca'].read_bytes() == rows['ca'][1]
    assert stats['legacy_kept'] == 1 and stats['legacy_removed'] == 3
    assert any(str(planted['ca']) in r.getMessage() for r in caplog.records)
