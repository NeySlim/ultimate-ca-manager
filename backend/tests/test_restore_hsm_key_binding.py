"""A merge restore never binds one HSM key to two authorities.

The archive's authority lands on the key row the target already holds (same provider, same key
identifier); the target already gave that key to another authority. The restore is refused,
naming both, and nothing is changed. Each case runs on a database of its own, SQLite and PostgreSQL.
"""
import json
import os
import uuid
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, db
from models.hsm import HsmKey, HsmProvider
from models.ssh import SSHCertificateAuthority
from services.backup import manifest
from services.backup.errors import BackupSchemaError

PASSWORD = 'Correct-Horse-Battery-9'
_PG_URL = os.environ.get('UCM_TEST_PG_URL')
SECTIONS = ('certificate_authorities', 'ssh_cas', 'hsm_keys', 'hsm_providers')


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    return {name: name in names for name in manifest.SECTIONS}


class _Token:
    """One provider and one key row, its signatures made by a local twin."""

    def __init__(self, real=None):
        self.real = real or ec.generate_private_key(ec.SECP256R1())
        self.pem = self.real.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        tag = uuid.uuid4().hex[:8]
        provider = HsmProvider(type='pkcs11', name=f'restore-{tag}',
                               config=json.dumps({'module_path': '/opt/vendor/lib/libvendor.so'}))
        db.session.add(provider)
        db.session.flush()
        self.key = HsmKey(provider_id=provider.id, key_identifier=f'k-{tag}', label=f'k-{tag}',
                          algorithm='EC-P256', key_type='asymmetric', purpose='signing',
                          public_key_pem=self.pem)
        db.session.add(self.key)
        db.session.commit()

    def patches(self):
        def sign(key_id, data, algo=None, hash_algorithm=None):
            digest = {'sha384': hashes.SHA384, 'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
            return self.real.sign(data, ec.ECDSA(digest))
        return (patch('services.hsm.HsmService.sign', side_effect=sign),
                patch('services.hsm.HsmService.get_public_key', return_value=self.pem))

    def ssh_ca(self, descr, ca_type):
        from services.ssh_ca_service import SSHCAService
        one, two = self.patches()
        with one, two:
            return SSHCAService.import_hsm_ca(descr=descr, ca_type=ca_type, hsm_key_id=self.key.id)

    def x509_ca(self, descr):
        from services.ca_service import CAService
        one, two = self.patches()
        with one, two:
            return CAService.create_internal_ca(descr=descr, dn={'CN': descr}, hsm_key_id=self.key.id)


def _remove(ca):
    from tests.seeded_rows import delete_cas
    if isinstance(ca, CA):
        delete_cas(CA.query.filter_by(id=ca.id))
    else:
        db.session.delete(ca)
    db.session.commit()


def _holders(key_id):
    return sorted([f'x509:{d}' for (d,) in db.session.query(CA.descr).filter_by(hsm_key_id=key_id)]
                  + [f'ssh:{d}' for (d,) in db.session.query(SSHCertificateAuthority.descr)
                     .filter_by(hsm_key_id=key_id)])


CASES = {
    # archived authority, authority the target gave the key to since, and how each is named
    'ssh_on_ssh': (lambda t: t.ssh_ca('archived', 'user'), lambda t: t.ssh_ca('here', 'host'),
                   "SSH user CA 'archived'", "SSH host CA 'here'"),
    'ssh_on_x509': (lambda t: t.ssh_ca('archived', 'user'), lambda t: t.x509_ca('here'),
                    "SSH user CA 'archived'", "X.509 CA 'here'"),
    'x509_on_ssh': (lambda t: t.x509_ca('archived'), lambda t: t.ssh_ca('here', 'host'),
                    "X.509 CA 'archived'", "SSH host CA 'here'"),
    'x509_on_x509': (lambda t: t.x509_ca('archived'), lambda t: t.x509_ca('here'),
                     "X.509 CA 'archived'", "X.509 CA 'here'"),
}


def _refused_merge(app, case):
    archived, here, archived_name, here_name = CASES[case]
    with app.app_context():
        token = _Token()
        held = archived(token)
        kind = 'x509' if isinstance(held, CA) else 'ssh'
        blob = _service().create_backup(PASSWORD, include=_only(*SECTIONS))
        _remove(held)
        here(token)
        before = _holders(token.key.id)
        with pytest.raises(BackupSchemaError) as refused:
            _service().restore_backup(blob, PASSWORD, mode='merge')
        db.session.rollback()
        message = str(refused.value)
        assert archived_name in message and here_name in message, message
        assert f"HSM key '{token.key.label}'" in message, message
        assert 'IntegrityError' not in message and 'UNIQUE' not in message.upper(), message
        assert _holders(token.key.id) == before and len(before) == 1
        assert kind + ':archived' not in before
        db.session.remove()


@pytest.mark.parametrize('case', sorted(CASES))
def test_a_merge_onto_a_key_taken_here_is_refused_on_sqlite(app, tmp_path, case):
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'restore.db'}"):
        _refused_merge(app, case)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('case', sorted(CASES))
def test_a_merge_onto_a_key_taken_here_is_refused_on_postgresql(app, case):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'restore_bind_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _refused_merge(app, case)


@pytest.mark.parametrize('kind', ['ssh', 'x509'])
def test_a_merge_of_the_authority_already_on_the_key_is_restored_on_sqlite(app, tmp_path, kind):
    """The archive's authority is the one already here: it is updated, not refused."""
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'restore.db'}"), app.app_context():
        token = _Token()
        token.ssh_ca('same', 'user') if kind == 'ssh' else token.x509_ca('same')
        blob = _service().create_backup(PASSWORD, include=_only(*SECTIONS))
        _service().restore_backup(blob, PASSWORD, mode='merge')
        assert _holders(token.key.id) == [f'{kind}:same']
        db.session.remove()


def test_a_key_shared_before_the_restore_does_not_stop_it_on_sqlite(app, tmp_path):
    """Two authorities on one key from an earlier release: the merge is not theirs to refuse."""
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'restore.db'}"), app.app_context():
        token = _Token()
        token.x509_ca('earlier')
        db.session.add(SSHCertificateAuthority(
            refid=str(uuid.uuid4()), descr='shared', ca_type='host', public_key='x', private_key='',
            key_source='hsm', hsm_key_id=token.key.id, key_type='ecdsa-p256', fingerprint='SHA256:x'))
        db.session.commit()
        blob = _service().create_backup(PASSWORD, include=_only('hsm_keys', 'hsm_providers'))
        _service().restore_backup(blob, PASSWORD, mode='merge')
        assert _holders(token.key.id) == ['ssh:shared', 'x509:earlier']
        db.session.remove()


def _archive_with_two_x509_cas_on_one_key(app, url):
    """An archive of an installation where two X.509 CAs share one key (a 2.x race left it so)."""
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, url) as engine, app.app_context():
        token = _Token()
        token.x509_ca('first')
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP INDEX uq_ca_hsm_key_id')
        db.session.add(CA(refid=str(uuid.uuid4()), descr='second', crt='', hsm_key_id=token.key.id))
        db.session.commit()
        blob = _service().create_backup(PASSWORD, include=_only(*SECTIONS))
        label = token.key.label
        db.session.remove()
    return blob, label


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_an_archive_giving_one_key_to_two_x509_cas_is_refused_on_sqlite(app, tmp_path, mode):
    from tests.test_backup_cross_installation import _bound_to
    blob, label = _archive_with_two_x509_cas_on_one_key(app, f"sqlite:///{tmp_path / 'source.db'}")
    with _bound_to(app, f"sqlite:///{tmp_path / 'target.db'}"), app.app_context():
        with pytest.raises(BackupSchemaError) as refused:
            _service().restore_backup(blob, PASSWORD, mode=mode)
        db.session.rollback()
        message = str(refused.value)
        assert (f"HSM key '{label}'" in message and "X.509 CA 'first'" in message
                and "X.509 CA 'second'" in message), message
        assert 'UNIQUE' not in message.upper() and 'nothing has been changed' in message, message
        assert CA.query.count() == 0 and HsmKey.query.count() == 0
        db.session.remove()


def _token_key_on_two_rows(app, tmp_path, archived, here, mode='merge'):
    """The archive's authority on its own provider row, the target's on another row of the same token key."""
    from tests.test_backup_cross_installation import _bound_to
    real = ec.generate_private_key(ec.SECP256R1())
    with _bound_to(app, f"sqlite:///{tmp_path / 'source.db'}"), app.app_context():
        archived(_Token(real))
        blob = _service().create_backup(PASSWORD, include=_only(*SECTIONS))
        db.session.remove()
    with _bound_to(app, f"sqlite:///{tmp_path / 'target.db'}"), app.app_context():
        token = _Token(real)
        here(token)
        before = sorted(_holders(token.key.id))
        with pytest.raises(BackupSchemaError) as refused:
            _service().restore_backup(blob, PASSWORD, mode=mode)
        db.session.rollback()
        assert sorted(_holders(token.key.id)) == before
        assert HsmKey.query.count() == 1
        db.session.remove()
    return str(refused.value)


@pytest.mark.parametrize('case', sorted(CASES))
def test_a_merge_onto_another_row_of_a_token_key_taken_here_is_refused(app, tmp_path, case):
    archived, here, archived_name, here_name = CASES[case]
    message = _token_key_on_two_rows(app, tmp_path, archived, here)
    assert archived_name in message and here_name in message, message
    assert 'nothing has been changed' in message, message


def test_two_rows_of_one_token_key_bound_before_the_restore_do_not_stop_it_on_sqlite(app, tmp_path):
    """Two rows of one token key already bound here (a race on PostgreSQL): not the merge's to refuse."""
    from tests.test_backup_cross_installation import _bound_to
    with _bound_to(app, f"sqlite:///{tmp_path / 'restore.db'}"), app.app_context():
        real = ec.generate_private_key(ec.SECP256R1())
        one, two = _Token(real), _Token(real)
        one.x509_ca('earlier')
        db.session.add(SSHCertificateAuthority(
            refid=str(uuid.uuid4()), descr='twin', ca_type='host', public_key='x', private_key='',
            key_source='hsm', hsm_key_id=two.key.id, key_type='ecdsa-p256', fingerprint='SHA256:x'))
        db.session.commit()
        blob = _service().create_backup(PASSWORD, include=_only('hsm_keys', 'hsm_providers'))
        _service().restore_backup(blob, PASSWORD, mode='merge')
        assert _holders(one.key.id) == ['x509:earlier'] and _holders(two.key.id) == ['ssh:twin']
        db.session.remove()


@pytest.mark.parametrize('kind', ['x509', 'ssh'])
def test_a_replacement_whose_removed_authority_waits_for_the_writes_frees_its_key(app, tmp_path, monkeypatch,
                                                                                kind):
    """The authority here goes, the archived one takes its key back: the removal waiting for the writes
    (a kept row still names it) does not keep the key from the archived authority."""
    from services.backup.restore import replace
    from tests.test_backup_cross_installation import _bound_to
    section = 'certificate_authorities' if kind == 'x509' else 'ssh_cas'
    real_defer = replace._defer_what_kept_rows_need

    def defer_the_authorities(replacement):
        real_defer(replacement)
        doomed = replacement.doomed.get(section, set())
        if doomed:
            replacement.deferred = {**replacement.deferred,
                                    section: replacement.deferred.get(section, set()) | doomed}

    with _bound_to(app, f"sqlite:///{tmp_path / 'restore.db'}"), app.app_context():
        token = _Token()
        make = (lambda d: token.x509_ca(d)) if kind == 'x509' else (lambda d: token.ssh_ca(d, 'user'))
        held = make('archived')
        blob = _service().create_backup(PASSWORD, include=_only(*SECTIONS))
        _remove(held)
        make('here')
        monkeypatch.setattr(replace, '_defer_what_kept_rows_need', defer_the_authorities)
        _service().restore_backup(blob, PASSWORD, mode='replace')
        assert _holders(token.key.id) == [f'{kind}:archived']
        db.session.remove()
