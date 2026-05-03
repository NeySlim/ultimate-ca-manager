"""Tests for utils.db_transaction helpers.

Both ``safe_commit`` (API-layer, returns Flask response) and
``commit_or_rollback`` (service-layer, returns bool) must:
- return success when commit() works
- rollback + log + return failure when commit() raises
"""

import logging
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_logger():
    return MagicMock(spec=logging.Logger)


def test_safe_commit_success(app, fake_logger):
    """safe_commit returns (True, None) on success."""
    from utils.db_transaction import safe_commit
    with app.app_context(), patch("utils.db_transaction.db.session.commit") as commit:
        ok, err = safe_commit(fake_logger)
    assert ok is True
    assert err is None
    commit.assert_called_once()
    fake_logger.error.assert_not_called()


def test_safe_commit_rollback_on_failure(app, fake_logger):
    """safe_commit rolls back, logs with traceback, and returns Flask error response."""
    from utils.db_transaction import safe_commit
    with app.app_context(), \
         patch("utils.db_transaction.db.session.commit", side_effect=RuntimeError("boom")) as commit, \
         patch("utils.db_transaction.db.session.rollback") as rollback:
        ok, err = safe_commit(fake_logger, "Custom message")
    assert ok is False
    assert err is not None  # Flask response tuple
    commit.assert_called_once()
    rollback.assert_called_once()
    # exc_info=True for traceback
    fake_logger.error.assert_called_once()
    args, kwargs = fake_logger.error.call_args
    assert "Custom message" in args[0]
    assert "boom" in args[0]
    assert kwargs.get("exc_info") is True


def test_commit_or_rollback_success(app, fake_logger):
    """commit_or_rollback returns True on success."""
    from utils.db_transaction import commit_or_rollback
    with app.app_context(), patch("utils.db_transaction.db.session.commit") as commit:
        result = commit_or_rollback(fake_logger)
    assert result is True
    commit.assert_called_once()
    fake_logger.error.assert_not_called()


def test_commit_or_rollback_failure(app, fake_logger):
    """commit_or_rollback rolls back, logs with traceback, returns False."""
    from utils.db_transaction import commit_or_rollback
    with app.app_context(), \
         patch("utils.db_transaction.db.session.commit", side_effect=RuntimeError("kaboom")) as commit, \
         patch("utils.db_transaction.db.session.rollback") as rollback:
        result = commit_or_rollback(fake_logger, "while updating widget")
    assert result is False
    commit.assert_called_once()
    rollback.assert_called_once()
    fake_logger.error.assert_called_once()
    args, kwargs = fake_logger.error.call_args
    assert "while updating widget" in args[0]
    assert "kaboom" in args[0]
    assert kwargs.get("exc_info") is True


def test_callsites_use_commit_or_rollback():
    """Critical auth/mTLS/WebAuthn paths must use commit_or_rollback,
    not bare db.session.commit() — bare commits can crash the auth flow
    without rollback if the DB is degraded."""
    import ast
    import os

    base = os.path.join(os.path.dirname(__file__), "..")
    targets = [
        ("auth/unified.py", 2),
        ("services/mtls_auth_service.py", 4),
        ("services/webauthn_service.py", 4),
    ]
    for rel, expected_helper_calls in targets:
        path = os.path.join(base, rel)
        src = open(path).read()
        tree = ast.parse(src)

        bare = 0
        helper = 0
        for node in ast.walk(tree):
            # Count bare db.session.commit() not wrapped in a Try
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "commit":
                    v = node.func.value
                    if isinstance(v, ast.Attribute) and v.attr == "session":
                        # Check if any enclosing Try wraps it
                        wrapped = False
                        for parent in ast.walk(tree):
                            if isinstance(parent, ast.Try):
                                for stmt in ast.walk(parent):
                                    if stmt is node:
                                        wrapped = True
                                        break
                                if wrapped:
                                    break
                        if not wrapped:
                            bare += 1
                elif node.func.attr == "commit_or_rollback" or (
                    isinstance(node.func, ast.Name) and node.func.id == "commit_or_rollback"
                ):
                    helper += 1
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "commit_or_rollback":
                    helper += 1

        assert bare == 0, f"{rel} still has {bare} bare db.session.commit() outside try/except"
        assert helper >= expected_helper_calls, (
            f"{rel} should have at least {expected_helper_calls} commit_or_rollback() "
            f"calls, found {helper}"
        )
