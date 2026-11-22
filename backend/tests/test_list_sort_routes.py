"""Server-sorted lists: every key in both directions, absent values last, ties settled by the id,
unknown keys refused. Runs on PostgreSQL too through UCM_TEST_APP_PG_URL."""
import json
import string
import threading
import uuid
from collections import namedtuple
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from models import AuditLog, Certificate, User, db
from models.auth_certificate import AuthCertificate
from utils.datetime_utils import utc_now
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

D = datetime
ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)
Seeded = namedtuple('Seeded', 'url params rows_of values per_page')


def _key(value):
    # The server folds ASCII letters only and compares UTF-8 bytes, on both engines
    return value.translate(ASCII_LOWER).encode() if isinstance(value, str) else value


def expected_order(values, descending):
    """The ids of *values* ({id: value}) in the contract's order: value, then id, absent values last."""
    present = sorted(((_key(v), i) for i, v in values.items() if v is not None), reverse=descending)
    absent = sorted((i for i, v in values.items() if v is None), reverse=descending)
    return [i for _, i in present] + absent


def walk(client, url, params, rows_of, per_page):
    """Every id the list gives, page after page."""
    seen = []
    for page in range(1, 400):
        r = client.get(url, query_string={**params, 'page': page, 'per_page': per_page})
        assert r.status_code == 200, r.data
        rows = rows_of(r.get_json())
        if not rows:
            return seen
        seen += [row['id'] for row in rows]
    raise AssertionError(f'{url} never ran out of pages')


def _tag():
    return f'srt{uuid.uuid4().hex[:8]}'


def _keep_nulls(row, *names):
    """Writes NULL where *row* was given None: a column default would otherwise fill it at flush."""
    absent = {name: None for name in names if getattr(row, name) is None}
    db.session.add(row)
    db.session.flush()
    if absent:
        type(row).query.filter_by(id=row.id).update(absent, synchronize_session=False)
    return row.id


def _by_key(ids, columns):
    """{key: {id: value}} from one tuple of values per id."""
    return {key: dict(zip(ids, values)) for key, values in columns.items()}


# --- /certificates -------------------------------------------------------------

@pytest.fixture(scope='module')
def certificates(app):
    tag = _tag()
    rows = [  # subject_cn, descr, issuer, valid_to, valid_from, created_at, serial, key_algo, source, revoked
        ('beta', 'Kilo', 'CN=Zed', D(2030, 1, 1), D(2020, 1, 1), D(2024, 1, 1), 'B', 'RSA 2048', 'acme', False),
        (None, 'Alpha', None, None, None, D(2024, 1, 1), 'a', None, None, True),
        ('BETA', 'alpha', 'cn=zed', D(2030, 1, 1), D(2021, 6, 1), D(2023, 1, 1), 'c', 'rsa 2048', 'manual', False),
        ('Gamma', 'zulu', 'CN=Alpha', D(2027, 1, 1), D(2020, 1, 1), D(2025, 1, 1), 'A', 'EC P-256', 'scep', True),
        ('Éclair', 'Écho', 'CN=Éa', D(2029, 1, 1), D(2022, 1, 1), None, 'd', 'Ed25519', 'acme', False),
    ]
    ids = []
    with app.app_context():
        for cn, descr, issuer, valid_to, valid_from, created, serial, algo, source, revoked in rows:
            cert = Certificate(refid=str(uuid.uuid4()), subject=f'CN={tag}', subject_cn=cn, descr=descr,
                               issuer=issuer, valid_to=valid_to, valid_from=valid_from, created_at=created,
                               serial_number=f'{tag}{serial}', key_algo=algo, source=source,
                               revoked=revoked, crt='Zm9v')
            ids.append(_keep_nulls(cert, 'created_at', 'source'))
        db.session.commit()
    names = [r[0] or r[1] for r in rows]
    values = _by_key(ids, {
        'subject': names, 'subject_cn': names, 'descr': [r[1] for r in rows],
        'issuer': [r[2] for r in rows], 'valid_to': [r[3] for r in rows], 'valid_from': [r[4] for r in rows],
        'created_at': [r[5] for r in rows], 'serial_number': [f'{tag}{r[6]}' for r in rows],
        'key_algo': [r[7] for r in rows], 'source': [r[8] or 'manual' for r in rows],
        'revoked': [r[9] for r in rows],
    })
    yield Seeded('/api/v2/certificates', {'search': tag}, lambda b: b['data'], values, 2)
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


# --- /csrs and /csrs/history -----------------------------------------------------

@pytest.fixture(scope='module')
def csr_rows(app, auth_client):
    tag = _tag()
    ids = []
    for i in range(7):
        r = auth_client.post('/api/v2/csrs', json={'cn': f'{tag}-{i}.example', 'key_type': 'RSA 2048'})
        assert r.status_code in (200, 201), r.data
        ids.append(r.get_json()['data']['id'])
    rows = [  # subject_cn, descr, created_by, created_at, key_algo, valid_from, valid_to, signed
        ('b', 'q', 'Zoe', D(2024, 1, 1), 'RSA 2048', None, D(2030, 1, 1), False),
        (None, 'A', 'adam', D(2024, 1, 1), None, D(2021, 1, 1), None, False),
        ('B', 'x', None, D(2023, 1, 1), 'rsa 2048', D(2020, 1, 1), D(2030, 1, 1), False),
        ('c', 'y', 'ZOE', None, 'EC P-256', None, D(2028, 1, 1), False),
        ('m', 'r', 'kim', D(2025, 1, 1), 'EC P-384', D(2022, 1, 1), D(2031, 1, 1), True),
        (None, 'K', 'Kim', D(2025, 1, 1), None, None, None, True),
        ('a', 'z', None, D(2022, 1, 1), 'RSA 4096', D(2022, 1, 1), D(2031, 1, 1), True),
    ]
    with app.app_context():
        for row_id, (cn, descr, by, created, algo, vfrom, vto, signed) in zip(ids, rows):
            cert = db.session.get(Certificate, row_id)
            cert.subject_cn, cert.descr, cert.created_by, cert.created_at = cn, descr, by, created
            cert.key_algo, cert.valid_from, cert.valid_to = algo, vfrom, vto
            if signed:
                cert.crt = 'Zm9v'
        db.session.commit()
    columns = {
        'cn': [r[0] or r[1] for r in rows], 'requester': [r[2] for r in rows], 'created_at': [r[3] for r in rows],
        'key_type': [r[4] for r in rows], 'signed_at': [r[5] for r in rows], 'valid_to': [r[6] for r in rows],
        'id': ids,
    }
    pending = [i for i, r in zip(ids, rows) if not r[7]]
    signed = [i for i, r in zip(ids, rows) if r[7]]
    # The requests carry keys: drop_new_cas_and_certificates deletes them through the service
    return tag, _by_key(ids, columns), pending, signed


def _subset(values, ids):
    return {key: {i: v for i, v in by_id.items() if i in ids} for key, by_id in values.items()}


@pytest.fixture(scope='module')
def csrs(csr_rows):
    tag, values, pending, _ = csr_rows
    return Seeded('/api/v2/csrs', {'search': tag}, lambda b: b['data'], _subset(values, pending), 2)


@pytest.fixture(scope='module')
def csrs_history(csr_rows):
    tag, values, _, signed = csr_rows
    return Seeded('/api/v2/csrs/history', {'search': tag}, lambda b: b['data'], _subset(values, signed), 2)


# --- /ssh/certificates -------------------------------------------------------------

@pytest.fixture(scope='module')
def ssh(app):
    from models.ssh import SSHCertificate, SSHCertificateAuthority
    tag = _tag()
    now = utc_now()
    with app.app_context():
        cas = []
        for name in ('beta CA', 'Alpha CA'):
            ca = SSHCertificateAuthority(descr=f'{name} {tag}', ca_type='user', public_key='ssh-ed25519 AAAA',
                                         private_key='unused', key_type='ed25519', fingerprint=f'SHA256:{tag}{name}')
            db.session.add(ca)
            db.session.flush()
            cas.append(ca)
        rows = [  # ca, cert_type, key_id, serial, valid_from, valid_to, created_at, revoked, status rank
            (0, 'user', 'b', 5, D(2024, 1, 1), now + timedelta(days=90), D(2024, 1, 1), False, 2),
            (1, 'host', 'A', 5, D(2023, 1, 1), now - timedelta(days=1), D(2024, 1, 1), False, 0),
            (0, 'user', 'B', 7, D(2023, 1, 1), now + timedelta(days=3), None, False, 1),
            (1, 'User', 'c', 1, D(2025, 1, 1), now + timedelta(days=90), D(2022, 1, 1), True, 3),
            (0, 'host', 'a', 2, D(2025, 1, 1), now - timedelta(days=2), D(2026, 1, 1), False, 0),
        ]
        ids = []
        for ca, kind, key_id, serial, vfrom, vto, created, revoked, _ in rows:
            cert = SSHCertificate(ssh_ca_id=cas[ca].id, cert_type=kind, key_id=key_id, public_key='ssh-ed25519 AAAA',
                                  certificate='ssh-ed25519-cert-v01@openssh.com AAAA', principals='["alice"]',
                                  serial=serial, valid_from=vfrom, valid_to=vto, key_type='ed25519',
                                  fingerprint=f'SHA256:{tag}{key_id}{serial}', created_at=created, revoked=revoked)
            ids.append(_keep_nulls(cert, 'created_at'))
        names = [cas[r[0]].descr for r in rows]
        ca_ids = [ca.id for ca in cas]
        db.session.commit()
    values = _by_key(ids, {
        'id': ids, 'key_id': [r[2] for r in rows], 'cert_type': [r[1] for r in rows], 'serial': [r[3] for r in rows],
        'valid_from': [r[4] for r in rows], 'valid_to': [r[5] for r in rows], 'created_at': [r[6] for r in rows],
        'ca': names, 'status': [r[8] for r in rows],
    })
    return Seeded('/api/v2/ssh/certificates', {'ca_id': ca_ids}, lambda b: b['data'], values, 2)


# --- /user-certificates ---------------------------------------------------------------

@pytest.fixture(scope='module')
def user_certificates(app, create_cert):
    tag = _tag()
    now = utc_now()
    with app.app_context():
        owner = User(username=f'zz-sort-{tag}', email=f'{tag}@example.test', role='viewer')
        owner.set_password(uuid.uuid4().hex)
        db.session.add(owner)
        db.session.commit()
        owners = {'admin': User.query.filter_by(username='admin').first().id, 'other': owner.id}
    # name, owner, created_at, valid_until, last_used_at, certificate state, status rank
    rows = [
        ('b', 'admin', D(2024, 1, 1), D(2030, 1, 1), None, 'valid', 2),
        ('A', 'other', D(2024, 1, 1), None, D(2025, 1, 1), 'expired', 0),
        ('B', 'admin', None, D(2029, 1, 1), D(2025, 1, 1), 'revoked', 3),
        (None, 'other', D(2023, 1, 1), D(2030, 1, 1), None, 'expiring', 1),
        ('c', 'admin', D(2026, 1, 1), None, D(2026, 1, 1), 'orphan', 4),
        ('a', 'other', D(2022, 1, 1), D(2031, 1, 1), None, 'expired', 0),
    ]
    ids = []
    for i, (name, who, created, until, used, state, _) in enumerate(rows):
        serial, issuer = f'{tag}-none-{i}', ''
        if state != 'orphan':
            made = create_cert(cn=f'{tag}-{i}.example')
            with app.app_context():
                cert = db.session.get(Certificate, made['id'])
                cert.revoked = state == 'revoked'
                cert.valid_to = {'expired': now - timedelta(days=1),
                                 'expiring': now + timedelta(days=5)}.get(state, cert.valid_to)
                serial, issuer = cert.serial_number, cert.issuer
                db.session.commit()
        with app.app_context():
            row = AuthCertificate(user_id=owners[who], cert_serial=serial, cert_subject=f'CN={tag}-{i}',
                                  cert_issuer=issuer, cert_fingerprint='', name=name, enabled=True,
                                  created_at=created, valid_until=until, last_used_at=used)
            ids.append(_keep_nulls(row, 'created_at'))
            db.session.commit()
    usernames = {'admin': 'admin', 'other': f'zz-sort-{tag}'}
    values = _by_key(ids, {
        'name': [r[0] for r in rows], 'owner': [usernames[r[1]] for r in rows], 'created_at': [r[2] for r in rows],
        'valid_until': [r[3] for r in rows], 'last_used_at': [r[4] for r in rows], 'status': [r[6] for r in rows],
    })
    yield Seeded('/api/v2/user-certificates', {'search': tag}, lambda b: b['data']['items'], values, 2)
    with app.app_context():
        AuthCertificate.query.filter(AuthCertificate.id.in_(ids)).delete(synchronize_session=False)
        User.query.filter_by(id=owners['other']).delete()
        db.session.commit()


# --- /acme/history ---------------------------------------------------------------------

@pytest.fixture(scope='module')
def acme_history(app):
    tag = _tag()
    rows = [  # subject_cn, valid_to, created_at, source
        ('b.example', D(2030, 1, 1), D(2024, 1, 1), 'acme'),
        (None, None, D(2024, 1, 1), 'letsencrypt'),
        ('B.example', D(2030, 1, 1), None, 'acme_client'),
        ('a.example', D(2027, 1, 1), D(2023, 1, 1), 'acme'),
    ]
    ids = []
    with app.app_context():
        for cn, vto, created, source in rows:
            cert = Certificate(refid=str(uuid.uuid4()), subject=f'CN={cn}', subject_cn=cn, descr=tag,
                               valid_to=vto, created_at=created, source=source, crt='Zm9v')
            ids.append(_keep_nulls(cert, 'created_at'))
        db.session.commit()
    values = _by_key(ids, {'common_name': [r[0] for r in rows], 'valid_to': [r[1] for r in rows],
                           'created_at': [r[2] for r in rows], 'source': [r[3] for r in rows]})
    yield Seeded('/api/v2/acme/history', {'search': tag}, lambda b: b['data'], values, 2)
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


# --- /audit/logs -------------------------------------------------------------------------

@pytest.fixture(scope='module')
def audit(app):
    from services.audit_service import AuditService
    tag = _tag()
    with app.app_context():
        for i in range(3):
            AuditService.log_action(action='sort_probe', resource_type='test', details=f'{tag} {i}')
        rows = AuditLog.query.filter(AuditLog.details.like(f'{tag}%')).all()
        values = {'timestamp': {row.id: row.timestamp for row in rows}}
    assert len(values['timestamp']) == 3
    return Seeded('/api/v2/audit/logs', {'search': tag}, lambda b: b['data'], values, 2)


# --- ACME accounts, local orders ---------------------------------------------------------

@pytest.fixture(scope='module')
def acme_rows(app):
    from models.acme_models import AcmeAccount, AcmeOrder
    tag = _tag()
    accounts = [  # account_id, status, contact, created_at, orders
        (f'b-{tag}', 'valid', '["mailto:b@example.test"]', D(2024, 1, 1), 2),
        (f'A-{tag}', 'revoked', None, D(2024, 1, 1), 0),
        (f'B-{tag}', 'deactivated', '["mailto:B@example.test"]', D(2023, 1, 1), 2),
        (f'c-{tag}', 'valid', '["mailto:a@example.test"]', D(2026, 1, 1), 1),
    ]
    orders = [  # account index, status, domain, created_at, expires
        (0, 'valid', 'b', D(2024, 1, 1), D(2024, 2, 1)),
        (0, 'pending', 'A', D(2024, 1, 1), D(2024, 2, 1)),
        (2, 'invalid', 'B', D(2023, 1, 1), D(2023, 2, 1)),
        (2, 'ready', 'c', D(2025, 1, 1), D(2024, 2, 1)),
        (3, 'processing', 'a', D(2022, 1, 1), D(2022, 2, 1)),
    ]
    with app.app_context():
        account_ids = []
        for account_id, status, contact, created, _ in accounts:
            row = AcmeAccount(account_id=account_id, jwk='{}', jwk_thumbprint=f'{account_id}-{uuid.uuid4().hex}',
                              status=status, contact=contact, created_at=created)
            db.session.add(row)
            db.session.flush()
            account_ids.append(row.id)
        order_ids = []
        for index, status, domain, created, expires in orders:
            identifiers = json.dumps([{'type': 'dns', 'value': f'{domain}.{tag}.example'}])
            row = AcmeOrder(account_id=accounts[index][0], status=status, identifiers=identifiers,
                            created_at=created, expires=expires)
            db.session.add(row)
            db.session.flush()
            order_ids.append((row.id, identifiers))
        db.session.commit()
    rank = {'pending': 0, 'ready': 1, 'processing': 2, 'valid': 3, 'invalid': 4}
    yield {
        'accounts': _by_key(account_ids, {
            'account_id': [a[0] for a in accounts], 'status': [{'valid': 0, 'deactivated': 1, 'revoked': 2}[a[1]]
                                                               for a in accounts],
            'contact': [a[2] for a in accounts], 'created_at': [a[3] for a in accounts],
            'orders': [a[4] for a in accounts]}),
        'orders': _by_key([o[0] for o in order_ids], {
            'created_at': [o[3] for o in orders], 'expires': [o[4] for o in orders],
            'status': [rank[o[1]] for o in orders], 'account': [accounts[o[0]][0] for o in orders],
            'domain': [i for _, i in order_ids]}),
        'tag': tag, 'account_ids': account_ids,
    }
    with app.app_context():
        AcmeOrder.query.filter(AcmeOrder.id.in_([o[0] for o in order_ids])).delete(synchronize_session=False)
        AcmeAccount.query.filter(AcmeAccount.id.in_(account_ids)).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture(scope='module')
def acme_accounts(acme_rows):
    return Seeded('/api/v2/acme/accounts', {}, lambda b: b['data'], acme_rows['accounts'], 3)


@pytest.fixture(scope='module')
def acme_orders(acme_rows):
    return Seeded('/api/v2/acme/orders', {'domain': acme_rows['tag']}, lambda b: b['data']['items'],
                  acme_rows['orders'], 2)


# --- EAB credentials -------------------------------------------------------------------------

@pytest.fixture(scope='module')
def eab(app):
    from models import AcmeEabCredential
    tag = _tag()
    rows = [  # label, kid, status, created_at, expires_at, used_at
        ('b', f'{tag}-B', 'active', D(2024, 1, 1), None, D(2025, 1, 1)),
        (None, f'{tag}-a', 'revoked', D(2024, 1, 1), D(2030, 1, 1), None),
        ('B', f'{tag}-c', 'active', D(2023, 1, 1), D(2029, 1, 1), D(2025, 1, 1)),
        ('a', f'{tag}-A', 'revoked', D(2026, 1, 1), D(2030, 1, 1), None),
    ]
    ids = []
    with app.app_context():
        for label, kid, status, created, expires, used in rows:
            cred = AcmeEabCredential(kid=kid, label=label, status=status, created_at=created,
                                     expires_at=expires, used_at=used)
            cred.hmac_key_b64 = 'AAAA'
            db.session.add(cred)
            db.session.flush()
            ids.append(cred.id)
        db.session.commit()
    values = _by_key(ids, {'label': [r[0] for r in rows], 'kid': [r[1] for r in rows],
                           'status': [r[2] for r in rows], 'created_at': [r[3] for r in rows],
                           'expires_at': [r[4] for r in rows], 'used_at': [r[5] for r in rows]})
    yield Seeded('/api/v2/acme/eab-credentials', {}, lambda b: b['data'], values, 3)
    with app.app_context():
        AcmeEabCredential.query.filter(AcmeEabCredential.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


# --- Key recovery ----------------------------------------------------------------------------

@pytest.fixture(scope='module')
def key_recovery(app):
    from models import KeyRecoveryRequest
    rows = [  # cert_cn, status, requested_by, requested_at
        ('b', 'approved', 'Zoe', D(2024, 1, 1)),
        (None, 'pending', 'adam', D(2024, 1, 1)),
        ('B', 'cancelled', 'zoe', D(2023, 1, 1)),
        ('a', 'recovered', 'Kim', D(2026, 1, 1)),
        ('c', 'rejected', 'kim', D(2022, 1, 1)),
    ]
    rank = {'pending': 0, 'approved': 1, 'recovered': 2, 'rejected': 3, 'cancelled': 4}
    ids = []
    with app.app_context():
        for cn, status, by, at in rows:
            req = KeyRecoveryRequest(cert_id=1, cert_cn=cn, reason='sort', status=status,
                                     requested_by=by, requested_at=at)
            db.session.add(req)
            db.session.flush()
            ids.append(req.id)
        db.session.commit()
    values = _by_key(ids, {'id': ids, 'cert_cn': [r[0] for r in rows], 'status': [rank[r[1]] for r in rows],
                           'requested_by': [r[2] for r in rows], 'requested_at': [r[3] for r in rows]})
    yield Seeded('/api/v2/key-recovery', {}, lambda b: b['data']['requests'], values, 3)
    with app.app_context():
        KeyRecoveryRequest.query.filter(KeyRecoveryRequest.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


# --- SCEP requests ----------------------------------------------------------------------------

@pytest.fixture(scope='module')
def scep_requests(app):
    from models.scep import SCEPRequest
    tag = _tag()
    rows = [  # transaction_id, status, subject, client_ip, created_at
        (f'b-{tag}', 'approved', 'CN=b', '10.0.0.2', D(2024, 1, 1)),
        (f'A-{tag}', 'pending', None, None, D(2024, 1, 1)),
        (f'B-{tag}', 'rejected', 'CN=B', '10.0.0.10', None),
        (f'c-{tag}', 'pending', 'CN=a', '10.0.0.2', D(2026, 1, 1)),
    ]
    rank = {'pending': 0, 'approved': 1, 'rejected': 2}
    ids = []
    with app.app_context():
        for tx, status, subject, ip, created in rows:
            req = SCEPRequest(transaction_id=tx, csr='AAAA', status=status, subject=subject,
                              client_ip=ip, created_at=created)
            ids.append(_keep_nulls(req, 'created_at'))
        db.session.commit()
    values = _by_key(ids, {'transaction_id': [r[0] for r in rows], 'status': [rank[r[1]] for r in rows],
                           'subject': [r[2] for r in rows], 'client_ip': [r[3] for r in rows],
                           'created_at': [r[4] for r in rows]})
    yield Seeded('/api/v2/scep/requests', {'search': tag}, lambda b: b['data'], values, 2)
    with app.app_context():
        SCEPRequest.query.filter(SCEPRequest.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


# --- Discovered certificates -------------------------------------------------------------------

@pytest.fixture(scope='module')
def discovery(app):
    from models.discovered_certificate import DiscoveredCertificate
    tag = _tag()
    rows = [  # target, subject, issuer, not_after, status, first_seen, last_seen
        ('b.example', 'CN=b', 'CN=Z', D(2030, 1, 1), 'managed', D(2024, 1, 1), D(2025, 1, 1)),
        ('A.example', None, None, None, 'error', D(2024, 1, 1), D(2025, 1, 1)),
        ('B.example', 'CN=B', 'cn=z', D(2030, 1, 1), 'unmanaged', None, D(2024, 1, 1)),
        ('a.example', 'CN=a', 'CN=A', D(2027, 1, 1), 'managed', D(2023, 1, 1), None),
    ]
    rank = {'error': 0, 'unmanaged': 1, 'managed': 2}
    ids = []
    with app.app_context():
        for target, subject, issuer, not_after, status, first, last in rows:
            row = DiscoveredCertificate(target=target, port=443, subject=subject, issuer=issuer, not_after=not_after,
                                        status=status, first_seen=first, last_seen=last,
                                        serial_number=f'{tag}{len(ids)}')
            ids.append(_keep_nulls(row, 'first_seen', 'last_seen'))
        db.session.commit()
    values = _by_key(ids, {'target': [r[0] for r in rows], 'subject': [r[1] for r in rows],
                           'issuer': [r[2] for r in rows], 'not_after': [r[3] for r in rows],
                           'status': [rank[r[4]] for r in rows], 'first_seen': [r[5] for r in rows],
                           'last_seen': [r[6] for r in rows]})
    yield Seeded('/api/v2/discovery', {'search': tag}, lambda b: b['data']['items'], values, 2)
    with app.app_context():
        DiscoveredCertificate.query.filter(DiscoveredCertificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


# --- Windows enrolment profiles ----------------------------------------------------------------

@pytest.fixture(scope='module')
def windows_profiles(app):
    from models import WindowsEnrollmentProfile
    from tests.keytab_support import keytab
    tag = _tag()
    rows = [  # name, realm, created_at, enabled, keytab, state rank
        (f'b-{tag}', f'B.{tag}.TEST', D(2024, 1, 1), True, True, 2),
        (f'A-{tag}', None, D(2024, 1, 1), True, False, 1),
        (f'B-{tag}x', f'a.{tag}.test', None, False, True, 3),
        (f'c-{tag}', f'C.{tag}.TEST', D(2023, 1, 1), True, True, 2),
    ]
    ids = []
    with app.app_context():
        for name, realm, created, enabled, with_keytab, _ in rows:
            profile = WindowsEnrollmentProfile(name=name, realm=realm, enabled=enabled, created_at=created)
            if with_keytab:
                profile.set_keytab(keytab(f'HTTP/ucm.example@{(realm or tag).upper()}'))
            ids.append(_keep_nulls(profile, 'created_at'))
        db.session.commit()
    values = _by_key(ids, {'name': [r[0] for r in rows], 'realm': [r[1] for r in rows],
                           'created_at': [r[2] for r in rows], 'status': [r[5] for r in rows]})
    yield Seeded('/api/v2/windows-profiles', {'q': tag}, lambda b: b['data'], values, 2)
    with app.app_context():
        WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()


ROUTES = {
    'certificates': ('subject', 'subject_cn', 'descr', 'issuer', 'valid_to', 'valid_from', 'created_at',
                     'serial_number', 'key_algo', 'source', 'revoked'),
    'csrs': ('cn', 'requester', 'created_at', 'key_type', 'signed_at', 'valid_to', 'id'),
    'csrs_history': ('cn', 'requester', 'created_at', 'key_type', 'signed_at', 'valid_to', 'id'),
    'ssh': ('id', 'key_id', 'cert_type', 'serial', 'valid_from', 'valid_to', 'created_at', 'ca', 'status'),
    'user_certificates': ('name', 'owner', 'created_at', 'valid_until', 'last_used_at', 'status'),
    'acme_history': ('common_name', 'valid_to', 'created_at', 'source'),
    'audit': ('timestamp',),
    'acme_orders': ('created_at', 'expires', 'status', 'account', 'domain'),
    'acme_accounts': ('created_at', 'account_id', 'status', 'contact', 'orders'),
    'eab': ('created_at', 'label', 'kid', 'status', 'expires_at', 'used_at'),
    'key_recovery': ('id', 'requested_at', 'status', 'cert_cn', 'requested_by'),
    'scep_requests': ('created_at', 'status', 'subject', 'transaction_id', 'client_ip'),
    'discovery': ('last_seen', 'first_seen', 'not_after', 'target', 'issuer', 'subject', 'status'),
    'windows_profiles': ('name', 'realm', 'created_at', 'status'),
}
CASES = [(route, key) for route, keys in ROUTES.items() for key in keys]


@pytest.mark.parametrize('order', ['asc', 'desc'])
@pytest.mark.parametrize('route,key', CASES)
def test_each_key_sorts_both_ways_with_absent_values_last(request, auth_client, route, key, order):
    seeded = request.getfixturevalue(route)
    seen = walk(auth_client, seeded.url, {**seeded.params, 'sort_by': key, 'sort_order': order},
                seeded.rows_of, seeded.per_page)
    # Pages never share a row, and the seeded rows come in the contract's order
    assert len(seen) == len(set(seen))
    mine = [i for i in seen if i in seeded.values[key]]
    assert mine == expected_order(seeded.values[key], order == 'desc')


DEFAULTS = {
    'certificates': ('subject', 'asc'), 'csrs': ('created_at', 'desc'), 'ssh': ('created_at', 'desc'),
    'user_certificates': ('created_at', 'desc'), 'acme_history': ('created_at', 'desc'),
    'audit': ('timestamp', 'desc'), 'acme_orders': ('created_at', 'desc'), 'acme_accounts': ('created_at', 'desc'),
    'eab': ('created_at', 'desc'), 'key_recovery': ('id', 'desc'), 'scep_requests': ('created_at', 'desc'),
    'discovery': ('last_seen', 'desc'), 'windows_profiles': ('name', 'asc'),
}


@pytest.mark.parametrize('route', sorted(DEFAULTS))
def test_without_a_sort_the_default_key_applies(request, auth_client, route):
    seeded = request.getfixturevalue(route)
    key, order = DEFAULTS[route]
    seen = walk(auth_client, seeded.url, seeded.params, seeded.rows_of, seeded.per_page)
    mine = [i for i in seen if i in seeded.values[key]]
    assert mine == expected_order(seeded.values[key], order == 'desc')


URLS = {
    'certificates': '/api/v2/certificates', 'csrs': '/api/v2/csrs', 'csrs_history': '/api/v2/csrs/history',
    'ssh': '/api/v2/ssh/certificates', 'user_certificates': '/api/v2/user-certificates',
    'acme_history': '/api/v2/acme/history', 'audit': '/api/v2/audit/logs', 'acme_orders': '/api/v2/acme/orders',
    'acme_accounts': '/api/v2/acme/accounts', 'eab': '/api/v2/acme/eab-credentials',
    'key_recovery': '/api/v2/key-recovery', 'scep_requests': '/api/v2/scep/requests',
    'discovery': '/api/v2/discovery', 'windows_profiles': '/api/v2/windows-profiles',
}


@pytest.mark.parametrize('route', sorted(URLS))
@pytest.mark.parametrize('params,needle', [
    ({'sort_by': 'nonsense'}, "Unknown sort_by 'nonsense'"),
    ({'sort_by': 'id; DROP TABLE x'}, 'Unknown sort_by'),
    ({'sort_order': 'sideways'}, "Unknown sort_order 'sideways'"),
])
def test_an_unknown_key_or_direction_is_refused_with_the_allowed_keys(auth_client, route, params, needle):
    r = auth_client.get(URLS[route], query_string=params)
    assert r.status_code == 400, r.data
    body = r.get_json()
    assert needle in body['detail']
    allowed = body['details']['allowed_sort_by']
    assert allowed == sorted(set(ROUTES[route]) | _UNTESTED.get(route, set()))
    if 'sort_by' in params:
        assert body['detail'].endswith('allowed: ' + ', '.join(allowed))


# Keys whose order has its own tests (tie-break of the computed ranks: test_certificates_list_tiebreak)
_UNTESTED = {'certificates': {'status', 'compliance_grade'}}


def test_upper_case_direction_and_empty_key_read_as_given_and_default(auth_client, scep_requests):
    seen = walk(auth_client, scep_requests.url, {**scep_requests.params, 'sort_by': '', 'sort_order': 'ASC'},
                scep_requests.rows_of, 2)
    assert seen == expected_order(scep_requests.values['created_at'], False)


# --- The capped lists: their callers keep their shape and get the total ------------------------

@pytest.mark.parametrize('route,default_size', [('acme_accounts', 100), ('eab', 200), ('key_recovery', 500)])
def test_a_formerly_capped_list_keeps_its_shape_and_says_its_total(request, auth_client, route, default_size):
    seeded = request.getfixturevalue(route)
    r = auth_client.get(seeded.url)
    assert r.status_code == 200, r.data
    body = r.get_json()
    rows = seeded.rows_of(body)
    assert isinstance(rows, list) and len(rows) >= len(next(iter(seeded.values.values())))
    assert body['meta']['per_page'] == default_size and body['meta']['page'] == 1
    assert body['meta']['total'] == len(rows)
    if route == 'key_recovery':
        assert set(body['data']) == {'requests', 'dual_control'}
    small = auth_client.get(seeded.url, query_string={'per_page': 1, 'page': 2}).get_json()
    assert len(seeded.rows_of(small)) == 1 and small['meta']['total'] == body['meta']['total']


def test_discovery_keeps_limit_and_offset(auth_client, discovery):
    order = expected_order(discovery.values['last_seen'], True)
    r = auth_client.get(discovery.url, query_string={**discovery.params, 'limit': 2, 'offset': 1})
    assert r.status_code == 200, r.data
    assert [row['id'] for row in r.get_json()['data']['items']] == order[1:3]


def _statements(app, client, url):
    seen = []
    mine = threading.get_ident()

    def hook(conn, cursor, statement, *rest):
        if threading.get_ident() == mine:
            seen.append(statement)

    from utils.admin_allowlist import invalidate_cache
    with app.app_context():
        invalidate_cache()
        event.listen(db.engine, 'before_cursor_execute', hook)
        try:
            r = client.get(url)
        finally:
            event.remove(db.engine, 'before_cursor_execute', hook)
    assert r.status_code == 200, r.data
    return len(seen)


@pytest.mark.parametrize('sort_by', ['created_at', 'orders', 'status'])
def test_the_account_list_costs_the_same_statements_for_one_row_or_four(app, auth_client, acme_accounts, sort_by):
    one = _statements(app, auth_client, f'/api/v2/acme/accounts?per_page=1&sort_by={sort_by}')
    four = _statements(app, auth_client, f'/api/v2/acme/accounts?per_page=4&sort_by={sort_by}')
    assert one == four
