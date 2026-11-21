"""Both test harnesses refuse a non Latin-1 response header, as the real server does (#448)."""
import pytest
from flask import Response

from tests.fresh_app import fresh_app

OLD_HEADER = 'attachment; filename="テスト用.p12"'


def _non_latin1_view():
    return Response(b'x', headers={'Content-Disposition': OLD_HEADER})


def _health_endpoint(application):
    return application.url_map.bind('ucm.test').match('/health')[0]


def _assert_refused(application, client):
    with pytest.raises(UnicodeError, match='Content-Disposition'):
        client.get('/health')


def test_session_app_refuses_a_route_header(app, monkeypatch):
    monkeypatch.setitem(app.view_functions, _health_endpoint(app), _non_latin1_view)
    _assert_refused(app, app.test_client())


def test_session_app_refuses_an_after_request_header(app, monkeypatch):
    def add_header(response):
        response.headers['X-Name'] = 'テスト'
        return response
    monkeypatch.setitem(app.after_request_funcs, None, [*app.after_request_funcs.get(None, []), add_header])
    with pytest.raises(UnicodeError, match='X-Name'):
        app.test_client().get('/health')


def test_fresh_app_refuses_a_route_header():
    with fresh_app() as application:
        application.view_functions[_health_endpoint(application)] = _non_latin1_view
        _assert_refused(application, application.test_client())

