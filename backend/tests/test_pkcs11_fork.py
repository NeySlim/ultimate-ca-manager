"""A forked worker initializes its PKCS#11 library itself (Cryptoki: the state a
child inherits is undefined) and never finalizes the parent's copy."""
import os
import shutil
import subprocess
import types

import pytest

from services.hsm import pkcs11_provider

SOFTHSM_LIB = '/usr/lib/softhsm/libsofthsm2.so'
HAS_SOFTHSM = (bool(shutil.which('softhsm2-util')) and os.path.exists(SOFTHSM_LIB)
               and pkcs11_provider.PKCS11_AVAILABLE)


class _Error(Exception):
    pass


class _Lib:
    def __init__(self, refuse):
        if refuse:
            raise _Error('Initialisation error (already initialized)')
        self.finalized = False

    def finalize(self):
        self.finalized = True


@pytest.fixture
def fake(monkeypatch):
    loaded = {}
    state = types.SimpleNamespace(refuse=False, pid=1000, loaded=loaded)

    def lib(so):
        if so not in loaded:
            loaded[so] = _Lib(state.refuse)
        return loaded[so]
    monkeypatch.setattr(pkcs11_provider, 'pkcs11',
                        types.SimpleNamespace(lib=lib, _loaded=loaded, PKCS11Error=_Error))
    monkeypatch.setattr(pkcs11_provider, '_initialized_by', {})
    monkeypatch.setattr(pkcs11_provider, '_inherited', [])
    monkeypatch.setattr(pkcs11_provider.os, 'getpid', lambda: state.pid)
    return state


def test_the_same_process_reuses_its_library(fake):
    first = pkcs11_provider.cryptoki_library('/m.so')
    assert pkcs11_provider.cryptoki_library('/m.so') is first


def test_a_forked_child_initializes_its_own_library(fake):
    parent = pkcs11_provider.cryptoki_library('/m.so')
    fake.pid = 1001
    child = pkcs11_provider.cryptoki_library('/m.so')
    assert child is not parent and fake.loaded['/m.so'] is child
    assert parent in pkcs11_provider._inherited and not parent.finalized
    assert pkcs11_provider.cryptoki_library('/m.so') is child


def test_a_library_refusing_a_second_initialize_keeps_its_state(fake):
    parent = pkcs11_provider.cryptoki_library('/m.so')
    fake.pid, fake.refuse = 1001, True
    assert pkcs11_provider.cryptoki_library('/m.so') is parent
    assert fake.loaded['/m.so'] is parent and not parent.finalized


def test_a_refusal_with_nothing_inherited_is_raised(fake):
    pkcs11_provider.cryptoki_library('/m.so')
    fake.loaded.clear()
    fake.pid, fake.refuse = 1001, True
    with pytest.raises(_Error):
        pkcs11_provider.cryptoki_library('/m.so')


def _child_random(lib_for_child):
    """'fresh' or 'inherited' and the random bytes a forked child drew, or its error."""
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(read_fd)
            try:
                lib, session, parent = lib_for_child()
                drawn = len(session.generate_random(256))  # bits
                kind = 'inherited' if lib is parent else 'fresh'
                os.write(write_fd, f'{kind} {drawn}'.encode())
            except Exception as e:
                os.write(write_fd, f'error {type(e).__name__}: {e}'.encode())
        finally:
            os._exit(0)  # no interpreter teardown: nothing finalized in the child
    os.close(write_fd)
    os.waitpid(pid, 0)
    with os.fdopen(read_fd) as pipe:
        return pipe.read()


@pytest.mark.skipif(not HAS_SOFTHSM, reason='SoftHSM not installed')
@pytest.mark.parametrize('reset_on_fork, helper, expected', [
    ('true', True, 'fresh 32'),
    ('true', False, 'error'),  # the inherited state, the defect this guards against
    ('false', True, 'inherited 32'),
], ids=['resetting-module', 'resetting-module-unguarded', 'module-keeping-its-state'])
def test_a_forked_worker_uses_softhsm(tmp_path, monkeypatch, reset_on_fork, helper, expected):
    import pkcs11

    conf = tmp_path / 'softhsm2.conf'
    (tmp_path / 'tokens').mkdir()
    conf.write_text(f"directories.tokendir = {tmp_path / 'tokens'}\nobjectstore.backend = file\n"
                    f"log.level = ERROR\nlibrary.reset_on_fork = {reset_on_fork}\n")
    monkeypatch.setenv('SOFTHSM2_CONF', str(conf))
    subprocess.run(['softhsm2-util', '--init-token', '--free', '--label', 'ucmfork',
                    '--so-pin', '1234', '--pin', '1234'], check=True, capture_output=True)
    monkeypatch.setattr(pkcs11_provider, '_initialized_by', {})
    monkeypatch.setattr(pkcs11_provider, '_inherited', [])

    def release():
        lib = pkcs11._loaded.pop(SOFTHSM_LIB, None)
        if lib is not None:
            lib.finalize()
    release()
    try:
        parent = pkcs11_provider.cryptoki_library(SOFTHSM_LIB)
        with parent.get_token(token_label='ucmfork').open(user_pin='1234') as session:
            session.generate_random(128)

        def lib_for_child():
            if not helper:
                lib = pkcs11.lib(SOFTHSM_LIB)
                return lib, lib.get_token(token_label='ucmfork').open(user_pin='1234'), parent
            provider = pkcs11_provider.Pkcs11Provider(
                {'module_path': SOFTHSM_LIB, 'token_label': 'ucmfork', 'user_pin': '1234'})
            provider.connect()
            return provider._lib, provider._session, parent
        assert _child_random(lib_for_child).startswith(expected)
        # The parent's library still works after its child
        with parent.get_token(token_label='ucmfork').open(user_pin='1234') as session:
            assert len(session.generate_random(128)) == 16
    finally:
        release()
