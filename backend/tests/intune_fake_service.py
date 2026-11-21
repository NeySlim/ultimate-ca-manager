"""A local HTTP stand-in for the three Microsoft endpoints the Intune SCEP
client talks to: Entra token, Graph service discovery and ScepActions/*.

It listens on 127.0.0.1 (port chosen by the system). Answers are scripted per
kind ("token", "discover", "validate", "success", "failure"): each queued
(status, body) answers the next call of that kind, else the call succeeds.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from services.scep import intune_client as intune

GOOD = object()  # a queued answer meaning "behave normally"


class FakeIntune:
    def __init__(self):
        self.apps = {}      # (tenant, client_id) -> secret
        self.calls = []     # dicts: kind, tenant, ...
        self.script = {}    # kind -> list of (status, body bytes) or GOOD
        self.refusals = {}  # tenant -> (code, description) for validateRequest
        self._lock = threading.Lock()
        self._tokens = 0
        self._server = None

    # -- test side ---------------------------------------------------
    def register(self, tenant, client_id, secret):
        self.apps[(tenant, client_id)] = secret

    def queue(self, kind, status, body=b''):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.script.setdefault(kind, []).append((status, body))

    def of(self, kind, tenant=None):
        return [c for c in self.calls if c['kind'] == kind and (tenant is None or c['tenant'] == tenant)]

    @property
    def base(self):
        return f'http://127.0.0.1:{self._server.server_address[1]}/'

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, status, body, ctype='application/json'):
                self.send_response(status)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._reply(*fake.handle('GET', self.path, self.headers, b''))

            def do_POST(self):
                size = int(self.headers.get('Content-Length') or 0)
                self._reply(*fake.handle('POST', self.path, self.headers, self.rfile.read(size)))

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    def patch(self, monkeypatch):
        """Point the client's three Microsoft URLs here; no proxy for a local call."""
        monkeypatch.setattr(intune, 'AUTHORITY', self.base)
        monkeypatch.setattr(intune, 'GRAPH_RESOURCE_URL', self.base)
        monkeypatch.setattr(intune, 'INTUNE_RESOURCE_URL', self.base)
        monkeypatch.setenv('NO_PROXY', '127.0.0.1')
        monkeypatch.setenv('no_proxy', '127.0.0.1')

    # -- server side -------------------------------------------------
    def _scripted(self, kind):
        with self._lock:
            queue = self.script.get(kind) or []
            return queue.pop(0) if queue else GOOD

    def handle(self, method, path, headers, body):
        path = path.split('?')[0]
        if method == 'POST' and path.endswith('/oauth2/v2.0/token'):
            return self._token(path.strip('/').split('/')[0], parse_qs(body.decode()))
        if method == 'GET' and '/servicePrincipals/' in path:
            return self._discover(headers)
        if method == 'POST' and '/svc/' in path:
            return self._action(path, headers, body)
        return 404, b'{}'

    def _token(self, tenant, form):
        form = {k: v[0] for k, v in form.items()}
        with self._lock:
            self.calls.append({'kind': 'token', 'tenant': tenant, 'client_id': form.get('client_id'),
                               'scope': form.get('scope')})
            self._tokens += 1
            n = self._tokens
        scripted = self._scripted('token')
        if scripted is not GOOD:
            return scripted
        if self.apps.get((tenant, form.get('client_id'))) != form.get('client_secret'):
            return 401, b'{"error": "invalid_client"}'
        return 200, json.dumps({'access_token': f'tok~{tenant}~{n}', 'expires_in': 3600}).encode()

    @staticmethod
    def _tenant_of(headers):
        auth = headers.get('Authorization', '')
        return auth.split('~')[1] if auth.startswith('Bearer tok~') else None

    def _discover(self, headers):
        tenant = self._tenant_of(headers)
        self.calls.append({'kind': 'discover', 'tenant': tenant})
        scripted = self._scripted('discover')
        if scripted is not GOOD:
            return scripted
        if tenant is None:
            return 401, b'{}'
        return 200, json.dumps({'value': [{
            'providerName': 'ScepRequestValidationFEService',
            'uri': f'{self.base}svc/{tenant}'}]}).encode()

    def _action(self, path, headers, body):
        tenant = path.split('/svc/')[1].split('/')[0]
        kind = {'validateRequest': 'validate', 'successNotification': 'success',
                'failureNotification': 'failure'}[path.rsplit('/', 1)[1]]
        payload = json.loads(body or b'{}')
        self.calls.append({'kind': kind, 'tenant': tenant, 'token_tenant': self._tenant_of(headers),
                           'auth': headers.get('Authorization'), 'json': payload,
                           'api_version': headers.get('api-version')})
        scripted = self._scripted(kind)
        if scripted is not GOOD:
            return scripted
        if self._tenant_of(headers) != tenant:
            return 401, b'{}'
        if kind == 'validate' and tenant in self.refusals:
            code, description = self.refusals[tenant]
            return 200, json.dumps({'code': code, 'errorDescription': description}).encode()
        return 200, b'{"code": "Success", "errorDescription": ""}'
