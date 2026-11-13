"""The mTLS trusted CA is the only trust anchor of the 8443 listener.

RFC 5280 §6.1: the operator picks the anchor. Root R signs intermediates I
and I2; with I trusted, a client certificate from I2 or from R itself must
fail the handshake. Driven through gunicorn_config in a child process, the
way the master builds its socket (importing it here would monkey-patch the
suite).
"""
import base64
import datetime
import json
import os
import sqlite3
import subprocess
import sys

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip('gunicorn')


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _issue(cn, issuer=None, ca=False, eku=None):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    signer_key = issuer[1] if issuer else key
    builder = (x509.CertificateBuilder()
               .subject_name(_name(cn))
               .issuer_name(issuer[0].subject if issuer else _name(cn))
               .public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - datetime.timedelta(hours=1))
               .not_valid_after(now + datetime.timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                              critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                   signer_key.public_key()), critical=False))
    if ca:
        builder = builder.add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
    else:
        builder = builder.add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        builder = builder.add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
        if eku == ExtendedKeyUsageOID.SERVER_AUTH:
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName('server.test')]), critical=False)
    return builder.sign(signer_key, hashes.SHA256()), key


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.fixture(scope='module')
def bench(tmp_path_factory):
    """R signs I and I2; client leaves under I, under I2 and under R."""
    root = tmp_path_factory.mktemp('mtls_anchor')
    r = _issue('Bench Root', ca=True)
    i = _issue('Bench Issuing', issuer=r, ca=True)
    i2 = _issue('Bench Sibling', issuer=r, ca=True)
    server = _issue('server.test', eku=ExtendedKeyUsageOID.SERVER_AUTH)
    leaves = {
        # name -> (leaf, chain the client sends after it)
        'under_trusted': (_issue('alice', issuer=i, eku=ExtendedKeyUsageOID.CLIENT_AUTH), [i[0]]),
        'under_trusted_full_chain': (
            _issue('alice2', issuer=i, eku=ExtendedKeyUsageOID.CLIENT_AUTH), [i[0], r[0]]),
        'under_sibling': (_issue('mallory', issuer=i2, eku=ExtendedKeyUsageOID.CLIENT_AUTH),
                          [i2[0], r[0]]),
        'under_root': (_issue('eve', issuer=r, eku=ExtendedKeyUsageOID.CLIENT_AUTH), [r[0]]),
    }
    (root / 'server.pem').write_text(_pem(server[0]))
    (root / 'server.key').write_text(_key_pem(server[1]))
    clients = {}
    for name, ((leaf, key), chain) in leaves.items():
        (root / f'{name}.pem').write_text(_pem(leaf) + ''.join(_pem(c) for c in chain))
        (root / f'{name}.key').write_text(_key_pem(key))
        clients[name] = (str(root / f'{name}.pem'), str(root / f'{name}.key'))
    return {'root': root, 'R': r[0], 'I': i[0], 'clients': clients,
            'server': (str(root / 'server.pem'), str(root / 'server.key'))}


def _install(data_dir, bench, trusted):
    data_dir.mkdir()
    db = sqlite3.connect(str(data_dir / 'ucm.db'))
    db.execute("CREATE TABLE system_config (key VARCHAR(255) PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE certificate_authorities ("
               " refid VARCHAR(64) PRIMARY KEY, crt TEXT, descr TEXT, caref VARCHAR(64))")
    for key, value in (('mtls_enabled', 'true'), ('mtls_required', 'true'),
                       ('mtls_trusted_ca_id', trusted)):
        db.execute("INSERT INTO system_config VALUES (?, ?)", (key, value))
    for refid, cert, parent in (('ca-root', bench['R'], None), ('ca-issuing', bench['I'], 'ca-root')):
        stored = base64.b64encode(_pem(cert).encode()).decode()
        db.execute("INSERT INTO certificate_authorities VALUES (?, ?, ?, ?)",
                   (refid, stored, refid, parent))
    db.commit()
    db.close()


CHILD = r'''
import json, ssl, sys
bench = json.loads(sys.argv[1])
if bench['pre_313_defaults']:
    # Python before 3.13 builds the default context without partial chains
    _orig = ssl.create_default_context
    def _older(*a, **k):
        ctx = _orig(*a, **k)
        ctx.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
        return ctx
    ssl.create_default_context = _older
import gunicorn_config
from gunicorn.config import Config
from gunicorn.sock import ssl_context

conf = Config()
conf.set('certfile', bench['server'][0])
conf.set('keyfile', bench['server'][1])
conf.set('ca_certs', gunicorn_config.ca_certs)
conf.set('cert_reqs', gunicorn_config.cert_reqs)
conf.set('ssl_context', gunicorn_config.ssl_context)
server_ctx = ssl_context(conf)


def handshake(cert, key):
    client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.load_verify_locations(bench['server'][0])
    client_ctx.load_cert_chain(cert, key)
    s_in, s_out, c_in, c_out = (ssl.MemoryBIO() for _ in range(4))
    server = server_ctx.wrap_bio(s_in, s_out, server_side=True)
    client = client_ctx.wrap_bio(c_in, c_out, server_hostname='server.test')
    done = {'server': False, 'client': False}
    for _ in range(20):
        for name, end in (('client', client), ('server', server)):
            if done[name]:
                continue
            try:
                end.do_handshake()
                done[name] = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            except ssl.SSLError as exc:
                if name == 'server':
                    return 'refused: ' + exc.reason
                done[name] = True
        s_in.write(c_out.read())
        c_in.write(s_out.read())
        if done['server']:
            return 'accepted'
    return 'stalled'


print(json.dumps({name: handshake(*paths) for name, paths in bench['clients'].items()}))
'''


def _outcomes(tmp_path, bench, trusted, pre_313_defaults=False):
    data_dir = tmp_path / 'data'
    _install(data_dir, bench, trusted)
    env = {k: v for k, v in os.environ.items()
           if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    env.update(DATA_DIR=str(data_dir), UCM_BASE_PATH=str(tmp_path), PYTHONPATH=BACKEND)
    payload = json.dumps({'clients': bench['clients'], 'server': bench['server'],
                          'pre_313_defaults': pre_313_defaults})
    run = subprocess.run([sys.executable, '-c', CHILD, payload], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return {name: result.split(':')[0] for name, result in
            json.loads(run.stdout.strip().splitlines()[-1]).items()}


@pytest.mark.parametrize('pre_313_defaults', [False, True], ids=['py313', 'older-python'])
def test_only_certificates_of_the_trusted_intermediate_pass(tmp_path, bench, pre_313_defaults):
    assert _outcomes(tmp_path, bench, 'ca-issuing', pre_313_defaults) == {
        'under_trusted': 'accepted',
        'under_trusted_full_chain': 'accepted',
        'under_sibling': 'refused',
        'under_root': 'refused',
    }


def test_a_trusted_root_anchors_its_whole_hierarchy(tmp_path, bench):
    assert _outcomes(tmp_path, bench, 'ca-root') == {
        'under_trusted': 'accepted',
        'under_trusted_full_chain': 'accepted',
        'under_sibling': 'accepted',
        'under_root': 'accepted',
    }
