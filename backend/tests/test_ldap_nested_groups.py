"""LDAP option ``ldap_nested_groups``: on Active Directory, the nested groups and the primary group.

ldap3's MOCK_SYNC cannot evaluate LDAP_MATCHING_RULE_TRANSITIVE_EVAL (MS-ADTS 3.1.1.3.4.4.4)
nor resolve a ``<SID=…>`` base (MS-ADTS 3.1.1.3.1.2.4): ``Chain`` answers both at the library
boundary as a domain controller would (a visited set, so a cycle ends) and records the requests
as sent, which is what these tests pin.
"""
import json
import logging
import re
import struct
import uuid

import ldap3
import pytest
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import safe_dn

from models import db
from models.sso import SSOProvider
from tests.test_ldap_group_reading import (  # noqa: F401  (env is a fixture)
    PW, UNREADABLE, Directory, _tool, env)

IN_CHAIN = '1.2.840.113556.1.4.1941'
_CLAUSE = re.compile(r'\(member:1\.2\.840\.113556\.1\.4\.1941:=((?:[^()*\\]|\\[0-9a-fA-F]{2})*)\)')
DOMAIN = (21, 1111, 2222, 3333)
GROUPS = 'OU=Groups,DC=example,DC=com'
USERS = 'CN=Users,DC=example,DC=com'
DOMAIN_USERS = f'CN=Domain Users,{USERS}'


def _sid(rid, domain=DOMAIN):
    parts = (*domain, rid)
    return bytes([1, len(parts)]) + (5).to_bytes(6, 'big') + struct.pack(f'<{len(parts)}I', *parts)


def _unescape(value):
    out, i = bytearray(), 0
    while i < len(value):
        if value[i] == '\\':
            out.append(int(value[i + 1:i + 3], 16))
            i += 3
        else:
            out.extend(value[i].encode())
            i += 1
    return out.decode()


class Chain:
    """The AD side of the transitive rule, over the mock directory."""

    def __init__(self, d, monkeypatch):
        self.d, self.filters, self.error = d, [], None
        self.sid_bases, self.sid_error = [], False
        chain = self
        base_conn = ldap3.Connection

        class _Conn(base_conn):
            def search(self, base, flt, *a, **kw):
                if base.startswith('<SID='):
                    chain.sid_bases.append((base, kw.get('search_scope')))
                    if chain.sid_error:
                        raise ldap3.core.exceptions.LDAPOperationsErrorResult('insufficientAccessRights')
                    sid = bytes.fromhex(base[5:-1])
                    base = next((dn for dn, attrs in chain.d.server.dit.items()
                                 if sid in attrs.get('objectSid', [])), 'cn=no-such-sid')
                    return super().search(base, flt, *a, **kw)
                if IN_CHAIN not in flt:
                    return super().search(base, flt, *a, **kw)
                chain.filters.append((base, flt, kw.get('size_limit'), kw.get('time_limit')))
                if chain.error == 'raise':
                    raise ldap3.core.exceptions.LDAPOperationsErrorResult('operationsError')
                clauses = _CLAUSE.findall(flt)
                if len(clauses) != flt.count(IN_CHAIN):
                    raise ldap3.core.exceptions.LDAPInvalidFilterError(flt)
                flt = _CLAUSE.sub(lambda m: chain.rewrite(_unescape(m.group(1))), flt)
                size = kw.pop('size_limit', 0) or 0
                done = super().search(base, flt, *a, **kw)
                if chain.error in ('timeLimitExceeded', 'sizeLimitExceeded') or (
                        size and len(self.response or []) > size):
                    code = 3 if chain.error == 'timeLimitExceeded' else 4
                    self.result = {'result': code, 'description': chain.error or 'sizeLimitExceeded',
                                   'message': '', 'dn': '', 'referrals': None, 'type': 'searchResDone'}
                    return False
                return done

        monkeypatch.setattr(ldap3, 'Connection', _Conn)

    def closure(self, dn):
        """Groups holding ``dn`` at any depth (EvalTransitiveFilter, its Visited set)."""
        found, todo = set(), [safe_dn(dn).lower()]
        while todo:
            target = todo.pop()
            for gdn, attrs in self.d.server.dit.items():
                members = {safe_dn(m.decode() if isinstance(m, bytes) else m).lower()
                           for m in attrs.get('member', [])}
                if target in members and gdn.lower() not in found:
                    found.add(gdn.lower())
                    todo.append(gdn.lower())
        return [g for g in self.d.server.dit if g.lower() in found]

    def rewrite(self, dn):
        held = self.closure(dn)
        if not held:
            return '(objectClass=noSuchClass)'
        return '(|' + ''.join(f'(distinguishedName={escape_filter_chars(g)})' for g in held) + ')'


def _group(d, dn, members=(), rid=None, cn=None):
    attrs = {'objectClass': ['group'], 'cn': cn or dn.split(',')[0][3:], 'distinguishedName': dn}
    if members:
        attrs['member'] = list(members)
    if rid is not None:
        attrs['objectSid'] = _sid(rid)
    d.add(dn, attrs)


def _forest(monkeypatch, user, rdn=None, primary=513, ad=True,
            staff='OU=Staff,DC=example,DC=com', groups=GROUPS):
    """User in PKI-Ops (direct), PKI-Ops in PKI-Team in PKI-Admins; Domain Users (primary)
    in VPN-All; a group the user is not in."""
    contexts = ['DC=example,DC=com', 'CN=Configuration,DC=example,DC=com']
    d = Directory(monkeypatch, 'ad', contexts)
    if not ad:  # the same entries behind a root DSE without LDAP_CAP_ACTIVE_DIRECTORY_OID
        d.server.info.supported_features = [f for f in d.server.info.supported_features
                                            if f[0] != '1.2.840.113556.1.4.800']
    d.add(USERS, {'objectClass': ['top']})
    udn = f'CN={rdn or user},{staff}'
    d.add(udn, {'objectClass': ['user'], 'sAMAccountName': user, 'cn': user, 'displayName': user,
                'mail': f'{user}@example.com', 'userPassword': PW, 'distinguishedName': udn,
                'memberOf': [f'CN=PKI-Ops,{groups}'], 'primaryGroupID': str(primary),
                'objectSid': _sid(1105), 'userAccountControl': '512',
                'objectGUID': uuid.uuid4().bytes_le})
    udn = next(k for k in d.server.dit if k.lower() == safe_dn(udn).lower())
    _group(d, f'CN=PKI-Ops,{groups}', [udn], rid=1201)
    _group(d, f'CN=PKI-Team,{groups}', [f'CN=PKI-Ops,{groups}'], rid=1202)
    _group(d, f'CN=PKI-Admins,{groups}', [f'CN=PKI-Team,{groups}'], rid=1203)
    _group(d, DOMAIN_USERS, rid=513)
    _group(d, f'CN=VPN-All,{groups}', [DOMAIN_USERS], rid=1204)
    _group(d, f'CN=Unrelated,{groups}', [f'CN=someone,{groups}'], rid=1205)
    return d, Chain(d, monkeypatch), udn


def _provider(env, **kw):
    base = dict(ldap_base_dn='DC=example,DC=com', ldap_user_filter='(sAMAccountName={username})',
                ldap_username_attr='sAMAccountName', ldap_fullname_attr='displayName',
                ldap_group_filter='(objectClass=group)', ldap_group_member_attr='memberOf',
                role_mapping=json.dumps({'PKI-Admins': 'admin'}))
    base.update(kw)
    return env.provider(**base)


def _groups(env, pid, user):
    import api.v2.sso.connection_tests as connection_tests
    with env.app.app_context():
        info, err = connection_tests._ldap_authenticate_user(db.session.get(SSOProvider, pid), user, PW)
    return info, err


ALL = {'PKI-Ops', 'PKI-Team', 'PKI-Admins', 'Domain Users', 'VPN-All'}


# ── Off: today's behaviour ───────────────────────────────────────────────────

def test_off_reads_the_direct_groups_only(env, monkeypatch):
    user = env.user()
    d, chain, _ = _forest(monkeypatch, user)
    pid = _provider(env, role_mapping=json.dumps({'PKI-Ops': 'operator'}))
    info, err = _groups(env, pid, user)
    assert err is None and info['groups'] == ['PKI-Ops']
    assert chain.filters == []
    assert not [f for _, f, _ in d.searches if 'objectSid' in f or IN_CHAIN in f]


def test_off_a_rule_on_a_parent_group_gives_no_role(env, monkeypatch):
    user = env.user()
    _forest(monkeypatch, user)
    pid = _provider(env)
    assert env.login(pid, user)[0] == 403


def test_the_option_is_off_by_default(app):
    with app.app_context():
        p = SSOProvider(name=f'nest-{uuid.uuid4().hex[:6]}', provider_type='ldap')
        db.session.add(p)
        db.session.commit()
        try:
            assert p.ldap_nested_groups is False
            assert p.to_dict()['ldap_nested_groups'] is False
        finally:
            db.session.delete(p)
            db.session.commit()


# ── On: direct + nested at any depth + primary group ─────────────────────────

@pytest.mark.parametrize('member_attr', ['memberOf', 'member'])
def test_on_reads_three_levels_and_the_primary_group(env, monkeypatch, member_attr):
    user = env.user()
    d, chain, udn = _forest(monkeypatch, user)
    pid = _provider(env, ldap_nested_groups=True, ldap_group_member_attr=member_attr)
    info, err = _groups(env, pid, user)
    assert err is None, err
    assert set(info['groups']) == ALL and len(info['groups']) == len(ALL)
    assert 'Unrelated' not in info['groups']
    # One transitive search: the user and the primary group, the group filter kept
    [(base, flt, size, seconds)] = chain.filters
    assert base == 'DC=example,DC=com'
    assert flt == (f'(&(objectClass=group)(|(member:{IN_CHAIN}:={escape_filter_chars(udn)})'
                   f'(member:{IN_CHAIN}:={escape_filter_chars(DOMAIN_USERS)})))')
    assert size and seconds
    # The primary group is read by its SID wherever it lies: the user's domain SID and
    # primaryGroupID, as a <SID=hex> base object (MS-ADTS 3.1.1.3.1.2.4)
    assert chain.sid_bases == [(f'<SID={_sid(513).hex()}>', ldap3.BASE)]
    assert not [f for _, f, _ in d.searches if 'objectSid=' in f]


def test_on_a_rule_reached_only_through_a_parent_gives_its_role(env, monkeypatch, auth_client):
    user = env.user()
    _forest(monkeypatch, user)
    pid = _provider(env, ldap_nested_groups=True)
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'admin'
    tool = _tool(auth_client, pid, user)
    assert set(tool['groups']) == ALL and tool['resolved_role'] == 'admin'
    assert 'nested' in tool['group_source']


def test_on_a_rule_on_a_parent_of_the_primary_group_gives_its_role(env, monkeypatch):
    user = env.user()
    _forest(monkeypatch, user)
    pid = _provider(env, ldap_nested_groups=True, role_mapping=json.dumps({'VPN-All': 'operator'}))
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'operator'


def test_on_required_groups_see_the_nested_groups(env, monkeypatch):
    user = env.user()
    _forest(monkeypatch, user)
    pid = _provider(env, ldap_nested_groups=True, role_mapping=None,
                    ldap_required_groups=json.dumps(['PKI-Team']))
    assert env.login(pid, user)[0] == 200


# ── Where the groups are searched: the primary group is read wherever it lies ─────

def test_a_group_base_limited_to_an_ou_still_reads_the_parents(env, monkeypatch):
    """The primary group (CN=Users) is outside OU=Groups: its own name does not count, its
    parents under the base do, and the login goes through."""
    user = env.user()
    _forest(monkeypatch, user)
    pid = _provider(env, ldap_nested_groups=True, ldap_group_base_dn=GROUPS,
                    role_mapping=json.dumps({'VPN-All': 'operator', 'PKI-Admins': 'admin'}))
    info, err = _groups(env, pid, user)
    assert err is None, err
    assert set(info['groups']) == ALL - {'Domain Users'}
    assert env.login(pid, user)[0] == 200 and env.role(user) == 'admin'


def test_a_deduced_group_base_still_reads_the_parents(env, monkeypatch):
    """No group base, a base DN two levels under the domain: the groups are searched under
    its parent OU=Corp, which does not hold CN=Users."""
    user = env.user()
    corp = 'OU=Corp,DC=example,DC=com'
    d, chain, _ = _forest(monkeypatch, user, staff=f'OU=People,{corp}', groups=f'OU=Groups,{corp}')
    pid = _provider(env, ldap_nested_groups=True, ldap_base_dn=f'OU=People,{corp}',
                    role_mapping=json.dumps({'VPN-All': 'operator', 'PKI-Admins': 'admin'}))
    info, err = _groups(env, pid, user)
    assert err is None, err
    assert set(info['groups']) == ALL - {'Domain Users'}
    [(base, _, _, _)] = chain.filters
    assert base.lower() == corp.lower()
    assert env.login(pid, user)[0] == 200 and env.role(user) == 'admin'


def test_a_limit_under_the_deduced_base_is_not_retried_under_the_base_dn(
        env, monkeypatch, auth_client, caplog):
    """Under OU=People, the base DN, there are fewer groups: retrying there is a partial answer."""
    import api.v2.sso.connection_tests as connection_tests
    user = env.user()
    corp = 'OU=Corp,DC=example,DC=com'
    _forest(monkeypatch, user, staff=f'OU=People,{corp}', groups=f'OU=Groups,{corp}')
    monkeypatch.setattr(connection_tests, 'NESTED_GROUPS_LIMIT', 3)
    pid = _provider(env, ldap_nested_groups=True, ldap_base_dn=f'OU=People,{corp}',
                    role_mapping=json.dumps({'PKI-Ops': 'admin'}))
    _refused(env, pid, user, auth_client, 'sizeLimitExceeded', caplog)


def test_a_name_twin_of_a_primary_group_outside_the_base_gives_no_role(env, monkeypatch):
    """A group under the base named like the user's primary group, which lies outside it:
    the rule on that name must not reach the user through the primary group."""
    user = env.user()
    d, _, _ = _forest(monkeypatch, user)
    _group(d, f'CN=Domain Users,{GROUPS}', [f'CN=someone,{GROUPS}'], rid=1300)
    pid = _provider(env, ldap_nested_groups=True, ldap_group_base_dn=GROUPS,
                    role_mapping=json.dumps({'Domain Users': 'admin'}))
    info, err = _groups(env, pid, user)
    assert err is None and 'Domain Users' not in info['groups']
    assert env.login(pid, user)[0] == 403


def test_the_group_filter_applies_to_the_primary_group(env, monkeypatch):
    user = env.user()
    _forest(monkeypatch, user)
    pid = _provider(env, ldap_nested_groups=True,
                    ldap_group_filter='(&(objectClass=group)(cn=PKI-*))')
    info, err = _groups(env, pid, user)
    assert err is None, err
    assert set(info['groups']) == {'PKI-Ops', 'PKI-Team', 'PKI-Admins'}


def test_each_connection_of_the_nested_read_has_a_receive_timeout(env, monkeypatch):
    import api.v2.sso.connection_tests as connection_tests
    user = env.user()
    _forest(monkeypatch, user)
    real, bounds = connection_tests._service_connection, []

    def spy(provider, server, **kw):
        bounds.append(kw)
        return real(provider, server, **kw)
    monkeypatch.setattr(connection_tests, '_service_connection', spy)
    pid = _provider(env, ldap_nested_groups=True)
    assert _groups(env, pid, user)[1] is None
    assert {'receive_timeout': connection_tests.NESTED_GROUPS_SECONDS} in bounds


def test_a_cycle_of_groups_ends(env, monkeypatch):
    user = env.user()
    d, chain, _ = _forest(monkeypatch, user)
    # PKI-Admins back into PKI-Ops: A in B in C in A
    d.remove(f'CN=PKI-Ops,{GROUPS}')
    udn = next(k for k in d.server.dit if k.lower().startswith(f'cn={user.lower()},'))
    _group(d, f'CN=PKI-Ops,{GROUPS}', [udn, f'CN=PKI-Admins,{GROUPS}'], rid=1201)
    pid = _provider(env, ldap_nested_groups=True)
    info, err = _groups(env, pid, user)
    assert err is None and set(info['groups']) == ALL
    assert len(chain.filters) == 1


# ── Never a silent fallback ──────────────────────────────────────────────────

def _refused(env, pid, user, auth_client, cause, caplog):
    with caplog.at_level(logging.WARNING):
        code, body = env.login(pid, user)
    assert (code, body.get('message')) == (403, UNREADABLE)
    assert any('could not be read' in r.getMessage() and cause in r.getMessage()
               for r in caplog.records), caplog.text
    tool = _tool(auth_client, pid, user)
    assert tool['refusal'] == 'groups_unreadable' and tool['resolved_role'] is None
    assert cause in (tool.get('groups_error') or '')


def test_a_server_that_is_not_active_directory_is_refused(env, monkeypatch, auth_client, caplog):
    user = env.user()
    _, chain, _ = _forest(monkeypatch, user, ad=False)
    pid = _provider(env, ldap_nested_groups=True, role_mapping=json.dumps({'PKI-Ops': 'admin'}))
    _refused(env, pid, user, auth_client, '1.2.840.113556.1.4.800', caplog)
    assert chain.filters == []


@pytest.mark.parametrize('error', ['raise', 'timeLimitExceeded', 'sizeLimitExceeded'])
def test_a_failed_transitive_search_is_refused(env, monkeypatch, auth_client, caplog, error):
    user = env.user()
    _, chain, _ = _forest(monkeypatch, user)
    chain.error = error
    # PKI-Ops is direct: a fallback to the direct groups would let the user in
    pid = _provider(env, ldap_nested_groups=True, role_mapping=json.dumps({'PKI-Ops': 'admin'}))
    cause = {'raise': 'operationsError'}.get(error, error)
    _refused(env, pid, user, auth_client, cause, caplog)
    chain.error = None
    assert env.login(pid, user)[0] == 200  # control


def test_more_groups_than_the_cap_are_refused(env, monkeypatch, auth_client, caplog):
    import api.v2.sso.connection_tests as connection_tests
    user = env.user()
    _forest(monkeypatch, user)
    monkeypatch.setattr(connection_tests, 'NESTED_GROUPS_LIMIT', 3)
    pid = _provider(env, ldap_nested_groups=True, role_mapping=json.dumps({'PKI-Ops': 'admin'}))
    _refused(env, pid, user, auth_client, 'sizeLimitExceeded', caplog)
    monkeypatch.setattr(connection_tests, 'NESTED_GROUPS_LIMIT', 4)
    assert env.login(pid, user)[0] == 200


def test_a_primary_group_not_found_is_refused(env, monkeypatch, auth_client, caplog):
    user = env.user()
    _forest(monkeypatch, user, primary=599)
    pid = _provider(env, ldap_nested_groups=True, role_mapping=json.dumps({'PKI-Ops': 'admin'}))
    _refused(env, pid, user, auth_client, 'primary group', caplog)


def test_a_refused_sid_read_is_refused(env, monkeypatch, auth_client, caplog):
    user = env.user()
    _, chain, _ = _forest(monkeypatch, user)
    chain.sid_error = True
    pid = _provider(env, ldap_nested_groups=True, role_mapping=json.dumps({'PKI-Ops': 'admin'}))
    _refused(env, pid, user, auth_client, 'insufficientAccessRights', caplog)


# ── RFC 4515 §3: no filter injection ─────────────────────────────────────────

SPECIAL_RDN = 'x\\,y (a*b) \\\\ \\00 '


def test_the_user_dn_is_escaped_in_the_transitive_filter(env, monkeypatch):
    user = env.user()
    _, chain, udn = _forest(monkeypatch, user, rdn=SPECIAL_RDN + user)
    pid = _provider(env, ldap_nested_groups=True)
    info, err = _groups(env, pid, user)
    assert err is None and set(info['groups']) == ALL
    [(_, flt, _, _)] = chain.filters
    sent = escape_filter_chars(udn)
    assert f'(member:{IN_CHAIN}:={sent})' in flt
    for raw, escaped in (('*', '\\2a'), ('(', '\\28'), (')', '\\29'), ('\\', '\\5c')):
        assert escaped in sent
    assert '\\5c00' in sent and '\\5c,' in sent  # the DN's own \00 and \, escapes


def test_a_nul_in_a_dn_value_is_escaped():
    from api.v2.sso import connection_tests
    flt = connection_tests._nested_filter('(objectClass=group)', 'CN=a\x00b*,DC=x', 'CN=g,DC=x')
    assert '\x00' not in flt and 'a\\00b\\2a' in flt


def test_the_member_filter_of_today_escapes_the_user_dn(env, monkeypatch):
    """The existing member search, option off: RFC 4515 §3 holds already."""
    user = env.user()
    d, _, udn = _forest(monkeypatch, user, rdn=SPECIAL_RDN + user)
    pid = _provider(env, ldap_group_member_attr='member')
    info, err = _groups(env, pid, user)
    assert err is None and info['groups'] == ['PKI-Ops']
    assert [f for _, f, _ in d.searches if '(member=' in f] == [
        f'(&(objectClass=group)(member={escape_filter_chars(udn)}))']


def test_the_user_filter_of_today_escapes_the_username(env, monkeypatch):
    user = env.user()
    d, _, _ = _forest(monkeypatch, user)
    pid = _provider(env, ldap_nested_groups=True)
    assert env.login(pid, '*')[0] == 401
    assert env.login(pid, f'{user})(cn=*')[0] == 401
    sent = [f for _, f, _ in d.searches if f.startswith('(sAMAccountName=')]
    assert sent[-2:] == ['(sAMAccountName=\\2a)', f'(sAMAccountName={user}\\29\\28cn=\\2a)']


# ── API ──────────────────────────────────────────────────────────────────────

def test_the_option_is_saved_and_shown(app, auth_client):
    body = {'name': f'nest-{uuid.uuid4().hex[:6]}', 'provider_type': 'ldap',
            'ldap_server': 'ldap.example.com', 'ldap_base_dn': 'dc=example,dc=com'}
    r = auth_client.post('/api/v2/sso/providers', json=body)
    assert r.status_code in (200, 201), r.data
    pid = r.get_json()['data']['id']
    try:
        assert r.get_json()['data']['ldap_nested_groups'] is False
        r = auth_client.put(f'/api/v2/sso/providers/{pid}', json={'ldap_nested_groups': True})
        assert r.status_code == 200 and r.get_json()['data']['ldap_nested_groups'] is True
        with app.app_context():
            assert db.session.get(SSOProvider, pid).ldap_nested_groups is True
        r = auth_client.put(f'/api/v2/sso/providers/{pid}', json={'ldap_nested_groups': False})
        assert r.get_json()['data']['ldap_nested_groups'] is False
    finally:
        with app.app_context():
            SSOProvider.query.filter_by(id=pid).delete()
            db.session.commit()
    r = auth_client.post('/api/v2/sso/providers', json={**body, 'ldap_nested_groups': True})
    pid = r.get_json()['data']['id']
    try:
        assert r.get_json()['data']['ldap_nested_groups'] is True
    finally:
        with app.app_context():
            SSOProvider.query.filter_by(id=pid).delete()
            db.session.commit()


def test_the_option_goes_through_a_backup_and_a_restore(app):
    from services.backup.export_generic import IdentityIndex, export_section
    from services.backup.restore import RestorePlan
    from services.backup.restore.apply import apply_columns
    name = f'nest-bk-{uuid.uuid4().hex[:6]}'
    with app.app_context():
        from tests.sso_identity_support import step_aside
        others = step_aside('ldap')
        db.session.add(SSOProvider(name=name, provider_type='ldap', ldap_nested_groups=True))
        db.session.commit()
        try:
            [row] = [r for r in export_section('sso_providers', IdentityIndex()) if r['name'] == name]
            assert row['ldap_nested_groups'] is True
            SSOProvider.query.filter_by(name=name).delete()
            db.session.commit()
            restored = SSOProvider(name=name, provider_type='ldap')
            db.session.add(restored)
            apply_columns(restored, 'sso_providers', row, RestorePlan())
            db.session.commit()
            assert SSOProvider.query.filter_by(name=name).one().ldap_nested_groups is True
        finally:
            SSOProvider.query.filter_by(name=name).delete()
            db.session.commit()
            others.back()


@pytest.mark.parametrize('value', ['true', 1, 'false', 0, None, [True]])
def test_a_value_that_is_not_a_boolean_is_refused(app, auth_client, value):
    name = f'nest-{uuid.uuid4().hex[:6]}'
    body = {'name': name, 'provider_type': 'ldap', 'ldap_server': 'ldap.example.com',
            'ldap_base_dn': 'dc=example,dc=com'}
    try:
        r = auth_client.post('/api/v2/sso/providers', json={**body, 'ldap_nested_groups': value})
        assert r.status_code == 400 and 'ldap_nested_groups' in r.get_json()['message']
        with app.app_context():
            assert SSOProvider.query.filter_by(name=name).count() == 0
        r = auth_client.post('/api/v2/sso/providers', json={**body, 'ldap_nested_groups': True})
        pid = r.get_json()['data']['id']
        r = auth_client.put(f'/api/v2/sso/providers/{pid}', json={'ldap_nested_groups': value})
        assert r.status_code == 400 and 'ldap_nested_groups' in r.get_json()['message']
        with app.app_context():
            assert db.session.get(SSOProvider, pid).ldap_nested_groups is True
    finally:
        with app.app_context():
            SSOProvider.query.filter_by(name=name).delete()
            db.session.commit()
