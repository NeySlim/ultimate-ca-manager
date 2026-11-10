"""(e) Both nodes started together on an empty schema: the schema is built once, both serve."""
import pytest

from migration_runner import _list_migration_names

pytestmark = pytest.mark.ha


def test_simultaneous_start_builds_the_schema_once(cluster):
    # Every process of both nodes (masters and scheduler processes) initialises the database
    logs = {node.name: node.app_log_text() for node in cluster.nodes}
    built = {name: text.count('Creating database tables...') for name, text in logs.items()}
    assert sorted(built.values()) == [0, 1], built
    assert all('Database tables already exist' in text for text in logs.values())

    applied = [name for (name,) in cluster.sql('SELECT name FROM _migrations')]
    assert sorted(applied) == sorted(_list_migration_names())
    assert cluster.sql("SELECT count(*) FROM users WHERE username = 'admin'") == [(1,)]
    for node in cluster.nodes:
        assert node.ready()['status'] == 'ready'
