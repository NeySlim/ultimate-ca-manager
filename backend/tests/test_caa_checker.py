"""Tests for utils.caa_checker (RFC 6844 / RFC 8659 CAA enforcement).

DNS is fully mocked — no network. Each test sets up which CAA rdata each
zone returns as we walk up the domain tree.
"""

from __future__ import annotations

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

    def test_dns_error_treated_as_no_record(self):
        with patch('dns.resolver.resolve',
                   side_effect=dns.exception.Timeout()):
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

    def test_issue_parameters_are_stripped(self):
        # "issue" value may carry ;accounturi=... parameters (RFC 8657)
        rec = _FakeCAA('issue', 'ucm.example.com; accounturi=https://a/1')
        with _patch({'example.com': [rec]}):
            ok, _ = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True

    def test_empty_issue_denies_all(self):
        with _patch({'example.com': [_FakeCAA('issue', '')]}):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is False
        assert 'denies all' in reason

    def test_record_without_issue_tags_allows(self):
        # Only an iodef tag present → no issue restriction
        with _patch({'example.com': [_FakeCAA('iodef', 'mailto:x@example.com')]}):
            ok, reason = check_caa('www.example.com', ['ucm.example.com'])
        assert ok is True
        assert 'no issue tags' in reason


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

    def test_empty_issuer_list_denies_when_any_issue_tag_present(self):
        with _patch({'example.com': [_FakeCAA('issue', 'letsencrypt.org')]}):
            ok, _ = check_caa('www.example.com', None)
        assert ok is False
