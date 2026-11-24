"""Kerberos to a Microsoft CA in FIPS mode: allowed only on a Kerberos library built on OpenSSL.

FIPS 140-3 keeps the security functions in the validated module: the MIT libk5crypto loaded in
the process must hand its cryptography to the system OpenSSL (libcrypto among its DT_NEEDED,
as RHEL builds it). Debian's does its own, so the Docker image refuses Kerberos in FIPS mode,
on certsrv and on the WinRM channel, with a 400 naming the library. GSSAPI is faked here.
"""
import os
import struct
import sys

import pytest

import fips_mode
from tests.conftest import get_json
from tests.msca_kerberos_support import FakeGssapi
from tests.test_msca_kerberos_failure import _connection, _csr, ca, keytab  # noqa: F401 - fixtures
from tests.test_msca_kerberos_keytab import _channel_row, _run_ps, kerberos, pywinrm  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

LIBRARY = '/usr/lib/x86_64-linux-gnu/libk5crypto.so.3.1'


def _elf(needed, bits=64, endian='<', soname=None):
    """A shared object holding only what the loader reads: one PT_LOAD, a PT_DYNAMIC, DT_NEEDED
    (and DT_SONAME when given)."""
    ehsize, phentsize = (64, 56) if bits == 64 else (52, 32)
    strtab = b'\0'
    names = []
    for name in needed + ([soname] if soname else []):
        names.append(len(strtab))
        strtab += name.encode() + b'\0'
    strtab_off = ehsize + 2 * phentsize
    dyn_off = strtab_off + len(strtab) + (-(strtab_off + len(strtab)) % 8)
    entry = endian + ('qQ' if bits == 64 else 'iI')
    dyn = b''.join(struct.pack(entry, 14 if soname and i == len(needed) else 1, n)
                   for i, n in enumerate(names))
    dyn += struct.pack(entry, 5, 0x1000 + strtab_off) + struct.pack(entry, 10, len(strtab))
    dyn += struct.pack(entry, 0, 0)
    total = dyn_off + len(dyn)
    if bits == 64:
        phdr = endian + 'IIQQQQQQ'
        load = struct.pack(phdr, 1, 5, 0, 0x1000, 0x1000, total, total, 0x1000)
        dynamic = struct.pack(phdr, 2, 6, dyn_off, 0x1000 + dyn_off, 0, len(dyn), len(dyn), 8)
        header = struct.pack(endian + 'HHIQQQIHHHHHH', 3, 62, 1, 0, ehsize, 0, 0, ehsize, phentsize, 2, 0, 0, 0)
    else:
        phdr = endian + 'IIIIIIII'
        load = struct.pack(phdr, 1, 0, 0x1000, 0x1000, total, total, 5, 0x1000)
        dynamic = struct.pack(phdr, 2, dyn_off, 0x1000 + dyn_off, 0, len(dyn), len(dyn), 6, 4)
        header = struct.pack(endian + 'HHIIIIIHHHHHH', 3, 3, 1, 0, ehsize, 0, 0, ehsize, phentsize, 2, 0, 0, 0)
    ident = b'\x7fELF' + bytes([1 if bits == 32 else 2, 1 if endian == '<' else 2, 1]) + b'\0' * 9
    image = bytearray(total)
    image[:ehsize] = ident + header
    image[ehsize:ehsize + 2 * phentsize] = load + dynamic
    image[strtab_off:strtab_off + len(strtab)] = strtab
    image[dyn_off:total] = dyn
    return bytes(image)


@pytest.mark.parametrize('bits, endian', [(64, '<'), (32, '<'), (64, '>'), (32, '>')])
def test_the_needed_libraries_are_read_from_the_dynamic_section(tmp_path, bits, endian):
    from utils.elf_needed import needed_libraries
    path = tmp_path / 'lib.so'
    path.write_bytes(_elf(['libkrb5support.so.0', 'libcrypto.so.3', 'libc.so.6'], bits, endian))
    assert needed_libraries(str(path)) == ['libkrb5support.so.0', 'libcrypto.so.3', 'libc.so.6']


@pytest.mark.parametrize('bits, endian', [(64, '<'), (32, '>')])
def test_the_soname_is_read_beside_the_needed_libraries(tmp_path, bits, endian):
    from utils.elf_needed import dynamic_names
    path = tmp_path / 'lib.so'
    path.write_bytes(_elf(['libc.so.6'], bits, endian, soname='libk5crypto.so.3'))
    assert dynamic_names(str(path)) == ('libk5crypto.so.3', ['libc.so.6'])
    path.write_bytes(_elf(['libc.so.6'], bits, endian))
    assert dynamic_names(str(path)) == (None, ['libc.so.6'])


def test_a_real_extension_names_the_openssl_it_links():
    import _ssl
    from utils.elf_needed import needed_libraries
    if not getattr(_ssl, '__file__', None):
        pytest.skip('_ssl is built into this interpreter')
    assert any(name.startswith('libcrypto.so') for name in needed_libraries(_ssl.__file__))


@pytest.mark.parametrize('cut', [None, 100], ids=['not-elf', 'truncated'])
def test_a_file_that_is_no_shared_object_is_an_error(tmp_path, cut):
    from utils.elf_needed import needed_libraries
    path = tmp_path / 'lib.so'
    path.write_bytes(b'not an elf at all, long enough to be read as one ' * 2 if cut is None
                     else _elf(['libcrypto.so.3'])[:cut])
    with pytest.raises(ValueError):
        needed_libraries(str(path))


# e_phoff of the ELF header; p_offset of the PT_DYNAMIC header (the second one, at 64 + 56)
@pytest.mark.parametrize('field', [32, 64 + 56 + 8], ids=['e_phoff', 'dynamic-p_offset'])
def test_an_offset_beyond_any_file_is_a_value_error(tmp_path, field):
    from utils.elf_needed import needed_libraries
    image = bytearray(_elf(['libcrypto.so.3']))
    image[field:field + 8] = b'\xff' * 8
    path = tmp_path / 'lib.so'
    path.write_bytes(bytes(image))
    with pytest.raises(ValueError):
        needed_libraries(str(path))


def test_damaged_headers_give_names_or_a_value_error_never_another_exception(tmp_path):
    import random
    from utils.elf_needed import needed_libraries
    rng = random.Random(20261124)
    original = _elf(['libkrb5support.so.0', 'libcrypto.so.3'])
    path = tmp_path / 'lib.so'
    for _ in range(400):
        image = bytearray(original)
        for _ in range(rng.randint(1, 4)):
            at = rng.randrange(16, 160)
            image[at:at + 8] = rng.choice([b'\xff' * 8, b'\x00' * 8, rng.randbytes(8)])
        path.write_bytes(bytes(image[:len(original)]))
        try:
            names = needed_libraries(str(path))
        except ValueError:
            continue
        assert isinstance(names, list) and all(isinstance(n, str) for n in names)


def test_a_forged_library_is_refused_not_a_crash(loaded):
    from services.msca import kerberos
    path = loaded(['libcrypto.so.3'])
    image = bytearray(open(path, 'rb').read())
    image[32:40] = b'\xff' * 8
    open(path, 'wb').write(bytes(image))
    assert kerberos.fips_crypto_problem().startswith(f'{path} cannot be read')


# --- which Kerberos library is loaded ---------------------------------------------------------

K5 = 'libk5crypto.so.3'
GSS = 'libgssapi_krb5.so.2'


@pytest.fixture
def loaded(monkeypatch, tmp_path):
    """A fake /proc/self/maps holding python-gssapi's extension, libgssapi_krb5 and libk5crypto:
    ``loaded(needed)`` gives libk5crypto these DT_NEEDED, ``loaded(None)`` maps none."""
    from services.msca import kerberos
    monkeypatch.setattr(kerberos, 'gssapi_available', lambda: True)
    maps = tmp_path / 'maps'
    monkeypatch.setattr(kerberos, '_PROC_MAPS', str(maps))
    folder = tmp_path / 'lib dir'
    folder.mkdir()
    extension = folder / 'creds.cpython-313-x86_64-linux-gnu.so'
    extension.write_bytes(_elf([GSS, 'libc.so.6']))
    monkeypatch.setattr(kerberos, '_gssapi_extension', lambda: str(extension))
    state = {'lines': []}

    def mapped(path):
        state['lines'].append(f'7f{len(state["lines"]):02x}0-7f{len(state["lines"]):02x}f r-xp 00000000 08:01 '
                              f'{len(state["lines"]) + 10} {path}')
        maps.write_text('\n'.join(state['lines']) + '\n')

    def library(name, needed, soname, mapped_too=True):
        path = folder / name
        path.write_bytes(_elf(needed, soname=soname))
        if mapped_too:
            mapped(path)
        return str(path)

    def load(needed, name='libk5crypto.so.3.1', decoys=()):
        for decoy in decoys:
            mapped(decoy)
        mapped('/usr/lib/x86_64-linux-gnu/libkrb5.so.3.3')
        mapped(extension)
        library('libgssapi_krb5.so.2.2', ['libkrb5.so.3', K5, 'libc.so.6'], GSS)
        if needed is None:
            maps.write_text('\n'.join(state['lines']) + '\n')
            return None
        return library(name, needed, K5)
    load.library, load.mapped, load.extension, load.folder = library, mapped, str(extension), folder
    return load


def test_a_library_on_openssl_is_allowed(loaded):
    from services.msca.kerberos import fips_crypto_problem
    loaded(['libkrb5support.so.0', 'libcrypto.so.3', 'libc.so.6'])
    assert fips_crypto_problem() is None


def test_a_library_with_its_own_cryptography_is_named(loaded):
    from services.msca.kerberos import fips_crypto_problem
    path = loaded(['libkrb5support.so.0', 'libc.so.6'])
    assert fips_crypto_problem() == f'{path} does its own cryptography, outside the FIPS module'


def test_no_mit_crypto_library_loaded_is_refused(loaded):
    from services.msca.kerberos import fips_crypto_problem
    loaded(None)
    assert 'libk5crypto' in fips_crypto_problem()


def test_the_library_judged_is_the_one_gssapi_reaches_not_the_first_mapped(loaded, tmp_path):
    """A libk5crypto of another soname, built on OpenSSL and mapped first, is not the one judged."""
    from services.msca.kerberos import fips_crypto_problem
    decoy = tmp_path / 'other' / 'libk5crypto.so.3.9'
    decoy.parent.mkdir()
    decoy.write_bytes(_elf(['libcrypto.so.3'], soname='libk5crypto.so.9'))
    path = loaded(['libkrb5support.so.0', 'libc.so.6'], decoys=[decoy])
    assert fips_crypto_problem() == f'{path} does its own cryptography, outside the FIPS module'


def test_two_mapped_libraries_of_the_soname_are_refused(loaded, tmp_path):
    from services.msca.kerberos import fips_crypto_problem
    twin = tmp_path / 'other' / 'libk5crypto.so.3.1'
    twin.parent.mkdir()
    twin.write_bytes(_elf(['libcrypto.so.3'], soname=K5))
    loaded(['libcrypto.so.3'], decoys=[twin])
    assert fips_crypto_problem() == f'several files of {K5} are loaded'


def test_an_extension_that_is_not_mapped_is_refused(loaded, monkeypatch, tmp_path):
    from services.msca import kerberos
    loaded(['libcrypto.so.3'])
    elsewhere = tmp_path / 'creds.so'
    elsewhere.write_bytes(_elf([GSS]))
    monkeypatch.setattr(kerberos, '_gssapi_extension', lambda: str(elsewhere))
    assert kerberos.fips_crypto_problem() == f'the gssapi extension {elsewhere} is not loaded'


def test_an_extension_on_another_gssapi_is_refused(loaded):
    from services.msca.kerberos import fips_crypto_problem
    loaded(['libcrypto.so.3'])
    open(loaded.extension, 'wb').write(_elf(['libgssapi.so.3', 'libc.so.6']))
    assert fips_crypto_problem() == f'{loaded.extension} needs no libgssapi_krb5'


def test_without_the_extension_file_the_library_is_unknown(loaded, monkeypatch):
    from services.msca import kerberos
    loaded(['libcrypto.so.3'])
    monkeypatch.setattr(kerberos, '_gssapi_extension', lambda: None)
    assert kerberos.fips_crypto_problem() == 'the gssapi extension module is not found'


@pytest.mark.parametrize('needed', [['libcrypto.so.3'], ['libkrb5support.so.0']], ids=['openssl', 'own'])
def test_the_first_verdict_outlives_the_files_it_read(loaded, needed):
    """An update of krb5-libs leaves the mapped library '(deleted)': the verdict read while the files
    were there is kept for the process, and nothing is read again."""
    from services.msca import kerberos
    path = loaded(needed)
    first = kerberos.fips_crypto_problem()
    for name in (path, loaded.extension, kerberos._PROC_MAPS):
        os.remove(name)
    assert kerberos.fips_crypto_problem() == first


def test_a_library_that_cannot_be_read_is_judged_again(loaded):
    from services.msca import kerberos
    path = loaded(['libcrypto.so.3'])
    good = open(path, 'rb').read()
    open(path, 'wb').write(b'\x7fELF' + b'\xff' * 60)
    assert kerberos.fips_crypto_problem().startswith(f'{path} cannot be read')
    open(path, 'wb').write(good)
    assert kerberos.fips_crypto_problem() is None


def test_unreadable_maps_are_read_again(loaded):
    from services.msca import kerberos
    loaded(['libcrypto.so.3'])
    lines = open(kerberos._PROC_MAPS).read()
    os.remove(kerberos._PROC_MAPS)
    assert kerberos.fips_crypto_problem() == f'{kerberos._PROC_MAPS} cannot be read'
    open(kerberos._PROC_MAPS, 'w').write(lines)
    assert kerberos.fips_crypto_problem() is None


def test_a_verdict_before_gssapi_is_importable_is_not_kept(loaded, monkeypatch):
    from services.msca import kerberos
    loaded(['libcrypto.so.3'])
    monkeypatch.setattr(kerberos, 'gssapi_available', lambda: False)
    assert kerberos.fips_crypto_problem() == kerberos.MISSING_LIBRARY
    monkeypatch.setattr(kerberos, 'gssapi_available', lambda: True)
    extension = loaded.extension
    monkeypatch.setattr(kerberos, '_gssapi_extension', lambda: None)
    assert kerberos.fips_crypto_problem() == 'the gssapi extension module is not found'
    monkeypatch.setattr(kerberos, '_gssapi_extension', lambda: extension)
    assert kerberos.fips_crypto_problem() is None


def test_without_gssapi_the_library_is_missing(monkeypatch):
    from services.msca import kerberos
    monkeypatch.setattr(kerberos, 'gssapi_available', lambda: False)
    assert kerberos.fips_crypto_problem() == kerberos.MISSING_LIBRARY


# --- the sign-in refused in FIPS mode -----------------------------------------------------------

PROBLEM = f'{LIBRARY} does its own cryptography, outside the FIPS module'


@pytest.fixture
def outside(monkeypatch):
    from services.msca import kerberos
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: PROBLEM)


def _refusal_text(message):
    assert message.startswith('Kerberos sign-in not available in FIPS mode: '), message
    assert PROBLEM in message and 'system OpenSSL' in message, message


def test_fips_mode_refuses_the_credential_before_any_acquisition(monkeypatch, outside, tmp_path):
    from services.msca.kerberos import KerberosFipsRefused, initiator_credential
    gss = FakeGssapi().install(monkeypatch)
    path = tmp_path / 'svc.keytab'
    path.write_bytes(b'\x05\x02')
    with pytest.raises(KerberosFipsRefused) as raised:
        initiator_credential(1, 'svc@ONE.TEST', str(path))
    _refusal_text(str(raised.value))
    assert gss.acquired == []


@pytest.mark.parametrize('fips, problem', [(False, PROBLEM), (True, None)])
def test_outside_fips_mode_or_on_openssl_the_credential_is_acquired(monkeypatch, tmp_path, fips, problem):
    from services.msca import kerberos
    gss = FakeGssapi().install(monkeypatch)
    monkeypatch.setattr(fips_mode, 'enabled', lambda: fips)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: problem)
    path = tmp_path / 'svc.keytab'
    path.write_bytes(b'\x05\x02')
    kerberos.initiator_credential(1, 'svc@ONE.TEST', str(path))
    assert gss.principals == ['svc@ONE.TEST']


def test_signing_through_certsrv_answers_the_fips_400(app, auth_client, ca, keytab, monkeypatch, outside):  # noqa: F811
    import json
    from models.msca import MSCARequest
    gss = FakeGssapi().install(monkeypatch)
    msca_id = _connection(app, 'krb-fips-sign.test.local', keytab)
    csr_id = _csr(app, 'krb-fips-sign.test.local')
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}',
                         data=json.dumps({'template': 'WebServer'}), content_type='application/json')
    assert r.status_code == 400, r.data
    body = get_json(r)
    _refusal_text(body['message'])
    assert body['type'] == fips_mode.PROBLEM_TYPE
    assert gss.acquired == [] and gss.tokens == [] and ca == []
    with app.app_context():
        assert MSCARequest.query.filter_by(msca_id=msca_id, csr_id=csr_id).count() == 0


def test_the_winrm_channel_is_refused_before_any_message(pywinrm, kerberos, outside):  # noqa: F811
    from services.msca.admin_channel import MSCAAdminChannelError
    with pytest.raises(MSCAAdminChannelError) as raised:
        _run_ps(_channel_row(kerberos.keytab))
    _refusal_text(str(raised.value))
    assert kerberos.acquired == [] and pywinrm.sent == []


@pytest.mark.parametrize('problem, advice', [
    (None, 'use the Kerberos transport'),
    (PROBLEM, f'Kerberos cannot replace it here ({PROBLEM}): turn off the WinRM channel'),
])
def test_the_ntlm_refusal_offers_kerberos_only_where_fips_mode_allows_it(app, monkeypatch, problem, advice):
    from services.msca import admin_channel, kerberos
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError
    from tests.test_msca_admin_channel import _make_msca_cert
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(admin_channel, 'kerberos_transport_available', lambda: True)
    monkeypatch.setattr(kerberos, 'fips_crypto_problem', lambda: problem)
    msca_id, _, _ = _make_msca_cert(app, ('outside' if problem else 'onssl') + '-advice.fips.local')
    with app.app_context():
        from models import db
        from models.msca import MicrosoftCA
        msca = db.session.get(MicrosoftCA, msca_id)
        msca.winrm_host = 'dc.fips.local'
        with pytest.raises(MSCAAdminChannelError, match='NTLM is not available in FIPS mode') as exc:
            MicrosoftCAAdminChannelMixin._build_session(msca)
    assert advice in str(exc.value)


def test_without_gssapi_nothing_is_imported_to_judge_the_library(monkeypatch):
    from services.msca import kerberos
    monkeypatch.setitem(sys.modules, 'gssapi', None)
    assert kerberos.fips_crypto_problem() == kerberos.MISSING_LIBRARY
