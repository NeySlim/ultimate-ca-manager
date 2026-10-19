"""Every scope a route checks is either grantable by a custom role or reserved.

A new @require_auth scope that nobody classified would be silently refused to
every custom role, or, the other way round, a reserved one could drift into the
grantable list. Both fail here.
"""
import re
from pathlib import Path

from auth.permissions import (
    CUSTOM_ROLE_GRANTABLE_PERMISSIONS, ENFORCED_PERMISSIONS, INLINE_CHECKED_PERMISSIONS,
    RESERVED_PERMISSIONS, custom_role_permissions, is_reserved_permission,
)
from models.rbac import CustomRole

BACKEND = Path(__file__).resolve().parent.parent

# Roles created on first start (app.py): none of their permissions may be lost.
SEEDED = ['Operator', 'Auditor', 'Viewer', 'Certificate Manager', 'CA Administrator',
          'Security Auditor']


def _checked(app):
    assert ENFORCED_PERMISSIONS, 'no route recorded its scopes'
    return ENFORCED_PERMISSIONS | INLINE_CHECKED_PERMISSIONS


def test_every_checked_scope_is_classified(app):
    unclassified = sorted(p for p in _checked(app)
                          if p not in CUSTOM_ROLE_GRANTABLE_PERMISSIONS
                          and not is_reserved_permission(p))
    assert not unclassified, f'classify as grantable or reserved: {unclassified}'


def test_grantable_and_reserved_do_not_overlap(app):
    assert not [p for p in CUSTOM_ROLE_GRANTABLE_PERMISSIONS if is_reserved_permission(p)]


def test_no_grantable_scope_is_dead(app):
    dead = sorted(set(CUSTOM_ROLE_GRANTABLE_PERMISSIONS) - _checked(app))
    assert not dead, f'grantable but checked by no route: {dead}'


def test_every_reservation_is_a_real_scope(app):
    assert not sorted(set(RESERVED_PERMISSIONS) - _checked(app))


def test_inline_checks_are_declared():
    """Inventory, not behaviour: has_permission() literals outside the decorator."""
    found = set()
    for path in BACKEND.rglob('*.py'):
        if 'tests' in path.parts or '.venv' in path.parts:
            continue
        found |= set(re.findall(r"has_permission\(\s*['\"]([a-z_]+:[a-z_]+)['\"]",
                                path.read_text(errors='replace')))
    assert found <= INLINE_CHECKED_PERMISSIONS, sorted(found - INLINE_CHECKED_PERMISSIONS)


def test_seeded_roles_keep_every_checked_permission(app):
    with app.app_context():
        for name in SEEDED:
            role = CustomRole.query.filter_by(name=name).first()
            assert role is not None, name
            granted = set(custom_role_permissions(role))
            lost = [p for p in role.permissions or [] if p in _checked(app) and p not in granted]
            assert not lost, f'{name} loses {lost}'
