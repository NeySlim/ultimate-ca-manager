"""
Microsoft CA CRL revocation sync tests (#185)

The sync fetches the CA's CRL, verifies its signature against the CA cert,
and marks UCM-known certs revoked when they are revoked CA-side (one-way).
Here the CRL/CA are generated locally and the network layer is monkeypatched.
"""
import base64
import json
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tests.conftest import get_json

CONTENT_JSON = 'application/json'
BASE = '/api/v2/microsoft-cas'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type=CONTENT_JSON)


@pytest.fixture(scope='module')
def fake_adcs():
    """A fake AD CS: CA key/cert, one issued cert, and a CRL revoking it."""
    from utils.datetime_utils import utc_now

    now = utc_now()
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fake ADCS Root')])
    ca_cert = (x509.CertificateBuilder()
               .subject_name(ca_name).issuer_name(ca_name)
               .public_key(ca_key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1))
               .not_valid_after(now + timedelta(days=3650))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .sign(ca_key, hashes.SHA256()))

    def issue(cn):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
                .issuer_name(ca_name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(hours=1))
                .not_valid_after(now + timedelta(days=365))
                .sign(ca_key, hashes.SHA256()))
        return cert

    revoked_cert = issue('crlsync-revoked.test.local')
    valid_cert = issue('crlsync-valid.test.local')

    entry = (x509.RevokedCertificateBuilder()
             .serial_number(revoked_cert.serial_number)
             .revocation_date(now - timedelta(minutes=30))
             .add_extension(x509.CRLReason(x509.ReasonFlags.key_compromise), critical=False)
             .build())
    crl = (x509.CertificateRevocationListBuilder()
           .issuer_name(ca_name)
           .last_update(now - timedelta(minutes=10))
           .next_update(now + timedelta(days=7))
           .add_revoked_certificate(entry)
           .sign(ca_key, hashes.SHA256()))

    return {
        'ca_key': ca_key,
        'ca_cert_pem': ca_cert.public_bytes(serialization.Encoding.PEM).decode(),
        'revoked_cert': revoked_cert,
        'valid_cert': valid_cert,
        'crl': crl,
        'crl_der': crl.public_bytes(serialization.Encoding.DER),
    }


def _add_connection_with_certs(app, name, fake):
    """Insert a connection + the two issued certs as UCM msca certs."""
    with app.app_context():
        from models import Certificate, db
        from models.msca import MicrosoftCA, MSCARequest

        msca = MicrosoftCA(name=name, server='adcs.test.local',
                           auth_method='basic', enabled=True,
                           crl_sync_enabled=True,
                           crl_url='https://crl.test.local/fake.crl')
        db.session.add(msca)
        db.session.flush()

        ids = {}
        for label, cert_obj in (('revoked', fake['revoked_cert']),
                                ('valid', fake['valid_cert'])):
            cn = cert_obj.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
            pem = cert_obj.public_bytes(serialization.Encoding.PEM).decode()
            cert = Certificate(
                refid=f'crl-{name[-8:]}-{label}',
                descr=f'MSCA: {cn}',
                crt=base64.b64encode(pem.encode()).decode(),
                cert_type='server',
                subject=f'CN={cn}', subject_cn=cn,
                serial_number=format(cert_obj.serial_number, 'X'),
                source='msca',
                imported_from=f'msca:{name}',
            )
            db.session.add(cert)
            db.session.flush()
            db.session.add(MSCARequest(msca_id=msca.id, cert_id=cert.id,
                                       template='WebServer', status='issued'))
            ids[label] = cert.id
        db.session.commit()
        return msca.id, ids


@pytest.fixture
def patched_network(monkeypatch, fake_adcs):
    """Patch CRL download + CA cert retrieval; the signature check stays real."""
    from services.msca.crl_sync import MicrosoftCACRLSyncMixin
    from services.msca.connection import MicrosoftCAConnectionMixin

    class FakeResp:
        status_code = 200
        content = fake_adcs['crl_der']

    monkeypatch.setattr(
        'utils.ssrf_protection.safe_request_get',
        lambda url, **kw: FakeResp(),
    )

    class FakeClient:
        def get_ca_cert(self, encoding='b64'):
            return fake_adcs['ca_cert_pem']

    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client',
                        staticmethod(lambda msca: FakeClient()))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client',
                        staticmethod(lambda client: None))
    return fake_adcs


class TestCrlSyncService:

    def test_sync_revokes_matching_certs(self, app, auth_client, fake_adcs, patched_network):
        msca_id, ids = _add_connection_with_certs(app, 'CRL Sync A', fake_adcs)

        r = post_json(auth_client, f'{BASE}/{msca_id}/sync-crl', {})
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['revoked'] == 1
        assert data['checked'] == 2
        assert data['crl_entries'] == 1
        assert data['certs'][0]['revoke_reason'] == 'keyCompromise'
        assert data['crl_url'] == 'https://crl.test.local/fake.crl'

        with app.app_context():
            from models import Certificate, db
            revoked = db.session.get(Certificate, ids['revoked'])
            valid = db.session.get(Certificate, ids['valid'])
            assert revoked.revoked is True
            assert revoked.revoke_reason == 'keyCompromise'
            assert revoked.revoked_at is not None
            assert valid.revoked in (False, None)

            from models.msca import MicrosoftCA
            msca = db.session.get(MicrosoftCA, msca_id)
            assert msca.last_crl_sync_result.startswith('success')
            assert msca.last_crl_sync_at is not None

    def test_sync_is_idempotent(self, app, auth_client, fake_adcs, patched_network):
        msca_id, _ = _add_connection_with_certs(app, 'CRL Sync B', fake_adcs)

        r = post_json(auth_client, f'{BASE}/{msca_id}/sync-crl', {})
        assert get_json(r)['data']['revoked'] == 1
        # Second run: the already-revoked cert is no longer a candidate
        r = post_json(auth_client, f'{BASE}/{msca_id}/sync-crl', {})
        assert r.status_code == 200
        data = get_json(r)['data']
        assert data['revoked'] == 0
        assert data['checked'] == 1

    def test_sync_rejects_bad_crl_signature(self, app, auth_client, fake_adcs,
                                            patched_network, monkeypatch):
        """A CRL that doesn't verify against the CA cert must be rejected."""
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        from services.msca.connection import MicrosoftCAConnectionMixin

        msca_id, ids = _add_connection_with_certs(app, 'CRL Sync C', fake_adcs)

        # CA cert whose key did NOT sign the CRL
        other_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
        from utils.datetime_utils import utc_now
        from datetime import timedelta as _td
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Wrong CA')])
        wrong_ca = (x509.CertificateBuilder()
                    .subject_name(name).issuer_name(name)
                    .public_key(other_key.public_key())
                    .serial_number(x509.random_serial_number())
                    .not_valid_before(utc_now() - _td(days=1))
                    .not_valid_after(utc_now() + _td(days=10))
                    .sign(other_key, hashes.SHA256()))
        wrong_pem = wrong_ca.public_bytes(serialization.Encoding.PEM).decode()

        class WrongClient:
            def get_ca_cert(self, encoding='b64'):
                return wrong_pem

        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client',
                            staticmethod(lambda msca: WrongClient()))

        r = post_json(auth_client, f'{BASE}/{msca_id}/sync-crl', {})
        assert r.status_code == 400
        assert 'signature' in get_json(r)['message'].lower()

        with app.app_context():
            from models import Certificate, db
            from models.msca import MicrosoftCA
            assert db.session.get(Certificate, ids['revoked']).revoked in (False, None)
            assert db.session.get(MicrosoftCA, msca_id).last_crl_sync_result.startswith('failed')

    def test_sync_without_crl_url_or_cdp_fails(self, app, auth_client, fake_adcs,
                                               patched_network):
        # Certs in this connection have no CDP extension and no crl_url is set
        # → the URL resolution must fail cleanly. (Certs here DO lack CDP.)
        msca_id, _ = _add_connection_with_certs(app, 'CRL Sync D', fake_adcs)
        with app.app_context():
            from models import db
            from models.msca import MicrosoftCA
            db.session.get(MicrosoftCA, msca_id).crl_url = None
            db.session.commit()

        r = post_json(auth_client, f'{BASE}/{msca_id}/sync-crl', {})
        assert r.status_code == 400
        assert 'CRL URL' in get_json(r)['message']


class TestCrlSyncCrud:

    def test_create_with_crl_sync_fields(self, auth_client):
        r = post_json(auth_client, BASE, {
            'name': 'CRL CRUD Create', 'server': 'adcs.test.local',
            'auth_method': 'basic', 'username': 'u', 'password': 'p',
            'crl_sync_enabled': True,
            'crl_url': 'https://adcs.test.local/CertEnroll/ca.crl',
        })
        assert r.status_code == 201, r.data
        data = get_json(r)['data']
        assert data['crl_sync_enabled'] is True
        assert data['crl_url'] == 'https://adcs.test.local/CertEnroll/ca.crl'

    def test_update_crl_sync_fields(self, auth_client):
        r = post_json(auth_client, BASE, {
            'name': 'CRL CRUD Update', 'server': 'adcs.test.local',
            'auth_method': 'basic', 'username': 'u', 'password': 'p',
        })
        msca_id = get_json(r)['data']['id']

        r = put_json(auth_client, f'{BASE}/{msca_id}', {
            'crl_sync_enabled': True,
            'crl_url': 'https://adcs.test.local/CertEnroll/ca.crl',
        })
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['crl_sync_enabled'] is True
        assert data['crl_url'] == 'https://adcs.test.local/CertEnroll/ca.crl'

    def test_crl_url_rejects_cloud_metadata(self, auth_client):
        r = post_json(auth_client, BASE, {
            'name': 'CRL CRUD Bad URL', 'server': 'adcs.test.local',
            'auth_method': 'basic', 'username': 'u', 'password': 'p',
            'crl_url': 'http://169.254.169.254/latest/crl',
        })
        assert r.status_code == 400

    def test_crl_url_rejects_non_http(self, auth_client):
        r = post_json(auth_client, BASE, {
            'name': 'CRL CRUD LDAP URL', 'server': 'adcs.test.local',
            'auth_method': 'basic', 'username': 'u', 'password': 'p',
            'crl_url': 'ldap:///CN=ca,CN=cdp',
        })
        assert r.status_code == 400


def test_a_key_the_ca_revoked_as_compromised_is_kept(app, auth_client, fake_adcs, patched_network):
    from models.compromised_key import CompromisedKeyRecord
    from utils.spki_digest import public_key_sha256
    msca_id, _ids = _add_connection_with_certs(app, 'CRL Sync K', fake_adcs)
    assert post_json(auth_client, f'{BASE}/{msca_id}/sync-crl', {}).status_code == 200
    with app.app_context():
        kept = {r.public_key_sha256: r.source for r in CompromisedKeyRecord.query.filter_by(source='msca')}
        assert kept.get(public_key_sha256(fake_adcs['revoked_cert'].public_key())) == 'msca'
        assert public_key_sha256(fake_adcs['valid_cert'].public_key()) not in kept
