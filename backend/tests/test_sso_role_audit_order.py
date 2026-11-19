"""A role change is recorded once it has been made, not before.

`_get_or_create_sso_user` synchronises the role an identity provider reports
onto the local account. The entry saying the role changed used to be written
before the assignment and before the commit, and `AuditService.log_action`
commits the session it is given: the entry decided whether the identity
binding made a few lines above survived, while the assignment it described
had not happened yet.

Two things are pinned here: the entry names the change that was actually
made, and it is not written at all when the change is rolled back.
"""
import pytest

from models import db, AuditLog, User


@pytest.fixture
def make_provider(app):
    """Providers and accounts made here are removed afterwards.

    The suite shares one database and does not roll back between tests, so a
    provider left enabled is one the next test finds. Leaving one behind made
    `test_ldap_login_no_enabled_provider` fail, which is the right answer to
    the wrong question.
    """
    from models.sso import SSOProvider

    made = []

    def _make(**overrides):
        settings = {
            'name': 'role-order-probe',
            'provider_type': 'ldap',
            'enabled': True,
            'auto_create_users': True,
            'default_role': 'viewer',
        }
        settings.update(overrides)
        with app.app_context():
            row = SSOProvider(**settings)
            db.session.add(row)
            db.session.commit()
            made.append(row.id)
            return row.id

    yield _make

    with app.app_context():
        for provider_id in made:
            User.query.filter_by(sso_provider_id=provider_id).delete(
                synchronize_session=False)
            SSOProvider.query.filter_by(id=provider_id).delete(
                synchronize_session=False)
        db.session.commit()


class TestTheRoleChangeIsRecordedAfterItIsMade:
    def test_the_entry_names_the_change_that_was_committed(
            self, app, make_provider):
        """The account really holds the new role, and the entry says so."""
        from api.v2.sso.ldap_routes import _get_or_create_sso_user
        from models.sso import SSOProvider

        provider_id = make_provider(
            role_mapping='{"pki-admins": "admin"}',
            sync_role_on_login=True)

        with app.app_context():
            existing = User(username='role-order-probe-user',
                            email='probe@example.test', role='viewer',
                            active=True, auth_source='ldap')
            existing.set_password('unused-by-sso-logins')
            existing.sso_provider_id = provider_id
            db.session.add(existing)
            db.session.commit()

            provider = db.session.get(SSOProvider, provider_id)
            user, err = _get_or_create_sso_user(
                provider, 'role-order-probe-user', 'probe@example.test',
                'Probe User', {'groups': ['pki-admins']})
            assert err is None, err
            assert user.role == 'admin', (
                f'the role was not actually changed: {user.role}')

            entry = AuditLog.query.filter_by(
                action='role_change',
                resource_name='role-order-probe-user').first()
            assert entry is not None, 'the change was made and not recorded'
            assert 'viewer' in entry.details and 'admin' in entry.details, (
                f'the entry does not name the change made: {entry.details}')

    def test_the_ledger_never_claims_a_role_the_account_does_not_hold(
            self, app, make_provider, monkeypatch):
        """The distinguishing case: the audit's own commit succeeds and the
        one after it fails.

        Written first, the entry went in on its own commit and the assignment
        that followed was rolled back, so the ledger said the account was an
        administrator while the account was still a viewer. Written after, the
        assignment is what committed first; an entry that cannot then be
        written is a missing line, not a false one.

        Failing the *second* commit is what separates the two. Failing every
        commit proves nothing, because `log_action` commits too and simply
        writes nothing when it cannot.
        """
        from api.v2.sso.ldap_routes import _get_or_create_sso_user
        from models.sso import SSOProvider

        provider_id = make_provider(
            name='role-order-probe-2',
            role_mapping='{"pki-admins": "admin"}', sync_role_on_login=True)

        with app.app_context():
            existing = User(username='role-order-refused',
                            email='refused@example.test', role='viewer',
                            active=True, auth_source='ldap')
            existing.set_password('unused-by-sso-logins')
            existing.sso_provider_id = provider_id
            db.session.add(existing)
            db.session.commit()

            real_commit = db.session.commit
            calls = {'n': 0}

            def _second_one_fails():
                calls['n'] += 1
                if calls['n'] == 2:
                    raise RuntimeError('commit refused')
                return real_commit()

            provider = db.session.get(SSOProvider, provider_id)
            monkeypatch.setattr(db.session, 'commit', _second_one_fails,
                                raising=False)
            _get_or_create_sso_user(
                provider, 'role-order-refused', 'refused@example.test',
                'Refused User', {'groups': ['pki-admins']})
            monkeypatch.undo()

            db.session.expire_all()
            held = db.session.query(User).filter_by(
                username='role-order-refused').first().role
            entry = AuditLog.query.filter_by(
                action='role_change',
                resource_name='role-order-refused').first()

            if entry is not None:
                assert held == 'admin', (
                    'the ledger records a role change the account does not '
                    f'hold: it says {entry.details!r} and the account is '
                    f'{held!r}')


class TestADisabledAccountIsNotSynchronised:
    """A login that is going to be refused writes nothing on the way.

    All three callers refuse a disabled account a few lines after asking for
    it, but the synchronisation had already run: the directory's email, full
    name and role were written to the record, a `last_login` was stamped for
    a login that did not happen, and an audit line said the role changed.

    The one that outlives the attempt is `sso_external_id`. It is bound once,
    on first use, and it is what decides whose account this is. Bound while
    the account was disabled, it hands that account to whoever held the
    identifier at the directory the day it is switched back on.
    """

    def test_nothing_about_the_account_is_touched(self, app, make_provider):
        from api.v2.sso.ldap_routes import _get_or_create_sso_user
        from models.sso import SSOProvider

        provider_id = make_provider(
            name='disabled-account-probe',
            role_mapping='{"pki-admins": "admin"}',
            sync_role_on_login=True, auto_update_users=True)

        with app.app_context():
            disabled = User(username='disabled-sso-user',
                            email='old@example.test', role='viewer',
                            full_name='Old Name', active=False,
                            auth_source='ldap')
            disabled.set_password('unused-by-sso-logins')
            disabled.sso_provider_id = provider_id
            db.session.add(disabled)
            db.session.commit()

            provider = db.session.get(SSOProvider, provider_id)
            user, err = _get_or_create_sso_user(
                provider, 'disabled-sso-user', 'new@example.test',
                'New Name',
                {'groups': ['pki-admins'], 'sub': 'attacker-controlled-id'})

            assert err is None
            assert user is not None and not user.active, (
                'the caller still needs the account back in order to refuse it')

            db.session.expire_all()
            again = User.query.filter_by(username='disabled-sso-user').first()
            assert again.role == 'viewer', (
                f'a refused login re-synchronised the role: {again.role}')
            assert again.email == 'old@example.test', (
                f'a refused login rewrote the email: {again.email}')
            assert again.full_name == 'Old Name', (
                f'a refused login rewrote the name: {again.full_name}')
            assert again.last_login is None, (
                'a refused login was stamped as a login')
            assert again.sso_external_id is None, (
                'a refused login bound an external identifier to a disabled '
                'account, which is who the account belongs to once it is '
                'switched back on')

            assert AuditLog.query.filter_by(
                action='role_change',
                resource_name='disabled-sso-user').first() is None, (
                'the ledger records a role change for a refused login')
