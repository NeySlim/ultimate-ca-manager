"""A request the common name pattern refuses is an env:Sender fault and an audit entry naming the
template and the variable (SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL)."""

import pytest
from cryptography.x509.oid import NameOID

from models import CertificateTemplate, db
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
