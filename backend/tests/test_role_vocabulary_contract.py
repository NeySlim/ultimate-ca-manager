"""Four built-in roles, and every list of them says four.

`auth/permissions.ROLE_PERMISSIONS` defines admin, operator, auditor and
viewer. Three other places restated the list and two of them left `auditor`
out:

* `api/v2/users/management.py` -- the CSV bulk import -- checked against
  three names and **silently rewrote** anything else to `viewer`. An
  operator importing a file of auditors got viewers, with no error and no
  mention in the result. `viewer` has no `read:audit`, so the accounts
  created for people whose job is to read the audit log could not read it.
  The single-user route next door returns a 400 for an unknown role, so the
  same value was refused by one door and quietly changed by another.
* `api/v2/rbac.RESERVED_ROLE_NAMES` also had three, so a **custom** role
  could be created called `auditor`, sitting beside the built-in one of the
  same name. The other three names are refused with a 409.

A role vocabulary is not a matter of taste per file: it is the set the
permission table has entries for.
"""
import io
import json

import pytest

from auth.permissions import BUILTIN_ROLES, ROLE_PERMISSIONS

pytestmark = pytest.mark.usefixtures('drop_new_users')


class TestOneVocabulary:
    def test_the_builtin_roles_are_the_ones_with_permissions(self):
        assert set(BUILTIN_ROLES) == set(ROLE_PERMISSIONS)
        assert 'auditor' in BUILTIN_ROLES

    def test_no_module_restates_a_shorter_list(self):
        """A source scan: the two that drifted both drifted by omission, and
        a hard-coded list is how they got the chance."""
        import ast
        import os

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        builtins = set(BUILTIN_ROLES)

        for base, dirs, names in os.walk(here):
            dirs[:] = [d for d in dirs
                       if d not in ('__pycache__', 'tests', 'migrations')]
            for name in names:
                if not name.endswith('.py'):
                    continue
                path = os.path.join(base, name)
                if os.path.relpath(path, here) == os.path.join(
                        'auth', 'permissions.py'):
                    continue    # the definition itself
                try:
                    tree = ast.parse(open(path).read())
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.List, ast.Set, ast.Tuple)):
                        continue
                    values = [e.value for e in node.elts
                              if isinstance(e, ast.Constant)
                              and isinstance(e.value, str)]
                    if not values or len(values) != len(node.elts):
                        continue
                    chosen = set(values)
                    # A collection made only of built-in role names, but not
                    # all of them, is a copy that has already drifted.
                    if chosen and chosen < builtins and len(chosen) >= 3:
                        offenders.append(
                            f'{os.path.relpath(path, here)}:{node.lineno} '
                            f'{sorted(chosen)}')

        assert offenders == [], (
            'these restate the built-in roles and leave some out: '
            f'{offenders}. Use auth.permissions.BUILTIN_ROLES.')


class TestTheBulkImportDoesNotRewriteARole:
    def _csv(self, role):
        return (
            'username,email,full_name,role,password\n'
            f'bulkrole_{role},bulkrole_{role}@example.com,Bulk {role},'
            f'{role},Str0ng@Pass!{role[:3].title()}\n'
        )

    @pytest.mark.parametrize('role', sorted(ROLE_PERMISSIONS))
    def test_every_builtin_role_survives_the_import(self, auth_client, role):
        r = auth_client.post(
            '/api/v2/users/import',
            data={'file': (io.BytesIO(self._csv(role).encode()),
                           f'roles-{role}.csv')},
            content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data

        listing = auth_client.get('/api/v2/users?per_page=100').get_json() or {}
        rows = listing.get('data')
        if isinstance(rows, dict):
            rows = rows.get('items') or rows.get('users') or []
        made = next((u for u in rows
                     if u.get('username') == f'bulkrole_{role}'), None)
        assert made is not None, f'the import did not create the {role} row'
        assert made['role'] == role, (
            f'a {role} row was imported as {made["role"]}: the import rewrote '
            'a role the rest of the product accepts, and said nothing')

    def test_a_role_that_is_not_a_role_is_reported_not_rewritten(
            self, auth_client):
        r = auth_client.post(
            '/api/v2/users/import',
            data={'file': (io.BytesIO(self._csv('wizard').encode()),
                           'roles-wizard.csv')},
            content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        body = (r.get_json() or {}).get('data') or {}
        errors = json.dumps(body.get('errors') or [])
        assert 'wizard' in errors or body.get('skipped'), (
            'an unknown role was accepted and turned into a viewer without '
            f'a word: {json.dumps(body)[:200]}')


class TestABuiltinRoleNameIsReserved:
    @pytest.mark.parametrize('name', sorted(ROLE_PERMISSIONS))
    def test_a_custom_role_cannot_take_it(self, auth_client, name):
        r = auth_client.post(
            '/api/v2/rbac/roles',
            data=json.dumps({'name': name, 'description': 'collision',
                             'permissions': ['read:certificates']}),
            content_type='application/json')
        assert r.status_code == 409, (
            f'a custom role called {name!r} was created beside the built-in '
            f'one of the same name (answered {r.status_code})')
