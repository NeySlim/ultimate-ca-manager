"""A reconciliation killed by SIGKILL halfway: the next one gives the files the rows name.

The child is a pytest process of its own on the same SQLite file and directories;
it stops in the middle of its writes and the parent kills it with SIGKILL.
"""
import base64
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

CHILD_ENV = 'UCM_TEST_RECONCILE_CHILD'


@contextmanager
def _installation(app, spec, create_schema):
    from config.settings import Config
    from tests.test_backup_cross_installation import _bound_to
    patch = pytest.MonkeyPatch()
    try:
        for name in ('CA_DIR', 'CERT_DIR', 'PRIVATE_DIR', 'DATA_DIR'):
            patch.setattr(Config, name, Path(spec[name]))
        with _bound_to(app, spec['url'], create_schema=create_schema), app.app_context():
            yield
    finally:
        patch.undo()


@pytest.mark.skipif(not os.environ.get(CHILD_ENV), reason='run by the parent test only')
def test_child_reconciles_until_it_is_killed(app):
    from services import file_regen_service as regen
    spec = json.loads(os.environ[CHILD_ENV])
    real, done = regen._replace, []

    def stops_halfway(*args, **kwargs):
        real(*args, **kwargs)
        done.append(True)
        if len(done) == 3:
            Path(spec['progress']).write_text('halfway')
            time.sleep(120)

    with _installation(app, spec, create_schema=False):
        regen._replace = stops_halfway
        regen.reconcile_files(full=True)


def _expected():
    from models import CA, Certificate
    from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path
    from utils.key_codec import load_pem_bytes
    files = {}
    for ca in CA.query.all():
        files[str(ca_cert_path(ca))] = base64.b64decode(ca.crt)
        files[str(ca_key_path(ca))] = load_pem_bytes(ca.prv)
    for cert in Certificate.query.all():
        files[str(cert_cert_path(cert))] = base64.b64decode(cert.crt)
        files[str(cert_key_path(cert))] = load_pem_bytes(cert.prv)
    return files


def _on_disk(spec):
    from services.file_regen_service import DIR_ID_NAME, MARKER_NAME
    found = {}
    for name in ('CA_DIR', 'CERT_DIR', 'PRIVATE_DIR'):
        for path in Path(spec[name]).iterdir():
            if path.name not in (MARKER_NAME, DIR_ID_NAME):
                found[str(path)] = path.read_bytes()
    return found


@pytest.mark.slow
def test_a_reconciliation_killed_halfway_is_completed_by_the_next(app, tmp_path):
    from security.encryption import key_encryption
    from services import file_regen_service as regen
    from models import db
    from tests.test_restore_replace_dependents import _authority_row, _certificate_row
    if key_encryption.is_encrypting:
        pytest.skip('the suite runs with values in the clear')
    spec = {name: str(tmp_path / name.lower()) for name in (
        'CA_DIR', 'CERT_DIR', 'PRIVATE_DIR', 'DATA_DIR')}
    spec.update(url=f"sqlite:///{tmp_path / 'ucm.db'}", progress=str(tmp_path / 'progress'))
    Path(spec['DATA_DIR']).mkdir()
    with _installation(app, spec, create_schema=True), regen.insert_file_writes_suspended():
        issuer = _authority_row(f'killed-{uuid.uuid4().hex[:8]}')
        for n in range(4):
            _certificate_row(f'killed-{n}-{uuid.uuid4().hex[:6]}', issuer)
        regen.advance_generation()
        db.session.commit()

    env = dict(os.environ, **{CHILD_ENV: json.dumps(spec)})
    env = {k: v for k, v in env.items() if not k.startswith('GIT_')}
    child = subprocess.Popen(
        [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-p', 'no:xdist',
         f'{__file__}::test_child_reconciles_until_it_is_killed'],
        cwd=str(Path(__file__).resolve().parents[1]), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 90
        while not Path(spec['progress']).exists():
            assert child.poll() is None, 'the child ended before it was killed'
            assert time.monotonic() < deadline, 'the child never reached its writes'
            time.sleep(0.2)
        os.kill(child.pid, signal.SIGKILL)
    finally:
        child.wait(30)
    assert child.returncode == -signal.SIGKILL

    with _installation(app, spec, create_schema=False):
        assert len(_on_disk(spec)) == 3
        assert regen.reconcile_files()['status'] == 'done'
        assert _on_disk(spec) == _expected()
        real, writes = regen._replace, []
        regen._replace = lambda *a, **k: writes.append(a[1]) or real(*a, **k)
        try:
            regen.reconcile_files(full=True)
        finally:
            regen._replace = real
        assert writes == [regen.MARKER_NAME] * 3
