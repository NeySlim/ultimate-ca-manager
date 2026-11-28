"""The releases cache is restored after every test, whatever a test left in it."""
from services import updates


def test_a_test_may_leave_the_cache_dirty():
    updates._releases_cache['error'] = 'left behind'
    updates._releases_cache['error_ts'] = 123.0


def test_the_next_test_sees_the_cache_as_it_was():
    assert updates._releases_cache['error'] is None
    assert updates._releases_cache['error_ts'] == 0
