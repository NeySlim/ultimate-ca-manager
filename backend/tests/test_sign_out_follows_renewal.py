"""A sign-out sent with the old cookie while a renewal moves the session to a new identifier
ends the session under its new identifier too.

The sign-out opened the record before the move and saves after it: the old record is gone,
and the move left a short-lived pointer to the new identifier, which the sign-out follows
(files, SQL on SQLite and on PostgreSQL shared by two nodes, Redis). A request that only
finds its session stale follows nothing: the renewed session stays.
"""
import pytest

from tests.test_factor_change_sessions import (  # noqa: F401 (fixtures)
    _cleanup, _drop_session_table_from_metadata, _make_user, _open_session, _post, _signed_in,
    nodes, PASSWORD)


def _change_password(c, new):
    r = _post(c, '/api/v2/account/password', {'current_password': PASSWORD, 'new_password': new})
    assert r.status_code == 200, r.data


def _close_other_sessions(c):
    assert _post(c, '/api/v2/account/sessions/revoke-all').status_code == 200


def _sign_out_opened_before(node, cookie, renewals):
    """Signs out with ``cookie``, its session read before ``renewals`` run and saved after."""
    from flask import request, session as flask_session
    from api.v2.auth import _sign_out
    from auth.unified import AuthManager
    with node.test_request_context('/api/v2/auth/logout', method='POST',
                                   headers={'Cookie': f'session={cookie}'}):
        assert AuthManager().authenticate_request(request) is not None
        renewals()
        _sign_out()
        response = node.response_class()
        node.session_interface.save_session(node, flask_session, response)
        return response


def _cookie_deleted(response):
    return any(h.startswith('session=;') for h in response.headers.getlist('Set-Cookie'))


@pytest.mark.parametrize('moves', [1, 2])
def test_a_sign_out_with_the_old_cookie_ends_the_renewed_session(nodes, moves):
    first_node, second_node = nodes
    user = _make_user(first_node)
    try:
        this = _open_session(first_node, user)
        old = this.get_cookie('session').value

        def renewals():
            _change_password(this, 'Renewed-Once-During-0ut!')
            if moves == 2:
                _close_other_sessions(this)
            assert this.get_cookie('session').value != old
            assert _signed_in(this)

        response = _sign_out_opened_before(second_node, old, renewals)
        assert _cookie_deleted(response)
        assert not _signed_in(this)
    finally:
        _cleanup(first_node, user)


def test_a_stale_request_during_the_renewal_leaves_the_renewed_session(nodes):
    """Only a sign-out follows the move: a request emptied for its replaced version does not."""
    from flask import request, session as flask_session
    from auth.unified import AuthManager
    first_node, second_node = nodes
    user = _make_user(first_node)
    try:
        this = _open_session(first_node, user)
        old = this.get_cookie('session').value
        with second_node.test_request_context('/api/v2/account/profile',
                                              headers={'Cookie': f'session={old}'}):
            _change_password(this, 'Renewed-While-Stale-0k!')
            assert AuthManager().authenticate_request(request) is None
            response = second_node.response_class()
            second_node.session_interface.save_session(second_node, flask_session, response)
        assert not _cookie_deleted(response)
        assert _signed_in(this)
    finally:
        _cleanup(first_node, user)


def test_the_pointer_left_by_a_move_is_never_a_session(nodes):
    """The old identifier opens nothing, and the account's session count ignores the pointer."""
    from utils.session_census import count_sessions
    from models import User, db
    first_node, _second_node = nodes
    user = _make_user(first_node)
    try:
        this = _open_session(first_node, user)
        old = this.get_cookie('session').value
        _change_password(this, 'Renewed-Pointer-Only-0k!')
        stale = first_node.test_client()
        stale.set_cookie('session', old)
        assert stale.get('/api/v2/account/profile').status_code == 401
        with first_node.app_context():
            row = db.session.get(User, user['id'])
            assert count_sessions(row, row.session_version) == 1
            db.session.remove()
    finally:
        _cleanup(first_node, user)
