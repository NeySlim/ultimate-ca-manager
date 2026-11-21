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

Every seeding path now delegates to auth.initial_admin.seed_admin(), the one
place that builds the account: the paths are parsed (AST) to hold that, and
seed_admin() itself is checked by running it.
"""
import ast
from pathlib import Path

import pytest

from models import User

BACKEND_DIR = Path(__file__).resolve().parent.parent

CANONICAL = BACKEND_DIR / 'auth' / 'initial_admin.py'
# Every file that seeds the bootstrap admin, through seed_admin().
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


def test_seeding_call_sites_only_use_mapped_kwargs():
    path = CANONICAL
    mapped = _mapped_names()
    calls = list(_user_call_kwargs(path))
    assert calls, f"expected at least one User(...) call in {path}"
    for lineno, names in calls:
        unknown = names - mapped
        assert not unknown, (
            f"{path.name}:{lineno} passes non-mapped kwargs {sorted(unknown)} "
            f"to User(...) — SQLAlchemy will raise TypeError when this runs"
        )


def _calls_seed_admin(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None)
            if name == 'seed_admin':
                return True
    return False


@pytest.mark.parametrize('path', SEEDING_FILES, ids=lambda p: p.name)
def test_seeding_paths_delegate_to_the_one_builder(path):
    """A second builder would drift from the first, as the reset endpoint once did."""
    assert _calls_seed_admin(path), f"{path.name} must create the admin through seed_admin()"
    assert not list(_user_call_kwargs(path)), f"{path.name} builds a User(...) of its own"


@pytest.mark.parametrize('provided', [True, False], ids=['provided', 'generated'])
def test_seed_admin_builds_the_configured_exempt_account(app, tmp_path, provided):
    """Identity from configuration, the #141 exemption, set_password(), forced only when generated."""
    from auth.initial_admin import MARKER_KEY, PASSWORD_FILE_NAME, seed_admin
    from models import SystemConfig, db
    config = {'INITIAL_ADMIN_USERNAME': 'seed-guard-admin', 'INITIAL_ADMIN_EMAIL': 'seed@example.test',
              'DATA_DIR': str(tmp_path)}
    if provided:
        config['INITIAL_ADMIN_PASSWORD'] = 'Seed-Guard-Pass-1!'
    with app.app_context():
        try:
            admin = seed_admin(config)
            db.session.flush()
            assert (admin.username, admin.email, admin.role) == ('seed-guard-admin', 'seed@example.test', 'admin')
            assert admin.active is True and admin.totp_exempt is True
            assert admin.force_password_change is (not provided)
            marker = SystemConfig.query.filter_by(key=MARKER_KEY).first()
            if provided:
                assert admin.check_password('Seed-Guard-Pass-1!')
                assert not (tmp_path / PASSWORD_FILE_NAME).exists()
            else:
                value = (tmp_path / PASSWORD_FILE_NAME).read_text().rstrip('\n')
                assert admin.check_password(value)
                assert marker is not None and str(admin.id) in marker.value
        finally:
            db.session.rollback()


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
