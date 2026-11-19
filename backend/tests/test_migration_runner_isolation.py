"""create_app() resolves the migration runner's target from the environment,
not from the in-memory test config: it must only ever see the test's own
database, whatever /etc/ucm/ucm.env names on this machine."""
import os
from pathlib import Path


def test_migration_runner_targets_the_test_data_dir(app):
    import migration_runner

    url = migration_runner._get_db_url()
    if url.startswith('postgresql'):
        from tests import pg_app_harness
        assert pg_app_harness.ENABLED and f'search_path%3D{pg_app_harness.SCHEMA}%20' in url
        return
    assert url.startswith('sqlite:///'), url
    target = Path(url[len('sqlite:///'):]).resolve()
    data_dir = Path(os.environ['DATA_DIR']).resolve()
    assert data_dir in target.parents, (
        f"the runner would migrate {target}, outside the test data dir {data_dir}")
