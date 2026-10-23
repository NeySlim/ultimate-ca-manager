"""
Guard: every admin-bootstrap seeding site must construct a User the way the
canonical bootstrap paths do — not merely with kwargs that happen to be
mapped columns.

SQLAlchemy's declarative constructor raises TypeError on any non-mapped
keyword, so a drifted kwarg (`is_active=True` where the column is `active`)
turns the seeding path into a crash — harmless in backend/init_db.py (a
manual fallback script), destructive in POST /api/v2/system/database/reset,
where the TypeError fired AFTER drop_all() and left a wiped database with no
admin user, masked as a generic "Database reset failed".

Valid kwarg NAMES are not enough, though: the reset endpoint once passed
only mapped columns yet still hard-coded 'admin'/'admin@localhost' (a
deployment with INITIAL_ADMIN_USERNAME set got the WRONG admin back from a
UI button), skipped totp_exempt (under global 2FA enforcement the recreated
admin had no enrolled device and no exemption — the exact lockout #141
exists to prevent), and bypassed the hash pin in User.set_password() with
a bare generate_password_hash(). The canonical-shape test below asserts the
three properties every seeding site must agree on.

The seeding call sites are parsed from source (AST) so a future rename or a
new kwarg is caught without anyone remembering to update this test. No app
or database is needed, so this also runs on hosts where the shared `app`
fixture cannot start.
"""
import ast
from pathlib import Path

import pytest

from models import User

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Every file that seeds the bootstrap admin via User(...).
SEEDING_FILES = [
    BACKEND_DIR / 'init_db.py',
    BACKEND_DIR / 'app.py',
    BACKEND_DIR / 'database_health.py',
    BACKEND_DIR / 'api' / 'v2' / 'system' / 'database.py',
]


def _user_call_kwargs(path):
    """Yield (lineno, {kwarg names}) for every `User(...)` call in the file."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'User'
        ):
            names = {kw.arg for kw in node.keywords if kw.arg is not None}
            yield node.lineno, names


def _mapped_names():
    return {attr.key for attr in User.__mapper__.attrs}


def test_user_model_has_no_is_active_attribute():
    """The column is `active`; if this ever changes, update the seeders too."""
    mapped = _mapped_names()
    assert 'active' in mapped
    assert 'is_active' not in mapped


@pytest.mark.parametrize('path', SEEDING_FILES, ids=lambda p: p.name)
def test_seeding_call_sites_only_use_mapped_kwargs(path):
    mapped = _mapped_names()
    calls = list(_user_call_kwargs(path))
    assert calls, f"expected at least one User(...) call in {path}"
    for lineno, names in calls:
        unknown = names - mapped
        assert not unknown, (
            f"{path.name}:{lineno} passes non-mapped kwargs {sorted(unknown)} "
            f"to User(...) — SQLAlchemy will raise TypeError when this runs"
        )


CONFIG_MARKERS = ('INITIAL_ADMIN_USERNAME', 'INITIAL_ADMIN_EMAIL',
                  'INITIAL_ADMIN_PASSWORD')


def _seed_facts(path):
    """Extract, from one seeding file:
    - the kwarg map (name -> value AST node) of every User(...) call,
    - the argument nodes of every ``<obj>.set_password(...)`` call,
    - the attribute names assigned True after construction
      (``admin.totp_exempt = True`` — the app.py/database_health.py style),
      and those assigned ``initial_password_needs_change(...)``,
    - per config marker, the local names bound from an expression that
      references it (``admin_username = app.config.get(...)`` — the
      init_db.py style).
    """
    tree = ast.parse(path.read_text(encoding='utf-8'))
    calls = []
    set_password_args = []
    true_attr_assigns = set()
    gated_attr_assigns = set()
    config_bound = {marker: set() for marker in CONFIG_MARKERS}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'User':
                calls.append({kw.arg: kw.value for kw in node.keywords if kw.arg})
            elif isinstance(node.func, ast.Attribute) and node.func.attr == 'set_password':
                set_password_args.extend(node.args)
        elif isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Constant) and node.value.value is True:
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute):
                        true_attr_assigns.add(tgt.attr)
            elif _is_needs_change_call(node.value):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute):
                        gated_attr_assigns.add(tgt.attr)
            else:
                value_dump = ast.dump(node.value)
                for marker in CONFIG_MARKERS:
                    if marker in value_dump:
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name):
                                config_bound[marker].add(tgt.id)
    return calls, set_password_args, true_attr_assigns, gated_attr_assigns, config_bound


def _is_needs_change_call(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'initial_password_needs_change')


def _comes_from(marker, node, config_bound):
    """True when `node` references the config marker directly, or is a local
    name bound from an expression that does (one level of indirection)."""
    if node is None:
        return False
    if marker in ast.dump(node):
        return True
    return isinstance(node, ast.Name) and node.id in config_bound[marker]


@pytest.mark.parametrize('path', SEEDING_FILES, ids=lambda p: p.name)
def test_seeding_sites_match_the_canonical_bootstrap_shape(path):
    """Every seeding site must agree with app.py/database_health.py on the
    identity source, the 2FA exemption, and the password-hashing helper —
    kwarg-name validity alone let all three regress unseen in the reset
    endpoint."""
    calls, set_password_args, true_attr_assigns, gated_attr_assigns, config_bound = _seed_facts(path)
    assert calls, f"expected at least one User(...) call in {path}"

    for kwargs in calls:
        # 1. Identity comes from configuration, never a literal: a reset on
        #    a deployment with INITIAL_ADMIN_USERNAME set must recreate THAT
        #    admin, not 'admin'.
        username = kwargs.get('username')
        assert username is not None, f"{path.name}: User(...) without username="
        assert _comes_from('INITIAL_ADMIN_USERNAME', username, config_bound), (
            f"{path.name}: seeded username must come from "
            f"INITIAL_ADMIN_USERNAME, not a hard-coded literal"
        )
        email = kwargs.get('email')
        assert _comes_from('INITIAL_ADMIN_EMAIL', email, config_bound), (
            f"{path.name}: seeded email must come from INITIAL_ADMIN_EMAIL"
        )

        # 2. The password goes through User.set_password(), which pins the
        #    hash algorithm — never a password_hash= kwarg built elsewhere.
        assert 'password_hash' not in kwargs, (
            f"{path.name}: pass the password through set_password() (hash "
            f"pin, models/user.py), not a precomputed password_hash="
        )

        # 3. The 2FA-lockout exemption (#141), and a forced rotation decided
        #    by the one rule (only the public default password), either as
        #    constructor kwargs or assigned right after construction.
        exempt = kwargs.get('totp_exempt')
        assert (isinstance(exempt, ast.Constant) and exempt.value is True) \
            or 'totp_exempt' in true_attr_assigns, (
                f"{path.name}: seeded admin must set totp_exempt=True "
                f"(kwarg or attribute assignment)"
            )
        assert _is_needs_change_call(kwargs.get('force_password_change')) \
            or 'force_password_change' in gated_attr_assigns, (
                f"{path.name}: force_password_change must come from "
                f"initial_password_needs_change(<INITIAL_ADMIN_PASSWORD>)"
            )

    assert any(
        _comes_from('INITIAL_ADMIN_PASSWORD', arg, config_bound)
        for arg in set_password_args
    ), (
        f"{path.name}: the seeded password must be "
        f"set_password(<INITIAL_ADMIN_PASSWORD>)"
    )


def test_seeding_kwargs_construct_a_user():
    """Belt and braces: the exact kwarg shape used by the fixed seeders must
    construct without TypeError and land on the right attributes."""
    user = User(
        username='seed-guard',
        email='seed-guard@example.test',
        password_hash='x',
        role='admin',
        active=True,
        force_password_change=True,
        totp_exempt=True,
    )
    assert user.active is True
    assert user.force_password_change is True
    assert user.totp_exempt is True
