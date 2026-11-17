"""Regression tests: ACME IP-identifier challenges skipped the SSRF guard
(security audit v2.203, item #5).

Both challenge validators gated the private-address check on
``identifier_type == "dns"``:

    if identifier_type == "dns" and not self._acme_allow_private_ips():
        validate_host_not_private(identifier_value)

so an RFC 8738 ``{"type":"ip"}`` order skipped it unconditionally — even with
``acme.allow_private_ips`` explicitly turned off. An external client could order
``{"type":"ip","value":"169.254.169.254"}`` and have the server issue
``GET http://169.254.169.254/.well-known/acme-challenge/<token>``: blind SSRF to
the cloud metadata service or any internal host.

``validate_host_not_private`` already handles a literal IP, so the fix is simply
to stop keying the guard on the identifier type.
"""
import pytest

from utils.ssrf_protection import validate_host_not_private


def _make_ip_challenge(value, challenge_type):
    """Persist an account/order/authz/challenge for an RFC 8738 'ip' order."""
    import json
    import uuid

    from models import db
    from models.acme_models import (
        AcmeAccount, AcmeAuthorization, AcmeChallenge, AcmeOrder,
    )

    acct = AcmeAccount(
        jwk='{"kty":"RSA","n":"AA","e":"AQAB"}',
        jwk_thumbprint=uuid.uuid4().hex + uuid.uuid4().hex[:11],
        status='valid',
    )
    db.session.add(acct)
    db.session.flush()

    order = AcmeOrder(
        account_id=acct.account_id,
        status='pending',
        identifiers=json.dumps([{'type': 'ip', 'value': value}]),
    )
    db.session.add(order)
    db.session.flush()

    authz = AcmeAuthorization(
        order_id=order.order_id,
        account_id=acct.account_id,
        identifier=json.dumps({'type': 'ip', 'value': value}),
        status='pending',
    )
    db.session.add(authz)
    db.session.flush()

    challenge = AcmeChallenge(
        authorization_id=authz.authorization_id,
        type=challenge_type,
        token='ssrf-probe-token',
        status='pending',
    )
    db.session.add(challenge)
    db.session.commit()
    return challenge, acct


@pytest.fixture
def acme_service(app):
    from services.acme.acme_service import AcmeService
    with app.app_context():
        yield AcmeService(base_url='http://localhost')


@pytest.mark.parametrize('addr', [
    '169.254.169.254',   # cloud metadata service
    '127.0.0.1',         # loopback
    '10.0.0.5',          # RFC 1918
    '192.168.1.1',
    '172.16.0.1',
])
def test_private_addresses_are_recognised_by_the_guard(addr):
    """Baseline: the guard itself handles literal IPs — it was never called."""
    with pytest.raises(ValueError):
        validate_host_not_private(addr)


def test_public_ip_passes_the_guard():
    validate_host_not_private('8.8.8.8')  # must not raise


class TestChallengeGuardCoversIpIdentifiers:
    """The guard must run for 'ip' identifiers, not just 'dns'.

    Both validators are driven with private IP identifiers and
    ``allow_private_ips`` off. A blocked challenge returns False and never
    performs the outbound fetch; before the fix the fetch was attempted.
    """

    def _prepare(self, acme_service, monkeypatch, identifier_type, value):
        monkeypatch.setattr(
            acme_service, '_acme_allow_private_ips', lambda: False
        )
        # Record any attempt to actually reach the target.
        reached = {'fetched': False}

        import requests as _requests

        def _boom(*_a, **_kw):
            reached['fetched'] = True
            raise AssertionError(
                f'SSRF: outbound request attempted to {value!r}'
            )

        monkeypatch.setattr(_requests, 'get', _boom)

        import socket as _socket

        def _boom_conn(*_a, **_kw):
            reached['fetched'] = True
            raise AssertionError(
                f'SSRF: outbound connection attempted to {value!r}'
            )

        monkeypatch.setattr(_socket, 'create_connection', _boom_conn)
        return reached

    @pytest.mark.parametrize('value', ['169.254.169.254', '127.0.0.1', '10.0.0.5'])
    def test_http01_blocks_private_ip_identifier(
        self, app, acme_service, monkeypatch, value
    ):
        reached = self._prepare(acme_service, monkeypatch, 'ip', value)
        with app.app_context():
            blocked, outcome = self._run_http01(acme_service, monkeypatch, value)
        assert blocked is False
        assert not reached['fetched'], (
            'the challenge validator reached out to a private address'
        )
        # Assert the blocked OUTCOME, not just the return value: False is also
        # what a failed fetch returns.
        assert outcome['status'] == 'invalid'
        assert 'rejectedIdentifier' in outcome['error']

    def _run_http01(self, acme_service, monkeypatch, value):
        """Invoke the HTTP-01 validator against a persisted 'ip' challenge.

        Returns the verdict plus a snapshot of the challenge's recorded
        outcome. The snapshot has to be taken here, while the session is
        still open — reading the attributes after the caller's app context
        exits raises DetachedInstanceError.
        """
        challenge, account = _make_ip_challenge(value, 'http-01')
        blocked = acme_service.validate_http01_challenge(challenge, account)
        return blocked, {
            'status': challenge.status,
            'error': challenge.error or '',
        }

    @pytest.mark.parametrize('value', ['169.254.169.254', '127.0.0.1'])
    def test_tls_alpn01_blocks_private_ip_identifier(
        self, app, acme_service, monkeypatch, value
    ):
        reached = self._prepare(acme_service, monkeypatch, 'ip', value)
        with app.app_context():
            challenge, account = _make_ip_challenge(value, 'tls-alpn-01')
            blocked = acme_service.validate_tls_alpn01_challenge(
                challenge, account
            )
            # Snapshot inside the context; the instance detaches on exit.
            outcome = {
                'status': challenge.status,
                'error': challenge.error or '',
            }
        assert blocked is False
        assert not reached['fetched'], (
            'the TLS-ALPN-01 validator connected to a private address'
        )
        assert outcome['status'] == 'invalid'
        assert 'rejectedIdentifier' in outcome['error']

    def test_public_ip_identifier_is_not_blocked_by_the_guard(
        self, app, acme_service, monkeypatch
    ):
        """Control: a public IP identifier still proceeds to the fetch.

        The stubbed requests.get raises, so reaching it proves the SSRF guard
        allowed the address through rather than short-circuiting first.
        """
        value = '8.8.8.8'
        reached = self._prepare(acme_service, monkeypatch, 'ip', value)
        with app.app_context():
            challenge, account = _make_ip_challenge(value, 'http-01')
            acme_service.validate_http01_challenge(challenge, account)
        assert reached['fetched'], (
            'a public IP identifier was blocked — the guard is too broad'
        )
