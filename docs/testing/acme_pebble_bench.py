#!/usr/bin/env python3
"""Scenarios for UCM's ACME client against Pebble. Runs on the Docker host, stdlib only,
after `acme-pebble-bench.sh up`. See acme-pebble-bench.md.

    python3 acme_pebble_bench.py [--only s1,s3,...] [--report out.json]
"""
import argparse
import base64
import datetime as dt
import http.cookiejar
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

PREFIX = os.environ.get('BENCH_PREFIX', 'ucm-pebble')
NET_BASE = os.environ.get('BENCH_SUBNET', '10.231.77.0/24').rsplit('.', 1)[0]
CHALLTEST_IP, PEBBLE_IP, UCM_IP = f'{NET_BASE}.2', f'{NET_BASE}.3', f'{NET_BASE}.4'
UCM_URL = f'https://{UCM_IP}:8443'
PEBBLE_MGMT = f'https://{PEBBLE_IP}:15000'
DIRECTORY = 'https://pebble:14000/dir'
UCM_C, PEBBLE_C = f'{PREFIX}-ucm', f'{PREFIX}-ca'
USER = os.environ.get('UCM_USER', 'admin')
# Unset: the password UCM generated at its first start, read from its data directory
PASSWORD = os.environ.get('UCM_PASSWORD', '')
# The first login must change the initial password; the bench sets this one.
BENCH_PASSWORD = os.environ.get('UCM_BENCH_PASSWORD', 'Pebble-Bench-2026!')
DOMAIN = os.environ.get('BENCH_DOMAIN', 'bench.example.com')
RETRY_AFTER = int(os.environ.get('PEBBLE_RETRY_AFTER_ORDER', '40'))
HOOK = '/usr/local/bin/python3 /bench/acme_pebble_hook.py'
DB_PATH = '/opt/ucm/data/ucm.db'
# What a stopped process leaves on an order it was finalizing or renewing
LEASE_SECONDS = 600

INSECURE = ssl.create_default_context()
INSECURE.check_hostname = False
INSECURE.verify_mode = ssl.CERT_NONE  # bench-only self-signed endpoints

RESULTS = {}
CTX = {}


def log(msg):
    print(f'[{dt.datetime.now():%H:%M:%S}] {msg}', flush=True)


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


# ── plumbing ────────────────────────────────────────────────────────────────

def sh(*args, check=True, inp=None, stderr=True):
    proc = subprocess.run(args, input=inp, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f'{args}: rc={proc.returncode} {proc.stderr.strip()}')
    return proc.stdout + (proc.stderr if stderr else '')


def generated_password():
    return sh('docker', 'exec', UCM_C, 'cat', '/opt/ucm/data/initial-admin-password',
              check=False, stderr=False).strip()


class Ucm:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=INSECURE),
            urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def call(self, method, path, body=None, timeout=600):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(UCM_URL + path, data=data, method=method)
        req.add_header('Content-Type', 'application/json')
        if self.csrf:
            req.add_header('X-CSRF-Token', self.csrf)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read().decode(), exc.code
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, {'raw': raw[:500]}

    def login(self):
        for _ in range(60):
            for password in (BENCH_PASSWORD, PASSWORD or generated_password()):
                self.jar.clear()
                self.csrf = None
                try:
                    status, body = self.call('POST', '/api/v2/auth/login/password',
                                             {'username': USER, 'password': password}, timeout=10)
                except (urllib.error.URLError, ConnectionError, TimeoutError):
                    break
                if status != 200:
                    continue
                self.csrf = body['data']['csrf_token']
                if body['data'].get('force_password_change'):
                    self.ok('POST', '/api/v2/account/password', {'new_password': BENCH_PASSWORD})
                    return self.login()
                return
            time.sleep(2)
        raise RuntimeError('UCM login failed')

    def ok(self, method, path, body=None, expect=(200, 201)):
        status, data = self.call(method, path, body)
        if status not in expect:
            raise RuntimeError(f'{method} {path} -> {status} {data}')
        return data.get('data', data)


UCM = Ucm()

_DB_SNIPPET = r'''
import json, sqlite3, sys
q = json.load(sys.stdin)
c = sqlite3.connect("file:%s?mode=ro" % q["path"], uri=True)
c.row_factory = sqlite3.Row
print(json.dumps([dict(r) for r in c.execute(q["sql"], q["params"])], default=str))
'''


def db(sql, *params):
    """Read-only query on UCM's SQLite database inside its container."""
    out = sh('docker', 'exec', '-i', UCM_C, 'python3', '-c', _DB_SNIPPET,
             inp=json.dumps({'path': DB_PATH, 'sql': sql, 'params': params}))
    return json.loads(out)


def in_ucm(code):
    """Python run inside the UCM image, backend on the path, no application started."""
    return sh('docker', 'exec', '-i', '-w', '/opt/ucm/backend', UCM_C, 'python3', '-', inp=code, stderr=False)


def pebble_mgmt(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(PEBBLE_MGMT + path, data=data, method=method)
    try:
        with urllib.request.urlopen(req, context=INSECURE, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def container_log(name, since):
    return sh('docker', 'logs', '--since', since.strftime('%Y-%m-%dT%H:%M:%S.%fZ'), name, check=False)


def ucm_log(since, pattern=None):
    text = sh('docker', 'exec', UCM_C, 'cat', '/opt/ucm/data/ucm.log', check=False)
    stamp = since.strftime('%Y-%m-%d %H:%M:%S')  # the container logs in UTC
    lines = [l for l in text.splitlines() if l[:19] >= stamp]
    if pattern:
        lines = [l for l in lines if re.search(pattern, l)]
    return lines


def pebble_log(since, pattern=None):
    lines = container_log(PEBBLE_C, since).splitlines()
    if pattern:
        lines = [l for l in lines if re.search(pattern, l)]
    return lines


def record(name, verdict, *evidence):
    RESULTS[name] = {'verdict': verdict, 'evidence': [e for e in evidence if e]}
    log(f'{name}: {verdict}')
    for e in RESULTS[name]['evidence']:
        for line in str(e).splitlines()[:40]:
            print(f'    {line}')


def orders_for(domain):
    return db("SELECT id, status, certificate_id, order_url, error_message, renewal_failures, "
              "acme_client_account_id, created_at FROM acme_client_orders "
              "WHERE domains LIKE ? ORDER BY id", f'%"{domain}"%')


def certs_for(domain):
    return db("SELECT id, refid, serial_number, subject, source, valid_to, revoked, "
              "prv IS NOT NULL AS has_key FROM certificates WHERE san_dns LIKE ? OR descr = ? "
              "ORDER BY id", f'%{domain}%', domain)


def cert_pem(cert_id):
    row = db('SELECT crt FROM certificates WHERE id = ?', cert_id)[0]
    return base64.b64decode(row['crt']).decode()


def wait_order(order_id, done=('issued', 'invalid', 'error', 'pending'), timeout=420):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        row = db('SELECT status, error_message, certificate_id FROM acme_client_orders WHERE id = ?',
                 order_id)
        status = row[0]['status'] if row else 'deleted'
        if not seen or seen[-1] != status:
            seen.append(status)
        if status in done and len(seen) > 1 or status in ('issued', 'invalid', 'deleted'):
            return (row[0] if row else {}), seen
        time.sleep(0.5)
    return row[0], seen


def request_order(domain, provider, account, **extra):
    body = {'domains': [domain], 'challenge_type': 'dns-01', 'dns_provider_id': provider,
            'acme_account_id': account, **extra}
    data = UCM.ok('POST', '/api/v2/acme/client/request', body)
    return data['order']['id']


def run_task(name='acme_auto_renewal'):
    t0 = time.monotonic()
    data = UCM.ok('POST', f'/api/v2/system/scheduler/{name}/run')
    return data, round(time.monotonic() - t0, 1)


def leaf_info(pem):
    out = sh('openssl', 'x509', '-noout', '-serial', '-subject', '-issuer', '-ext',
             'subjectAltName', '-enddate', inp=pem)
    return ' | '.join(l.strip() for l in out.splitlines() if l.strip())


def pebble_cert_status(serial):
    """UCM stores the serial in decimal, Pebble's management API takes hex."""
    return pebble_mgmt('GET', f'/cert-status-by-serial/{int(serial):x}')


def set_ari_due(pem):
    """Pebble management: make this certificate's ARI window lie in the past."""
    start = now_utc() - dt.timedelta(days=2)
    window = {'suggestedWindow': {'start': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                  'end': (start + dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}}
    return pebble_mgmt('POST', '/set-renewal-info/', {'certificate': pem, 'ariResponse': json.dumps(window)})


def key_matches(cert_id):
    """Whether the key UCM stores for a certificate row is the certificate's."""
    return in_ucm(f'''
import base64, sqlite3
from cryptography import x509
from cryptography.hazmat.primitives import serialization
c = sqlite3.connect("{DB_PATH}")
crt, prv = c.execute("SELECT crt, prv FROM certificates WHERE id = {int(cert_id)}").fetchone()
cert = x509.load_pem_x509_certificate(base64.b64decode(crt))
from utils.key_codec import load_pem_bytes
key = serialization.load_pem_private_key(load_pem_bytes(prv, context="bench"), None)
pub = lambda k: k.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
print("key matches certificate:", pub(key.public_key()) == pub(cert.public_key()))
''').strip()


def lease_expiry(order_id):
    """When the lease left on an order runs out (UTC), None without one."""
    row = db('SELECT renewal_claimed_at FROM acme_client_orders WHERE id = ?', order_id)
    stamp = row[0]['renewal_claimed_at'] if row else None
    if not stamp:
        return None
    taken = dt.datetime.fromisoformat(stamp).replace(tzinfo=dt.timezone.utc)
    return taken + dt.timedelta(seconds=LEASE_SECONDS)


def wait_lease(order_id, ev):
    expiry = lease_expiry(order_id)
    ev.append(f'lease on order {order_id} runs out at {expiry}')
    while expiry and now_utc() < expiry + dt.timedelta(seconds=3):
        time.sleep(5)


# ── setup ───────────────────────────────────────────────────────────────────

def setup():
    UCM.login()
    UCM.ok('PATCH', '/api/v2/acme/client/settings', {
        'email': 'bench@example.com', 'dns_propagation_timeout': 10, 'dns_propagation_delay': 0,
        'renewal_enabled': True,
        'dns01_resolver_mode': 'custom', 'dns01_nameservers': f'{CHALLTEST_IP}:8053'})
    providers = {}
    for name, args in (('challtest', ''), ('challtest-wrong', ' --wrong'), ('challtest-flip', '')):
        p = UCM.ok('POST', '/api/v2/dns-providers', {
            'name': name, 'provider_type': 'custom_command',
            'credentials': {'create_command': HOOK + args, 'delete_command': HOOK}})
        providers[name] = p['id']
    accounts = {}
    # main: Retry-After below the poll timeout; slow: Retry-After beyond it
    for label, timeout in (('pebble-main', 120), ('pebble-slow', 30)):
        a = UCM.ok('POST', '/api/v2/acme/client/accounts', {
            'directory_url': DIRECTORY, 'label': label, 'email': 'bench@example.com',
            'order_poll_timeout_sec': timeout, 'order_poll_interval_sec': 3})
        UCM.ok('POST', f'/api/v2/acme/client/accounts/{a["id"]}/register', {})
        accounts[label] = a['id']
    CTX.update(providers=providers, accounts=accounts)
    log(f'setup: providers={providers} accounts={accounts}')


# ── scenarios ───────────────────────────────────────────────────────────────

def finalize_to_next_poll(since):
    """Seconds between the finalize POST and the next POST-as-GET of an order, in Pebble's log
    (which names the route, not the order: scenarios run one order at a time)."""
    stamps = []
    for line in pebble_log(since):
        m = re.match(r'Pebble (\d{4}/\d\d/\d\d \d\d:\d\d:\d\d) (.*)', line)
        if m:
            stamps.append((dt.datetime.strptime(m.group(1), '%Y/%m/%d %H:%M:%S'), m.group(2)))
    idx = next((i for i, (_, msg) in enumerate(stamps) if msg.startswith('POST /finalize-order/')), None)
    if idx is None:
        return None, None
    fin = stamps[idx][0]
    after = [t for t, msg in stamps[idx + 1:] if msg.startswith('POST /my-order/')]
    return fin, (after[0] - fin).total_seconds() if after else None


def s1_issuance():
    domain = f's1.{DOMAIN}'
    since = now_utc()
    oid = request_order(domain, CTX['providers']['challtest'], CTX['accounts']['pebble-main'])
    row, seen = wait_order(oid)
    CTX['s1'] = {'order': oid, 'since': since}
    certs = certs_for(domain)
    if row.get('status') != 'issued' or len(certs) != 1:
        return record('S1 issuance', 'FAIL', f'statuses={seen} row={row}', f'certs={certs}',
                      *ucm_log(since, r'ERROR|WARNING|acme')[-15:])
    cert = certs[0]
    pem = cert_pem(cert['id'])
    serial = cert['serial_number']
    st, body = pebble_cert_status(serial)
    key_check = in_ucm(f'''
import base64, sqlite3
from cryptography import x509
from cryptography.hazmat.primitives import serialization
c = sqlite3.connect("{DB_PATH}")
crt, prv = c.execute("SELECT crt, prv FROM certificates WHERE id = {cert['id']}").fetchone()
cert = x509.load_pem_x509_certificate(base64.b64decode(crt))
from utils.key_codec import load_pem_bytes
key = serialization.load_pem_private_key(load_pem_bytes(prv, context="bench"), None)
pub = lambda k: k.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
print("key matches certificate:", pub(key.public_key()) == pub(cert.public_key()))
''')
    CTX['s1'].update(cert=cert['id'], pem=pem, serial=serial)
    ok = st == 200 and 'key matches certificate: True' in key_check and domain in leaf_info(pem)
    record('S1 issuance', 'PASS' if ok else 'FAIL',
           f'order {oid} statuses {seen}, certificate_id={row["certificate_id"]}',
           f'UCM leaf: {leaf_info(pem)}',
           f'Pebble /cert-status-by-serial/{serial}: HTTP {st} {body.strip()[:200]}',
           key_check.strip())


def s3_retry_after():
    ev = []
    verdicts = []
    s1 = CTX.get('s1')
    if s1:
        fin, gap = finalize_to_next_poll(s1['since'])
        ev.append(f'main account (poll timeout 120 s, interval 3 s), Pebble Retry-After {RETRY_AFTER} s: '
                  f'finalize at {fin}, next order poll after {gap} s')
        verdicts.append(gap is not None and RETRY_AFTER - 2 <= gap <= RETRY_AFTER + 3)
    domain = f's3.{DOMAIN}'
    since = now_utc()
    oid = request_order(domain, CTX['providers']['challtest'], CTX['accounts']['pebble-slow'])
    row, seen = wait_order(oid)
    fin, gap = finalize_to_next_poll(since)
    ev.append(f'slow account (poll timeout 30 s): order {oid} statuses {seen}, finalize at {fin}, '
              f'next order poll after {gap} s, final status {row.get("status")} {row.get("error_message")}')
    verdicts.append(row.get('status') == 'issued' and gap is not None and 27 <= gap <= 33)
    record('S3 Retry-After', 'PASS' if all(verdicts) else 'FAIL', *ev,
           *ucm_log(since, r'not ready|Certificate not ready|Finaliz')[-5:])


def s7_long_cn():
    label = 'l' * 50
    domain = f'{label}.s7.{DOMAIN}'
    since = now_utc()
    oid = request_order(domain, CTX['providers']['challtest'], CTX['accounts']['pebble-main'])
    row, seen = wait_order(oid)
    certs = certs_for(domain)
    csr = in_ucm(f'''
import base64
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec
from services.acme.acme_client_service import AcmeClientService
b64 = AcmeClientService._build_csr_b64(ec.generate_private_key(ec.SECP256R1()), ["{domain}"], "{domain}")
csr = x509.load_der_x509_csr(base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)))
san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
print("len", len("{domain}"), "subject", repr(csr.subject.rfc4514_string()), "SAN critical", san.critical,
      "SAN", san.value.get_values_for_type(x509.DNSName))
''')
    ok = row.get('status') == 'issued' and len(certs) == 1 and "subject ''" in csr and 'SAN critical True' in csr
    record('S7 CN > 64', 'PASS' if ok else 'FAIL', f'order {oid} statuses {seen} row={row}',
           f'leaf: {leaf_info(cert_pem(certs[0]["id"]))}' if certs else 'no certificate',
           f'CSR built by UCM for the same name: {csr.strip()}',
           *([] if ok else ucm_log(since, r'ERROR|WARNING|Finaliz')[-10:]))


def s2_s6_scheduled_renewal():
    s1 = CTX['s1']
    domain = f's1.{DOMAIN}'
    old_cert = s1['cert']
    ev = []
    # RFC 9773 §4.1 CertID computed by UCM, checked against Pebble's renewalInfo
    certid = in_ucm(f'''
from services.acme.acme_client_service import AcmeClientService
print(AcmeClientService.certificate_identifier(open("/dev/stdin").read() if False else {s1["pem"]!r}))
''').strip()
    ari_url = f'https://{PEBBLE_IP}:14000/draft-ietf-acme-ari-03/renewalInfo/{certid}'
    try:
        with urllib.request.urlopen(ari_url, context=INSECURE, timeout=10) as resp:
            ari = f'HTTP {resp.status} Retry-After={resp.headers.get("Retry-After")} {resp.read().decode().strip()}'
    except urllib.error.HTTPError as exc:
        ari = f'HTTP {exc.code} {exc.read().decode()}'
    ev.append(f'CertID {certid} -> GET renewalInfo: {ari}')
    s6_ok = ari.startswith('HTTP 200')
    st, body = set_ari_due(s1['pem'])
    ev.append(f'Pebble set-renewal-info (window in the past): HTTP {st} {body.strip()}')
    before_orders, before_certs = orders_for(domain), certs_for(domain)
    since = now_utc()
    task, secs = run_task()
    after_orders, after_certs = orders_for(domain), certs_for(domain)
    ev.append(f'acme_auto_renewal run: {secs} s, status={task.get("last_status")} error={task.get("last_error")}')
    ev.append(f'orders before {[(o["id"], o["status"], o["certificate_id"]) for o in before_orders]} '
              f'after {[(o["id"], o["status"], o["certificate_id"]) for o in after_orders]}')
    ev.append(f'certificates before {[(c["id"], c["serial_number"]) for c in before_certs]} '
              f'after {[(c["id"], c["serial_number"]) for c in after_certs]}')
    replaces = pebble_log(since, r'(?i)replac')
    ev.append('Pebble on replaces: ' + (' / '.join(replaces) or 'nothing logged'))
    others = db("SELECT id, domains, status FROM acme_client_orders WHERE id NOT IN (%s)" %
                ','.join(str(o['id']) for o in after_orders))
    ev.append(f'other orders after the run: {others}')
    # Renewed in place: the same row, a new serial Pebble issued, the stored key the certificate's
    same_row = [c['id'] for c in after_certs] == [old_cert]
    new_serial = after_certs[0]['serial_number'] if same_row else None
    st, _body = pebble_cert_status(new_serial) if new_serial else (None, '')
    ev.append(f'row {old_cert}: serial {s1["serial"]} -> {new_serial}, Pebble /cert-status-by-serial: HTTP {st}; '
              + key_matches(old_cert))
    renewed = (same_row and new_serial != s1['serial'] and st == 200 and len(after_orders) == 1
               and after_orders[0]['status'] == 'issued' and after_orders[0]['certificate_id'] == old_cert
               and 'key matches certificate: True' in key_matches(old_cert))
    # A second pass must not renew again
    task2, secs2 = run_task()
    again_orders, again_certs = orders_for(domain), certs_for(domain)
    ev.append(f'second run: {secs2} s, certificates {[(c["id"], c["serial_number"]) for c in again_certs]}, '
              f'orders {[(o["id"], o["status"]) for o in again_orders]}')
    stable = again_certs == after_certs and len(again_orders) == 1
    CTX['s2'] = {'certid': certid}
    record('S2 scheduled renewal', 'PASS' if renewed and stable else 'FAIL', *ev,
           *ucm_log(since, r'(?i)renew|replaces|ERROR')[-12:])
    s6_replaces = bool(replaces) and renewed
    record('S6 ARI', 'PASS' if s6_ok and s6_replaces else 'FAIL',
           f'renewalInfo with UCM CertID: {ari}',
           f'newOrder with replaces accepted: {s6_replaces} ({" / ".join(replaces) or "no Pebble log"})')


def s8_binding_follows_renewal():
    """A deployment bound to the certificate: the renewal queues its delivery for the same row."""
    domain = f's8.{DOMAIN}'
    oid = request_order(domain, CTX['providers']['challtest'], CTX['accounts']['pebble-main'])
    row, _ = wait_order(oid)
    certs0 = certs_for(domain)
    if row.get('status') != 'issued' or len(certs0) != 1:
        return record('S8 binding follows the renewal', 'ERROR', f'setup issuance failed: {row}')
    cert_id = certs0[0]['id']
    target = UCM.ok('POST', '/api/v2/deploy/targets',
                    {'name': 'bench-s8', 'host': '192.0.2.10', 'username': 'bench'})
    binding = UCM.ok('POST', '/api/v2/deploy/bindings',
                     {'target_id': target['id'], 'certificate_id': cert_id, 'cert_path': '/srv/bench/s8.pem'})
    set_ari_due(cert_pem(cert_id))
    since = now_utc()
    task, secs = run_task()
    certs1 = certs_for(domain)
    order1 = db('SELECT status, certificate_id FROM acme_client_orders WHERE id = ?', oid)[0]
    bound = db('SELECT certificate_id FROM deploy_bindings WHERE id = ?', binding['id'])[0]['certificate_id']
    deliveries = db('SELECT id, event_type, status, created_at FROM deploy_deliveries WHERE binding_id = ?',
                    binding['id'])
    ok = ([c['id'] for c in certs1] == [cert_id] and certs1[0]['serial_number'] != certs0[0]['serial_number']
          and order1['certificate_id'] == cert_id and bound == cert_id
          and any(d['event_type'] == 'certificate.renewed' for d in deliveries))
    record('S8 binding follows the renewal', 'PASS' if ok else 'FAIL',
           f'binding {binding["id"]} on certificate {cert_id}; renewal run {secs} s status={task.get("last_status")}',
           f'certificate {cert_id}: serial {certs0[0]["serial_number"]} -> '
           f'{certs1[0]["serial_number"] if certs1 else None}; order {oid} -> certificate {order1["certificate_id"]}; '
           f'binding -> certificate {bound}',
           f'deploy_deliveries of the binding: {deliveries}',
           *ucm_log(since, r'(?i)Deploy: queued|renewed|ERROR')[-6:])


def s4_invalid():
    ev = []
    domain = f's4.{DOMAIN}'
    since = now_utc()
    oid = request_order(domain, CTX['providers']['challtest-wrong'], CTX['accounts']['pebble-main'])
    row, seen = wait_order(oid)
    ev.append(f'first issuance with a wrong TXT: order {oid} statuses {seen}, '
              f'status={row.get("status")} error_message={row.get("error_message")!r}')
    ev += pebble_log(since, r'(?i)invalid|incorrect|valid ')[-3:]
    first_ok = row.get('status') == 'invalid' and bool(row.get('error_message')) \
        and len(orders_for(domain)) == 1 and not certs_for(domain)
    record('S4a invalid order on issuance', 'PASS' if first_ok else 'FAIL', *ev)
    ev = []

    # Renewal of an issued order whose DNS-01 now fails
    domain_b = f's4b.{DOMAIN}'
    flip = CTX['providers']['challtest-flip']
    oid_b = request_order(domain_b, flip, CTX['accounts']['pebble-main'])
    row_b, _ = wait_order(oid_b)
    cert_b = certs_for(domain_b)
    if row_b.get('status') != 'issued' or not cert_b:
        return record('S4b invalid order on renewal', 'ERROR', f'setup issuance of {domain_b} failed: {row_b}')
    UCM.ok('PATCH', f'/api/v2/dns-providers/{flip}', {
        'credentials': {'create_command': HOOK + ' --wrong', 'delete_command': HOOK}})
    set_ari_due(cert_pem(cert_b[0]['id']))
    since = now_utc()
    task, secs = run_task()
    orders_b = orders_for(domain_b)
    ev.append(f'renewal with a wrong TXT: run {secs} s status={task.get("last_status")}; '
              f'orders {[(o["id"], o["status"], o["certificate_id"], o["renewal_failures"], o["error_message"]) for o in orders_b]}')
    ev += ucm_log(since, r'(?i)renewal failed|Failed to renew|invalid')[-4:]
    since2 = now_utc()
    task, secs = run_task()
    orders_b2 = orders_for(domain_b)
    ev.append(f'second renewal attempt: orders {[(o["id"], o["status"], o["renewal_failures"]) for o in orders_b2]}')
    ev += ucm_log(since2, r'(?i)replaces')[-3:]
    ev += pebble_log(since2, r'(?i)replac|alreadyReplaced')[-3:]
    orphans = [o for o in orders_b2 if o['id'] != oid_b]
    renew_ok = not orphans and orders_b2[0]['renewal_failures'] >= 1 and orders_b2[0]['status'] == 'issued'
    ev.append(f'orphan child orders left by the failed renewals: {[(o["id"], o["status"]) for o in orphans]}')
    UCM.ok('PATCH', f'/api/v2/dns-providers/{flip}', {
        'credentials': {'create_command': HOOK, 'delete_command': HOOK}})
    # Still due through its ARI override: later scenarios must find one due order only
    UCM.ok('DELETE', f'/api/v2/acme/client/orders/{oid_b}')
    record('S4b invalid order on renewal', 'PASS' if renew_ok else 'FAIL', *ev)


def s5_crash_after_finalize():
    """UCM killed between the finalize request and the download, on a first issuance."""
    ev = []
    domain = f's5.{DOMAIN}'
    since = now_utc()
    oid = request_order(domain, CTX['providers']['challtest'], CTX['accounts']['pebble-main'])
    hit = _kill_after_finalize(since)
    if not hit:
        return record('S5 crash after finalize', 'ERROR', 'finalize never reached Pebble',
                      *ucm_log(since, r'ERROR|WARNING')[-10:])
    ev.append(f'Pebble saw: {hit.strip()} -> docker kill {UCM_C} (SIGKILL, inside the Retry-After sleep)')
    time.sleep(1)
    issued = pebble_log(since, r'Issued certificate serial')
    ev += issued
    sh('docker', 'start', UCM_C)
    UCM.login()
    row = db('SELECT status, certificate_id, pending_key IS NOT NULL AS has_pending_key, renewal_claimed_at '
             'FROM acme_client_orders WHERE id = ?', oid)[0]
    ev.append(f'after restart: order {oid} {row}')
    status, body = UCM.call('POST', f'/api/v2/acme/client/orders/{oid}/finalize')
    ev.append(f'POST /orders/{oid}/finalize at once -> HTTP {status} {body.get("message") or body}')
    CTX['s5'] = {'order': oid, 'since': since, 'issued': issued}
    ok = bool(row['has_pending_key']) and row['certificate_id'] is None and status == 409 and len(issued) == 1
    record('S5 crash after finalize (P1-3)', 'PASS' if ok else 'FAIL', *ev)


def s5_resume():
    """Once the dead process's lease runs out, a status check imports what Pebble issued."""
    s5 = CTX.get('s5')
    if not s5:
        return record('S5 resume', 'ERROR', 's5 did not run')
    ev, oid = [], s5['order']
    wait_lease(oid, ev)
    since = now_utc()
    deadline = time.monotonic() + 120
    answer = None
    while time.monotonic() < deadline:
        _st, body = UCM.call('GET', f'/api/v2/acme/client/orders/{oid}/status')
        answer = (body.get('data') or {}).get('status')
        if answer == 'issued':
            break
        time.sleep(10)
    row = db('SELECT status, certificate_id, pending_key IS NOT NULL AS has_pending_key, renewal_claimed_at '
             'FROM acme_client_orders WHERE id = ?', oid)[0]
    ev.append(f'GET /orders/{oid}/status -> {answer}; order {row}')
    certs_after = db('SELECT COUNT(*) AS n FROM certificates')[0]['n']
    cert = db('SELECT id, serial_number FROM certificates WHERE id = ?', row['certificate_id'] or 0)
    serial_hex = f'{int(cert[0]["serial_number"]):x}' if cert else None
    pebble_serial = re.search(r'serial ([0-9a-f]+)', s5['issued'][0]).group(1) if s5['issued'] else None
    ev.append(f'imported certificate {cert}, serial {serial_hex}; Pebble issued {pebble_serial} before the kill')
    # s5b runs in between: only this scenario's names and order count
    domain = f's5.{DOMAIN}'
    s5_certs, s5_orders = certs_for(domain), orders_for(domain)
    ev.append(f'certificates for {domain}: {[(c["id"], c["serial_number"]) for c in s5_certs]}, '
              f'orders {[(o["id"], o["status"]) for o in s5_orders]} (all certificates: {certs_after})')
    match = key_matches(row['certificate_id']) if cert else ''
    ev.append(match)
    ok = (answer == 'issued' and row['status'] == 'issued' and not row['has_pending_key']
          and serial_hex == pebble_serial and [c['id'] for c in s5_certs] == [row['certificate_id']]
          and [o['id'] for o in s5_orders] == [oid] and 'key matches certificate: True' in match)
    record('S5 resume after the crash', 'PASS' if ok else 'FAIL', *ev,
           *ucm_log(since, r'(?i)resum|finaliz|ERROR')[-6:])


def _kill_after_finalize(since, timeout=180):
    """SIGKILL the UCM container once Pebble has logged a finalize POST after *since*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hit = next((l for l in pebble_log(since) if 'POST /finalize-order/' in l), None)
        if hit:
            sh('docker', 'kill', UCM_C)
            return hit
        time.sleep(0.3)
    return None


def s5b_crash_during_renewal():
    """The same cut on the scheduled path: the renewal's order keeps the key, the lease holds."""
    import threading
    ev = []
    domain = f's5b.{DOMAIN}'
    oid = request_order(domain, CTX['providers']['challtest'], CTX['accounts']['pebble-main'])
    row, _ = wait_order(oid)
    certs0 = certs_for(domain)
    if row.get('status') != 'issued' or len(certs0) != 1:
        return record('S5b crash during renewal', 'ERROR', f'setup issuance failed: {row}')
    set_ari_due(cert_pem(certs0[0]['id']))
    since = now_utc()
    worker = threading.Thread(target=lambda: UCM.call('POST', '/api/v2/system/scheduler/acme_auto_renewal/run'),
                              daemon=True)
    worker.start()
    hit = _kill_after_finalize(since)
    if not hit:
        return record('S5b crash during renewal', 'ERROR', 'no finalize seen')
    ev.append(f'scheduled renewal running; Pebble saw {hit.strip()} -> docker kill')
    time.sleep(1)
    issued = pebble_log(since, r'Issued certificate serial|marked as replaced')
    ev += issued
    sh('docker', 'start', UCM_C)
    UCM.login()
    # The scheduler's own first pass after a start meets the dead renewal's lease
    deadline = time.monotonic() + 300
    done = []
    while time.monotonic() < deadline and not done:
        done = ucm_log(since, r"Task 'acme_auto_renewal' (completed|failed)")
        time.sleep(2)
    skipped = ucm_log(since, rf'Order {oid} skipped')
    orders1 = db('SELECT id, status, certificate_id, renewal_enabled, pending_key IS NOT NULL AS has_pending_key '
                 'FROM acme_client_orders WHERE domains LIKE ? ORDER BY id', f'%"{domain}"%')
    certs1 = certs_for(domain)
    ev.append(f'after restart: orders {orders1}, certificates {[(c["id"], c["serial_number"]) for c in certs1]}')
    ev.append(f'first scheduler pass: {done[-1][:120] if done else "not seen"}; {skipped[-1] if skipped else "no skip"}')
    kept = [o for o in orders1 if o['id'] != oid]
    CTX['s5b'] = {'order': oid, 'since': since, 'cert': certs0[0]['id'], 'serial0': certs0[0]['serial_number'],
                  'kept': kept[0]['id'] if kept else None,
                  'issued': [l for l in issued if 'Issued certificate serial' in l]}
    ok = (len(kept) == 1 and kept[0]['has_pending_key'] and not kept[0]['renewal_enabled']
          and kept[0]['status'] in ('processing', 'valid') and bool(skipped)
          and [c['id'] for c in certs1] == [certs0[0]['id']])
    record('S5b crash during renewal (P1-3)', 'PASS' if ok else 'FAIL', *ev)


def s5b_resume():
    """Once the lease runs out, the next renewal imports what Pebble issued, into the same row."""
    s5b = CTX.get('s5b')
    if not s5b:
        return record('S5b resume', 'ERROR', 's5b did not run')
    ev, oid = [], s5b['order']
    domain = f's5b.{DOMAIN}'
    wait_lease(oid, ev)
    since = now_utc()
    task, secs = run_task()
    orders2 = orders_for(domain)
    certs2 = certs_for(domain)
    ev.append(f'renewal run {secs} s status={task.get("last_status")}: orders '
              f'{[(o["id"], o["status"], o["certificate_id"]) for o in orders2]}, certificates '
              f'{[(c["id"], c["serial_number"]) for c in certs2]}')
    serial_hex = f'{int(certs2[0]["serial_number"]):x}' if certs2 else None
    pebble_serial = re.search(r'serial ([0-9a-f]+)', s5b['issued'][0]).group(1) if s5b['issued'] else None
    ev.append(f'row {s5b["cert"]} serial now {serial_hex}; Pebble issued {pebble_serial} before the kill')
    issued_total = pebble_log(s5b['since'], r'Issued certificate serial')
    ev.append(f'certificates Pebble issued since the renewal started: {len(issued_total)}')
    ev += ucm_log(since, r'(?i)resumes order|replaces rejected|alreadyReplaced')
    match = key_matches(s5b['cert'])
    ev.append(match)
    ok = ([c['id'] for c in certs2] == [s5b['cert']] and serial_hex == pebble_serial
          and [o['id'] for o in orders2] == [oid] and orders2[0]['status'] == 'issued'
          and len(issued_total) == 1 and 'key matches certificate: True' in match
          and not ucm_log(since, r'replaces rejected'))
    record('S5b resume after the crash', 'PASS' if ok else 'FAIL', *ev)


SCENARIOS = {'s1': s1_issuance, 's3': s3_retry_after, 's7': s7_long_cn,
             's2': s2_s6_scheduled_renewal, 's8': s8_binding_follows_renewal, 's4': s4_invalid,
             's5': s5_crash_after_finalize, 's5b': s5b_crash_during_renewal,
             's5r': s5_resume, 's5br': s5b_resume}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default=','.join(SCENARIOS))
    ap.add_argument('--report', default=None)
    args = ap.parse_args()
    t0 = time.monotonic()
    setup()
    for key in args.only.split(','):
        log(f'--- {key}')
        try:
            SCENARIOS[key]()
        except Exception as exc:  # a broken scenario must not hide the others
            record(key, 'ERROR', repr(exc))
    log(f'total {round(time.monotonic() - t0)} s')
    for name, res in RESULTS.items():
        print(f'{res["verdict"]:15} {name}')
    if args.report:
        with open(args.report, 'w') as fh:
            json.dump(RESULTS, fh, indent=2, default=str)
    return 0 if all(r['verdict'] == 'PASS' for r in RESULTS.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
