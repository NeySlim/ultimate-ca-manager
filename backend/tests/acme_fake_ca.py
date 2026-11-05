"""An in-memory ACME CA for the client's finalize and renewal paths: orders, finalize, download.

It certifies the key of the CSR it is sent, so what UCM stores can be checked against what
the CA issued. Only the calls the client makes after the challenges are modelled.
"""
import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from services.acme.acme_client_service import AcmeClientService


def _response(status=200, body=None, text=''):
    return SimpleNamespace(status_code=status, headers={}, json=lambda: body or {}, text=text)


class FakeCA:
    def __init__(self, base='https://ca.example'):
        self.base = base
        self.key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fake ACME CA')])
        now = datetime.now(timezone.utc)
        self.cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                     .public_key(self.key.public_key()).serial_number(1)
                     .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=3650))
                     .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                     .add_extension(x509.SubjectKeyIdentifier.from_public_key(self.key.public_key()),
                                    critical=False)
                     .sign(self.key, hashes.SHA256()))
        self.orders = {}
        self.posts = []
        self.serial = 0x5000
        self.finalize_status = 'valid'  # what the finalize request answers
        self.on_finalize = None  # called with the order URL once the CA has issued
        self.on_download = None  # called with the order URL before the certificate is served

    @property
    def ca_pem(self):
        return self.cert.public_bytes(serialization.Encoding.PEM).decode()

    def issue(self, public_key, names, days=90):
        """A leaf for ``public_key`` and its chain, as PEM text."""
        self.serial += 1
        now = datetime.now(timezone.utc)
        leaf = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
                .issuer_name(self.cert.subject).public_key(public_key).serial_number(self.serial)
                .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=days))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()),
                               critical=False)
                .sign(self.key, hashes.SHA256()))
        return leaf.public_bytes(serialization.Encoding.PEM).decode() + self.ca_pem

    def order(self, url, names, status='ready', pem=None):
        """Register an order the CA holds at ``url``; ``pem`` makes it valid with that certificate."""
        self.orders[url] = {'names': names, 'status': 'valid' if pem else status, 'pem': pem}
        return url

    def post(self, url, payload, use_jwk=False):
        self.posts.append((url, payload))
        if url in self.orders:
            o = self.orders[url]
            if o['status'] == 'gone':
                return _response(404, {'type': 'urn:ietf:params:acme:error:malformed'})
            body = {'status': o['status'], 'finalize': f'{url}/finalize'}
            if o['status'] == 'valid':
                body['certificate'] = f'{url}/cert'
            return _response(200, body)
        if url.endswith('/finalize'):
            order_url = url[:-len('/finalize')]
            o = self.orders[order_url]
            der = base64.urlsafe_b64decode(payload['csr'] + '=' * (-len(payload['csr']) % 4))
            csr = x509.load_der_x509_csr(der)
            o['pem'] = self.issue(csr.public_key(), o['names'])
            o['status'] = self.finalize_status
            if self.on_finalize:
                self.on_finalize(order_url)
            body = {'status': o['status']}
            if o['status'] == 'valid':
                body['certificate'] = f'{order_url}/cert'
            return _response(200, body)
        if url.endswith('/cert'):
            order_url = url[:-len('/cert')]
            if self.on_download:
                self.on_download(order_url)
            return _response(200, text=self.orders[order_url]['pem'])
        raise AssertionError(f'unexpected CA call {url}')

    def client(self):
        """A client whose calls to the CA land here."""
        svc = object.__new__(AcmeClientService)
        svc._post = self.post
        svc._select_certificate_chain = lambda resp: resp.text
        svc.get_poll_settings = lambda: {'order_poll_timeout_sec': 30, 'order_poll_interval_sec': 1}
        svc._order_retry_after = None
        svc.account = None
        svc.environment = 'production'
        return svc


def leaf_of(pem):
    return x509.load_pem_x509_certificate(pem.split('-----END CERTIFICATE-----')[0].encode()
                                          + b'-----END CERTIFICATE-----\n')


def key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def names_json(names):
    return json.dumps(names)
