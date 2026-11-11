"""(g) Without Redis, an event born of a request on one node reaches the browsers of both, once."""
import threading
import time

import pytest
import socketio

from tests.ha.cluster import create_ca, wait_until

pytestmark = pytest.mark.ha


class Browser:
    """A Socket.IO client (long polling) on one node, signed in with the admin's session cookie."""

    def __init__(self, node, admin):
        self.events = []
        self._lock = threading.Lock()
        http = node.session()
        http.cookies.update(admin.http.cookies.get_dict())
        self.sio = socketio.Client(http_session=http, ssl_verify=False, reconnection=False)
        self.sio.on('event', self._record)
        self.sio.connect(node.base, transports=['polling'], wait_timeout=30)

    def _record(self, payload):
        with self._lock:
            self.events.append(payload)

    def named(self, name, type_):
        with self._lock:
            return [e for e in self.events if e.get('type') == type_ and e['data'].get('name') == name]

    def close(self):
        self.sio.disconnect()


def test_an_event_of_a_request_on_a_reaches_a_client_of_each_node_once(cluster, admin):
    a, b = cluster.nodes
    browsers = [Browser(a, admin), Browser(b, admin)]
    try:
        name = 'HA realtime CA'
        create_ca(admin, name)
        for browser in browsers:
            wait_until(lambda browser=browser: browser.named(name, 'ca.created'), 30, 'ca.created relayed')
        time.sleep(6)  # several reader passes and a gap grace: nothing arrives twice
        assert [len(browser.named(name, 'ca.created')) for browser in browsers] == [1, 1]
        assert all('_origin' not in e for browser in browsers for e in browser.events)
    finally:
        for browser in browsers:
            browser.close()
