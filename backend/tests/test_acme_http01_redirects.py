"""Regression tests for http-01 redirect following (RFC 8555 §8.3).

A site-wide http→https 301 covering /.well-known/acme-challenge/ is the
normal nginx/Apache reality; the validator must walk the redirect instead of
comparing the 301 body to the key authorization. Every hop is re-vetted:
scheme, port, cloud metadata, and — under allow_private_ips=false — private
address targets.
"""
import socket

import pytest
import requests

from models import db
from models.acme_models import AcmeAccount
from services.acme.acme_service import AcmeService
from services.acme.http01 import MAX_REDIRECTS as _HTTP01_MAX_REDIRECTS
import utils.ssrf_protection as ssrf_protection


@pytest.fixture
def acme_account_id(app):
    with app.app_context():
        # The app fixture's DB is session-scoped with no per-test rollback,
        # and jwk_thumbprint is UNIQUE — reuse the row across tests.
        acct = AcmeAccount.query.filter_by(
            jwk_thumbprint='redirect-test-thumbprint'
        ).first()
        if acct is None:
            acct = AcmeAccount(
                jwk='{}',
                jwk_thumbprint='redirect-test-thumbprint',
                status='valid',
            )
            db.session.add(acct)
            db.session.commit()
        return acct.account_id


class _Resp:
    def __init__(self, status_code=200, text='', headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


def _install_get(monkeypatch, script):
    """Stub requests.get; `script` is a list consumed in order, or a callable
    url → _Resp. Returns the recorded (url, kwargs) calls."""
    calls = []

    def _get(url, **kwargs):
        calls.append((url, kwargs))
        if callable(script):
            return script(url)
        return script[len(calls) - 1]

    monkeypatch.setattr(requests, 'get', _get)
    return calls


def _make_http01(service, account_id, domain):
    order = service.create_order(
        account_id, [{'type': 'dns', 'value': domain}]
    )
    authz = order.authorizations.first()
    challenge = next(
        c for c in authz.challenges if c.type == 'http-01'
    )
    account = AcmeAccount.query.filter_by(account_id=account_id).first()
    key_authz = service._compute_key_authorization(
        challenge.token, account.jwk_thumbprint
    )
    return challenge, account, key_authz


class TestHttp01RedirectFollowing:
    def test_follows_http_to_https_redirect(
        self, app, acme_account_id, monkeypatch
    ):
        """The canonical breakage: port 80 answers 301 → https, the key
        authorization lives behind the redirect."""
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            challenge, account, key_authz = _make_http01(
                service, acme_account_id, 'redirect.example.com'
            )
            http_url = (
                'http://redirect.example.com/.well-known/acme-challenge/'
                f'{challenge.token}'
            )
            https_url = http_url.replace('http://', 'https://', 1)
            calls = _install_get(monkeypatch, [
                _Resp(301, headers={'Location': https_url}),
                _Resp(200, text=key_authz),
            ])

            assert service.validate_http01_challenge(challenge, account) is True
            assert challenge.status == 'valid'
            assert [url for url, _ in calls] == [http_url, https_url]
            # https hop must neither auto-redirect nor verify TLS — the target
            # usually serves the very certificate being renewed.
            assert calls[1][1].get('allow_redirects') is False
            assert calls[1][1].get('verify') is False

    def test_relative_location_is_resolved(
        self, app, acme_account_id, monkeypatch
    ):
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            challenge, account, key_authz = _make_http01(
                service, acme_account_id, 'relative.example.com'
            )
            calls = _install_get(monkeypatch, [
                _Resp(302, headers={'Location': '/answers/here'}),
                _Resp(200, text=key_authz),
            ])

            assert service.validate_http01_challenge(challenge, account) is True
            assert calls[1][0] == 'http://relative.example.com/answers/here'

    def test_redirect_loop_is_bounded(
        self, app, acme_account_id, monkeypatch
    ):
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            challenge, account, _ = _make_http01(
                service, acme_account_id, 'loop.example.com'
            )
            calls = _install_get(
                monkeypatch,
                lambda url: _Resp(
                    301, headers={'Location': 'http://loop.example.com/again'}
                ),
            )

            assert service.validate_http01_challenge(challenge, account) is False
            assert challenge.status == 'invalid'
            assert 'connection' in (challenge.error or '')
            assert 'redirect' in (challenge.error or '')
            assert len(calls) == _HTTP01_MAX_REDIRECTS + 1

    @pytest.mark.parametrize('location,refused_for', [
        ('ftp://files.example.com/x', 'scheme'),
        ('https://redirect.example.com:8443/x', 'port'),
        ('http://169.254.169.254/latest/api/token', 'metadata'),
    ])
    def test_forbidden_redirect_targets_are_refused(
        self, app, acme_account_id, monkeypatch, location, refused_for
    ):
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            challenge, account, _ = _make_http01(
                service, acme_account_id, 'forbidden.example.com'
            )
            calls = _install_get(monkeypatch, [
                _Resp(301, headers={'Location': location}),
            ])

            assert service.validate_http01_challenge(challenge, account) is False
            assert challenge.status == 'invalid'
            assert 'connection' in (challenge.error or '')
            # The forbidden target must never be fetched.
            assert len(calls) == 1

    def test_private_redirect_target_refused_when_private_ips_disallowed(
        self, app, acme_account_id, monkeypatch
    ):
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            challenge, account, _ = _make_http01(
                service, acme_account_id, 'public-front.example.com'
            )

            def _resolve(host, *_a, **_kw):
                ip = (
                    '10.0.0.5' if host == 'internal.example.com'
                    else '93.184.216.34'
                )
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0))]

            monkeypatch.setattr(
                ssrf_protection.socket, 'getaddrinfo', _resolve
            )
            monkeypatch.setattr(
                AcmeService, '_acme_allow_private_ips', lambda self: False
            )
            calls = _install_get(monkeypatch, [
                _Resp(301, headers={'Location': 'http://internal.example.com/'}),
            ])

            assert service.validate_http01_challenge(challenge, account) is False
            assert challenge.status == 'invalid'
            assert 'connection' in (challenge.error or '')
            assert len(calls) == 1
