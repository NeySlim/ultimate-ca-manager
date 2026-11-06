"""ACME client: the identifier, the CSR and the waits a CA sees, and when a renewal is due."""
import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import Certificate, SystemConfig, db
from models.acme_models import AcmeClientOrder
from services import acme_renewal_service as renew_mod
from services.acme.acme_client_service import AcmeClientService

ORDER_URL = 'https://ca.example/order/audit'
AKI = bytes.fromhex('69885B6B87464041E1B37B847BA0AE2CDE01C8D4')


def _cert_with_serial(serial, key=None):
    key = key or ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'ari.example')])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()) \
        .serial_number(serial).not_valid_before(now).not_valid_after(now + timedelta(days=90)) \
        .add_extension(x509.AuthorityKeyIdentifier(AKI, None, None), critical=False) \
        .sign(key, hashes.SHA256())


@pytest.mark.parametrize('serial, expected', [
    (0x87654321, 'aYhba4dGQEHhs3uEe6CuLN4ByNQ.AIdlQyE'),  # the example of RFC 9773 §4.1
    (0x7F654321, 'aYhba4dGQEHhs3uEe6CuLN4ByNQ.f2VDIQ'),
])
def test_the_ari_identifier_holds_the_der_value_of_the_serial(serial, expected):
    assert AcmeClientService.certificate_identifier(_cert_with_serial(serial)) == expected


def _csr(name):
    key = ec.generate_private_key(ec.SECP256R1())
    der = base64.urlsafe_b64decode(AcmeClientService._build_csr_b64(key, [name], name) + '==')
    return x509.load_der_x509_csr(der)


def test_a_name_too_long_for_a_cn_goes_in_a_critical_san_only():
    name = f"{'a' * 61}.{'b' * 61}.example.com"
    csr = _csr(name)
    assert list(csr.subject) == []
    san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert san.critical and san.value.get_values_for_type(x509.DNSName) == [name]


def test_a_name_of_64_characters_stays_in_the_cn():
    name = f"{'a' * 52}.example.com"
    assert len(name) == 64
    csr = _csr(name)
    assert csr.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value == name
    assert not csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).critical


def _service():
    return AcmeClientService.__new__(AcmeClientService)


def _response(status=200, body=None, retry_after=None):
    headers = {'Retry-After': retry_after} if retry_after is not None else {}
    return SimpleNamespace(status_code=status, json=lambda: body or {}, headers=headers)


class _Clock:
    """Virtual time, so a wait is measured instead of slept."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock():
    virtual = _Clock()
    with patch('services.acme.acme_client_service.time', virtual):
        yield virtual


@pytest.fixture
def order(app):
    with app.app_context():
        row = AcmeClientOrder(domains=json.dumps(['audit.example.com']), challenge_type='dns-01',
                              environment='staging', status='ready', order_url=ORDER_URL,
                              finalize_url=f'{ORDER_URL}/finalize')
        db.session.add(row)
        db.session.commit()
        yield row
        db.session.rollback()
        AcmeClientOrder.query.filter_by(order_url=ORDER_URL).delete()
        db.session.commit()


def _poll_settings(svc, timeout=180, interval=3):
    svc.get_poll_settings = lambda: {'order_poll_timeout_sec': timeout, 'order_poll_interval_sec': interval}


def _finalizing_service(answers, finalize):
    """The order is ready, finalize answers `finalize`, then each poll takes the next answer."""
    svc = _service()
    _poll_settings(svc)
    answers = iter(answers)
    first = [True]

    def post(url, _payload):
        if url == f'{ORDER_URL}/finalize':
            return finalize
        if url == 'https://ca.example/cert':
            return _response(200)
        if first[0]:
            first[0] = False
            return _response(200, {'status': 'ready'})
        return next(answers)

    svc._post = post
    svc._generate_cert_key = lambda _order: (ec.generate_private_key(ec.SECP256R1()), None)
    svc._select_certificate_chain = lambda _resp: 'pem'
    svc._import_certificate = MagicMock(return_value=None)
    return svc


def test_finalize_waits_as_long_as_the_ca_asks(clock, order):
    processing = {'status': 'processing'}
    svc = _finalizing_service(
        [_response(200, {'status': 'valid', 'certificate': 'https://ca.example/cert'})],
        _response(200, processing, retry_after='60'))
    svc.finalize_order(order)
    assert clock.sleeps == [pytest.approx(60, abs=2)]
    svc._import_certificate.assert_called_once()


def test_a_poll_answer_sets_the_next_wait_too(clock, order):
    finalize = _response(200, {'status': 'processing'})
    svc = _finalizing_service(
        [_response(200, {'status': 'processing'}, retry_after='40'),
         _response(200, {'status': 'valid', 'certificate': 'https://ca.example/cert'})], finalize)
    svc.finalize_order(order)
    assert clock.sleeps[0] == 3 and clock.sleeps[1] == pytest.approx(40, abs=2)


def test_finalize_polls_past_the_old_thirty_seconds(clock, order):
    processing = _response(200, {'status': 'processing'})
    done = _response(200, {'status': 'valid', 'certificate': 'https://ca.example/cert'})
    svc = _finalizing_service([processing] * 19 + [done], processing)
    svc.finalize_order(order)
    assert sum(clock.sleeps) == 60
    svc._import_certificate.assert_called_once()


def test_finalize_gives_up_at_the_poll_timeout(clock, order):
    processing = _response(200, {'status': 'processing'})
    svc = _finalizing_service([processing] * 100, processing)
    ok, message, _cert = svc.finalize_order(order)
    assert not ok and message == 'Certificate not ready after polling'
    assert sum(clock.sleeps) == 180
    svc._import_certificate.assert_not_called()


def test_a_renewal_waits_for_the_validation_it_started(clock, order):
    svc = _service()
    _poll_settings(svc)
    answers = iter([_response(200, {'status': 'pending'})] * 13 + [_response(200, {'status': 'ready'})])
    svc._post = lambda *_args: next(answers)
    status, _data = svc.wait_for_order(order)
    assert status == 'ready' and sum(clock.sleeps) == 39


def test_a_key_revoked_as_compromised_is_not_certified_again(app, clock, order):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    done = _response(200, {'status': 'valid', 'certificate': 'https://ca.example/cert'})

    def key_certified_with(reason):
        source = Certificate(refid=f'audit-{reason}', descr='audit', prv=base64.b64encode(pem).decode(),
                             revoked=True, revoke_reason=reason)
        db.session.add(source)
        db.session.commit()
        order.key_source = 'reuse'
        order.source_certificate_id = source.id
        db.session.commit()
        svc = _finalizing_service([], done)
        seen = {}
        svc._build_csr_b64 = lambda cert_key, *_args: seen.update(key=cert_key) or 'csr'
        svc.finalize_order(order)
        order.source_certificate_id = None
        db.session.delete(source)
        db.session.commit()
        return seen['key'].public_key().public_numbers()

    original = key.public_key().public_numbers()
    assert key_certified_with('superseded') == original
    assert key_certified_with('key_compromise') != original


def test_a_compromised_key_on_an_earlier_certificate_of_the_chain_is_not_reused(app, clock, order):
    # A was revoked, B carries the same key and is not: B would certify it at every renewal
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())

    def stored(refid, serial, reason=None):
        der = _cert_with_serial(serial, key).public_bytes(serialization.Encoding.PEM)
        row = Certificate(refid=refid, descr='audit', crt=base64.b64encode(der).decode(),
                          prv=base64.b64encode(pem).decode(), revoked=bool(reason), revoke_reason=reason)
        db.session.add(row)
        db.session.commit()
        return row

    def reused_from(source):
        order.key_source = 'reuse'
        order.source_certificate_id = source.id
        db.session.commit()
        svc = _finalizing_service([], _response(200, {'status': 'valid', 'certificate': 'https://ca.example/cert'}))
        seen = {}
        svc._build_csr_b64 = lambda cert_key, *_args: seen.update(key=cert_key) or 'csr'
        svc.finalize_order(order)
        return seen['key'].public_key().public_numbers() == key.public_key().public_numbers()

    later = stored('audit-chain-b', 0x1002)
    earlier = stored('audit-chain-a', 0x1001, 'superseded')
    try:
        assert reused_from(later)
        earlier.revoke_reason = 'keyCompromise'
        db.session.commit()
        assert not reused_from(later)
    finally:
        order.source_certificate_id = None
        db.session.delete(later)
        db.session.delete(earlier)
        db.session.commit()


def test_a_csr_whose_key_was_revoked_as_compromised_never_reaches_the_ca(app, clock, order):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'audit.example.com')])
    san = x509.SubjectAlternativeName([x509.DNSName('audit.example.com')])
    csr = x509.CertificateSigningRequestBuilder().subject_name(name).add_extension(san, critical=False) \
        .sign(key, hashes.SHA256())
    pem = _cert_with_serial(0x1003, key).public_bytes(serialization.Encoding.PEM)
    revoked = Certificate(refid='audit-csr', descr='audit', crt=base64.b64encode(pem).decode(),
                          revoked=True, revoke_reason='keyCompromise')
    order.key_source = 'csr'
    order.csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()
    db.session.add(revoked)
    db.session.commit()
    posted = []
    svc = _finalizing_service([], _response(200, {'status': 'valid', 'certificate': 'https://ca.example/cert'}))
    answer = svc._post
    svc._post = lambda url, payload: posted.append(url) or answer(url, payload)
    try:
        ok, message, _cert = svc.finalize_order(order)
        assert not ok and 'revoked as compromised' in message
        assert f'{ORDER_URL}/finalize' not in posted
        revoked.revoke_reason = 'superseded'
        db.session.commit()
        svc._post = lambda url, payload: posted.append(url) or (
            _response(200, {'status': 'ready'}) if url == ORDER_URL else answer(url, payload))
        svc.finalize_order(order)
        assert f'{ORDER_URL}/finalize' in posted
    finally:
        db.session.delete(revoked)
        db.session.commit()


@pytest.mark.sqlite_only(reason='a dangling source_certificate_id is refused by the foreign key')
def test_a_reuse_whose_source_is_gone_says_so(app, clock, order):
    order.key_source = 'reuse'
    order.source_certificate_id = 987654
    db.session.commit()
    svc = _finalizing_service([], _response(200, {'status': 'valid', 'certificate': 'https://ca.example/cert'}))
    ok, message, _cert = svc.finalize_order(order)
    assert not ok and message == 'The certificate holding the key to reuse no longer exists'


def _order_due(valid_days, left_days, threshold_days, short_of_a_second=False):
    now = datetime(2026, 11, 5)
    certificate = SimpleNamespace(valid_from=now - timedelta(days=valid_days - left_days),
                                  valid_to=now + timedelta(days=left_days, seconds=-short_of_a_second))
    row = SimpleNamespace(id=1, certificate_id=1, expires_at=certificate.valid_to)
    with patch.object(renew_mod, '_cached_renewal_info', return_value=None), \
            patch.object(renew_mod.db.session, 'get', return_value=certificate):
        return renew_mod._order_is_due(row, now, now + timedelta(days=threshold_days))


@pytest.mark.parametrize('valid, left, threshold, due', [
    (20, 20, 30, False),  # just issued, under a threshold longer than its life
    (20, 6, 30, True),  # the last third
    (20, 7, 30, False),
    (31, 30, 30, False),  # still nearly all of its life ahead
    (31, 10, 30, True),
    (90, 45, 60, True),  # a threshold up to two thirds of the life is the operator's
    (45, 29, 30, True),
    (90, 61, 60, False),
])
def test_a_threshold_longer_than_the_life_keeps_a_last_third(valid, left, threshold, due):
    assert _order_due(valid, left, threshold) is due


def test_a_threshold_of_two_thirds_holds_on_notafter_one_second_short():
    # How public CAs issue: the validity period counts both of its ends
    assert _order_due(90, 45, 60, short_of_a_second=True) is True


@pytest.mark.parametrize('account_url, renews', [('https://ca.example/acct/1', True), (None, False)])
def test_only_a_registration_needs_the_email(app, order, account_url, renews):
    client = MagicMock()
    client._get_account_url.return_value = account_url
    client._fetch_directory.return_value = {}
    client.account = None
    client.create_order.return_value = (False, 'stopped here', None)
    order.challenge_type = 'http-01'
    db.session.commit()
    row = SystemConfig.query.filter_by(key='acme.client.email').first()
    previous = row.value if row else None
    if row:
        db.session.delete(row)
        db.session.commit()
    try:
        with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=client):
            with pytest.raises(Exception, match='stopped here' if renews else 'email not configured'):
                renew_mod.renew_certificate(order)
    finally:
        if previous is not None:
            db.session.add(SystemConfig(key='acme.client.email', value=previous, description='test'))
            db.session.commit()
    assert client.create_order.called is renews


@pytest.mark.parametrize('value', ['99999999999999', 'Fri, 31 Dec 9999 23:59:59 -2359', 'soon', '-5'])
def test_an_absurd_retry_after_falls_back_to_the_interval(clock, order, value):
    svc = _service()
    _poll_settings(svc)
    answers = iter([_response(200, {'status': 'pending'}, retry_after=value), _response(200, {'status': 'ready'})])
    svc._post = lambda *_args: next(answers)
    status, data = svc.wait_for_order(order)
    assert status == 'ready' and data == {'status': 'ready'} and clock.sleeps == [3]


@pytest.mark.parametrize('status, detail, retried', [
    (400, 'no', True), (404, 'no', True), (409, 'no', True), (429, 'no', False), (500, 'no', False),
    (429, 'too many replacements', False), (500, 'cannot replace', True),
    (403, 'urn:ietf:params:acme:error:rateLimited', False),
])
def test_a_refused_replaces_is_dropped_but_not_on_a_rate_limit(app, status, detail, retried):
    svc = _service()
    svc.environment = 'staging'
    svc.account = None
    svc.ensure_account = lambda _email: (True, 'ok')
    svc._fetch_directory = lambda: {'newOrder': 'https://ca.example/new-order', 'renewalInfo': 'https://ca.example/ari'}
    sent = []

    def post(_url, payload):
        sent.append(dict(payload))
        kind = detail if detail.startswith('urn:') else 'urn:ietf:params:acme:error:malformed'
        return _response(status, {'type': kind, 'detail': detail})

    svc._post = post
    ok, _message, _order = svc.create_order(['audit.example.com'], 'a@example.com', replaces='x.y')
    assert not ok
    assert [('replaces' in p) for p in sent] == ([True, False] if retried else [True])
