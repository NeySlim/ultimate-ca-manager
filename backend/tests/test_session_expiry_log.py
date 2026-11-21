"""The session expiry log line names each limit by its own label."""
import logging
from datetime import timedelta

import pytest

from auth.unified import AuthManager
from utils.datetime_utils import utc_now


@pytest.mark.parametrize('key, label, reason', [
    ('login_time', 'max', 'max lifetime'),
    ('last_activity', 'timeout', 'inactivity'),
])
def test_the_expiry_log_names_the_limit_that_ended_the_session(caplog, key, label, reason):
    now = utc_now()
    data = {key: (now - timedelta(seconds=120)).isoformat()}
    with caplog.at_level(logging.INFO, logger='auth.unified'):
        assert AuthManager.session_ended(data, now, label='alice', limits=(60, 60))
    line = next(r.getMessage() for r in caplog.records if 'Session expired' in r.getMessage())
    assert f'({reason})' in line and line.endswith(f', {label}=60s')
