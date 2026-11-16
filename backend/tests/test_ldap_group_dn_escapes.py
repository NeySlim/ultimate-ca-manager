"""A group or base DN with an escaped comma is read the same by the LDAP login and its mapping test."""
import json
import logging
import uuid
from types import SimpleNamespace

import pytest

from models import db
from models.sso import SSOProvider
from tests.conftest import get_json

GROUP = 'Ops, Paris'
GROUP_DN = 'CN=Ops\\, Paris,OU=Groups\\, EU,dc=example,dc=test'
BASE_DN = 'ou=People\\, EU,dc=example,dc=test'
USER_DN = 'uid=probe,ou=People\\, EU,dc=example,dc=test'


class _Directory:
    """Finds the user, answers memberOf with GROUP_DN and a member search with GROUP under BASE_DN's parent."""

    def __init__(self):
        self.bases = []

    def connection(self, server, user=None, password=None, **kwargs):
        directory = self

        class _Conn:
            def __init__(self):
                self.user, self.entries = user, []

            def search(self, base, query, attributes=None):
                directory.bases.append(base)
                attributes = attributes or []
                if attributes == ['cn']:  # the member/uniqueMember group search
                    group = SimpleNamespace(cn=GROUP)
                    self.entries = [group] if base == 'dc=example,dc=test' else []
                    return
                entry = SimpleNamespace(entry_dn=USER_DN, uid='probe', mail='', cn='Probe')
                if 'memberOf' in attributes or attributes == ['*', '+']:
                    entry.memberOf = SimpleNamespace(values=[GROUP_DN])
                self.entries = [entry]

            def unbind(self):
                return None
        return _Conn()


def _patch(monkeypatch, directory):
    import ldap3
    import api.v2.sso.connection_tests as connection_tests
    import api.v2.sso.mapping_tests as mapping_tests
    monkeypatch.setattr(ldap3, 'Server', lambda *a, **k: object())
    monkeypatch.setattr(ldap3, 'Connection', directory.connection)
    for module in (connection_tests, mapping_tests):
        monkeypatch.setattr(module, '_build_ldap_tls', lambda provider: None)
        monkeypatch.setattr(module, '_decrypt_ldap_password', lambda provider: 'svc')
    monkeypatch.setattr(connection_tests, 'ldap_bind', lambda conn, provider: True)
    monkeypatch.setattr(connection_tests, '_check_account_disabled', lambda *a: False)


@pytest.fixture
def provider(app):
    def make(member_attr):
        with app.app_context():
            row = SSOProvider(
                name=f'escaped-ldap-{uuid.uuid4().hex[:6]}', provider_type='ldap', enabled=True,
                ldap_server='ldap.example.test', ldap_port=389, ldap_base_dn=BASE_DN,
                ldap_bind_dn='cn=svc,dc=example,dc=test',
                ldap_user_filter='(uid={username})', ldap_username_attr='uid',
                ldap_email_attr='mail', ldap_fullname_attr='cn',
                ldap_group_filter='(objectClass=group)', ldap_group_member_attr=member_attr,
                ldap_required_groups=json.dumps([GROUP]), role_mapping=json.dumps({GROUP: 'operator'}),
                default_role='viewer')
            db.session.add(row)
            db.session.commit()
            made.append(row.id)
            return row.id
    made = []
    yield make
    with app.app_context():
        for provider_id in made:
            SSOProvider.query.filter_by(id=provider_id).delete()
        db.session.commit()


@pytest.mark.parametrize('member_attr', ['memberOf', 'member'])
def test_the_mapping_test_reads_the_escaped_group_as_the_login_does(app, auth_client, monkeypatch, provider,
                                                                    member_attr, caplog):
    provider_id = provider(member_attr)
    directory = _Directory()
    _patch(monkeypatch, directory)

    r = auth_client.post(f'/api/v2/sso/providers/{provider_id}/test-mapping', json={'username': 'probe'})
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    assert data['groups'] == [GROUP]
    assert data['resolved_role'] == 'operator' and data['access_allowed'] is True

    # The login itself: the groups it logs are the same, so the dry run predicts it
    import api.v2.sso.connection_tests as connection_tests
    with app.app_context(), caplog.at_level(logging.INFO, logger=connection_tests.logger.name):
        row = db.session.get(SSOProvider, provider_id)
        row.ldap_required_groups = json.dumps(['Nobody'])
        connection_tests._ldap_authenticate_user(row, 'probe', 'pw')
        db.session.rollback()
    assert f"user groups: {[GROUP]}" in caplog.text
