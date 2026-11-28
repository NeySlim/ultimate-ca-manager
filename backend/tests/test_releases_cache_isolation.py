"""The releases cache is restored after every test, whatever a test left in it."""
from services import updates
from tests.conftest import restored_releases_cache


def test_the_cache_comes_back_as_it_was():
    before = dict(updates._releases_cache)
    with restored_releases_cache():
        updates._releases_cache['error'] = 'left behind'
        updates._releases_cache['error_ts'] = 123.0
        updates._releases_cache['stray'] = True
    assert updates._releases_cache == before
