"""What a route does when the commit it asked for did not happen.

`safe_commit` answers a pair: whether the commit went through, and the
response to send when it did not. Eight routes tested the pair itself rather
than its first half, and a non-empty tuple is always true, so
`if not safe_commit(...)` never ran its own error branch: the commit failed,
the session was rolled back, and the route carried on to announce a success.

What that produced, measured on the ACME external-account credentials: a 201
carrying `"id": null` and the one-time HMAC key of a credential that does not
exist, an audit entry recording a creation that was undone, and a setting
answered as saved that the next request does not see.
"""
import pytest

from models import db


@pytest.fixture
def commit_always_fails(monkeypatch, auth_client):
    """Make the next db.session.commit() fail the way a busy database does.

    `safe_commit` catches it, rolls back and answers (False, response). The
    session stays usable afterwards, which is the point of the rollback.
    """
    import utils.db_transaction as transaction

    # A client whose session an earlier restore revoked signs in again here,
    # while commits still work: the login itself commits.
    assert auth_client.get('/api/v2/acme/eab-credentials').status_code == 200

    real_commit = transaction.db.session.commit
    calls = {'n': 0}

    def failing_commit():
        calls['n'] += 1
        raise RuntimeError('database is locked')

    monkeypatch.setattr(transaction.db.session, 'commit', failing_commit,
                        raising=False)
    yield calls
    monkeypatch.setattr(transaction.db.session, 'commit', real_commit,
                        raising=False)


@pytest.fixture
def session_revoked(auth_client):
    """What a restore earlier in the worker leaves: a client signed out."""
    auth_client._client.post('/api/v2/auth/logout')


class TestTheFailingCommitMeetsASignedInClient:
    def test_a_revoked_session_does_not_turn_the_failure_into_a_login_error(
            self, auth_client, session_revoked, commit_always_fails):
        response = auth_client.put('/api/v2/acme/eab-required',
                                   json={'eab_required': True})

        assert response.status_code == 500
        assert commit_always_fails['n'] >= 1


class TestTheAnswerIsAPair:
    def test_the_pair_is_never_falsy(self):
        """The reason the mistake is silent: both halves of the answer are
        wrapped in a tuple, and a tuple with two items is true whatever they
        are. A route that tests the pair tests nothing."""
        refusal = (False, 'the response safe_commit would have sent')

        assert bool(refusal) is True
        assert (not refusal) is False

    def test_no_route_tests_the_pair_instead_of_its_first_half(self):
        """Read from the parsed source, not from its text.

        A scan by regular expression sees the mistake in a comment or in the
        prose of a docstring as readily as in code, so a single line of
        explanation anywhere in the tree could fail this test, or a call
        written across two lines could slip past it. The `if` statements are
        asked of the syntax tree instead.

        Kept as a test rather than as a comment: it is the only thing that
        stops the ninth occurrence from being written."""
        import ast
        import os

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def calls_safe_commit(node):
            call = node.operand if isinstance(node, ast.UnaryOp) else node
            return (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == 'safe_commit')

        wrong = []
        for zone in ('api', 'services', 'utils', 'auth', 'security'):
            for base, _dirs, names in os.walk(os.path.join(here, zone)):
                if '__pycache__' in base:
                    continue
                for name in names:
                    if not name.endswith('.py'):
                        continue
                    path = os.path.join(base, name)
                    try:
                        tree = ast.parse(open(path).read())
                    except SyntaxError:
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, ast.If) and calls_safe_commit(node.test):
                            wrong.append(
                                f'{os.path.relpath(path, here)}:{node.lineno}')
        assert wrong == [], (
            'these call sites test the pair safe_commit returns instead of '
            f'unpacking it, so their error branch can never run: {wrong}. '
            'Write `ok, err = safe_commit(...)` then `if not ok: return err`.')


class TestARouteDoesNotAnnounceWhatItDidNotWrite:
    """The route that loses the most when it gets this wrong.

    An external-account credential is shown its HMAC key once, by design. A
    201 for a credential that was rolled back hands the operator a secret
    that opens nothing, and the real one is never issued.
    """

    def test_a_failed_commit_is_not_answered_as_a_creation(
            self, app, auth_client, commit_always_fails):
        response = auth_client.post(
            '/api/v2/acme/eab-credentials',
            json={'label': 'safe-commit-contract'})

        assert commit_always_fails['n'] >= 1, 'the commit was never attempted'
        assert response.status_code == 500, (
            f'the route answered {response.status_code} for a credential the '
            'database never took')

        with app.app_context():
            from models.acme_models import AcmeEabCredential
            assert AcmeEabCredential.query.filter_by(
                label='safe-commit-contract').count() == 0

    def test_a_failed_commit_does_not_answer_a_setting_as_saved(
            self, app, auth_client, commit_always_fails):
        """`eab_required` decides whether an ACME account may register
        without an external binding. Answered as saved and not written, the
        operator believes the admission control is on."""
        response = auth_client.put('/api/v2/acme/eab-required',
                                   json={'eab_required': True})

        assert response.status_code == 500, (
            f'the route answered {response.status_code} for a setting the '
            'database never took')
