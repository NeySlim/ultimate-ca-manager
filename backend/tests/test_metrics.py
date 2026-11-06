"""Tests for the Prometheus /metrics endpoint and renderer."""
import pytest

from models import db, SystemConfig


def _set_token(value):
    row = SystemConfig.query.filter_by(key='metrics_token').first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key='metrics_token', value=value))
    db.session.commit()


class TestRenderer:
    def test_render_is_valid_exposition(self, app):
        with app.app_context():
            from services.metrics_service import render_metrics
            out = render_metrics()
            assert 'ucm_build_info' in out
            assert '# TYPE ucm_certificates gauge' in out
            assert 'ucm_scheduler_task_runs_total' in out
            assert 'ucm_scheduler_state_stale 0' in out  # no scheduler process to wait for here
            assert 'ucm_webhook_deliveries' in out
            # every non-comment line is "name value" or 'name{...} value'
            for line in out.splitlines():
                if line and not line.startswith('#'):
                    assert ' ' in line

    def test_label_values_escaped(self, app):
        with app.app_context():
            from services.metrics_service import _Doc
            d = _Doc()
            d.metric('x', 1, version='a"b\\c')
            assert 'a\\"b\\\\c' in d.render()


class TestEndpointGating:
    def test_disabled_returns_404(self, app, client):
        with app.app_context():
            SystemConfig.query.filter_by(key='metrics_token').delete()
            db.session.commit()
        r = client.get('/metrics')
        assert r.status_code == 404

    def test_missing_token_returns_401(self, app, client):
        with app.app_context():
            _set_token('s3cr3t-scrape-token')
        try:
            r = client.get('/metrics')
            assert r.status_code == 401, r.data
            r2 = client.get('/metrics', headers={'Authorization': 'Bearer wrong'})
            assert r2.status_code == 401
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(key='metrics_token').delete()
                db.session.commit()

    def test_valid_token_returns_metrics(self, app, client):
        with app.app_context():
            _set_token('s3cr3t-scrape-token')
        try:
            r = client.get('/metrics', headers={'Authorization': 'Bearer s3cr3t-scrape-token'})
            assert r.status_code == 200
            assert b'ucm_build_info' in r.data
            assert 'text/plain' in r.content_type
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(key='metrics_token').delete()
                db.session.commit()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
