"""Regression tests for the API-key permission-resource validator (PR #178).

`POST /api/v2/account/apikeys` rejects any scope whose resource is not in
`auth.permissions.VALID_RESOURCES`. The original bug was a hardcoded list that had
drifted from the scopes `@require_auth` actually enforces (so valid scopes like
`write:csrs` were rejected). Deriving `VALID_RESOURCES` purely from `ROLE_PERMISSIONS`
fixed that but re-introduced a narrower drift: admin-only resources (`users`, `system`,
`sso`) are reachable only through the `*` wildcard, so they never appear in a named
role's scope list and were dropped — meaning an admin could no longer mint an API key
scoped to user management, system/discovery, or SSO config.

These tests pin the invariant so it can't drift again: the set of resources an API key
may be scoped to must cover EVERY resource the app enforces via `@require_auth`.
"""
import ast
import os

from auth.permissions import VALID_RESOURCES

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKIP_DIRS = {"tests", "migrations", "__pycache__", "venv", ".venv", "node_modules", ".git"}
_ACTIONS = {"read", "write", "delete", "admin"}


def _resources_in_call(call):
    """Yield resource names from the string scopes passed to a require_auth(...) call.

    Walks the call so both `require_auth(['read:users'])` and `require_auth('read:users')`
    (and multiple scopes) are covered. Only literal scopes are seen — which is exactly the
    enforced surface we care about.
    """
    for node in ast.walk(call):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and ":" in node.value:
            action, _, resource = node.value.partition(":")
            if action in _ACTIONS and resource and resource != "*":
                yield resource


def enforced_resources():
    """Map every resource referenced in a real `@require_auth(...)` decorator across the
    backend to an example file. AST-based, so docstring 'Usage:' examples are ignored."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(BACKEND_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in node.decorator_list:
                    if not isinstance(dec, ast.Call):
                        continue
                    name = dec.func.attr if isinstance(dec.func, ast.Attribute) else getattr(dec.func, "id", None)
                    if name != "require_auth":
                        continue
                    for res in _resources_in_call(dec):
                        found.setdefault(res, os.path.relpath(path, BACKEND_ROOT))
    return found


def test_valid_resources_covers_every_enforced_scope():
    """VALID_RESOURCES must be a superset of every resource `@require_auth` enforces —
    otherwise an admin can't scope an API key to a route the server actually guards."""
    enforced = enforced_resources()
    missing = {r: loc for r, loc in enforced.items() if r not in VALID_RESOURCES}
    assert not missing, (
        "VALID_RESOURCES is missing resources that @require_auth enforces "
        "(API keys can't be scoped to them): "
        + ", ".join(f"{r} (e.g. {loc})" for r, loc in sorted(missing.items()))
    )


def test_valid_resources_includes_known_regressions():
    """Explicit anchors for the exact resources behind the PR #178 bug + the collateral
    regression it introduced."""
    for resource in ("csrs", "users", "system", "sso"):
        assert resource in VALID_RESOURCES, (
            f"{resource!r} is enforced by @require_auth but not scope-able on an API key"
        )
