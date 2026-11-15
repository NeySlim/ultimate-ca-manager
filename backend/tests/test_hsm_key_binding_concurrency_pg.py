"""An X.509 and an SSH CA created at once on one HSM key: one is created, the other refused.

Both creations lock the hsm_keys row before checking either table (services.hsm.key_binding);
the first one pauses after its binding check, so without the lock the second one would pass them too.
"""
import json
import os
import threading
import time
import uuid
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, db
from models.hsm import HsmKey, HsmProvider
from models.ssh import SSHCertificateAuthority
from services.hsm.key_binding import HsmKeyBound

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
PAUSE = 1.5


def _key(app, real):
    pub = real.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        provider = HsmProvider(type='pkcs11', name=f'race-{tag}',
                               config=json.dumps({'module_path': '/opt/vendor/lib/libvendor.so'}))
        db.session.add(provider)
        db.session.commit()
        key = HsmKey(provider_id=provider.id, key_identifier=f'k-{tag}', label=f'k-{tag}', algorithm='EC-P256',
                     key_type='asymmetric', purpose='signing', public_key_pem=pub)
        db.session.add(key)
        db.session.commit()
        key_id = key.id
        db.session.remove()
    return key_id, pub


def _create_ssh(key_id):
    from services.ssh_ca_service import SSHCAService
    return SSHCAService.import_hsm_ca(descr=f'race-ssh-{key_id}', ca_type='user', hsm_key_id=key_id).id


def _create_x509(key_id):
    from services.ca_service import CAService
    return CAService.create_internal_ca(descr=f'race-x509-{key_id}', dn={'CN': f'race-{key_id}'},
                                        hsm_key_id=key_id).id


def _race(app, key_id, first, second):
    """Run *first* then *second* on one key, *first* pausing after its checks; their outcomes."""
    from services.hsm import key_binding
    checked, outcome, locked = threading.Event(), {}, set()
    real_refusal, real_lock = key_binding.refuse_bound_key, key_binding.lock_key

    def lock(key_id):
        locked.add(threading.current_thread().name)
        return real_lock(key_id)

    def pause_first(key):
        # Only the check made under lock_key pauses: an earlier unlocked check proves nothing
        real_refusal(key)
        if threading.current_thread().name == 'first' and 'first' in locked:
            checked.set()
            time.sleep(PAUSE)

    def run(name, create):
        with app.app_context():
            if name == 'second':
                checked.wait(10)
            try:
                outcome[name] = ('created', create(key_id))
            except HsmKeyBound as e:
                db.session.rollback()
                outcome[name] = ('refused', str(e))
            db.session.remove()

    with patch.object(key_binding, 'refuse_bound_key', side_effect=pause_first), \
            patch.object(key_binding, 'lock_key', side_effect=lock):
        threads = [threading.Thread(target=run, name='first', args=('first', first)),
                   threading.Thread(target=run, name='second', args=('second', second))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    return outcome


def _held(app, key_id):
    with app.app_context():
        n = (CA.query.filter_by(hsm_key_id=key_id).count()
             + SSHCertificateAuthority.query.filter_by(hsm_key_id=key_id).count())
        db.session.remove()
    return n


def _sign_with(real):
    def sign(key_id, data, algo=None, hash_algorithm=None):
        digest = {'sha384': hashes.SHA384, 'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
        return real.sign(data, ec.ECDSA(digest))
    return sign


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('order', ['ssh_first', 'x509_first'])
def test_an_x509_and_an_ssh_ca_racing_on_one_key_on_postgresql(app, order):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    first, second = (_create_ssh, _create_x509) if order == 'ssh_first' else (_create_x509, _create_ssh)
    real = ec.generate_private_key(ec.SECP256R1())
    with _a_schema_of_our_own(f'hsm_bind_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        key_id, pub = _key(app, real)
        with patch('services.hsm.HsmService.sign', side_effect=_sign_with(real)), \
                patch('services.hsm.HsmService.get_public_key', return_value=pub):
            outcome = _race(app, key_id, first, second)
        assert outcome['first'][0] == 'created', outcome
        assert outcome['second'][0] == 'refused', outcome
        assert 'already backs the' in outcome['second'][1]
        assert _held(app, key_id) == 1


@pytest.mark.parametrize('order', ['ssh_first', 'x509_first'])
def test_an_x509_and_an_ssh_ca_racing_on_one_key_on_sqlite(app, tmp_path, order):
    """SQLite has no row lock: the no-op UPDATE of lock_key takes the write lock instead."""
    from tests.test_backup_cross_installation import _bound_to

    first, second = (_create_ssh, _create_x509) if order == 'ssh_first' else (_create_x509, _create_ssh)
    real = ec.generate_private_key(ec.SECP256R1())
    with _bound_to(app, f"sqlite:///{tmp_path / 'race.db'}"):
        key_id, pub = _key(app, real)
        with patch('services.hsm.HsmService.sign', side_effect=_sign_with(real)), \
                patch('services.hsm.HsmService.get_public_key', return_value=pub):
            outcome = _race(app, key_id, first, second)
        assert outcome['first'][0] == 'created' and outcome['second'][0] == 'refused', outcome
        assert _held(app, key_id) == 1


def _write_lock_free(engine, key_id):
    """True when another connection takes, without waiting, the lock lock_key takes."""
    if engine.dialect.name == 'sqlite':
        import sqlite3
        conn = sqlite3.connect(engine.url.database, timeout=0, isolation_level=None)
        try:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('ROLLBACK')
            return True
        except sqlite3.OperationalError:
            return False
        finally:
            conn.close()
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    with engine.connect() as conn:
        try:
            conn.execute(text('SELECT id FROM hsm_keys WHERE id = :id FOR UPDATE NOWAIT'), {'id': key_id})
            return True
        except OperationalError:
            return False
        finally:
            conn.rollback()


def _bind_ssh_elsewhere(engine, key_id, descr):
    """Commit, on a connection of its own, an SSH CA on *key_id*."""
    from sqlalchemy.orm import Session
    with Session(engine) as other:
        other.add(SSHCertificateAuthority(
            refid=str(uuid.uuid4()), descr=descr, ca_type='host', public_key='x', private_key='',
            key_source='hsm', hsm_key_id=key_id, key_type='ecdsa-p256', fingerprint=f'SHA256:{uuid.uuid4().hex}'))
        other.commit()


def _proof_cases(app, engine, real):
    """The proof of possession runs before lock_key; the binding is checked again under it."""
    from services.ssh_ca_service import SSHCAService
    key_id, pub = _key(app, real)
    sign = _sign_with(real)
    seen = []

    def slow_sign(kid, *args, **kwargs):
        seen.append(_write_lock_free(engine, kid))
        time.sleep(0.2)
        return sign(kid, *args, **kwargs)
    with patch('services.hsm.HsmService.sign', side_effect=slow_sign), \
            patch('services.hsm.HsmService.get_public_key', return_value=pub), app.app_context():
        SSHCAService.import_hsm_ca(descr=f'proof-{key_id}', ca_type='user', hsm_key_id=key_id)
        db.session.remove()
    assert seen and all(seen), seen

    real = ec.generate_private_key(ec.SECP256R1())
    key_id, pub = _key(app, real)
    sign = _sign_with(real)
    descr = f'raced-{key_id}'

    def binding_sign(kid, *args, **kwargs):
        _bind_ssh_elsewhere(engine, kid, descr)
        return sign(kid, *args, **kwargs)
    with patch('services.hsm.HsmService.sign', side_effect=binding_sign), \
            patch('services.hsm.HsmService.get_public_key', return_value=pub), app.app_context():
        with pytest.raises(HsmKeyBound, match=f"SSH host CA '{descr}'"):
            SSHCAService.import_hsm_ca(descr=f'late-{key_id}', ca_type='user', hsm_key_id=key_id)
        db.session.rollback()
        db.session.remove()
    assert _held(app, key_id) == 1


def test_the_token_proof_runs_outside_the_binding_lock_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'proof.db'}") as engine:
        _proof_cases(app, engine, ec.generate_private_key(ec.SECP256R1()))


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_the_token_proof_runs_outside_the_binding_lock_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'hsm_proof_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True) as engine:
        _proof_cases(app, engine, ec.generate_private_key(ec.SECP256R1()))
