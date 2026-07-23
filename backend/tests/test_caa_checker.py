"""Tests for utils.caa_checker (RFC 6844 / RFC 8659 CAA enforcement).

DNS is fully mocked — no network. Each test sets up which CAA rdata each
zone returns as we walk up the domain tree.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import dns.resolver
import dns.exception

from utils.caa_checker import check_caa, check_caa_for_domains


class _FakeCAA:
    """Minimal stand-in for a dns CAA rdata (flags/tag/value)."""

    def __init__(self, tag='issue', value='ucm.example.com', flags=0):
        self.flags = flags
        self.tag = tag.encode()
        self.value = value.encode()


def _resolver(zone_records):
    """Return a fake dns.resolver.resolve keyed by zone name.

    zone_records: {'example.com': [_FakeCAA(...), ...]}. Zones absent from the
    map raise NXDOMAIN (no record); an empty list raises NoAnswer.
    """
    def _resolve(name, rdtype):
        assert rdtype == 'CAA'
        key = str(name).rstrip('.')
        if key not in zone_records:
            raise dns.resolver.NXDOMAIN()
        records = zone_records[key]
        if not records:
            raise dns.resolver.NoAnswer()
        return records
    return _resolve


def _patch(zone_records):
    return patch('dns.resolver.resolve', side_effect=_resolver(zone_records))


class TestNoRecords:
    def test_no_caa_anywhere_allows(self):
        with _patch({}):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True
        assert 'No CAA record' in reason

    @pytest.mark.parametrize('dns_error', [
        dns.exception.Timeout(),
        dns.resolver.NoNameservers(),
    ])
    def test_dns_error_soft_fails_by_default(self, dns_error):
        # Air-gapped/split-horizon deployments SERVFAIL or time out on CAA:
        # pre-2.200 behaviour (non-blocking) is the default again.
        with patch('dns.resolver.resolve', side_effect=dns_error):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True
        assert 'No CAA record' in reason

    @pytest.mark.parametrize('dns_error', [
        dns.exception.Timeout(),
        dns.resolver.NoNameservers(),
    ])
    def test_dns_error_denies_issuance_when_enforced(self, dns_error):
        with patch('dns.resolver.resolve', side_effect=dns_error):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'],
                                   fail_hard=True)
        assert ok is False
        assert 'DNS' in reason

    def test_nodata_continues_to_parent(self):
        with _patch({'example.com': [_FakeCAA('issue', 'ucm.example.com')]}):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True


class TestIssueMatching:
    def test_matching_issuer_allows(self):
        with _patch({'example.com': [_FakeCAA('issue', 'ucm.example.com')]}):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True
        assert 'authorized' in reason.lower()

    def test_non_matching_issuer_denies(self):
        with _patch({'example.com': [_FakeCAA('issue', 'letsencrypt.org')]}):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is False
        assert 'letsencrypt.org' in reason

    def test_issuer_match_is_case_insensitive(self):
        with _patch({'example.com': [_FakeCAA('issue', 'UCM.Example.COM')]}):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True

    def test_accounturi_match_allows(self):
        rec = _FakeCAA(
            'issue',
            'ucm.example.com; accounturi=https://ca.example/acme/acct/account-1',
        )
        with _patch({'example.com': [rec]}):
            ok, _ = check_caa(
                'www.example.com',
                ['ucm.example.com'],
                account_url='https://ca.example/acme/acct/account-1',
            )
        assert ok is True

    def test_accounturi_mismatch_denies(self):
        rec = _FakeCAA(
            'issue',
            'ucm.example.com; accounturi=https://ca.example/acme/acct/account-1',
        )
        with _patch({'example.com': [rec]}):
            ok, reason = check_caa(
                'www.example.com',
                ['ucm.example.com'],
                account_url='https://ca.example/acme/acct/account-2',
            )
        assert ok is False
        assert 'accounturi' in reason

    def test_accounturi_without_request_account_denies(self):
        rec = _FakeCAA(
            'issue',
            'ucm.example.com; accounturi=https://ca.example/acme/acct/account-1',
        )
        with _patch({'example.com': [rec]}):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is False

    def test_validationmethods_allows_used_method(self):
        rec = _FakeCAA(
            'issue',
            'ucm.example.com; validationmethods=http-01,dns-01',
        )
        with _patch({'example.com': [rec]}):
            ok, _ = check_caa(
                'www.example.com',
                ['ucm.example.com'],
                validation_method='dns-01',
            )
        assert ok is True

    def test_validationmethods_denies_other_method(self):
        rec = _FakeCAA('issue', 'ucm.example.com; validationmethods=http-01')
        with _patch({'example.com': [rec]}):
            ok, reason = check_caa(
                'www.example.com',
                ['ucm.example.com'],
                validation_method='dns-01',
            )
        assert ok is False
        assert 'validationmethods' in reason

    def test_validationmethods_with_indeterminable_method_allows(self):
        # Reused/auto-approved authorizations have no single determinable
        # challenge type — the parameter is not enforced in that case.
        rec = _FakeCAA('issue', 'ucm.example.com; validationmethods=dns-01')
        with _patch({'example.com': [rec]}):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True

    def test_validationmethods_with_wrong_method_denies(self):
        rec = _FakeCAA('issue', 'ucm.example.com; validationmethods=dns-01')
        with _patch({'example.com': [rec]}):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'],
                              validation_method='http-01')
        assert ok is False

    def test_alternate_matching_record_can_authorize(self):
        zones = {'example.com': [
            _FakeCAA(
                'issue',
                'ucm.example.com; accounturi=https://ca.example/acme/acct/other',
            ),
            _FakeCAA('issue', 'ucm.example.com'),
        ]}
        with _patch(zones):
            ok, _ = check_caa(
                'www.example.com',
                ['ucm.example.com'],
                account_url='https://ca.example/acme/acct/account-1',
            )
        assert ok is True

    def test_empty_issue_denies_all(self):
        with _patch({'example.com': [_FakeCAA('issue', '')]}):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is False
        assert 'denies all' in reason

    def test_record_without_issue_tags_allows(self, caplog):
        # Only an iodef tag present → no issue restriction
        caplog.set_level('INFO', logger='utils.caa_checker')
        with _patch({'example.com': [_FakeCAA('iodef', 'mailto:x@example.com')]}):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True
        assert 'no issue tags' in reason
        assert 'mailto:x@example.com' in caplog.text


class TestCriticalFlag:
    def test_unknown_critical_property_denies(self):
        zones = {'example.com': [
            _FakeCAA('future-property', 'value', flags=128),
            _FakeCAA('issue', 'ucm.example.com'),
        ]}
        with _patch(zones):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is False
        assert 'critical' in reason.lower()
        assert 'future-property' in reason

    def test_unknown_noncritical_property_is_ignored(self):
        zones = {'example.com': [
            _FakeCAA('future-property', 'value', flags=0),
            _FakeCAA('issue', 'ucm.example.com'),
        ]}
        with _patch(zones):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True


class TestTreeClimb:
    def test_child_record_takes_precedence_over_parent(self):
        # RFC 6844: first CAA set found while climbing wins; parent not consulted
        zones = {
            'www.example.com': [_FakeCAA('issue', 'ucm.example.com')],
            'example.com': [_FakeCAA('issue', 'letsencrypt.org')],
        }
        with _patch(zones):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True

    def test_parent_record_used_when_child_absent(self):
        with _patch({'example.com': [_FakeCAA('issue', 'letsencrypt.org')]}):
            ok, reason = check_caa('deep.sub.example.com', ['ucm.example.com'])
        assert ok is False
        assert 'example.com' in reason

    def test_tld_is_not_queried(self):
        seen = []

        def _resolve(name, rdtype):
            seen.append(str(name).rstrip('.'))
            raise dns.resolver.NXDOMAIN()

        with patch('dns.resolver.resolve', side_effect=_resolve):
            check_caa('www.example.com', ['ucm.example.com'])
        assert 'com' not in seen
        assert 'example.com' in seen
        assert 'www.example.com' in seen


class TestWildcard:
    def test_wildcard_prefix_stripped_for_lookup(self):
        seen = []

        def _resolve(name, rdtype):
            seen.append(str(name).rstrip('.'))
            raise dns.resolver.NXDOMAIN()

        with patch('dns.resolver.resolve', side_effect=_resolve):
            check_caa('*.example.com', ['ucm.example.com'])
        # The literal "*.example.com" must never be queried
        assert not any(s.startswith('*') for s in seen)
        assert 'example.com' in seen

    def test_issuewild_governs_wildcard_issuance(self):
        zones = {'example.com': [
            _FakeCAA('issue', 'letsencrypt.org'),
            _FakeCAA('issuewild', 'ucm.example.com'),
        ]}
        with _patch(zones):
            ok, _ = check_caa('*.example.com', ['ucm.example.com'])
        assert ok is True

    def test_issuewild_denies_when_only_issue_matches(self):
        zones = {'example.com': [
            _FakeCAA('issue', 'ucm.example.com'),
            _FakeCAA('issuewild', 'letsencrypt.org'),
        ]}
        with _patch(zones):
            ok, _ = check_caa('*.example.com', ['ucm.example.com'])
        assert ok is False

    def test_wildcard_falls_back_to_issue_when_no_issuewild(self):
        zones = {'example.com': [_FakeCAA('issue', 'ucm.example.com')]}
        with _patch(zones):
            ok, _ = check_caa('*.example.com', ['ucm.example.com'])
        assert ok is True


class TestIssuanceContext:
    def test_account_url_and_per_authorization_method(self):
        from services.acme.mixins.issuance import IssuanceMixin

        authorization = SimpleNamespace(
            identifier_obj={'type': 'dns', 'value': 'www.example.com'},
            wildcard=False,
            challenges=[
                SimpleNamespace(type='dns-01', status='pending'),
                SimpleNamespace(type='http-01', status='valid'),
            ],
        )
        order = SimpleNamespace(
            account_id='account-1',
            authorizations=[authorization],
        )
        mixin = IssuanceMixin()
        mixin.base_url = 'https://ca.example'

        account_url, methods = mixin._caa_request_context(order)

        assert account_url == 'https://ca.example/acme/acct/account-1'
        assert methods == {'www.example.com': 'http-01'}

    def test_ambiguous_valid_methods_fail_closed(self):
        from services.acme.mixins.issuance import IssuanceMixin

        authorization = SimpleNamespace(
            identifier_obj={'type': 'dns', 'value': 'example.com'},
            wildcard=True,
            challenges=[
                SimpleNamespace(type='dns-01', status='valid'),
                SimpleNamespace(type='http-01', status='valid'),
            ],
        )
        order = SimpleNamespace(
            account_id='account-1',
            authorizations=[authorization],
        )
        mixin = IssuanceMixin()
        mixin.base_url = 'https://ca.example'

        _, methods = mixin._caa_request_context(order)

        assert methods == {'*.example.com': None}


class TestMultipleDomains:
    def test_all_must_pass(self):
        zones = {
            'a.example.com': [_FakeCAA('issue', 'ucm.example.com')],
            'b.example.com': [_FakeCAA('issue', 'letsencrypt.org')],
        }
        with _patch(zones):
            ok, reason = check_caa_for_domains(
                ['a.example.com', 'b.example.com'], ['ucm.example.com'])
        assert ok is False
        assert 'b.example.com' in reason

    def test_all_pass(self):
        zones = {
            'a.example.com': [_FakeCAA('issue', 'ucm.example.com')],
            'b.example.com': [_FakeCAA('issue', 'ucm.example.com')],
        }
        with _patch(zones):
            ok, _ = check_caa_for_domains(
                ['a.example.com', 'b.example.com'], ['ucm.example.com'])
        assert ok is True

    def test_per_domain_validation_methods_are_forwarded(self):
        zones = {
            'a.example.com': [
                _FakeCAA('issue', 'ucm.example.com; validationmethods=dns-01')
            ],
            'b.example.com': [
                _FakeCAA('issue', 'ucm.example.com; validationmethods=http-01')
            ],
        }
        methods = {
            'a.example.com': 'dns-01',
            'b.example.com': 'http-01',
        }
        with _patch(zones):
            ok, _ = check_caa_for_domains(
                ['a.example.com', 'b.example.com'],
                ['ucm.example.com'],
                account_url='https://ca.example/acme/acct/account-1',
                validation_methods=methods,
            )
        assert ok is True

    def test_empty_issuer_list_denies_when_any_issue_tag_present(self):
        with _patch({'example.com': [_FakeCAA('issue', 'letsencrypt.org')]}):
            ok, _ = check_caa('www.example.com', None)
        assert ok is False
