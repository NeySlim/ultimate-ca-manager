"""A request the common name pattern refuses is an env:Sender fault and an audit entry naming the
template and the variable (SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL)."""

import pytest
from cryptography.x509.oid import NameOID

from models import Certificate, CertificateTemplate, db
from services.ad_connector import lookup as ad_lookup
from tests.test_wstep_kerberos_issue import _issued_cert_from_rstr
from tests.test_windows_profile_routing import _audits, _fault, _issue, _top_audit, world  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')
TEMPLATE = 'C04 A User'


def _identity(display_name):
    return {'dn_components': [('CN', 'User A'), ('CN', 'Users'), ('DC', 'c04a'), ('DC', 'test')],
            'upn': 'usera@c04a.test', 'mail': None, 'sam_account_name': 'usera',
            'display_name': display_name, 'given_name': None, 'surname': None}


@pytest.fixture
def patterned(app, world, monkeypatch):
    with app.app_context():
        template = db.session.get(CertificateTemplate, world['templates']['A User'])
        template.ad_derived_subject, template.subject_cn_pattern = True, '{displayName} (VPN)'
        db.session.commit()
    answer = {'identity': _identity('User A')}
    monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity', lambda config, sam: answer['identity'])
    return answer


@pytest.mark.parametrize('display_name,why', [
    (None, '{displayName} has no value in the directory for the requester'),
    ('', '{displayName} has no value in the directory for the requester'),
    ('U' * 59, 'the result is longer than 64 characters'),
    ('User\x00A', 'the result contains a control character'),
], ids=['absent', 'empty', 'too-long', 'control'])
def test_each_refusal_is_a_sender_fault_with_its_audit(app, client, world, patterned, display_name, why):
    patterned['identity'] = _identity(display_name)
    floor = _top_audit(app)
    message = f"Template '{TEMPLATE}' cannot build its common name: {why}"
    assert _fault(_issue(client, world, 'usera@C04A.TEST')) == (400, 's:Sender', message)
    rows = _audits(app, floor)
    assert [(action, user, name, ok) for action, user, name, _d, ok in rows] == [
        ('windows_enrollment.refused', 'usera@C04A.TEST', 'c04-a', False)]
    assert message in rows[0][3]


def test_the_pattern_names_the_issued_certificate(app, client, world, patterned):
    cert = _issued_cert_from_rstr(_issue(client, world, 'usera@C04A.TEST').data)
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'User A (VPN)'
    assert len(list(cert.subject)) == 1


# RFC 5280 §4.1.2.6: a subject the pattern renders is refused once another account's certificate carries it

SIDS = {'usera': 'S-1-5-21-4-5-6-1101', 'userb': 'S-1-5-21-4-5-6-1102'}
TAKEN = (f"Template '{TEMPLATE}' builds the subject CN=User A (VPN), "
         'which a certificate of another account already carries')


@pytest.fixture
def homonyms(app, world, patterned, monkeypatch):
    """usera and userb, two accounts of one display name, each with its own SID."""
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda config, sam: SIDS[sam])
    monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity',
                        lambda config, sam: dict(_identity('User A'), sam_account_name=sam,
                                                 upn=f'{sam}@c04a.test'))
    return patterned


def test_a_homonym_is_refused_with_the_holder_in_the_audit_only(app, client, world, homonyms):
    first = _issued_cert_from_rstr(_issue(client, world, 'usera@C04A.TEST').data)
    floor = _top_audit(app)
    assert _fault(_issue(client, world, 'userb@C04A.TEST')) == (400, 's:Sender', TAKEN)
    rows = _audits(app, floor)
    assert [(action, user, name, ok) for action, user, name, _d, ok in rows] == [
        ('windows_enrollment.refused', 'userb@C04A.TEST', 'c04-a', False)]
    assert f'{TAKEN} (serial {first.serial_number})' in rows[0][3]
    # The account that holds the subject is served again
    again = _issued_cert_from_rstr(_issue(client, world, 'usera@C04A.TEST').data)
    assert again.subject == first.subject


def test_an_approval_after_another_account_took_the_subject_is_refused(app, client, auth_client, world,
                                                                        homonyms):
    from tests.protocol_approval_support import approval_policy, approve, requests_of
    with approval_policy(app, world['cas']['A']['id'], 'c04-cn-taken') as policy_id:
        for principal in ('usera@C04A.TEST', 'userb@C04A.TEST'):
            assert b'Pending' in _issue(client, world, principal).data
        (a_id, *_a), (b_id, *_b) = requests_of(app, policy_id, 'wstep_request')
        approve(auth_client, b_id)
        r = auth_client.post(f'/api/v2/approvals/{a_id}/approve', json={'comment': 'ok'})
        body = r.get_json()
        assert body['message'] == 'Request closed', body
        statuses = {row[0]: (row[1], row[3] is None) for row in requests_of(app, policy_id, 'wstep_request')}
        assert statuses == {a_id: ('rejected', True), b_id: ('approved', False)}
        with app.app_context():
            holder = Certificate.query.filter_by(caref=world['cas']['A']['refid']).one()
            assert body['data']['issue_error'] == (
                f'The WSTEP request can no longer be issued: {TAKEN} (serial {holder.serial_number})')


def test_a_renewal_into_a_subject_another_account_holds_is_refused_and_audited(app, client, world, homonyms,
                                                                               monkeypatch):
    from tests.test_windows_profile_renewal import _enrolled, _renew_xml
    by_sid = {sid: sam for sam, sid in SIDS.items()}
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda config, sid: by_sid[sid])
    with app.app_context():
        db.session.get(CertificateTemplate, world['templates']['A User']).subject_cn_pattern = '{username}'
        db.session.commit()
    renewed, key = _enrolled(client, world, 'userb@C04A.TEST', 'c04-userb')
    with app.app_context():
        db.session.get(CertificateTemplate, world['templates']['A User']).subject_cn_pattern = '{displayName} (VPN)'
        db.session.commit()
    holder = _issued_cert_from_rstr(_issue(client, world, 'usera@C04A.TEST').data)
    floor = _top_audit(app)
    assert _fault(_renew_xml(client, renewed, key)) == (400, 's:Sender', TAKEN)
    rows = _audits(app, floor)
    assert [(action, ok) for action, _u, _n, _d, ok in rows] == [
        ('certificate.renewed', False), ('windows_enrollment.refused', False)]
    assert f'serial {holder.serial_number}' not in rows[0][3]
    assert rows[1][2] == 'c04-a'
    assert f'{TAKEN} (serial {holder.serial_number}) (renewed serial {renewed.serial_number}' in rows[1][3]
