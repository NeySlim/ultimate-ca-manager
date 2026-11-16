"""LDAP groups are read where they live, and the mapping test says what the login will do.

The directory is ldap3's MOCK_SYNC strategy behind the real ``_ldap_authenticate_user``,
the real ``/api/v2/sso/ldap/login`` door and the real mapping test route.
"""
import json
import logging
import uuid

import ldap3
import pytest

from models import db, User, AuditLog
from models.sso import SSOProvider, SSOSession

PW = 'S3cret!pw'
SVC_DN = 'cn=svc,dc=example,dc=com'
SVC_PW = 'svcpw'
UNREADABLE = 'Access denied: your groups could not be read from the directory'


def _cleanup(names):
    from api.v2.users.crud import _purge_user_dependencies
    for (uid,) in User.query.filter(User.username.in_(names)).with_entities(User.id).all():
        _purge_user_dependencies(uid)
    User.query.filter(User.username.in_(names)).delete(synchronize_session=False)
    db.session.commit()


class Directory:
    """A mock directory; every Connection the product opens lands on it."""

    def __init__(self, monkeypatch, kind='openldap', naming_contexts=None):
        info = ldap3.OFFLINE_SLAPD_2_4 if kind == 'openldap' else ldap3.OFFLINE_AD_2012_R2
        self.server = ldap3.Server('mock-dir', get_info=info)
        # What the root DSE of this directory publishes (RFC 4512 §5.1).
        self.server.info.naming_contexts = naming_contexts
        real_conn = ldap3.Connection
        self.fail_on = None  # substring of a search filter that raises
        self.searches = []
        self.admin = real_conn(self.server, user=SVC_DN, password=SVC_PW,
                               client_strategy=ldap3.MOCK_SYNC)
        self.admin.strategy.add_entry(SVC_DN, {'objectClass': ['person'], 'cn': 'svc', 'sn': 'svc',
                                               'userPassword': SVC_PW})
        for dn in ('dc=example,dc=com', 'ou=people,dc=example,dc=com',
                   'ou=groups,dc=example,dc=com',
                   'OU=Staff,DC=example,DC=com', 'OU=Groups,DC=example,DC=com'):
            self.admin.strategy.add_entry(dn, {'objectClass': ['top']})
        directory = self

        class _Conn(real_conn):
            def __init__(self, _server, *a, **kw):
                kw.pop('client_strategy', None)
                # Mock values are raw bytes; a real server's decode to str without the
                # schema. check_names=True gives the same str values here.
                kw['check_names'] = True
                ab = kw.pop('auto_bind', None)
                if ab == ldap3.AUTO_BIND_TLS_BEFORE_BIND:
                    ab = ldap3.AUTO_BIND_NO_TLS
                super().__init__(directory.server, *a, client_strategy=ldap3.MOCK_SYNC, **kw)
                if ab not in (None, False, ldap3.AUTO_BIND_NONE):
                    if not self.bind():
                        raise ldap3.core.exceptions.LDAPBindError('bind refused')

            def search(self, base, flt, *a, **kw):
                directory.searches.append((base, flt, kw.get('search_scope', ldap3.SUBTREE)))
                if directory.fail_on and directory.fail_on in flt:
                    raise ldap3.core.exceptions.LDAPOperationsErrorResult('insufficientAccessRights')
                if base.lower() not in {k.lower() for k in directory.server.dit}:
                    # A real server answers noSuchObject (RFC 4511 §4.5.1) for a base
                    # entry it does not hold; the mock matches by DN suffix instead.
                    base = 'cn=no-such-base'
                return super().search(base, flt, *a, **kw)

        monkeypatch.setattr(ldap3, 'Server', lambda *a, **k: directory.server)
        monkeypatch.setattr(ldap3, 'Connection', _Conn)

    def add(self, dn, attrs):
        self.admin.strategy.add_entry(dn, attrs)

    def remove(self, dn):
        del self.server.dit[dn]


def _provider(**kw):
    base = dict(name=f'grp-ldap-{uuid.uuid4().hex[:6]}', provider_type='ldap', enabled=True,
                ldap_server='dc1.example.com', ldap_port=389, ldap_use_ssl=False,
                ldap_bind_dn=SVC_DN, ldap_base_dn='dc=example,dc=com',
                ldap_user_filter='(uid={username})', ldap_username_attr='uid',
                ldap_email_attr='mail', ldap_fullname_attr='cn',
                auto_create_users=True, default_role='viewer')
    base.update(kw)
    p = SSOProvider(**base)
    p.ldap_bind_password = SVC_PW
    db.session.add(p)
    db.session.commit()
    return p.id


@pytest.fixture
def env(app, monkeypatch):
    created_p, created_u = [], []
    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='ldap').all()]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        db.session.commit()

    class E:
        pass
    e = E()
    e.app = app
    e.users = created_u

    def provider(**kw):
        with app.app_context():
            pid = _provider(**kw)
        created_p.append(pid)
        return pid

    def login(pid, username, password=PW):
        r = app.test_client().post('/api/v2/sso/ldap/login',
                                   json={'username': username, 'password': password,
                                         'provider_id': pid})
        return r.status_code, (r.get_json() or {})

    def user(prefix='grp'):
        name = f'{prefix}{uuid.uuid4().hex[:6]}'
        created_u.append(name)
        return name

    def role(username):
        with app.app_context():
            return User.query.filter_by(username=username).one().role

    e.provider, e.login, e.user, e.role = provider, login, user, role
    yield e
    with app.app_context():
        _cleanup(created_u)
        for pid in created_p:
            SSOSession.query.filter_by(provider_id=pid).delete()
            User.query.filter_by(sso_provider_id=pid).update({User.sso_provider_id: None})
            p = db.session.get(SSOProvider, pid)
            if p:
                db.session.delete(p)
        for opid, enabled in others:
            p = db.session.get(SSOProvider, opid)
            if p:
                p.enabled = enabled
        db.session.commit()


def _openldap(monkeypatch, user, groups_ou='ou=groups,dc=example,dc=com', group_cn='pki-admins',
              naming_contexts=('dc=example,dc=com',), member_of=False):
    d = Directory(monkeypatch, 'openldap', list(naming_contexts) if naming_contexts else None)
    udn = f'uid={user},ou=people,dc=example,dc=com'
    gdn = f'cn={group_cn},{groups_ou}'
    attrs = {'objectClass': ['inetOrgPerson'], 'uid': user, 'cn': user, 'sn': user,
             'mail': f'{user}@example.com', 'userPassword': PW, 'entryUUID': str(uuid.uuid4())}
    if member_of:  # the memberOf overlay
        attrs['memberOf'] = [gdn]
    d.add(udn, attrs)
    d.add(gdn, {'objectClass': ['groupOfNames'], 'cn': group_cn, 'member': [udn]})
    return d, udn


def _ad(monkeypatch, user, member_of, uac=512):
    d = Directory(monkeypatch, 'ad', ['DC=example,DC=com', 'CN=Configuration,DC=example,DC=com'])
    udn = f'CN={user},OU=Staff,DC=example,DC=com'
    d.add(udn, {'objectClass': ['user'], 'sAMAccountName': user, 'cn': user,
                'displayName': user, 'mail': f'{user}@example.com', 'userPassword': PW,
                'distinguishedName': udn, 'memberOf': member_of, 'primaryGroupID': '513',
                'userAccountControl': str(uac), 'objectGUID': uuid.uuid4().bytes_le})
    return d, udn


def _ad_provider(env, **kw):
    base = dict(ldap_base_dn='DC=example,DC=com', ldap_user_filter='(sAMAccountName={username})',
                ldap_username_attr='sAMAccountName', ldap_fullname_attr='displayName',
                ldap_group_filter='(objectClass=group)', ldap_group_member_attr='memberOf')
    base.update(kw)
    return env.provider(**base)


def _member_provider(env, **kw):
    base = dict(ldap_group_filter='(objectClass=groupOfNames)', ldap_group_member_attr='member',
                role_mapping=json.dumps({'pki-admins': 'admin'}))
    base.update(kw)
    return env.provider(**base)


def _tool(auth_client, pid, user):
    r = auth_client.post(f'/api/v2/sso/providers/{pid}/test-mapping', json={'username': user})
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def _audited(app, username, text):
    with app.app_context():
        return AuditLog.query.filter_by(action='login_failure', username=username).filter(
            AuditLog.details.contains(text)).count()


# ── 1. Group search base: the naming context, else the base DN ───────────────

def test_a_root_base_dn_reads_the_groups_of_its_naming_context(env, monkeypatch):
    """Base DN at the domain root (the form's placeholder): searched under ``dc=com``
    the groups were never found and a user the rule names was refused."""
    user = env.user()
    _openldap(monkeypatch, user)
    pid = _member_provider(env)
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'admin'


def test_groups_in_a_sibling_branch_of_the_users_are_read(env, monkeypatch):
    """``ou=people`` as base DN, groups under ``ou=groups``: the naming context holds both."""
    user = env.user()
    _openldap(monkeypatch, user)
    pid = _member_provider(env, ldap_base_dn='ou=people,dc=example,dc=com')
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'admin'


def test_without_a_published_naming_context_groups_are_searched_under_the_base_dn(
        env, monkeypatch):
    user = env.user()
    d, _ = _openldap(monkeypatch, user, naming_contexts=None)
    pid = _member_provider(env)
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'admin'
    group_bases = [b for b, f, _ in d.searches if '(member=' in f]
    assert group_bases == ['dc=example,dc=com']


def test_a_group_search_the_directory_refuses_is_never_read_as_no_group(
        env, monkeypatch, auth_client):
    """noSuchObject on the group search base (RFC 4511 §4.5.1) refuses as unreadable."""
    user = env.user()
    d, _ = _openldap(monkeypatch, user)
    pid = _member_provider(env, ldap_base_dn='ou=people,dc=example,dc=com')
    d.remove('dc=example,dc=com')
    code, body = env.login(pid, user)
    assert (code, body.get('message')) == (403, UNREADABLE)
    tool = _tool(auth_client, pid, user)
    assert tool['groups_readable'] is False and tool['access_allowed'] is False
    assert tool['refusal'] == 'groups_unreadable' and tool['resolved_role'] is None


# ── 2. No group filter ───────────────────────────────────────────────────────

def test_memberof_rules_without_a_group_filter_read_the_groups(env, monkeypatch):
    user = env.user()
    _ad(monkeypatch, user, ['CN=PKI-Admins,OU=Groups,DC=example,DC=com'])
    pid = _ad_provider(env, ldap_group_filter=None, role_mapping=json.dumps({'PKI-Admins': 'admin'}))
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'admin'


@pytest.mark.parametrize('member_attr', ['member', 'uniqueMember'])
def test_member_rules_without_a_group_filter_read_the_groups(env, monkeypatch, member_attr):
    user = env.user()
    d, udn = _openldap(monkeypatch, user)
    d.add('cn=pki-ops,ou=groups,dc=example,dc=com',
          {'objectClass': ['groupOfUniqueNames'], 'cn': 'pki-ops', 'uniqueMember': [udn]})
    pid = _member_provider(env, ldap_group_filter=None, ldap_group_member_attr=member_attr,
                           role_mapping=json.dumps({'pki-admins': 'admin', 'pki-ops': 'operator'}))
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == ('admin' if member_attr == 'member' else 'operator')


def test_required_groups_without_a_group_filter_read_the_groups(env, monkeypatch):
    user = env.user()
    _openldap(monkeypatch, user)
    pid = env.provider(ldap_group_filter='', ldap_group_member_attr='member',
                       ldap_required_groups=json.dumps(['pki-admins']))
    assert env.login(pid, user)[0] == 200
    other = env.user()
    _openldap(monkeypatch, other, group_cn='others')
    code, body = env.login(pid, other)
    assert (code, body.get('message')) == (
        403, 'Access denied: you are not a member of the required group(s)')


def test_a_provider_without_rules_nor_required_groups_reads_no_group(env, monkeypatch):
    user = env.user()
    d, _ = _openldap(monkeypatch, user)
    pid = env.provider(ldap_group_filter=None, ldap_group_member_attr='member')
    assert env.login(pid, user)[0] == 200
    assert not [f for _, f, _ in d.searches if '(member=' in f]


# ── 3. memberOf read on the user entry itself ────────────────────────────────

def test_memberof_is_read_by_a_base_search_on_the_user_entry(env, monkeypatch):
    """OpenLDAP with the memberOf overlay carries no distinguishedName value."""
    user = env.user()
    d, udn = _openldap(monkeypatch, user, member_of=True)
    pid = env.provider(ldap_group_filter=None, ldap_group_member_attr='memberOf',
                       role_mapping=json.dumps({'pki-admins': 'operator'}))
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'operator'
    reads = [s for s in d.searches if s[0] == udn]
    assert reads == [(udn, '(objectClass=*)', ldap3.BASE)]
    assert not [f for _, f, _ in d.searches if 'distinguishedName' in f]


def test_ad_memberof_keeps_working(env, monkeypatch):
    user = env.user()
    _ad(monkeypatch, user, ['CN=PKI-Admins,OU=Groups,DC=example,DC=com'])
    pid = _ad_provider(env, role_mapping=json.dumps({'PKI-Admins': 'operator'}))
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'operator'


# ── 4. Comparison: cn is caseIgnoreMatch for LDAP, exact for OIDC and SAML ───

def test_ldap_rule_and_group_compare_ignoring_case_and_edge_spaces(env, monkeypatch):
    user = env.user()
    _ad(monkeypatch, user, ['CN=PKI-Admins,OU=Groups,DC=example,DC=com'])
    # A rule stored before save-time trimming, and required groups in another case.
    pid = _ad_provider(env, role_mapping=json.dumps({' pki-admins ': 'operator'}),
                       ldap_required_groups=json.dumps(['pki-ADMINS']))
    assert env.login(pid, user)[0] == 200
    assert env.role(user) == 'operator'
    other = env.user()
    _ad(monkeypatch, other, ['CN=VPN,OU=Groups,DC=example,DC=com'])
    pid2 = _ad_provider(env, role_mapping=json.dumps({' pki-admins ': 'operator'}))
    assert env.login(pid2, other)[0] == 403


@pytest.mark.parametrize('provider_type', ['oauth2', 'saml'])
def test_oidc_and_saml_groups_stay_exact(provider_type):
    from types import SimpleNamespace
    from api.v2.sso.helpers import sso_admission, _resolve_mapped_roles
    p = SimpleNamespace(provider_type=provider_type, role_mapping={'pki-admins': 'admin'},
                        default_role='viewer')
    assert not sso_admission(p, {'groups': ['PKI-Admins']})
    assert not sso_admission(p, {'groups': [' pki-admins']})
    assert _resolve_mapped_roles(p, {'groups': ['PKI-Admins']}) == (None, None)
    assert sso_admission(p, {'groups': ['pki-admins']})
    assert _resolve_mapped_roles(p, {'groups': ['pki-admins']})[0] == 'admin'


def test_a_rule_key_is_saved_without_edge_spaces(app, auth_client):
    name = f'grp-save-{uuid.uuid4().hex[:6]}'
    r = auth_client.post('/api/v2/sso/providers', json={
        'name': name, 'provider_type': 'ldap', 'role_mapping': {'  pki-admins ': 'admin'},
        'ldap_server': 'ldap.example.com', 'ldap_base_dn': 'dc=example,dc=com'})
    assert r.status_code in (200, 201), r.data
    pid = r.get_json()['data']['id']
    try:
        with app.app_context():
            assert json.loads(db.session.get(SSOProvider, pid).role_mapping) == {'pki-admins': 'admin'}
        r = auth_client.put(f'/api/v2/sso/providers/{pid}',
                            json={'role_mapping': {'ops ': 'operator', ' ops': 'viewer'}})
        assert r.status_code == 400, r.data
        r = auth_client.put(f'/api/v2/sso/providers/{pid}',
                            json={'role_mapping': {' ops\t': 'operator'}})
        assert r.status_code == 200, r.data
        with app.app_context():
            assert json.loads(db.session.get(SSOProvider, pid).role_mapping) == {'ops': 'operator'}
    finally:
        with app.app_context():
            SSOProvider.query.filter_by(id=pid).delete()
            db.session.commit()


# ── 5. A failed group read says so ───────────────────────────────────────────

def test_a_failed_group_read_says_the_groups_could_not_be_read(env, monkeypatch, caplog):
    user = env.user()
    d, _ = _openldap(monkeypatch, user)
    pid = _member_provider(env)
    d.fail_on = '(member='
    with caplog.at_level(logging.WARNING):
        code, body = env.login(pid, user)
    assert (code, body.get('message')) == (403, UNREADABLE)
    assert 'no role mapping rule' not in body['message']
    assert any('could not be read' in r.getMessage() for r in caplog.records)
    assert _audited(env.app, user, 'groups could not be read') == 1
    assert _audited(env.app, user, 'no role mapping rule') == 0
    with env.app.app_context():
        assert User.query.filter_by(username=user).first() is None
    d.fail_on = None  # control: the same user enters once the read works
    assert env.login(pid, user)[0] == 200


def test_a_failed_group_read_with_required_groups_is_not_a_missing_group(env, monkeypatch):
    user = env.user()
    d, _ = _ad(monkeypatch, user, ['CN=PKI-Admins,OU=Groups,DC=example,DC=com'])
    pid = _ad_provider(env, ldap_required_groups=json.dumps(['PKI-Admins']))
    d.fail_on = '(objectClass=*)'
    code, body = env.login(pid, user)
    assert (code, body.get('message')) == (403, UNREADABLE)
    d.fail_on = None
    assert env.login(pid, user)[0] == 200


def test_a_failed_group_read_the_admission_does_not_need_lets_the_user_in(env, monkeypatch):
    user = env.user()
    d, _ = _openldap(monkeypatch, user)
    pid = env.provider(ldap_group_filter='(objectClass=groupOfNames)', ldap_group_member_attr='member')
    d.fail_on = '(member='
    assert env.login(pid, user)[0] == 200


# ── 6. The mapping test reads and decides as the login does ──────────────────

def _scenarios():
    def root_base(env, mp):
        user = env.user()
        _openldap(mp, user)
        return user, _member_provider(env), None

    def no_filter(env, mp):
        user = env.user()
        _ad(mp, user, ['CN=PKI-Admins,OU=Groups,DC=example,DC=com'])
        return user, _ad_provider(env, ldap_group_filter=None,
                                  role_mapping=json.dumps({'pki-admins': 'admin'})), None

    def unmatched(env, mp):
        user = env.user()
        _ad(mp, user, ['CN=VPN,OU=Groups,DC=example,DC=com'])
        return user, _ad_provider(env, role_mapping=json.dumps({'PKI-Admins': 'admin'})), 'unmapped'

    def disabled(env, mp):
        user = env.user()
        _ad(mp, user, ['CN=PKI-Admins,OU=Groups,DC=example,DC=com'], uac=514)
        return user, _ad_provider(env, role_mapping=json.dumps({'PKI-Admins': 'admin'})), \
            'account_disabled'

    def unreadable(env, mp):
        user = env.user()
        d, _ = _openldap(mp, user)
        d.fail_on = '(member='
        return user, _member_provider(env), 'groups_unreadable'

    def not_required(env, mp):
        user = env.user()
        _ad(mp, user, ['CN=VPN,OU=Groups,DC=example,DC=com'])
        return user, _ad_provider(env, ldap_required_groups=json.dumps(['PKI-Admins'])), \
            'group_denied'

    return [root_base, no_filter, unmatched, disabled, unreadable, not_required]


@pytest.mark.parametrize('scenario', _scenarios(), ids=lambda s: s.__name__)
def test_the_mapping_test_gives_the_login_verdict(env, monkeypatch, auth_client, scenario):
    user, pid, refusal = scenario(env, monkeypatch)
    tool = _tool(auth_client, pid, user)
    code, body = env.login(pid, user)
    assert tool['refusal'] == refusal
    assert tool['access_allowed'] is (refusal is None) is (code == 200), (tool, code, body)
    if refusal is None:
        assert tool['resolved_role'] == env.role(user)
    else:
        assert tool['resolved_role'] is None and tool['resolved_custom_role'] is None
    assert tool['account_checked'] is False and tool['note']


def test_the_mapping_test_lists_the_groups_the_login_reads(env, monkeypatch, auth_client, caplog):
    user = env.user()
    _openldap(monkeypatch, user)
    pid = _member_provider(env)
    assert _tool(auth_client, pid, user)['groups'] == ['pki-admins']
    import api.v2.sso.connection_tests as connection_tests
    with env.app.app_context():
        info, err = connection_tests._ldap_authenticate_user(db.session.get(SSOProvider, pid), user, PW)
    assert err is None and info['groups'] == ['pki-admins']
