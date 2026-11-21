"""Tests that need an optional backend (SoftHSM, the system GSSAPI, a Redis server).

`needs('softhsm', available, reason)` marks a test: it is skipped without the backend, and when
UCM_TEST_REQUIRE_SOFTHSM=1 any skip of it, for whatever reason, is reported as a failure instead.
The CI job that installs the backend sets the variable, so its tests cannot silently stop running.
"""
import os

import pytest

BACKENDS = ('softhsm', 'gssapi', 'redis')


def required_env(backend):
    return f'UCM_TEST_REQUIRE_{backend.upper()}'


def needs(backend, available, reason):
    assert backend in BACKENDS, backend
    return getattr(pytest.mark, f'needs_{backend}')(available=bool(available), reason=reason)


def _markers(item):
    for backend in BACKENDS:
        marker = item.get_closest_marker(f'needs_{backend}')
        if marker is not None:
            yield backend, marker


def pytest_configure(config):
    for backend in BACKENDS:
        config.addinivalue_line('markers', f'needs_{backend}(available, reason): needs {backend}; '
                                f'a skip fails under {required_env(backend)}=1')


def pytest_runtest_setup(item):
    for _, marker in _markers(item):
        if not marker.kwargs.get('available', True):
            pytest.skip(marker.kwargs.get('reason', 'optional backend missing'))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if not report.skipped or hasattr(report, 'wasxfail'):
        return
    for backend, _ in _markers(item):
        if os.environ.get(required_env(backend)) == '1':
            reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
            reason = reason.removeprefix('Skipped: ')
            report.outcome = 'failed'
            report.longrepr = f'skipped although {required_env(backend)}=1: {reason}'
            return
