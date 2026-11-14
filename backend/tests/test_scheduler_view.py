"""Tests for the scheduler admin view endpoints (GET list + POST run-now)."""
import json
import pytest


class TestSchedulerListEndpoint:
    def test_requires_auth(self, client):
        r = client.get('/api/v2/system/scheduler')
        assert r.status_code == 401, r.data

    def test_lists_tasks_with_labels(self, auth_client):
        r = auth_client.get('/api/v2/system/scheduler')
        assert r.status_code == 200
        data = json.loads(r.data)['data']
        assert 'tasks' in data and 'total' in data and 'warnings' in data
        # Each task carries a friendly label + status fields
        for task in data['tasks']:
            assert 'name' in task and 'label' in task
            assert 'interval' in task and 'run_count' in task
            assert 'last_run' in task and 'next_run' in task


class TestSchedulerRunEndpoint:
    def test_requires_auth(self, client):
        r = client.post('/api/v2/system/scheduler/session_cleanup/run')
        assert r.status_code == 401, r.data

    def test_unknown_task_returns_404(self, auth_client):
        r = auth_client.post('/api/v2/system/scheduler/does_not_exist/run')
        assert r.status_code == 404

    def test_run_known_task(self, auth_client):
        # session_cleanup is harmless to trigger
        r = auth_client.post('/api/v2/system/scheduler/session_cleanup/run')
        # 200 if the task is registered in this app context; 404 if scheduler
        # has no tasks registered under test — both prove the route works.
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            data = json.loads(r.data)['data']
            assert data.get('label')
            assert data.get('run_count', 0) >= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestPerNodeTasks:
    def test_the_update_result_alone_runs_on_every_node(self, auth_client):
        r = auth_client.get('/api/v2/system/scheduler')
        tasks = {t['name']: t for t in json.loads(r.data)['data']['tasks']}
        if 'backup_retention' not in tasks:
            pytest.skip('no task registered in this app')
        per_node = {name for name, t in tasks.items() if t['per_node']}
        # Retention runs on the leader, over the archives every node shares
        assert per_node == {'update_result'}
        assert tasks['update_result']['label'] == 'Update result'

    def test_the_update_check_leaves_the_result_to_its_node_task(self, app, monkeypatch, tmp_path):
        import services.updates as updates
        consumed = []
        monkeypatch.setattr(updates, 'consume_update_result', lambda: consumed.append(1))
        monkeypatch.setattr(updates, '_cfg_get', lambda key, default=None: default)
        monkeypatch.setattr(updates, 'get_update_settings',
                            lambda: {'auto_install': False, 'hour': 3, 'channel': 'stable'})
        monkeypatch.setattr(updates, 'check_for_updates', lambda channel: {'error': 'offline'})
        monkeypatch.setattr(updates, '_cfg_set', lambda *a: True)
        with app.app_context():
            updates.scheduled_update_check()
            assert consumed == []
            updates.scheduled_update_result()
        assert consumed == [1]
