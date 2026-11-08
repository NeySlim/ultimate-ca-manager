"""ACME server conformance: RFC 8555, RFC 8737, RFC 8738 and RFC 9773 points.

tls-alpn-01 SAN check, requested validity, revocation by the holder of the
authorizations, POST-as-GET on a challenge, reflected ``replaces`` and
``externalAccountBinding``, finalize after expiry, ``caaIdentities``, CN = IP
in a CSR, nonce purge and malformed requests.
"""
import base64 as b64
import hashlib
import ipaddress
import json
import ssl
import socket
import uuid
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from models import db, CA, Certificate, SystemConfig
from models.acme_models import (
    AcmeAccount, AcmeAuthorization, AcmeChallenge, AcmeNonce, AcmeOrder,
)
from services.acme.acme_service import AcmeService
from tests.test_acme_security_paths import (
    _add_eab_credential, _b64json, _build_jws, _gen_key_and_jwk, _nonce,
    _post_jws, _thumbprint,
)
from utils.datetime_utils import utc_now

BASE = 'http://localhost'


def _b64u(raw):
    return b64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _new_account(app):
    key, jwk = _gen_key_and_jwk()
    with app.app_context():
        acct = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=_thumbprint(jwk), status='valid')
        db.session.add(acct)
        db.session.commit()
        return {'key': key, 'jwk': jwk, 'account_id': acct.account_id,
                'kid': f'{BASE}/acme/acct/{acct.account_id}'}


@pytest.fixture
def account(app):
    return _new_account(app)


def _signed(client, acct, path, payload):
    jws = _build_jws(f'{BASE}{path}', payload, acct['key'], kid=acct['kid'], nonce=_nonce(client))
    return _post_jws(client, path, jws)


def _ready_order(app, acct, identifiers, *, expired_authz=False, expired_order=False, **order_kw):
    """An order whose authorizations are valid, so it is ready."""
    with app.app_context():
        service = AcmeService(base_url=BASE)
        order = service.create_order(account_id=acct['account_id'], identifiers=identifiers, **order_kw)
        past = utc_now() - timedelta(days=1)
        for authz in order.authorizations:
            authz.status = 'valid'
            if expired_authz:
                authz.expires = past
        order.status = 'ready'
        if expired_order:
            order.expires = past
        db.session.commit()
        return order.order_id


@pytest.fixture
def no_caa(monkeypatch):
    import utils.caa_checker as caa
    monkeypatch.setattr(caa, 'check_caa_for_domains', lambda *a, **k: (True, 'test'))


@pytest.fixture
def issuing_ca(app, create_ca):
    ca = create_ca(cn='ACME conformance CA')
    with app.app_context():
        return db.session.get(CA, ca['id']).refid


def _csr_pem(key, cn=None, dns=(), ips=()):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)] if cn else []))
    names = [x509.DNSName(d) for d in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    if names:
        builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
    return builder.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode()


def _finalize(app, order_id, csr_pem, ca_refid):
    with app.app_context():
        service = AcmeService(base_url=BASE)
        ok, error = service.finalize_order(order_id, csr_pem, ca_refid=ca_refid)
        order = AcmeOrder.query.filter_by(order_id=order_id).first()
        cert = None
        if ok:
            row = db.session.get(Certificate, order.certificate_id)
            cert = x509.load_pem_x509_certificate(b64.b64decode(row.crt))
        return ok, error, order.status, cert, getattr(service, '_last_finalize_error_type', None)


# --- tls-alpn-01: the validation certificate's SAN (RFC 8737 §3, RFC 8738 §6) ---

class _FakeTls:
    def __init__(self, der):
        self.der = der

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def selected_alpn_protocol(self):
        return 'acme-tls/1'

    def getpeercert(self, binary_form=False):
        return self.der


class _FakeSock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _alpn_cert(expected_hash, san_names):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'acme-tls-alpn')])
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(utc_now() - timedelta(minutes=5))
               .not_valid_after(utc_now() + timedelta(days=1))
               .add_extension(x509.UnrecognizedExtension(
                   x509.ObjectIdentifier('1.3.6.1.5.5.7.1.31'), b'\x04\x20' + expected_hash),
                   critical=True))
    if san_names:
        builder = builder.add_extension(x509.SubjectAlternativeName(san_names), critical=False)
    return builder.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.DER)


def _validate_alpn(app, monkeypatch, acct, identifier, san_for):
    import utils.ssrf_protection as ssrf
    monkeypatch.setattr(ssrf, 'validate_url_not_cloud_metadata', lambda *a, **k: None)
    monkeypatch.setattr(ssrf, 'validated_addresses', lambda *a, **k: ('h', ['192.0.2.1']))
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: _FakeSock())
    with app.app_context():
        service = AcmeService(base_url=BASE)
        order = service.create_order(account_id=acct['account_id'], identifiers=[identifier])
        challenge = next(c for c in order.authorizations[0].challenges if c.type == 'tls-alpn-01')
        account = AcmeAccount.query.filter_by(account_id=acct['account_id']).first()
        key_authz = service._compute_key_authorization(challenge.token, account.jwk_thumbprint)
        der = _alpn_cert(hashlib.sha256(key_authz.encode()).digest(), san_for)
        monkeypatch.setattr(ssl.SSLContext, 'wrap_socket', lambda self, sock, **k: _FakeTls(der))
        service.validate_tls_alpn01_challenge(challenge, account)
        return challenge.status, json.loads(challenge.error) if challenge.error else None


class TestTlsAlpnSubjectAltName:
    def test_dns_identifier_with_its_own_san_is_valid(self, app, monkeypatch, account):
        status, _ = _validate_alpn(app, monkeypatch, account, {'type': 'dns', 'value': 'alpn-ok.example'},
                                   [x509.DNSName('ALPN-OK.example')])
        assert status == 'valid'

    @pytest.mark.parametrize('san', [
        [x509.DNSName('evil.example')],
        [x509.DNSName('alpn-bad.example'), x509.DNSName('extra.example')],
        [x509.IPAddress(ipaddress.ip_address('192.0.2.7'))],
        [],
    ])
    def test_dns_identifier_with_another_san_is_refused(self, app, monkeypatch, account, san):
        status, error = _validate_alpn(app, monkeypatch, account,
                                       {'type': 'dns', 'value': 'alpn-bad.example'}, san)
        assert status == 'invalid'
        assert error['type'].endswith(':incorrectResponse')

    def test_ip_identifier_with_its_own_san_is_valid(self, app, monkeypatch, account):
        status, _ = _validate_alpn(app, monkeypatch, account, {'type': 'ip', 'value': '192.0.2.44'},
                                   [x509.IPAddress(ipaddress.ip_address('192.0.2.44'))])
        assert status == 'valid'

    @pytest.mark.parametrize('san', [
        [x509.IPAddress(ipaddress.ip_address('192.0.2.7'))],
        [x509.DNSName('192.0.2.45')],
    ])
    def test_ip_identifier_with_another_san_is_refused(self, app, monkeypatch, account, san):
        status, error = _validate_alpn(app, monkeypatch, account, {'type': 'ip', 'value': '192.0.2.45'}, san)
        assert status == 'invalid'
        assert error['type'].endswith(':incorrectResponse')


# --- notBefore / notAfter (RFC 8555 §7.4) ---

def _iso(dt):
    return dt.replace(microsecond=0).isoformat() + 'Z'


class TestRequestedValidity:
    def test_not_after_is_echoed_stored_and_read_back(self, app, client, account):
        not_after = utc_now() + timedelta(days=10)
        r = _signed(client, account, '/acme/new-order', {
            'identifiers': [{'type': 'dns', 'value': 'nafter.example'}], 'notAfter': _iso(not_after)})
        assert r.status_code == 201, r.get_json()
        assert r.get_json()['notAfter'] == _iso(not_after)
        order_url = r.headers['Location']
        read = _signed(client, account, order_url[len(BASE):], None)
        assert read.status_code == 200
        assert read.get_json()['notAfter'] == _iso(not_after)
        assert 'notBefore' not in read.get_json()

    def test_requested_window_is_issued(self, app, account, issuing_ca, no_caa):
        now = utc_now().replace(microsecond=0)
        # Off whole days, so a notAfter recomputed from a day count cannot land on it
        nb = now + timedelta(days=2, hours=3, minutes=11)
        na = now + timedelta(days=5, hours=5, minutes=17)
        order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'window.example'}],
                                not_before=nb, not_after=na)
        ok, error, status, cert, _ = _finalize(
            app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['window.example']),
            issuing_ca)
        assert ok, error
        assert cert.not_valid_before_utc.replace(tzinfo=None) == nb
        assert cert.not_valid_after_utc.replace(tzinfo=None) == na

    def test_requested_not_after_alone_is_issued(self, app, account, issuing_ca, no_caa):
        na = utc_now().replace(microsecond=0) + timedelta(days=3, hours=5, minutes=17)
        order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'naonly.example'}], not_after=na)
        ok, error, _, cert, _ = _finalize(
            app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['naonly.example']),
            issuing_ca)
        assert ok, error
        assert cert.not_valid_after_utc.replace(tzinfo=None) == na

    def test_not_after_beyond_the_issuing_ca_is_refused_at_finalize(
            self, app, account, issuing_ca, no_caa, monkeypatch):
        from services.acme import profiles
        real = profiles.issuance_params
        monkeypatch.setattr(profiles, 'issuance_params', lambda name: {**real(name), 'validity_days': 9000})
        na = utc_now().replace(microsecond=0) + timedelta(days=20 * 365)
        order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'pastca.example'}], not_after=na)
        ok, error, status, _, error_type = _finalize(
            app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['pastca.example']),
            issuing_ca)
        assert not ok
        assert 'notAfter' in error
        assert error_type == 'malformed'
        assert status == 'invalid'

    def test_signer_never_moves_a_requested_not_after(self, app, issuing_ca):
        from services.cert_service import CertificateService
        key = rsa.generate_private_key(65537, 2048)
        with app.app_context():
            row = Certificate(refid=f'na-{uuid.uuid4().hex}', descr='na', caref=issuing_ca,
                              csr=b64.b64encode(_csr_pem(key, dns=['na.example']).encode()).decode(),
                              cert_type='server_cert', source='acme', created_by='acme')
            db.session.add(row)
            db.session.flush()
            with pytest.raises(ValueError, match='notAfter'):
                CertificateService.sign_csr(cert_id=row.id, caref=issuing_ca, validity_days=90,
                                            digest='sha256', username='acme',
                                            not_after=utc_now() + timedelta(days=20 * 365))
            db.session.rollback()

    def test_window_a_policy_would_shorten_is_refused(self, app, account, create_ca, no_caa):
        from models.policy import CertificatePolicy
        ca = create_ca(cn='ACME conformance policy CA')
        with app.app_context():
            ca_refid = db.session.get(CA, ca['id']).refid
            pol = CertificatePolicy(name='acme-window-cap', policy_type='issuance', ca_id=ca['id'],
                                    requires_approval=False, min_approvers=1, is_active=True, priority=100)
            pol.set_rules({'max_validity_days': 5})
            db.session.add(pol)
            db.session.commit()
            pid = pol.id
        try:
            na = utc_now().replace(microsecond=0) + timedelta(days=30)
            order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'capped.example'}], not_after=na)
            ok, error, status, _, error_type = _finalize(
                app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['capped.example']),
                ca_refid)
            assert not ok
            assert 'acme-window-cap' in error
            assert status == 'invalid'
            assert error_type == 'badCSR'  # a policy refusal, as every policy refusal at finalize
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificatePolicy, pid))
                db.session.commit()

    @staticmethod
    def _policy_ca(app, create_ca, name, rules):
        from models.policy import CertificatePolicy
        ca = create_ca(cn=f'ACME conformance {name} CA')
        with app.app_context():
            pol = CertificatePolicy(name=name, policy_type='issuance', ca_id=ca['id'],
                                    requires_approval=False, min_approvers=1, is_active=True, priority=100)
            pol.set_rules(rules)
            db.session.add(pol)
            db.session.commit()
            return db.session.get(CA, ca['id']).refid, pol.id

    @staticmethod
    def _drop_policy(app, pid):
        from models.policy import CertificatePolicy
        with app.app_context():
            db.session.delete(db.session.get(CertificatePolicy, pid))
            db.session.commit()

    @pytest.mark.parametrize('dates', ['window', 'not_before_only', 'none', 'not_after_on_horizon'])
    def test_key_horizon_judges_the_issued_not_after(self, app, account, create_ca, no_caa, dates):
        now = utc_now().replace(microsecond=0)
        horizon = (now + timedelta(days=100)).date().isoformat()
        on_horizon = now + timedelta(days=10, hours=1)
        if dates == 'not_after_on_horizon':
            # Ends on the horizon day: a day count rounded up would land past it
            horizon = on_horizon.date().isoformat()
        ca_refid, pid = self._policy_ca(app, create_ca, f'acme-horizon-{dates}',
                                        {'key_type_horizons': {'RSA-2048': horizon}})
        kw = {'window': {'not_before': now + timedelta(days=200), 'not_after': now + timedelta(days=260)},
              'not_before_only': {'not_before': now + timedelta(days=50)},
              'none': {}, 'not_after_on_horizon': {'not_after': on_horizon}}[dates]
        try:
            order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'horizon.example'}], **kw)
            ok, error, status, _, _ = _finalize(
                app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['horizon.example']),
                ca_refid)
            if dates in ('none', 'not_after_on_horizon'):
                assert ok, error  # ends before or on the horizon
            else:
                assert not ok
                assert f'acme-horizon-{dates}' in error
                assert status == 'invalid'
        finally:
            self._drop_policy(app, pid)

    def test_not_after_a_few_seconds_past_the_profile_is_accepted(self, app, client, account):
        na = utc_now().replace(microsecond=0) + timedelta(days=90, seconds=5)
        r = _signed(client, account, '/acme/new-order', {
            'identifiers': [{'type': 'dns', 'value': 'skew.example'}], 'notAfter': _iso(na)})
        assert r.status_code == 201, r.get_json()

    def test_not_after_a_few_seconds_past_a_90_day_cap_is_issued(self, app, account, create_ca, no_caa):
        ca_refid, pid = self._policy_ca(app, create_ca, 'acme-skew-cap', {'max_validity_days': 90})
        na = utc_now().replace(microsecond=0) + timedelta(days=90, seconds=5)
        try:
            order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'skewcap.example'}], not_after=na)
            ok, error, _, cert, _ = _finalize(
                app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['skewcap.example']),
                ca_refid)
            assert ok, error
            assert cert.not_valid_after_utc.replace(tzinfo=None) == na
        finally:
            self._drop_policy(app, pid)

    def test_not_after_past_by_finalize_is_malformed(self, app, account, issuing_ca, no_caa):
        na = utc_now().replace(microsecond=0) - timedelta(hours=1)
        order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'lapsed.example'}], not_after=na)
        ok, error, status, _, error_type = _finalize(
            app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['lapsed.example']),
            issuing_ca)
        assert not ok
        assert error == 'notAfter is in the past'
        assert error_type == 'malformed'
        assert status == 'invalid'

    @pytest.mark.parametrize('fields', [
        {'notAfter': 200},
        {'notAfter': 'garbage'},
        {'notBefore': 'garbage'},
        {'notAfter': '__past__'},
        {'notAfter': '__beyond__'},
        {'notBefore': '__late__', 'notAfter': '__early__'},
        {'notBefore': '__backdated__'},
    ])
    def test_unfulfillable_window_is_refused_at_new_order(self, app, client, account, fields):
        now = utc_now()
        values = {'__past__': now - timedelta(days=1), '__beyond__': now + timedelta(days=200),
                  '__late__': now + timedelta(days=5), '__early__': now + timedelta(days=4),
                  '__backdated__': now - timedelta(days=2)}
        payload = {'identifiers': [{'type': 'dns', 'value': 'refused-window.example'}]}
        for name, value in fields.items():
            payload[name] = _iso(values[value]) if value in values else value
        r = _signed(client, account, '/acme/new-order', payload)
        assert r.status_code == 400, r.get_json()
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'


# --- revocation by the holder of the authorizations (RFC 8555 §7.6) ---

def _issue_cert(app, ca_refid, dns=(), ips=(), source='acme'):
    from services.cert_service import CertificateService
    key = rsa.generate_private_key(65537, 2048)
    csr = _csr_pem(key, dns=dns, ips=ips)
    with app.app_context():
        row = Certificate(refid=f'rev-{uuid.uuid4().hex}', descr='rev', caref=ca_refid,
                          csr=b64.b64encode(csr.encode()).decode(), cert_type='server_cert',
                          source=source, created_by='acme')
        db.session.add(row)
        db.session.flush()
        signed = CertificateService.sign_csr(cert_id=row.id, caref=ca_refid, cert_type='server_cert',
                                             validity_days=30, digest='sha256', username='acme')
        db.session.commit()
        cert = x509.load_pem_x509_certificate(b64.b64decode(signed.crt))
        return signed.id, cert.public_bytes(serialization.Encoding.DER)


def _grant(app, acct, identifiers, *, expired=False):
    with app.app_context():
        for ident in identifiers:
            value = ident['value']
            wildcard = value.startswith('*.')
            db.session.add(AcmeAuthorization(
                account_id=acct['account_id'], status='valid', wildcard=wildcard,
                identifier=json.dumps({'type': ident['type'], 'value': value[2:] if wildcard else value}),
                expires=utc_now() + (timedelta(days=-1) if expired else timedelta(days=10))))
        db.session.commit()


class TestRevocationByAuthorizationHolder:
    NAMES = ['rev-holder.example', '*.rev-holder.example']
    IPS = ['192.0.2.81']

    def _cert_of_other_account(self, app, issuing_ca):
        cert_id, der = _issue_cert(app, issuing_ca, dns=self.NAMES, ips=self.IPS)
        owner = _new_account(app)
        with app.app_context():
            db.session.add(AcmeOrder(account_id=owner['account_id'], status='valid', certificate_id=cert_id,
                                     identifiers=json.dumps([]), expires=utc_now() + timedelta(days=7)))
            db.session.commit()
        return cert_id, der

    def _idents(self):
        return [{'type': 'dns', 'value': n} for n in self.NAMES] + [{'type': 'ip', 'value': i} for i in self.IPS]

    def test_account_holding_every_authorization_may_revoke(self, app, client, issuing_ca):
        cert_id, der = self._cert_of_other_account(app, issuing_ca)
        holder = _new_account(app)
        _grant(app, holder, self._idents())
        r = _signed(client, holder, '/acme/revoke-cert', {'certificate': _b64u(der), 'reason': 4})
        assert r.status_code == 200, r.get_json()
        # RFC 8555 §7.6: 200 without a body, so no HTML media type
        assert r.data == b'' and r.headers['Content-Length'] == '0'
        assert 'Content-Type' not in r.headers
        with app.app_context():
            assert db.session.get(Certificate, cert_id).revoked

    def test_holder_cannot_revoke_a_certificate_issued_outside_acme(self, app, client, issuing_ca):
        cert_id, der = _issue_cert(app, issuing_ca, dns=self.NAMES, ips=self.IPS, source='manual')
        holder = _new_account(app)
        _grant(app, holder, self._idents())
        r = _signed(client, holder, '/acme/revoke-cert', {'certificate': _b64u(der), 'reason': 1})
        assert r.status_code == 403, r.get_json()
        with app.app_context():
            assert not db.session.get(Certificate, cert_id).revoked

    def test_auto_approved_authorizations_do_not_authorize(self, app, client, issuing_ca):
        from models.acme_models import AcmeLocalDomain
        cert_id, der = self._cert_of_other_account(app, issuing_ca)
        with app.app_context():
            ca_id = CA.query.filter_by(refid=issuing_ca).first().id
            db.session.add(AcmeLocalDomain(domain='rev-holder.example', issuing_ca_id=ca_id, auto_approve=True))
            db.session.commit()
        try:
            holder = _new_account(app)
            _grant(app, holder, self._idents())
            r = _signed(client, holder, '/acme/revoke-cert', {'certificate': _b64u(der), 'reason': 1})
            assert r.status_code == 403, r.get_json()
            with app.app_context():
                assert not db.session.get(Certificate, cert_id).revoked
        finally:
            with app.app_context():
                AcmeLocalDomain.query.filter_by(domain='rev-holder.example').delete()
                db.session.commit()

    @pytest.mark.parametrize('case', ['missing_ip', 'missing_wildcard', 'expired'])
    def test_partial_or_expired_authorizations_do_not_authorize(self, app, client, issuing_ca, case):
        cert_id, der = self._cert_of_other_account(app, issuing_ca)
        holder = _new_account(app)
        idents = self._idents()
        if case == 'missing_ip':
            idents = [i for i in idents if i['type'] != 'ip']
        elif case == 'missing_wildcard':
            idents = [i for i in idents if not i['value'].startswith('*.')]
        _grant(app, holder, idents, expired=(case == 'expired'))
        r = _signed(client, holder, '/acme/revoke-cert', {'certificate': _b64u(der)})
        assert r.status_code == 403
        with app.app_context():
            assert not db.session.get(Certificate, cert_id).revoked


# --- POST-as-GET on a challenge (RFC 8555 §6.3, §7.5.1, erratum 5729) ---

class TestChallengePostAsGet:
    def _pending_challenge(self, app, acct):
        with app.app_context():
            service = AcmeService(base_url=BASE)
            order = service.create_order(account_id=acct['account_id'],
                                         identifiers=[{'type': 'dns', 'value': 'chalget.example'}])
            ch = next(c for c in order.authorizations[0].challenges if c.type == 'http-01')
            return ch.url[len(BASE):]

    def test_empty_payload_reads_without_validating(self, app, client, account, monkeypatch):
        path = self._pending_challenge(app, account)
        calls = []
        monkeypatch.setattr(AcmeService, 'validate_http01_challenge', lambda *a, **k: calls.append(a))
        r = _signed(client, account, path, None)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status'] == 'pending'
        assert calls == []
        assert 'rel="up"' in ','.join(r.headers.getlist('Link'))

    def test_empty_object_triggers_validation(self, app, client, account, monkeypatch):
        path = self._pending_challenge(app, account)
        calls = []
        monkeypatch.setattr(AcmeService, 'validate_http01_challenge', lambda *a, **k: calls.append(a))
        r = _signed(client, account, path, {})
        assert r.status_code == 200
        assert len(calls) == 1

    def test_non_object_payload_is_malformed(self, app, client, account, monkeypatch):
        path = self._pending_challenge(app, account)
        monkeypatch.setattr(AcmeService, 'validate_http01_challenge',
                            lambda *a, **k: pytest.fail('validation triggered'))
        r = _signed(client, account, path, [1, 2])
        assert r.status_code == 400
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'


# --- replaces reflected (RFC 9773 §5) ---

class TestReplacesReflected:
    @staticmethod
    def _owned_certid(app, acct):
        """RFC 9773 CertID of a certificate the account holds (AKI and serial as stored)."""
        aki, serial = bytes.fromhex('a1b2c3d4'), 0x7a1c55
        key = rsa.generate_private_key(65537, 2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'replaced.example')])
        crt = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(serial).not_valid_before(utc_now() - timedelta(minutes=5))
               .not_valid_after(utc_now() + timedelta(days=30)).sign(key, hashes.SHA256()))
        with app.app_context():
            cert = Certificate(refid=f'replaced-{uuid.uuid4().hex[:24]}', descr='replaced',
                               crt=b64.b64encode(crt.public_bytes(serialization.Encoding.PEM)).decode(),
                               serial_number=str(serial), aki=':'.join(f'{b:02x}' for b in aki))
            db.session.add(cert)
            db.session.flush()
            db.session.add(AcmeOrder(account_id=acct['account_id'], status='valid', certificate_id=cert.id,
                                     identifiers=json.dumps([{'type': 'dns', 'value': 'replaced.example'}]),
                                     expires=utc_now() + timedelta(days=7)))
            db.session.commit()
        return _b64u(aki) + '.' + _b64u(serial.to_bytes(3, 'big'))

    def test_new_order_and_order_read_reflect_replaces(self, app, client, account):
        replaces = self._owned_certid(app, account)
        r = _signed(client, account, '/acme/new-order', {
            'identifiers': [{'type': 'dns', 'value': 'replacing.example'}], 'replaces': replaces})
        assert r.status_code == 201, r.get_json()
        assert r.get_json()['replaces'] == replaces
        read = _signed(client, account, r.headers['Location'][len(BASE):], None)
        assert read.get_json()['replaces'] == replaces


# --- externalAccountBinding reflected (RFC 8555 §7.3.4) ---

def test_new_account_reflects_external_account_binding(app, client):
    import hmac
    kid, secret = 'conformance-eab', b'conformance-eab-secret'
    with app.app_context():
        _add_eab_credential(kid, _b64u(secret))
    key, jwk = _gen_key_and_jwk()
    path = '/acme/new-account'
    protected = _b64json({'alg': 'HS256', 'kid': kid, 'url': f'{BASE}{path}'})
    payload = _b64json(jwk)
    eab = {'protected': protected, 'payload': payload,
           'signature': _b64u(hmac.new(secret, f'{protected}.{payload}'.encode(), hashlib.sha256).digest())}
    jws = _build_jws(f'{BASE}{path}', {'termsOfServiceAgreed': True, 'externalAccountBinding': eab},
                     key, jwk=jwk, nonce=_nonce(client))
    r = _post_jws(client, path, jws)
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['externalAccountBinding'] == eab


# --- finalize after expiry (RFC 8555 §7.1.6, §7.4) ---

class TestFinalizeAfterExpiry:
    def _finalize_route(self, client, acct, order_id):
        key = rsa.generate_private_key(65537, 2048)
        csr_der = x509.load_pem_x509_csr(_csr_pem(key, dns=['late.example']).encode()).public_bytes(
            serialization.Encoding.DER)
        return _signed(client, acct, f'/acme/order/{order_id}/finalize', {'csr': _b64u(csr_der)})

    @pytest.mark.parametrize('expired', ['order', 'authz'])
    def test_expired_order_or_authorization_is_not_ready(self, app, client, account, monkeypatch, expired):
        monkeypatch.setattr(AcmeService, 'finalize_order',
                            lambda *a, **k: pytest.fail('finalize reached the signer'))
        order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'late.example'}],
                                expired_order=(expired == 'order'), expired_authz=(expired == 'authz'))
        r = self._finalize_route(client, account, order_id)
        assert r.status_code == 403, r.get_json()
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:orderNotReady'
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            assert order.status == 'invalid'
            if expired == 'authz':
                assert {a.status for a in order.authorizations} == {'expired'}


    def test_reading_a_lapsed_valid_authorization_expires_it(self, app, client, account):
        order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'lapsed.example'}], expired_authz=True)
        with app.app_context():
            authz_id = AcmeOrder.query.filter_by(order_id=order_id).first().authorizations[0].authorization_id
        r = _signed(client, account, f'/acme/authz/{authz_id}', None)
        assert r.status_code == 200
        assert r.get_json()['status'] == 'expired'
        with app.app_context():
            assert AcmeOrder.query.filter_by(order_id=order_id).first().status == 'invalid'


# --- caaIdentities (RFC 8555 §7.1.1) ---

class TestCaaIdentities:
    def _set(self, app, value):
        with app.app_context():
            SystemConfig.query.filter_by(key='acme_caa_identifiers').delete()
            if value is not None:
                db.session.add(SystemConfig(key='acme_caa_identifiers', value=value))
            db.session.commit()

    def test_directory_publishes_the_configured_identities(self, app, client):
        self._set(app, 'ca.example.net, ca2.example.net')
        try:
            meta = client.get('/acme/directory').get_json()['meta']
            assert meta['caaIdentities'] == ['ca.example.net', 'ca2.example.net']
        finally:
            self._set(app, None)

    def test_finalize_checks_caa_against_the_same_identities(self, app, account, monkeypatch):
        import utils.caa_checker as caa
        seen = []
        monkeypatch.setattr(caa, 'check_caa_for_domains',
                            lambda domains, identities, **k: seen.append(identities) or (False, 'stop'))
        self._set(app, 'ca.example.net')
        try:
            order_id = _ready_order(app, account, [{'type': 'dns', 'value': 'caa-same.example'}])
            with app.test_request_context('/acme/directory'):
                ok, _ = AcmeService(base_url=BASE).finalize_order(
                    order_id, _csr_pem(rsa.generate_private_key(65537, 2048), dns=['caa-same.example']))
            assert not ok
            assert seen == [['ca.example.net']]
        finally:
            self._set(app, None)

    def test_directory_falls_back_to_the_public_host(self, app, client):
        self._set(app, None)
        assert client.get('/acme/directory').get_json()['meta']['caaIdentities'] == ['localhost']


# --- CN = IP in the CSR of an IP order ---

class TestIpCommonName:
    @pytest.mark.parametrize('identifiers,cn,dns,ips', [
        ([{'type': 'ip', 'value': '192.0.2.61'}], '192.0.2.61', [], ['192.0.2.61']),
        ([{'type': 'dns', 'value': 'mixed-cn.example'}, {'type': 'ip', 'value': '192.0.2.62'}],
         '192.0.2.62', ['mixed-cn.example'], ['192.0.2.62']),
        ([{'type': 'ip', 'value': '2001:db8::63'}], '2001:DB8:0::63', [], ['2001:db8::63']),
    ])
    def test_ip_common_name_is_accepted(self, app, account, issuing_ca, no_caa, identifiers, cn, dns, ips):
        order_id = _ready_order(app, account, identifiers)
        ok, error, status, cert, _ = _finalize(
            app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), cn=cn, dns=dns, ips=ips),
            issuing_ca)
        assert ok, error
        assert status == 'valid'

    def test_ip_common_name_outside_the_order_is_refused(self, app, account, issuing_ca, no_caa):
        order_id = _ready_order(app, account, [{'type': 'ip', 'value': '192.0.2.64'}])
        ok, error, _, _, _ = _finalize(
            app, order_id, _csr_pem(rsa.generate_private_key(65537, 2048), cn='192.0.2.99',
                                    ips=['192.0.2.64']), issuing_ca)
        assert not ok
        assert '192.0.2.99' in error


# --- nonce purge ---

def test_scheduled_purge_removes_expired_and_used_nonces(app):
    from services.acme.order_purge import scheduled_purge
    with app.app_context():
        now = utc_now()
        rows = {'expired': AcmeNonce(token='purge-expired', expires_at=now - timedelta(minutes=1)),
                'used': AcmeNonce(token='purge-used', expires_at=now + timedelta(hours=1), used=True),
                'fresh': AcmeNonce(token='purge-fresh', expires_at=now + timedelta(hours=1))}
        db.session.add_all(rows.values())
        db.session.commit()
        scheduled_purge()
        left = {n.token for n in AcmeNonce.query.filter(AcmeNonce.token.like('purge-%')).all()}
        assert left == {'purge-fresh'}
        AcmeNonce.query.filter(AcmeNonce.token.like('purge-%')).delete(synchronize_session=False)
        db.session.commit()


# --- malformed requests and nonce errors (RFC 8555 §6.2, §6.5, §7.2) ---

class TestMalformedRequests:
    @pytest.mark.parametrize('path', ['/acme/new-order', '/acme/revoke-cert', '/acme/key-change',
                                      '/acme/new-authz', '/acme/order/x/finalize', '/acme/challenge/x'])
    @pytest.mark.parametrize('body', ['{not json', '[1, 2]'])
    def test_non_json_body_is_malformed(self, client, path, body):
        r = client.post(path, data=body, content_type='application/jose+json')
        assert r.status_code == 400, r.get_data(as_text=True)
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'

    @pytest.mark.parametrize('path', ['/acme/new-order', '/acme/revoke-cert'])
    def test_non_object_payload_is_malformed(self, client, account, path):
        r = _signed(client, account, path, [1, 2])
        assert r.status_code == 400
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'

    def test_missing_nonce_is_bad_nonce(self, client, account):
        protected = _b64json({'alg': 'RS256', 'url': f'{BASE}/acme/new-order', 'kid': account['kid']})
        payload = _b64json({'identifiers': [{'type': 'dns', 'value': 'nonce.example'}]})
        from tests.test_acme_security_paths import _sign
        jws = {'protected': protected, 'payload': payload,
               'signature': _sign(account['key'], protected, payload)}
        r = _post_jws(client, '/acme/new-order', jws)
        assert r.status_code == 400
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:badNonce'

    def test_nonce_outside_base64url_is_malformed(self, client, account):
        jws = _build_jws(f'{BASE}/acme/new-order', {'identifiers': [{'type': 'dns', 'value': 'n.example'}]},
                         account['key'], kid=account['kid'], nonce='a b+c/')
        r = _post_jws(client, '/acme/new-order', jws)
        assert r.status_code == 400
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'

    def test_head_new_nonce_is_200_and_links_the_directory(self, client):
        for method, status in (('head', 200), ('get', 204)):
            r = getattr(client, method)('/acme/new-nonce')
            assert r.status_code == status
            assert r.headers.get('Replay-Nonce')
            assert 'rel="index"' in r.headers.get('Link', '')
