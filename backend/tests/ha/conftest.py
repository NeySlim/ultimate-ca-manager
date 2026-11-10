"""HA bench: opt-in with UCM_TEST_HA=1 and UCM_TEST_PG_URL, run with `pytest -m ha`.

Each test module gets a fresh cluster (schema and two nodes), stopped and dropped
after it; a failing test carries both nodes' logs in its report.
"""
import pytest

from tests.ha.cluster import ENABLED, Client, Cluster


def pytest_collection_modifyitems(config, items):
    if ENABLED:
        return
    skip = pytest.mark.skip(reason='HA bench: set UCM_TEST_HA=1 and UCM_TEST_PG_URL')
    for item in items:
        if item.get_closest_marker('ha'):
            item.add_marker(skip)


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    bench = Cluster(tmp_path_factory.mktemp('ha'))
    bench.create_schema()
    try:
        bench.start()
        yield bench
        assert not bench.guard_hits(), bench.guard_hits()
    finally:
        bench.close()


@pytest.fixture(scope='module')
def admin(cluster):
    """The admin logged in on node A."""
    return Client.login(cluster[0], cluster.password)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    bench = getattr(item, 'funcargs', {}).get('cluster')
    if report.failed and isinstance(bench, Cluster):
        guard = bench.guard_hits()
        if guard:
            report.sections.append(('HA guard', guard))
        for name, text in bench.logs().items():
            report.sections.append((f'HA node {name}', text[-20000:]))
