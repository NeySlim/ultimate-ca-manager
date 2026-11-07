"""EST, SCEP and TSA SignedData stay what they were: byte for byte where the signature is
deterministic, field for field otherwise, and verified by OpenSSL in both cases."""
import hashlib
import shutil
import subprocess

import pytest
from asn1crypto import cms, tsp

from tests import cms_golden

OPENSSL = shutil.which('openssl')


def _fixture(name):
    return (cms_golden.FIXTURES / f'{name}.der').read_bytes()


@pytest.mark.parametrize('name', [n for n, c in cms_golden.CASES.items() if c[2]])
def test_deterministic_output_is_the_golden_bytes(name):
    assert cms_golden.build(name) == _fixture(name)


@pytest.mark.parametrize('name', [n for n, c in cms_golden.CASES.items() if not c[2]])
def test_randomised_output_matches_the_golden_structure(name):
    kind = cms_golden.CASES[name][0]
    der = cms_golden.build(name)
    assert der != _fixture(name), 'a randomised signature came out identical'
    assert cms_golden.structure(der, kind) == cms_golden.structure(_fixture(name), kind)


@pytest.mark.parametrize('name', sorted(cms_golden.ERROR_CASES))
def test_refusals_keep_their_message(name):
    assert cms_golden.build_error(name) == cms_golden.errors_fixture()[name]


def _run(*args):
    result = subprocess.run([OPENSSL, *map(str, args)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


def _verify_ed448(signed, leaf_pem):
    """OpenSSL has no id-shake256-len: messageDigest and signature checked by hand."""
    from cryptography import x509
    info = signed['signer_infos'][0]
    content = signed['encap_content_info']['content'].contents
    digest = [a['values'][0].native for a in info['signed_attrs'] if a['type'].native == 'message_digest']
    assert digest == [hashlib.shake_256(content).digest(64)]
    attrs = info['signed_attrs'].untag().dump()
    x509.load_pem_x509_certificate(leaf_pem.read_bytes()).public_key().verify(
        info['signature'].native, attrs)


@pytest.mark.skipif(not OPENSSL, reason='needs the openssl command')
@pytest.mark.parametrize('name', [n for n in cms_golden.CASES if 'degenerate' not in n])
def test_openssl_verifies_the_output(name, tmp_path):
    kind, signer, _det, _make = cms_golden.CASES[name]
    der = cms_golden.build(name)
    root = cms_golden.FIXTURES / 'root.pem'
    leaf = cms_golden.FIXTURES / f"{ {'rsa_pss': 'rsa', 'hsm_rsa': 'rsa', 'hsm_ec': 'ec256', 'hsm_mldsa': 'mldsa'}.get(signer, signer)}.pem"
    if kind == 'tsa':
        token = tsp.TimeStampResp.load(der)['time_stamp_token']
        (tmp_path / 'token.der').write_bytes(token.dump())
        tst = cms_golden.signed_data(der, kind)['encap_content_info']['content'].parsed
        imprint = tst['message_imprint']
        hash_name = imprint['hash_algorithm']['algorithm'].native
        assert imprint['hashed_message'].native == hashlib.new(hash_name, cms_golden.TST_DATA).digest()
        _run('cms', '-verify', '-inform', 'DER', '-in', tmp_path / 'token.der', '-binary',
             '-CAfile', root, '-certfile', leaf, '-purpose', 'any', '-out', tmp_path / 'tst.der')
        assert (tmp_path / 'tst.der').read_bytes() == tst.dump()
        if 'mldsa' not in signer:
            (tmp_path / 'resp.der').write_bytes(der)
            _run('ts', '-verify', '-in', tmp_path / 'resp.der', '-digest',
                 imprint['hashed_message'].native.hex(), '-CAfile', root, '-untrusted', leaf)
        return
    if signer == 'ed448':
        _verify_ed448(cms_golden.signed_data(der, kind), leaf)
        return
    if kind == 'est':
        der = cms.ContentInfo({'content_type': 'signed_data', 'content': cms.SignedData.load(der)}).dump()
    (tmp_path / 'signed.der').write_bytes(der)
    args = ['cms', '-verify', '-inform', 'DER', '-in', tmp_path / 'signed.der', '-binary',
            '-CAfile', root, '-purpose', 'any', '-out', tmp_path / 'content.der']
    if cms_golden.signed_data(der, 'scep')['encap_content_info']['content'].native is None:
        (tmp_path / 'empty').write_bytes(b'')
        args += ['-content', tmp_path / 'empty']
    _run(*args)


def test_a_fixed_digest_suite_without_digest_takes_the_key_default():
    from utils.cms_signed import signature_suite
    keys = cms_golden.material()[0]
    assert signature_suite(keys['rsa'], hsm_digest=False).digest == 'sha256'
    assert signature_suite(keys['ec384'], hsm_digest=False).digest == 'sha384'
