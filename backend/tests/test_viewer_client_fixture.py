"""The shared viewer fixture leaves no account behind once its module is done."""
from models import User


def _fixture_function():
    from tests.conftest import viewer_client
    return getattr(viewer_client, '__wrapped__', None) or viewer_client.__pytest_wrapped__.obj


def _exists(app):
    with app.app_context():
        return User.query.filter_by(username='viewer_test').first() is not None


def test_the_viewer_account_is_removed_when_the_fixture_ends(app):
    assert not _exists(app)
    generator = _fixture_function()(app)
    client = next(generator)
    assert _exists(app) and client.get('/api/v2/auth/verify').status_code == 200
    assert next(generator, None) is None
    assert not _exists(app)
