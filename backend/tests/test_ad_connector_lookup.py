"""
Tests for services/ad_connector/lookup.py:

- parse_kerberos_principal / is_machine_principal: pure string parsing,
  no I/O.
- lookup_computer_dns_hostname: every failure mode (not configured, bind
  failure, not found, empty attribute) must return None, never raise --
  the WSTEP naked-CSR fallback depends on that to fail safely closed
  (falling back to the existing rejection, never issuing something wrong).
- _sid_bytes_to_string / lookup_object_sid: same fail-closed shape, for
  KB5014754 strong certificate mapping. The golden case uses a REAL SID
  captured this session from the lab, not a synthetic example.
"""
import pytest

from models import db, ADConnectorConfig
from services.ad_connector import lookup


class TestParseKerberosPrincipal:
    def test_machine_principal(self):
        assert lookup.parse_kerberos_principal('WIN11$@HAGLAND.DOMAIN') == ('WIN11$', 'HAGLAND.DOMAIN')

    def test_user_principal(self):
        assert lookup.parse_kerberos_principal('alice@HAGLAND.DOMAIN') == ('alice', 'HAGLAND.DOMAIN')

    def test_no_at_sign(self):
        assert lookup.parse_kerberos_principal('WIN11$') is None

    def test_empty_local_part(self):
        assert lookup.parse_kerberos_principal('@HAGLAND.DOMAIN') is None

    def test_empty_realm(self):
        assert lookup.parse_kerberos_principal('WIN11$@') is None

    def test_empty_string(self):
        assert lookup.parse_kerberos_principal('') is None

    def test_none(self):
        assert lookup.parse_kerberos_principal(None) is None


class TestIsMachinePrincipal:
    def test_machine_principal(self):
        assert lookup.is_machine_principal('WIN11$@HAGLAND.DOMAIN') is True

    def test_user_principal(self):
        assert lookup.is_machine_principal('alice@HAGLAND.DOMAIN') is False

    def test_malformed_no_at(self):
        assert lookup.is_machine_principal('WIN11$') is False

    def test_empty_string(self):
        assert lookup.is_machine_principal('') is False

    def test_none(self):
        assert lookup.is_machine_principal(None) is False


class TestRealmMatchesConnector:
    def test_matches(self, app, monkeypatch):
        _configure(monkeypatch, app)
        with app.app_context():
            assert lookup.realm_matches_connector('HAGLAND.DOMAIN') is True

    def test_case_insensitive(self, app, monkeypatch):
        _configure(monkeypatch, app)
        with app.app_context():
            assert lookup.realm_matches_connector('hagland.domain') is True

    def test_different_realm_rejected(self, app, monkeypatch):
        """A ticket from a trusted-but-different realm must not be treated
        as though it named an account in *this* domain -- sAMAccountName
        alone isn't globally unique the way a realm-qualified principal
        is."""
        _configure(monkeypatch, app)
        with app.app_context():
            assert lookup.realm_matches_connector('OTHER.DOMAIN') is False

    def test_connector_not_configured(self, app):
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
            assert lookup.realm_matches_connector('HAGLAND.DOMAIN') is False

    def test_connector_disabled(self, app, monkeypatch):
        _configure(monkeypatch, app, enabled=False)
        with app.app_context():
            assert lookup.realm_matches_connector('HAGLAND.DOMAIN') is False

    def test_empty_realm(self, app, monkeypatch):
        _configure(monkeypatch, app)
        with app.app_context():
            assert lookup.realm_matches_connector('') is False
            assert lookup.realm_matches_connector(None) is False

    def test_malformed_base_dn_fails_closed(self, app):
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(
                server='dc1.hagland.domain', base_dn='not a dn',
                bind_dn='svc-ucm', enabled=True,
            )
            config.bind_password = 'irrelevant'
            db.session.add(config)
            db.session.commit()
            assert lookup.realm_matches_connector('HAGLAND.DOMAIN') is False


class _FakeAttr:
    def __init__(self, value, raw_values=None):
        self.value = value
        self.raw_values = raw_values if raw_values is not None else ([value] if value else [])


class _FakeEntry:
    def __init__(self, attrs):
        self._attrs = attrs
        for key, value in attrs.items():
            setattr(self, key, _FakeAttr(value))

    def __contains__(self, key):
        return key in self._attrs


class _FakeConnection:
    def __init__(self, entries=None, search_raises=None):
        self.entries = entries or []
        self._search_raises = search_raises
        self.unbound = False

    def search(self, base_dn, filter_str, attributes=None):
        if self._search_raises:
            raise self._search_raises

    def unbind(self):
        self.unbound = True


def _configure(monkeypatch, app, enabled=True):
    with app.app_context():
        ADConnectorConfig.query.delete()
        config = ADConnectorConfig(
            server='dc1.hagland.domain', base_dn='DC=hagland,DC=domain',
            bind_dn='svc-ucm', enabled=enabled,
        )
        config.bind_password = 'irrelevant'
        db.session.add(config)
        db.session.commit()


class TestLookupComputerDnsHostname:
    def test_not_configured_returns_none(self, app):
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
            assert lookup.lookup_computer_dns_hostname('WIN11$') is None

    def test_disabled_returns_none(self, app):
        _configure(None, app, enabled=False)
        with app.app_context():
            assert lookup.lookup_computer_dns_hostname('WIN11$') is None

    def test_bind_failure_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(RuntimeError('bind failed')))
        with app.app_context():
            assert lookup.lookup_computer_dns_hostname('WIN11$') is None

    def test_computer_not_found_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[]))
        with app.app_context():
            assert lookup.lookup_computer_dns_hostname('WIN11$') is None

    def test_empty_attribute_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        entry = _FakeEntry({'dNSHostName': ''})
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[entry]))
        with app.app_context():
            assert lookup.lookup_computer_dns_hostname('WIN11$') is None

    def test_missing_attribute_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        entry = _FakeEntry({})
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[entry]))
        with app.app_context():
            assert lookup.lookup_computer_dns_hostname('WIN11$') is None

    def test_search_exception_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(
            lookup, '_connect',
            lambda config: _FakeConnection(search_raises=RuntimeError('search failed')),
        )
        with app.app_context():
            assert lookup.lookup_computer_dns_hostname('WIN11$') is None

    def test_success_returns_dns_hostname(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        entry = _FakeEntry({'dNSHostName': 'win11.hagland.domain'})
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[entry]))
        with app.app_context():
            assert lookup.lookup_computer_dns_hostname('WIN11$') == 'win11.hagland.domain'


class TestSidBytesToString:
    """Pure-function coverage of _sid_bytes_to_string -- no DB/Flask app
    needed. The golden case is a REAL SID captured this session via a live
    LDAP query against the lab's WIN11$ machine account (raw_values), not
    a synthetic example -- cross-validated against a real ADCS-issued
    certificate's own SID security extension sharing the same domain-SID
    prefix (see test_ad_security_extension.py)."""

    _WIN11_RAW_SID = bytes([
        0x01, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05,
        0x15, 0x00, 0x00, 0x00,
        0xd1, 0xba, 0xd9, 0x5f,
        0x3d, 0xff, 0x98, 0x25,
        0x71, 0x1a, 0xd2, 0x57,
        0x51, 0x04, 0x00, 0x00,
    ])

    def test_real_captured_sid(self):
        assert lookup._sid_bytes_to_string(self._WIN11_RAW_SID) == \
            'S-1-5-21-1608104657-630783805-1473387121-1105'

    def test_empty_bytes_returns_none(self):
        assert lookup._sid_bytes_to_string(b'') is None

    def test_none_returns_none(self):
        assert lookup._sid_bytes_to_string(None) is None

    def test_too_short_returns_none(self):
        assert lookup._sid_bytes_to_string(b'short') is None

    def test_length_mismatch_for_declared_sub_authority_count_returns_none(self):
        """byte[1] claims 5 sub-authorities but only 4 are present --
        malformed/truncated directory data must fail closed, not parse
        partial garbage."""
        truncated = self._WIN11_RAW_SID[:-4]
        assert lookup._sid_bytes_to_string(truncated) is None


class TestLookupObjectSid:
    """Mirrors TestLookupComputerDnsHostname's exact fail-closed shape --
    every failure mode returns None, never raises."""

    def test_not_configured_returns_none(self, app):
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
            assert lookup.lookup_object_sid('WIN11$') is None

    def test_disabled_returns_none(self, app):
        _configure(None, app, enabled=False)
        with app.app_context():
            assert lookup.lookup_object_sid('WIN11$') is None

    def test_bind_failure_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(RuntimeError('bind failed')))
        with app.app_context():
            assert lookup.lookup_object_sid('WIN11$') is None

    def test_not_found_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[]))
        with app.app_context():
            assert lookup.lookup_object_sid('WIN11$') is None

    def test_missing_attribute_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        entry = _FakeEntry({})
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[entry]))
        with app.app_context():
            assert lookup.lookup_object_sid('WIN11$') is None

    def test_empty_raw_values_returns_none(self, app, monkeypatch):
        # _FakeEntry wraps every dict value in _FakeAttr itself (see its
        # __init__) -- passing b'' here (not an already-built _FakeAttr)
        # lets _FakeAttr's own default (raw_values=[value] if value else
        # []) produce a genuinely empty raw_values list, matching what a
        # real empty/missing objectSid attribute would look like.
        _configure(None, app, enabled=True)
        entry = _FakeEntry({'objectSid': b''})
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[entry]))
        with app.app_context():
            assert lookup.lookup_object_sid('WIN11$') is None

    def test_search_exception_returns_none(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(
            lookup, '_connect',
            lambda config: _FakeConnection(search_raises=RuntimeError('search failed')),
        )
        with app.app_context():
            assert lookup.lookup_object_sid('WIN11$') is None

    def test_success_returns_sid_string(self, app, monkeypatch):
        """Reads raw_values (the real binary SID), not .value -- ldap3
        does not auto-format objectSid (confirmed empirically against the
        lab), so .value would give mangled bytes-as-string garbage."""
        _configure(None, app, enabled=True)
        raw_sid = TestSidBytesToString._WIN11_RAW_SID
        # Passing the raw bytes directly (not a pre-built _FakeAttr) --
        # _FakeEntry wraps it in _FakeAttr(raw_sid) itself, whose default
        # raw_values=[raw_sid] matches what ldap3's real raw_values gives.
        entry = _FakeEntry({'objectSid': raw_sid})
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeConnection(entries=[entry]))
        with app.app_context():
            assert lookup.lookup_object_sid('WIN11$') == 'S-1-5-21-1608104657-630783805-1473387121-1105'


class _FakeSequentialConnection:
    """Like ``_FakeConnection`` but returns a different ``entries`` list on
    each successive ``search()`` call -- needed for ``is_member_of_group``,
    which searches once to resolve a plain group name to a DN and again to
    check membership.
    """
    def __init__(self, entries_sequence):
        self._entries_sequence = list(entries_sequence)
        self.entries = []
        self.unbound = False

    def search(self, base_dn, filter_str, attributes=None):
        self.entries = self._entries_sequence.pop(0) if self._entries_sequence else []

    def unbind(self):
        self.unbound = True


class TestIsMemberOfGroup:
    def test_not_configured_returns_false(self, app):
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
            assert lookup.is_member_of_group('alice', 'VPN-Enroll') is False

    def test_disabled_returns_false(self, app):
        _configure(None, app, enabled=False)
        with app.app_context():
            assert lookup.is_member_of_group('alice', 'VPN-Enroll') is False

    def test_empty_sam_account_name_returns_false(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        with app.app_context():
            assert lookup.is_member_of_group('', 'VPN-Enroll') is False
            assert lookup.is_member_of_group(None, 'VPN-Enroll') is False

    def test_empty_group_returns_false(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        with app.app_context():
            assert lookup.is_member_of_group('alice', '') is False
            assert lookup.is_member_of_group('alice', None) is False

    def test_bind_failure_returns_false(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(RuntimeError('bind failed')))
        with app.app_context():
            assert lookup.is_member_of_group('alice', 'VPN-Enroll') is False

    def test_group_name_not_found_returns_false(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(lookup, '_connect', lambda config: _FakeSequentialConnection([[]]))
        with app.app_context():
            assert lookup.is_member_of_group('alice', 'VPN-Enroll') is False

    def test_member_by_group_name(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        group_entry = _FakeEntry({})
        group_entry.entry_dn = 'CN=VPN-Enroll,OU=Groups,DC=hagland,DC=domain'
        member_entry = _FakeEntry({'sAMAccountName': 'alice'})
        monkeypatch.setattr(
            lookup, '_connect',
            lambda config: _FakeSequentialConnection([[group_entry], [member_entry]]),
        )
        with app.app_context():
            assert lookup.is_member_of_group('alice', 'VPN-Enroll') is True

    def test_not_member_by_group_name(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        group_entry = _FakeEntry({})
        group_entry.entry_dn = 'CN=VPN-Enroll,OU=Groups,DC=hagland,DC=domain'
        monkeypatch.setattr(
            lookup, '_connect',
            lambda config: _FakeSequentialConnection([[group_entry], []]),
        )
        with app.app_context():
            assert lookup.is_member_of_group('alice', 'VPN-Enroll') is False

    def test_member_by_group_dn_skips_resolution_search(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        member_entry = _FakeEntry({'sAMAccountName': 'alice'})
        monkeypatch.setattr(
            lookup, '_connect',
            lambda config: _FakeSequentialConnection([[member_entry]]),
        )
        with app.app_context():
            assert lookup.is_member_of_group(
                'alice', 'CN=VPN-Enroll,OU=Groups,DC=hagland,DC=domain'
            ) is True

    def test_search_exception_returns_false(self, app, monkeypatch):
        _configure(None, app, enabled=True)
        monkeypatch.setattr(
            lookup, '_connect',
            lambda config: _FakeConnection(search_raises=RuntimeError('search failed')),
        )
        with app.app_context():
            assert lookup.is_member_of_group('alice', 'VPN-Enroll') is False

    def test_machine_principal_sam_account_name(self, app, monkeypatch):
        """A trailing '$' on a machine account's sAMAccountName is passed
        through unchanged -- it's a real part of the value, not stripped."""
        _configure(None, app, enabled=True)
        group_entry = _FakeEntry({})
        group_entry.entry_dn = 'CN=Enroll-Machines,OU=Groups,DC=hagland,DC=domain'
        member_entry = _FakeEntry({'sAMAccountName': 'WIN11$'})
        monkeypatch.setattr(
            lookup, '_connect',
            lambda config: _FakeSequentialConnection([[group_entry], [member_entry]]),
        )
        with app.app_context():
            assert lookup.is_member_of_group('WIN11$', 'Enroll-Machines') is True


class TestSplitServers:
    """The one field now names every DC to fail over between. The bare
    domain name that used to be the natural thing to type is exactly what
    breaks LDAPS on a multi-DC domain (each DC's certificate carries only
    its own FQDN), so the list has to survive round-tripping intact."""

    def test_single_hostname(self):
        assert lookup.split_servers('dc1.corp.local') == ['dc1.corp.local']

    def test_list_input(self):
        assert lookup.split_servers(['dc1.corp.local', 'dc2.corp.local']) == \
            ['dc1.corp.local', 'dc2.corp.local']

    def test_newline_separated_is_what_the_column_stores(self):
        assert lookup.split_servers('dc1.corp.local\ndc2.corp.local') == \
            ['dc1.corp.local', 'dc2.corp.local']

    def test_comma_separated_with_whitespace(self):
        assert lookup.split_servers(' dc1.corp.local ,dc2.corp.local ') == \
            ['dc1.corp.local', 'dc2.corp.local']

    def test_blank_rows_are_dropped(self):
        assert lookup.split_servers(['dc1.corp.local', '', '  ', None]) == ['dc1.corp.local']

    def test_a_pasted_row_is_split_like_the_old_single_field(self):
        """Storing a comma-joined row whole would read back as two servers
        the next time, so the inline test's key (the joined string) and the
        probe's (each host) would disagree, and re-saving the same form
        would look like a change and clear health."""
        assert lookup.split_servers(['dc1.corp.local,dc2.corp.local']) == \
            ['dc1.corp.local', 'dc2.corp.local']
        assert lookup.split_servers(['dc1.corp.local\ndc2.corp.local', 'dc3.corp.local']) == \
            ['dc1.corp.local', 'dc2.corp.local', 'dc3.corp.local']

    def test_a_row_that_is_not_a_string_is_skipped_not_raised(self):
        """Read on the enrollment path and off a column that could have been
        hand-edited: it must degrade to "no DCs", never raise."""
        assert lookup.split_servers([123, 'dc1.corp.local']) == ['dc1.corp.local']
        assert lookup.split_servers(5) == []
        assert lookup.split_servers({'a': 1}) == []

    def test_duplicates_collapse_keeping_first_position(self):
        assert lookup.split_servers(['dc2.corp.local', 'dc1.corp.local', 'dc2.corp.local']) == \
            ['dc2.corp.local', 'dc1.corp.local']

    def test_empty_and_none(self):
        assert lookup.split_servers('') == []
        assert lookup.split_servers(None) == []
        assert lookup.split_servers([]) == []

    def test_round_trips_through_join(self):
        servers = ['dc1.corp.local', 'dc2.corp.local', 'dc3.corp.local']
        assert lookup.split_servers(lookup.join_servers(servers)) == servers


class _RecordingConnector:
    """Stands in for ``_connect_to``, recording every host tried and
    failing the ones named in ``fail``."""

    def __init__(self, fail=()):
        self.fail = dict(fail) if isinstance(fail, dict) else {h: 'refused' for h in fail}
        self.attempted = []

    def __call__(self, config, host, tls):
        self.attempted.append(host)
        if host in self.fail:
            raise RuntimeError(self.fail[host])
        return _FakeConnection()


class TestConnectFailover:
    def _config(self, server):
        from types import SimpleNamespace
        return SimpleNamespace(
            server=server, port=636, use_ssl=True, verify_ssl=True,
            ca_bundle=None, bind_dn='svc-ucm', bind_password='irrelevant',
        )

    def test_first_server_wins_and_the_rest_are_left_alone(self, monkeypatch):
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        conn = lookup._connect(self._config(['dc1.corp.local', 'dc2.corp.local']))
        assert isinstance(conn, _FakeConnection)
        assert connector.attempted == ['dc1.corp.local']

    def test_falls_over_to_the_next_server(self, monkeypatch):
        connector = _RecordingConnector(fail=['dc1.corp.local'])
        monkeypatch.setattr(lookup, '_connect_to', connector)
        conn = lookup._connect(self._config(['dc1.corp.local', 'dc2.corp.local']))
        assert isinstance(conn, _FakeConnection)
        assert connector.attempted == ['dc1.corp.local', 'dc2.corp.local']

    def test_every_server_failing_names_each_one(self, monkeypatch):
        connector = _RecordingConnector(fail={
            'dc1.corp.local': 'certificate SAN mismatch',
            'dc2.corp.local': 'connection refused',
        })
        monkeypatch.setattr(lookup, '_connect_to', connector)
        with pytest.raises(lookup.ADConnectorConnectionError) as excinfo:
            lookup._connect(self._config(['dc1.corp.local', 'dc2.corp.local']))
        message = str(excinfo.value)
        assert 'dc1.corp.local: certificate SAN mismatch' in message
        assert 'dc2.corp.local: connection refused' in message

    def test_no_server_configured_raises(self, monkeypatch):
        monkeypatch.setattr(lookup, '_connect_to', _RecordingConnector())
        with pytest.raises(ValueError):
            lookup._connect(self._config(''))

    def test_ca_bundle_survives_every_attempt(self, monkeypatch):
        """The temp CA file used to be unlinked the moment the connection
        call returned. With failover there are several attempts, and each
        later one has to still find the bundle on disk."""
        import os

        seen = []

        def _spy(config, host, tls):
            seen.append((host, os.path.exists(tls.ca_certs_file)))
            raise RuntimeError('refused')

        monkeypatch.setattr(lookup, '_connect_to', _spy)
        config = self._config(['dc1.corp.local', 'dc2.corp.local'])
        config.ca_bundle = '-----BEGIN CERTIFICATE-----\nnot-a-real-cert\n-----END CERTIFICATE-----'
        with pytest.raises(lookup.ADConnectorConnectionError):
            lookup._connect(config)
        assert seen == [('dc1.corp.local', True), ('dc2.corp.local', True)]

    def test_ca_bundle_is_removed_afterwards(self, monkeypatch):
        captured = {}

        def _spy(config, host, tls):
            captured['path'] = tls.ca_certs_file
            return _FakeConnection()

        monkeypatch.setattr(lookup, '_connect_to', _spy)
        config = self._config(['dc1.corp.local'])
        config.ca_bundle = '-----BEGIN CERTIFICATE-----\nnot-a-real-cert\n-----END CERTIFICATE-----'
        lookup._connect(config)
        import os
        assert not os.path.exists(captured['path'])


class TestAnonymousBindIsRefusedEverywhere:
    """One rule, applied at every point that binds.

    The API refuses to save an enabled connector without both halves of the
    credential, but rows saved before that rule existed still have none, and
    ldap3 binds anonymously whenever either half is missing. So the bind
    paths refuse it themselves rather than trusting the save to have.
    """

    @staticmethod
    def _config(**overrides):
        from types import SimpleNamespace
        fields = dict(
            server=['dc1.corp.local'], port=636, use_ssl=True, verify_ssl=True,
            ca_bundle=None, bind_dn='svc-ucm', bind_password='irrelevant',
        )
        fields.update(overrides)
        return SimpleNamespace(**fields)

    @pytest.mark.parametrize('missing', ['bind_dn', 'bind_password'])
    def test_connect_refuses_before_reaching_a_dc(self, monkeypatch, missing):
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        with pytest.raises(ValueError) as excinfo:
            lookup._connect(self._config(**{missing: None}))
        assert 'anonymous bind' in str(excinfo.value)
        # Refused, not attempted and failed: no DC was contacted at all.
        assert connector.attempted == []

    @pytest.mark.parametrize('missing', ['bind_dn', 'bind_password'])
    def test_test_connection_refuses_without_binding(self, monkeypatch, missing):
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        result = lookup.test_connection(self._config(**{missing: None}))
        assert result['success'] is False
        assert result['servers'] == []
        assert connector.attempted == []

    @pytest.mark.parametrize('missing', ['bind_dn', 'bind_password'])
    def test_probe_refuses_without_binding(self, monkeypatch, missing):
        from services.ad_connector import health as h
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        # None, not []: "no DC was reached", which the caller must not
        # record as a verdict.
        assert h.probe(self._config(**{missing: None})) is None
        assert connector.attempted == []

    def test_a_full_credential_still_binds(self, monkeypatch):
        """The guard refuses the missing half, not every bind."""
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        assert lookup._connect(self._config()) is not None
        assert connector.attempted == ['dc1.corp.local']


class TestProbeNeverRaises:
    """probe() runs on the scheduler's thread. Anything escaping it is a
    failed run on every wake, whatever the probe interval says."""

    def test_a_tls_build_that_raises_is_not_an_exception(self, monkeypatch):
        from types import SimpleNamespace
        from services.ad_connector import health as h

        def _explode(config):
            raise OSError('no space left on device')

        monkeypatch.setattr(lookup, '_build_tls', _explode)
        config = SimpleNamespace(
            server=['dc1.corp.local'], port=636, use_ssl=True, verify_ssl=True,
            ca_bundle='-----BEGIN CERTIFICATE-----', bind_dn='svc-ucm',
            bind_password='irrelevant',
        )
        # None rather than [], which record() would turn into a verdict.
        assert h.probe(config) is None


class TestTestConnection:
    """Every DC is probed, not just enough of them to reach a verdict: a
    second DC that is down stays invisible until the first one fails in
    production otherwise."""

    def _config(self, server):
        from types import SimpleNamespace
        return SimpleNamespace(
            server=server, port=636, use_ssl=True, verify_ssl=True,
            ca_bundle=None, bind_dn='svc-ucm', bind_password='irrelevant',
        )

    def test_no_server(self):
        result = lookup.test_connection(self._config(''))
        assert result['success'] is False
        assert result['servers'] == []

    def test_single_server_success(self, monkeypatch):
        monkeypatch.setattr(lookup, '_connect_to', _RecordingConnector())
        result = lookup.test_connection(self._config(['dc1.corp.local']))
        assert result['success'] is True
        assert result['partial'] is False
        assert result['message'] == 'Connected and bound successfully'
        assert [r['server'] for r in result['servers']] == ['dc1.corp.local']

    def test_all_servers_probed_even_after_one_succeeds(self, monkeypatch):
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        result = lookup.test_connection(self._config(['dc1.corp.local', 'dc2.corp.local']))
        assert connector.attempted == ['dc1.corp.local', 'dc2.corp.local']
        assert result['success'] is True
        assert result['partial'] is False
        assert all(r['success'] for r in result['servers'])

    def test_partial_failure_is_flagged_not_reported_as_clean(self, monkeypatch):
        connector = _RecordingConnector(fail={'dc2.corp.local': 'certificate SAN mismatch'})
        monkeypatch.setattr(lookup, '_connect_to', connector)
        result = lookup.test_connection(self._config(['dc1.corp.local', 'dc2.corp.local']))
        assert result['success'] is True
        assert result['partial'] is True
        assert 'certificate SAN mismatch' in result['message']
        by_host = {r['server']: r for r in result['servers']}
        assert by_host['dc1.corp.local']['success'] is True
        assert by_host['dc2.corp.local']['success'] is False
        assert by_host['dc2.corp.local']['message'] == 'certificate SAN mismatch'

    def test_total_failure(self, monkeypatch):
        connector = _RecordingConnector(fail={
            'dc1.corp.local': 'certificate SAN mismatch',
            'dc2.corp.local': 'connection refused',
        })
        monkeypatch.setattr(lookup, '_connect_to', connector)
        result = lookup.test_connection(self._config(['dc1.corp.local', 'dc2.corp.local']))
        assert result['success'] is False
        assert result['partial'] is False
        assert result['message'].startswith('Connection failed: ')
        assert 'dc1.corp.local: certificate SAN mismatch' in result['message']
        assert 'dc2.corp.local: connection refused' in result['message']

    def test_connections_are_unbound(self, monkeypatch):
        opened = []

        def _spy(config, host, tls):
            conn = _FakeConnection()
            opened.append(conn)
            return conn

        monkeypatch.setattr(lookup, '_connect_to', _spy)
        lookup.test_connection(self._config(['dc1.corp.local', 'dc2.corp.local']))
        assert len(opened) == 2
        assert all(c.unbound for c in opened)


class TestServersProperty:
    def test_single_hostname_config_reads_as_one_element(self, app):
        """A config saved before this field accepted more than one DC holds
        a bare hostname and must keep working untouched."""
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.commit()
            config = ADConnectorConfig(server='dc1.hagland.domain')
            assert config.servers == ['dc1.hagland.domain']

    def test_setter_round_trips(self, app):
        with app.app_context():
            config = ADConnectorConfig()
            config.servers = ['dc1.corp.local', 'dc2.corp.local']
            assert config.servers == ['dc1.corp.local', 'dc2.corp.local']
            assert config.to_dict()['servers'] == ['dc1.corp.local', 'dc2.corp.local']

    def test_setter_clears_to_none(self, app):
        with app.app_context():
            config = ADConnectorConfig(server='dc1.corp.local')
            config.servers = []
            assert config.server is None
            assert config.servers == []


class TestHealthState:
    """The probe's verdict is advisory: it may reorder and thin the DC list
    that _connect walks, never empty it, and it expires. A stale or wrong
    verdict must degrade to "no opinion", not to a refused enrollment."""

    @staticmethod
    def _blob(servers, state='degraded', age_seconds=0):
        from datetime import timedelta
        from services.ad_connector import health as h
        from utils.datetime_utils import utc_now, utc_isoformat
        checked = utc_isoformat(utc_now() - timedelta(seconds=age_seconds))
        return {
            'state': state,
            'checked_at': checked,
            'servers': {
                host: {'healthy': ok, 'message': '', 'checked_at': checked, 'since': checked}
                for host, ok in servers.items()
            },
        }

    def test_unhealthy_server_is_dropped(self):
        from services.ad_connector import health as h
        blob = self._blob({'dc1.corp.local': False, 'dc2.corp.local': True})
        assert h.prioritise(['dc1.corp.local', 'dc2.corp.local'], blob) == ['dc2.corp.local']

    def test_healthy_server_is_promoted_ahead_of_unknown(self):
        from services.ad_connector import health as h
        blob = self._blob({'dc2.corp.local': True})
        assert h.prioritise(['dc1.corp.local', 'dc2.corp.local'], blob) == \
            ['dc2.corp.local', 'dc1.corp.local']

    def test_never_returns_empty_when_everything_is_down(self):
        """Trusting an all-down verdict would turn a UCM-side probe failure
        into a total enrollment outage. The bind gets to decide instead."""
        from services.ad_connector import health as h
        blob = self._blob({'dc1.corp.local': False, 'dc2.corp.local': False}, state='down')
        assert h.prioritise(['dc1.corp.local', 'dc2.corp.local'], blob) == \
            ['dc1.corp.local', 'dc2.corp.local']

    def test_stale_verdict_is_ignored(self):
        from services.ad_connector import health as h
        blob = self._blob({'dc1.corp.local': False}, age_seconds=h._HEALTH_STALE_FLOOR_SECONDS + 60)
        assert h.prioritise(['dc1.corp.local', 'dc2.corp.local'], blob) == \
            ['dc1.corp.local', 'dc2.corp.local']

    def test_the_window_follows_the_probe_interval(self):
        """A fixed window would expire every verdict long before the next
        probe on any interval above it, so _connect would be permanently
        without an opinion exactly where a slow probe needs one."""
        from services.ad_connector import health as h
        blob = self._blob({'dc1.corp.local': False}, age_seconds=3600)
        assert h.prioritise(['dc1.corp.local', 'dc2.corp.local'], blob) == \
            ['dc1.corp.local', 'dc2.corp.local']
        assert h.prioritise(['dc1.corp.local', 'dc2.corp.local'], blob, 7200) == \
            ['dc2.corp.local']

    def test_the_window_never_falls_below_the_floor(self):
        from services.ad_connector import health as h
        assert h.stale_after(60) == h._HEALTH_STALE_FLOOR_SECONDS
        assert h.stale_after(None) == h._HEALTH_STALE_FLOOR_SECONDS
        assert h.stale_after('nonsense') == h._HEALTH_STALE_FLOOR_SECONDS
        assert h.stale_after(h.MAX_PROBE_INTERVAL_SECONDS) == 2 * h.MAX_PROBE_INTERVAL_SECONDS

    def test_no_health_at_all_is_a_passthrough(self):
        from services.ad_connector import health as h
        assert h.prioritise(['dc1.corp.local'], None) == ['dc1.corp.local']
        assert h.prioritise(['dc1.corp.local'], {}) == ['dc1.corp.local']

    def test_corrupt_json_degrades_to_no_opinion(self):
        from services.ad_connector import health as h
        assert h.prioritise(['dc1.corp.local'], 'not json at all') == ['dc1.corp.local']
        assert h.state_of('not json at all') == h.STATE_UNKNOWN


class TestBuildState:
    def test_all_healthy_is_up(self):
        from services.ad_connector import health as h
        state = h._build_state([('dc1', True, 'ok'), ('dc2', True, 'ok')], None)
        assert state['state'] == h.STATE_UP
        assert (state['healthy'], state['total']) == (2, 2)

    def test_one_healthy_is_degraded(self):
        from services.ad_connector import health as h
        state = h._build_state([('dc1', True, 'ok'), ('dc2', False, 'refused')], None)
        assert state['state'] == h.STATE_DEGRADED

    def test_none_healthy_is_down(self):
        from services.ad_connector import health as h
        state = h._build_state([('dc1', False, 'refused'), ('dc2', False, 'refused')], None)
        assert state['state'] == h.STATE_DOWN

    def test_since_is_carried_forward_while_the_verdict_holds(self):
        """A DC down for an hour should report when it went down, not when
        it was last checked."""
        from services.ad_connector import health as h
        first = h._build_state([('dc1', False, 'refused')], None)
        went_down_at = first['servers']['dc1']['since']
        second = h._build_state([('dc1', False, 'refused')], first)
        assert second['servers']['dc1']['since'] == went_down_at

    def test_since_moves_when_the_verdict_flips(self):
        from services.ad_connector import health as h
        down = h._build_state([('dc1', False, 'refused')], None)
        up = h._build_state([('dc1', True, 'ok')], down)
        assert up['servers']['dc1']['since'] != down['servers']['dc1']['since']


class TestProbeIsDue:
    @staticmethod
    def _config(interval):
        from types import SimpleNamespace
        return SimpleNamespace(health_probe_interval=interval)

    def test_never_probed_is_due(self):
        from services.ad_connector import health as h
        assert h._is_due(self._config(120), None) is True

    def test_within_the_interval_is_not_due(self):
        from services.ad_connector import health as h
        blob = TestHealthState._blob({'dc1': True}, age_seconds=10)
        assert h._is_due(self._config(120), blob) is False

    def test_past_the_interval_is_due(self):
        from services.ad_connector import health as h
        blob = TestHealthState._blob({'dc1': True}, age_seconds=200)
        assert h._is_due(self._config(120), blob) is True

    def test_a_shortened_interval_takes_effect_without_restart(self):
        """The period is read from the row on every wake, not baked into the
        scheduler registration, so lowering it applies immediately."""
        from services.ad_connector import health as h
        blob = TestHealthState._blob({'dc1': True}, age_seconds=90)
        assert h._is_due(self._config(120), blob) is False
        assert h._is_due(self._config(60), blob) is True


class TestConnectSkipsUnhealthy:
    def _config(self, servers, health_blob):
        from types import SimpleNamespace
        return SimpleNamespace(
            server=servers, port=636, use_ssl=True, verify_ssl=True,
            ca_bundle=None, bind_dn='svc-ucm', bind_password='irrelevant',
            health=health_blob,
        )

    def test_known_bad_dc_is_not_dialled(self, monkeypatch):
        """The point of the probe: an enrollment must not pay dc1's connect
        timeout to rediscover what the probe already knows."""
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        blob = TestHealthState._blob({'dc1.corp.local': False, 'dc2.corp.local': True})
        lookup._connect(self._config(['dc1.corp.local', 'dc2.corp.local'], blob))
        assert connector.attempted == ['dc2.corp.local']

    def test_without_health_the_order_is_as_configured(self, monkeypatch):
        connector = _RecordingConnector()
        monkeypatch.setattr(lookup, '_connect_to', connector)
        lookup._connect(self._config(['dc1.corp.local', 'dc2.corp.local'], None))
        assert connector.attempted == ['dc1.corp.local']


class TestRunHealthProbe:
    def test_disabled_connector_is_skipped(self, app):
        from services.ad_connector import health as h
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(server='dc1.corp.local', enabled=False)
            db.session.add(config)
            db.session.commit()
            assert h.run_health_probe()['status'] == 'skipped'

    def test_probe_stores_its_verdict(self, app, monkeypatch):
        from services.ad_connector import health as h
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(
                server='dc1.corp.local\ndc2.corp.local', enabled=True,
                base_dn='DC=corp,DC=local', bind_dn='svc-ucm')
            config.bind_password = 'irrelevant'
            db.session.add(config)
            db.session.commit()
            monkeypatch.setattr(
                h, 'probe',
                lambda cfg: [('dc1.corp.local', False, 'refused'),
                             ('dc2.corp.local', True, 'ok')])
            result = h.run_health_probe()
            assert (result['status'], result['state']) == ('ok', h.STATE_DEGRADED)
            stored = ADConnectorConfig.get_singleton().health
            assert stored['servers']['dc1.corp.local']['healthy'] is False
            assert stored['servers']['dc2.corp.local']['healthy'] is True

    def test_a_probe_that_raised_is_a_failed_run(self, app, monkeypatch):
        """The scheduler reads 'status' and nothing else: anything it does
        not recognise counts as a successful run, so a probe that blew up
        would be logged and counted green in the admin view."""
        from services.ad_connector import health as h
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(
                server='dc1.corp.local', enabled=True, base_dn='DC=corp,DC=local',
                bind_dn='svc-ucm')
            config.bind_password = 'irrelevant'
            db.session.add(config)
            db.session.commit()

            def _explode(cfg):
                raise RuntimeError('DNS is down')

            monkeypatch.setattr(h, 'probe', _explode)
            result = h.run_health_probe()
            assert result['status'] == 'failed'
            assert 'DNS is down' in result['reason']

    def test_not_due_yet_is_a_skip_not_a_run(self, app, monkeypatch):
        """Registered at the scheduler's one-minute cadence, so most wakes
        do nothing -- reported as runs they would bury the real ones."""
        from services.ad_connector import health as h
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(
                server='dc1.corp.local', enabled=True, base_dn='DC=corp,DC=local',
                bind_dn='svc-ucm', health_probe_interval=3600)
            config.bind_password = 'irrelevant'
            config.health = TestHealthState._blob({'dc1.corp.local': True},
                                                  state='up', age_seconds=10)
            db.session.add(config)
            db.session.commit()
            monkeypatch.setattr(h, 'probe', lambda cfg: pytest.fail('should not probe'))
            assert h.run_health_probe()['status'] == 'skipped'

    def test_a_probe_that_could_not_run_keeps_the_stored_verdict(self, app, monkeypatch):
        """A _build_tls that raises is a failed run, not a verdict. Recording
        it would put state "unknown" and an empty server map over the real
        one, losing every DC's `since`, blanking the dialog and the badge,
        and counting a green run that never reached a domain controller. On
        a host whose temp directory is read-only that repeats every
        interval."""
        from services.ad_connector import health as h
        from services.ad_connector import lookup as lookup_mod
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(
                server='dc1.corp.local', enabled=True, base_dn='DC=corp,DC=local',
                bind_dn='svc-ucm')
            config.bind_password = 'irrelevant'
            # Older than the 120s default interval, so the probe is due
            # and actually runs rather than skipping as not due.
            config.health = TestHealthState._blob({'dc1.corp.local': False},
                                                  state='degraded', age_seconds=600)
            db.session.add(config)
            db.session.commit()

            def _explode(cfg):
                raise OSError('read-only file system')

            monkeypatch.setattr(lookup_mod, '_build_tls', _explode)
            result = h.run_health_probe()
            assert result['status'] == 'failed'
            stored = ADConnectorConfig.get_singleton().health
            assert stored['state'] == 'degraded'
            assert stored['servers']['dc1.corp.local']['healthy'] is False

    def test_a_connector_without_a_credential_is_skipped(self, app, monkeypatch):
        """An enabled row saved before the credential was required. The
        probe would otherwise bind anonymously every interval and record a
        health verdict for a connector no lookup can use."""
        from services.ad_connector import health as h
        with app.app_context():
            ADConnectorConfig.query.delete()
            db.session.add(ADConnectorConfig(
                server='dc1.corp.local', enabled=True, base_dn='DC=corp,DC=local',
                bind_dn='svc-ucm'))
            db.session.commit()
            monkeypatch.setattr(h, 'probe', lambda cfg: pytest.fail('should not probe'))
            result = h.run_health_probe()
            assert result['status'] == 'skipped'
            assert 'credential' in result['reason']
            # Nothing probed means nothing recorded: no verdict is invented.
            assert ADConnectorConfig.get_singleton().health == {}
