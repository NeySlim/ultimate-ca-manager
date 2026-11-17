"""Who may collect an approved key recovery.

The rule is written in the route: the original requester, or an administrator.
Two functions named `has_permission` live in the authentication package with
their arguments in opposite orders, and this route imported one and called it
the way the other expects. `get_role_permissions('admin:key_recovery')` finds
no role by that name and answers an empty list, so the administrator half of
the rule answered False for everyone, silently and without raising.

The failure is closed, not open: nobody gained anything, an administrator who
was not the requester was refused while the interface offered them the action.
What is lost is the dual-control path, with its `recovered_by` and its event,
since an administrator can still read the key through the export route.
"""
import pytest

from models import db


class TestTheTwoSpellingsOfTheSameQuestion:
    def test_the_route_asks_the_function_it_imported(self):
        """The two functions take their arguments in opposite orders, so the
        call has to match the import. Every other caller in the API uses the
        one that takes (required, permissions)."""
        import inspect

        from auth.permissions import has_permission as by_role
        from auth.unified import has_permission as by_permissions

        assert list(inspect.signature(by_role).parameters) == [
            'user_role', 'required_permission']
        assert list(inspect.signature(by_permissions).parameters) == [
            'required', 'user_permissions']

    def test_asking_the_wrong_one_answers_no_to_everything(self, app):
        """What the mistake produced, kept as a test so the shape of the bug
        stays legible: a role name in the permission slot finds no role."""
        from auth.permissions import get_role_permissions, has_permission

        with app.app_context():
            assert get_role_permissions('admin:key_recovery') == []
            assert has_permission('admin:key_recovery',
                                  ['admin:key_recovery']) is False
            assert has_permission('admin', 'admin:key_recovery') is True


class TestAnAdministratorMayCollectTheKey:
    def test_an_admin_who_is_not_the_requester_is_not_refused(
            self, app, auth_client, create_ca, create_cert):
        """The administrator half of the rule, exercised end to end."""
        from models.key_recovery import KeyRecoveryRequest

        ca = create_ca(cn='Key Recovery Override CA')
        cert = create_cert(cn='recovery-override.example.test', ca_id=ca['id'])

        with app.app_context():
            request_row = KeyRecoveryRequest(
                cert_id=cert['id'], requested_by='someone-else',
                reason='override test', status='approved')
            db.session.add(request_row)
            db.session.commit()
            rid = request_row.id

        try:
            response = auth_client.post(
                f'/api/v2/key-recovery/{rid}/recover',
                json={'password': 'recovery-password'})

            assert response.status_code != 403, (
                'the administrator was refused their own override: the rule '
                'says "the requester or an admin" and the admin half never '
                'answered yes')
        finally:
            with app.app_context():
                row = db.session.get(KeyRecoveryRequest, rid)
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()
