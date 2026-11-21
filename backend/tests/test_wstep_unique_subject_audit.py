"""A WSTEP request refused by the CA's unique subject rule (RFC 5280 §4.1.2.6) writes exactly one
audit entry, whatever the route: Kerberos, UsernamePassword, renewal by TLS client certificate,
approval of a held request."""
import pytest

from models import CA, AuditLog, db
from services.wstep import CES_KERBEROS_PATH, CES_USERNAME_PASSWORD_PATH
from tests.protocol_approval_support import requests_of
from tests.test_windows_profile_renewal import (  # noqa: F401
    _enrolled, _renew_tls, _signed, account, directory, mtls_anchor)
from tests.test_windows_profile_routing import NEGOTIATE, _csr, _fault, held_on_b, world  # noqa: F401
from tests.test_wstep_issue import _basic_auth
from tests.test_wstep_kerberos_issue import _build_rst
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _enforce(app, ca_id):
    with app.app_context():
        db.session.get(CA, ca_id).enforce_unique_subject = True
        db.session.commit()


def _entries(app, floor):
    with app.app_context():
        return [(a.action, a.success, a.details) for a in
                AuditLog.query.filter(AuditLog.id > floor).order_by(AuditLog.id)]


def _floor(app):
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


def _taken(app, world, ca, cn):
    """*cn* carried under CA *ca* by another entity's certificate; the option on."""
    taken, _key = _signed(app, world['cas'][ca]['id'], cn)
    _enforce(app, world['cas'][ca]['id'])
    return taken


def _kerberos(app, client, world):
    taken = _taken(app, world, 'A', 'c17-audit-krb')
    floor = _floor(app)
    world['principal'] = 'usera@C04A.TEST'
    r = client.post(CES_KERBEROS_PATH, data=_build_rst(_csr('c17-audit-krb')), headers=NEGOTIATE)
    assert _fault(r)[0] == 400
    return taken, floor


def _username_password(app, client, world):
    taken = _taken(app, world, 'A', 'c17-audit-up')
    floor = _floor(app)
    r = client.post(CES_USERNAME_PASSWORD_PATH, data=_build_rst(_csr('c17-audit-up')), headers=_basic_auth())
    assert _fault(r)[0] == 400
    return taken, floor


def _tls_renewal(app, client, world):
    old, key = _enrolled(client, world, 'usera@C04A.TEST', 'c17-audit-tls')
    taken = _taken(app, world, 'A', 'c17-audit-tls')
    floor = _floor(app)
    with mtls_anchor(app, world['cas']['A']['refid']):
        assert _fault(_renew_tls(client, old, key))[0] == 400
    return taken, floor


def _approval(app, client, world, auth_client, policy_id):
    world['principal'] = 'userb@C04B.TEST'
    r = client.post(CES_KERBEROS_PATH, data=_build_rst(_csr('c17-audit-held')), headers=NEGOTIATE)
    assert b'Pending' in r.data, r.data
    (approval_id, *_), = requests_of(app, policy_id, 'wstep_request')
    taken = _taken(app, world, 'B', 'c17-audit-held')
    floor = _floor(app)
    body = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'}).get_json()
    assert body['message'] == 'Request closed', body
    return taken, floor


@pytest.mark.parametrize('route, action', [
    ('kerberos', 'windows_enrollment.refused'),
    ('username_password', 'windows_enrollment.refused'),
    ('tls_renewal', 'windows_enrollment.refused'),
    ('approval', 'approval_closed'),
])
def test_a_wstep_refusal_of_a_taken_subject_is_audited_once(
        app, client, auth_client, directory, account, held_on_b, route, action):
    if route == 'approval':
        taken, floor = _approval(app, client, directory, auth_client, held_on_b)
    else:
        taken, floor = {'kerberos': _kerberos, 'username_password': _username_password,
                        'tls_renewal': _tls_renewal}[route](app, client, directory)
    entries = _entries(app, floor)
    assert [a for a, _ok, _d in entries] == [action], entries
    assert f'serial {taken.serial_number})' in entries[0][2]
