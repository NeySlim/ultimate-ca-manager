"""Tests for the dns-persist-01 challenge (draft-ietf-acme-dns-persist-01).

Unit tests cover the pure record parsing/matching; the integration class
drives the real HTTP challenge-response round-trip with a stubbed resolver.
"""
import json
from datetime import timedelta

import pytest

from models import db, SystemConfig
from models.acme_models import (
    AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge,
)
from services.acme import dns_persist
from utils.datetime_utils import utc_now

from tests.test_acme_security_paths import (
    _build_jws, _gen_key_and_jwk, _nonce, _post_jws, _thumbprint,
)


class _Rdata:
    """Minimal dnspython TXT rdata stand-in: .strings (list of bytes)."""
    def __init__(self, value: str):
        self.strings = [value.encode()]


class _Answers(list):
    pass


@pytest.fixture
def acme_persist_account(app):
    key, jwk = _gen_key_and_jwk()
    with app.app_context():
        acct = AcmeAccount(
            jwk=json.dumps(jwk),
            jwk_thumbprint=_thumbprint(jwk),
            status='valid',
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.account_id
    return {'key': key, 'jwk': jwk, 'account_id': acct_id}


def _set_cfg(app, key, value):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


def _enable(app, issuer='ca.normalize.test'):
    _set_cfg(app, 'acme.dns_persist_enabled', 'true')
    _set_cfg(app, 'acme_caa_identifiers', issuer)


def _disable(app):
    _set_cfg(app, 'acme.dns_persist_enabled', 'false')
    _set_cfg(app, 'acme_caa_identifiers', '')


class TestRecordParsing:
    def test_minimal_record(self):
        issuer, params = dns_persist.parse_issue_value(
            'ca.example; accounturi=https://ca.example/acct/123')
        assert issuer == 'ca.example'
        assert params['accounturi'] == 'https://ca.example/acct/123'

    def test_multi_string_rdata_joined(self):
        rdata = type('R', (), {'strings': [b'ca.example; accounturi=', b'https://x/acct/1']})()
        assert dns_persist.rdata_strings(rdata) == ['ca.example; accounturi=https://x/acct/1']

    def test_unknown_parameter_ignored(self):
        _issuer, params = dns_persist.parse_issue_value(
            'ca.example; accounturi=u; something-future=zzz')
        assert 'something-future' not in params

    def test_duplicate_parameter_malformed(self):
        with pytest.raises(ValueError, match='duplicate'):
            dns_persist.parse_issue_value('ca.example; policy=wildcard; policy=wildcard')

    def test_bad_persistuntil_malformed(self):
        with pytest.raises(ValueError, match='persistUntil'):
            dns_persist.parse_issue_value('ca.example; accounturi=u; persistUntil=notanum')

    def test_policy_value_case_insensitive(self):
        ok, _t, _d = dns_persist.check_record_against(
            'ca.example', {'accounturi': 'u', 'policy': 'WILDCARD'},
            ['ca.example'], 'u', is_exact_fqdn=True, is_wildcard_request=True, now_ts=0)
        assert ok

    def test_issuer_normalization(self):
        assert dns_persist.normalize_domain('EXAMPLE.com.') == 'example.com'


class TestRecordMatching:
    I = ['ca.example']

    def test_exact_fqdn_no_policy_ok(self):
        ok, _t, _d = dns_persist.check_record_against(
            'ca.example', {'accounturi': 'u'}, self.I, 'u',
            is_exact_fqdn=True, is_wildcard_request=False, now_ts=0)
        assert ok

    def test_wildcard_requires_policy(self):
        ok, t, _d = dns_persist.check_record_against(
            'ca.example', {'accounturi': 'u'}, self.I, 'u',
            is_exact_fqdn=True, is_wildcard_request=True, now_ts=0)
        assert not ok and t == 'unauthorized'

    def test_subdomain_ancestor_requires_policy(self):
        ok, t, _d = dns_persist.check_record_against(
            'ca.example', {'accounturi': 'u'}, self.I, 'u',
            is_exact_fqdn=False, is_wildcard_request=False, now_ts=0)
        assert not ok and t == 'unauthorized'

    def test_wrong_account_unauthorized(self):
        ok, t, d = dns_persist.check_record_against(
            'ca.example', {'accounturi': 'other'}, self.I, 'u',
            is_exact_fqdn=True, is_wildcard_request=False, now_ts=0)
        assert not ok and t == 'unauthorized' and 'accounturi' in d

    def test_missing_accounturi_malformed(self):
        ok, t, _d = dns_persist.check_record_against(
            'ca.example', {}, self.I, 'u',
            is_exact_fqdn=True, is_wildcard_request=False, now_ts=0)
        assert not ok and t == 'malformed'

    def test_persistuntil_expired_rejects_new_attempt(self):
        ok, t, d = dns_persist.check_record_against(
            'ca.example', {'accounturi': 'u', 'persistuntil': 100},
            self.I, 'u', is_exact_fqdn=True, is_wildcard_request=False, now_ts=101)
        assert not ok and t == 'unauthorized' and 'persistUntil' in d

    def test_persistuntil_future_valid(self):
        ok, _t, _d = dns_persist.check_record_against(
            'ca.example', {'accounturi': 'u', 'persistuntil': 200},
            self.I, 'u', is_exact_fqdn=True, is_wildcard_request=False, now_ts=101)
        assert ok

    def test_other_issuer_record_ignored(self):
        ok, t, _d = dns_persist.check_record_against(
            'someone.else', {'accounturi': 'u'}, self.I, 'u',
            is_exact_fqdn=True, is_wildcard_request=False, now_ts=0)
        assert (ok, t) == (False, None)  # not an error — simply not ours


def _make_persist_challenge(app, account_id, fqdn):
    # Store like OrderMixin._normalize_authorization_identifier does
    # (RFC 8555 §7.1.4): base domain in the identifier, wildcard as a flag.
    is_wildcard = fqdn.startswith('*.')
    base = fqdn[2:] if is_wildcard else fqdn
    with app.app_context():
        order = AcmeOrder(
            account_id=account_id,
            status='pending',
            identifiers=json.dumps([{'type': 'dns', 'value': fqdn}]),
        )
        db.session.add(order)
        db.session.commit()
        authz = AcmeAuthorization(
            order_id=order.order_id,
            account_id=account_id,
            identifier=json.dumps({'type': 'dns', 'value': base}),
            status='pending',
            expires=utc_now() + timedelta(days=1),
            wildcard=is_wildcard,
        )
        db.session.add(authz)
        db.session.commit()
        chall = AcmeChallenge(
            authorization_id=authz.authorization_id,
            type='dns-persist-01',
            status='pending',
            url='http://localhost/acme/challenge/placeholder',
        )
        db.session.add(chall)
        db.session.commit()
        chall.url = f'http://localhost/acme/challenge/{chall.challenge_id}'
        db.session.commit()
        return chall.challenge_id


def _dns_stub(monkeypatch, mapping):
    """mapping: name -> list[str]; missing name => NXDOMAIN-like error."""
    import dns.resolver
    def _resolve(name, rdtype=None):
        key = name.rstrip('.')
        if key in mapping:
            return _Answers(_Rdata(v) for v in mapping[key])
        raise dns.resolver.NXDOMAIN()
    monkeypatch.setattr('dns.resolver.resolve', _resolve)


def _respond(client, acct, chall_id):
    url = f'http://localhost/acme/challenge/{chall_id}'
    kid = f'http://localhost/acme/acct/{acct["account_id"]}'
    jws = _build_jws(url, {}, acct['key'], kid=kid, nonce=_nonce(client))
    return _post_jws(client, f'/acme/challenge/{chall_id}', jws)


def _chall_state(app, chall_id):
    with app.app_context():
        row = AcmeChallenge.query.filter_by(challenge_id=chall_id).first()
        return row.status, (json.loads(row.error) if row.error else None)


class TestDnsPersistChallengeFlow:
    ISSUER = 'ca.normalize.test'

    def _acct_uri(self, account_id):
        return f'http://localhost/acme/acct/{account_id}'

    def test_enabled_flag_offers_challenge_in_authz(self, app, acme_persist_account):
        _enable(app, self.ISSUER)
        from services.acme.acme_service import AcmeService
        svc = AcmeService(base_url='http://localhost')
        with app.app_context():
            authz = svc.create_pre_authorization(
                acme_persist_account['account_id'],
                {'type': 'dns', 'value': 'persist.example.com'})
            types = sorted(c.type for c in authz.challenges)
        assert 'dns-persist-01' in types
        assert 'dns-01' in types and 'http-01' in types
        _disable(app)

    def test_disabled_flag_no_persist_challenge(self, app, acme_persist_account):
        _disable(app)
        from services.acme.acme_service import AcmeService
        svc = AcmeService(base_url='http://localhost')
        with app.app_context():
            authz = svc.create_pre_authorization(
                acme_persist_account['account_id'],
                {'type': 'dns', 'value': 'persist.example.com'})
            types = [c.type for c in authz.challenges]
        assert 'dns-persist-01' not in types

    def test_valid_record_passes(self, app, client, acme_persist_account, monkeypatch):
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], 'persist.example.com')
        _dns_stub(monkeypatch, {
            '_validation-persist.persist.example.com': [
                f'{self.ISSUER}; accounturi={self._acct_uri(acme_persist_account["account_id"])}',
            ],
        })
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200, r.data
        status, _ = _chall_state(app, chall_id)
        assert status == 'valid'
        _disable(app)

    def test_wrong_account_fails_unauthorized(self, app, client, acme_persist_account, monkeypatch):
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], 'persist.example.com')
        _dns_stub(monkeypatch, {
            '_validation-persist.persist.example.com': [
                f'{self.ISSUER}; accounturi=http://localhost/acme/acct/aaaa1111',
            ],
        })
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200
        status, err = _chall_state(app, chall_id)
        assert status == 'invalid'
        assert err['type'].endswith(':unauthorized')
        _disable(app)

    def test_no_record_fails_incorrect_response(self, app, client, acme_persist_account, monkeypatch):
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], 'ghost.example.com')
        _dns_stub(monkeypatch, {})
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200
        status, err = _chall_state(app, chall_id)
        assert status == 'invalid'
        assert err['type'].endswith(':incorrectResponse')
        assert '_validation-persist.ghost.example.com' in err['detail']
        _disable(app)

    def test_wildcard_identifier_requires_wildcard_policy(self, app, client, acme_persist_account, monkeypatch):
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], '*.wild.example.com')
        _dns_stub(monkeypatch, {
            '_validation-persist.wild.example.com': [
                f'{self.ISSUER}; accounturi={self._acct_uri(acme_persist_account["account_id"])}',
            ],
        })
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200
        status, err = _chall_state(app, chall_id)
        assert status == 'invalid'
        assert err['type'].endswith(':unauthorized') and 'policy=wildcard' in err['detail']
        _disable(app)

    def test_wildcard_identifier_with_policy_passes(self, app, client, acme_persist_account, monkeypatch):
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], '*.wild.example.com')
        _dns_stub(monkeypatch, {
            '_validation-persist.wild.example.com': [
                f'{self.ISSUER}; accounturi={self._acct_uri(acme_persist_account["account_id"])}; policy=wildcard',
            ],
        })
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200
        status, _ = _chall_state(app, chall_id)
        assert status == 'valid'
        _disable(app)

    def test_subdomain_via_wildcard_ancestor(self, app, client, acme_persist_account, monkeypatch):
        """Record at parent with policy=wildcard authorizes subdomain FQDN (§6)."""
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], 'server.sub.example.com')
        _dns_stub(monkeypatch, {
            '_validation-persist.sub.example.com': [
                f'{self.ISSUER}; accounturi={self._acct_uri(acme_persist_account["account_id"])}; policy=wildcard',
            ],
        })
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200
        status, _ = _chall_state(app, chall_id)
        assert status == 'valid'
        _disable(app)

    def test_persistuntil_expired_record_rejected(self, app, client, acme_persist_account, monkeypatch):
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], 'persist.example.com')
        _dns_stub(monkeypatch, {
            '_validation-persist.persist.example.com': [
                f'{self.ISSUER}; accounturi={self._acct_uri(acme_persist_account["account_id"])}; persistUntil=946684800',
            ],
        })
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200
        status, err = _chall_state(app, chall_id)
        assert status == 'invalid'
        assert 'persistUntil' in err['detail']
        _disable(app)

    def test_custom_resolver_host_port_parsed(self, app):
        """acme.dns01_nameservers accepts host:port entries."""
        _set_cfg(app, 'acme.dns01_nameservers', '127.0.0.1:5353, 10.9.8.7')
        with app.app_context():
            from services.acme.acme_service import AcmeService
            resolver = AcmeService(base_url='http://localhost')._acme_dns01_resolver()
        assert resolver is not None
        assert resolver.nameservers == ['127.0.0.1', '10.9.8.7']
        assert resolver.port == 5353
        _set_cfg(app, 'acme.dns01_nameservers', '')

    def test_multiple_records_any_match_passes(self, app, client, acme_persist_account, monkeypatch):
        """Multi-issuer coexistence (§4.3): our record among others."""
        _enable(app, self.ISSUER)
        chall_id = _make_persist_challenge(
            app, acme_persist_account['account_id'], 'multi.example.com')
        _dns_stub(monkeypatch, {
            '_validation-persist.multi.example.com': [
                f'other-ca.example; accounturi=http://localhost/acme/acct/zzzz9999',
                f'{self.ISSUER}; accounturi={self._acct_uri(acme_persist_account["account_id"])}',
            ],
        })
        r = _respond(client, acme_persist_account, chall_id)
        assert r.status_code == 200
        status, _ = _chall_state(app, chall_id)
        assert status == 'valid'
        _disable(app)
