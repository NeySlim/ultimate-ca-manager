"""A certificate of a Windows enrollment profile renews through WSTEP only: EST
/simplereenroll and SCEP RenewalReq refuse it, whether its profile is enabled,
disabled or deleted since; a certificate of no profile renews as before."""
import uuid
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7

from models import AuditLog, Certificate, WindowsEnrollmentProfile, db
from services.scep.scep_service import SCEPService
from utils.datetime_utils import utc_now
from tests.test_est_rfc7030 import _post_csr, est_config  # noqa: F401
from tests.test_final_review_followups import _csr as _est_csr, _enrol, _pem
from tests.test_scep_renewal_challenge import ORIGINAL, _csr as _scep_csr, _enroll, _message, scep_ca  # noqa: F401
from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, PKI_STATUS_OID, _decrypt_response, _response_attributes,
)

STATES = ['enabled', 'disabled', 'deleted']


@pytest.fixture
def windows_profile(app):
    """A non-default profile removed afterwards, so no later file sees it."""
    with app.app_context():
        profile = WindowsEnrollmentProfile(name=f'c11-{uuid.uuid4().hex[:8]}', enabled=True)
        db.session.add(profile)
        db.session.commit()
        profile_id, name = profile.id, profile.name
    yield profile_id, name
    with app.app_context():
        Certificate.query.filter_by(windows_profile_id=profile_id).update(
            {'windows_profile_id': None}, synchronize_session=False)
        WindowsEnrollmentProfile.query.filter_by(id=profile_id).delete(synchronize_session=False)
        db.session.commit()


def _bind(cert, profile_id, state):
    """Record *cert* under the profile in *state*; 'deleted' keeps an id no profile holds."""
    if state == 'disabled':
        db.session.get(WindowsEnrollmentProfile, profile_id).enabled = False
    if state == 'deleted':
        top = db.session.query(db.func.max(WindowsEnrollmentProfile.id)).scalar() or 0
        profile_id = top + 1000
    Certificate.query.filter_by(serial_number=str(cert.serial_number)).update(
        {'windows_profile_id': profile_id}, synchronize_session=False)
    db.session.commit()


def _refusals(name):
    return AuditLog.query.filter(AuditLog.action == 'windows_enrollment.refused',
                                 AuditLog.details.contains(name)).all()


@pytest.mark.parametrize('state', STATES)
def test_est_reenroll_of_a_windows_profile_certificate_is_refused(
        client, app, est_config, windows_profile, state):
    profile_id, name = windows_profile
    cn = f'c11-est-{state}.example.test'
    leaf, key = _enrol(client, cn)
    with app.app_context():
        _bind(leaf, profile_id, state)
        before = Certificate.query.count()
    csr, _ = _est_csr(cn, key=key)

    r = _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf))

    assert r.status_code == 403, r.data
    assert b'Windows enrollment profile' in r.data
    with app.app_context():
        assert Certificate.query.count() == before
        row = Certificate.query.filter_by(serial_number=str(leaf.serial_number)).one()
        assert not row.archived
        (entry,) = AuditLog.query.filter(AuditLog.action == 'windows_enrollment.refused',
                                         AuditLog.details.contains(cn)).all()
        assert entry.success is False and 'EST' in entry.details
        if state == 'deleted':
            assert 'no longer exists' in entry.details
        else:
            assert entry.resource_name == name
            assert ('disabled' in entry.details) == (state == 'disabled')


def test_est_reenroll_of_a_wstep_certificate_recording_no_profile_is_refused(client, app, est_config):
    """A ``wstep`` row with no id belongs to the default profile (C-01): still not EST's to renew."""
    cn = 'c11-est-wstep.example.test'
    leaf, key = _enrol(client, cn)
    with app.app_context():
        Certificate.query.filter_by(serial_number=str(leaf.serial_number)).update(
            {'source': 'wstep'}, synchronize_session=False)
        db.session.commit()
    csr, _ = _est_csr(cn, key=key)
    r = _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf))
    assert r.status_code == 403, r.data
    assert b'Windows enrollment profile' in r.data


def test_est_reenroll_without_a_profile_still_renews(client, app, est_config):
    cn = 'c11-est-plain.example.test'
    leaf, key = _enrol(client, cn)
    csr, _ = _est_csr(cn, key=key)
    r = _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf))
    assert r.status_code == 200, r.data


def test_est_approval_of_a_held_reenroll_refuses_a_windows_certificate(
        client, app, est_config, windows_profile):
    """A re-enrolment queued before its certificate was bound is not issued on approval."""
    from services.est_approval import _issue
    from services.protocol_approval import ProtocolRequestGone
    cn = 'c11-est-held.example.test'
    leaf, key = _enrol(client, cn)
    csr, _ = _est_csr(cn, key=key)
    from cryptography.hazmat.primitives import serialization
    data = {'operation': 'reenroll', 'ca_id': est_config['id'], 'renewal_of': _pem(leaf),
            'csr': csr.public_bytes(serialization.Encoding.PEM).decode()}
    with app.app_context():
        _bind(leaf, windows_profile[0], 'enabled')
        before = Certificate.query.count()
        with pytest.raises(ProtocolRequestGone, match='windows_profile'):
            _issue(None, data)
        assert Certificate.query.count() == before


def _renewal(ca, ca_cert, issued, old_key, cn):
    request = _message(ca_cert, issued, old_key, 17,
                       _scep_csr(rsa.generate_private_key(public_exponent=65537, key_size=2048), cn))
    return SCEPService(ca.refid, challenge_password=ORIGINAL,
                       auto_approve=True).process_pkcs_req(request, '127.0.0.1')


@pytest.mark.parametrize('state', STATES)
def test_scep_renewal_of_a_windows_profile_certificate_is_refused(
        app, scep_ca, windows_profile, state):
    ca, ca_cert = scep_ca
    profile_id, name = windows_profile
    cn = f'c11-scep-{state}-{uuid.uuid4().hex[:6]}.example.test'
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issued = _enroll(ca, ca_cert, old_key, cn)
    _bind(issued, profile_id, state)
    before = Certificate.query.count()

    response, status = _renewal(ca, ca_cert, issued, old_key, cn)

    attrs = _response_attributes(response)
    assert status == 200
    # RFC 8894 §3.3.2.2: FAILURE with the failInfo of every refused renewal
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_OID] == str(SCEPService.FAIL_BAD_MESSAGE_CHECK)
    assert Certificate.query.count() == before
    (entry,) = _refusals(cn)
    assert entry.success is False and 'SCEP' in entry.details
    if state != 'deleted':
        assert entry.resource_name == name


def test_scep_renewal_without_a_profile_still_renews(app, scep_ca):
    ca, ca_cert = scep_ca
    cn = f'c11-scep-plain-{uuid.uuid4().hex[:6]}.example.test'
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issued = _enroll(ca, ca_cert, old_key, cn)
    response, _ = _renewal(ca, ca_cert, issued, old_key, cn)
    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    renewed = pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, old_key, issued))[0]
    assert renewed.subject == issued.subject


@pytest.mark.parametrize('lapse', ['valid', 'expired', 'superseded'])
def test_scep_manual_approval_refuses_a_windows_certificate(app, scep_ca, windows_profile, lapse):
    """A RenewalReq held before its certificate was bound is not issued on approval,
    even once that certificate has expired or been renewed by WSTEP."""
    ca, ca_cert = scep_ca
    cn = f'c11-scep-held-{uuid.uuid4().hex[:6]}.example.test'
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issued = _enroll(ca, ca_cert, old_key, cn)
    request = _message(ca_cert, issued, old_key, 17,
                       _scep_csr(rsa.generate_private_key(public_exponent=65537, key_size=2048), cn))
    service = SCEPService(ca.refid, challenge_password=ORIGINAL, auto_approve=False)
    response, _ = service.process_pkcs_req(request, '127.0.0.1')
    assert _response_attributes(response)[PKI_STATUS_OID] == '3'
    from models import SCEPRequest
    held = SCEPRequest.query.filter_by(ca_refid=ca.refid, status='pending').filter(
        SCEPRequest.subject.contains(cn)).one()
    _bind(issued, windows_profile[0], 'enabled')
    row = Certificate.query.filter_by(serial_number=str(issued.serial_number)).one()
    if lapse == 'expired':
        row.valid_to = utc_now() - timedelta(days=1)
    if lapse == 'superseded':
        row.archived = True
    db.session.commit()
    before = Certificate.query.count()
    with pytest.raises(Exception, match='Windows enrollment profile'):
        service.approve_request(held.transaction_id, 'admin')
    db.session.rollback()
    assert Certificate.query.count() == before


def test_scep_renewal_by_a_windows_certificate_past_its_not_after_is_audited(
        app, scep_ca, windows_profile, monkeypatch):
    """The validity window refuses it anyway: the refusal still says, and records, why."""
    ca, ca_cert = scep_ca
    profile_id, name = windows_profile
    cn = f'c11-scep-lapsed-{uuid.uuid4().hex[:6]}.example.test'
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issued = _enroll(ca, ca_cert, old_key, cn)
    _bind(issued, profile_id, 'enabled')
    later = issued.not_valid_after_utc.replace(tzinfo=None) + timedelta(days=1)
    monkeypatch.setattr('services.scep.scep_service.utc_now', lambda: later)

    response, _ = _renewal(ca, ca_cert, issued, old_key, cn)

    assert _response_attributes(response)[PKI_STATUS_OID] == '2'
    (entry,) = _refusals(cn)
    assert entry.resource_name == name


def test_a_revoked_windows_certificate_answers_revoked(app, scep_ca, windows_profile):
    from services.cert.issued_lookup import REVOKED, WINDOWS_PROFILE, protocol_renewal_status
    ca, ca_cert = scep_ca
    cn = f'c11-revoked-{uuid.uuid4().hex[:6]}.example.test'
    issued = _enroll(ca, ca_cert, rsa.generate_private_key(public_exponent=65537, key_size=2048), cn)
    _bind(issued, windows_profile[0], 'enabled')
    assert protocol_renewal_status(ca, issued)[1] == WINDOWS_PROFILE
    Certificate.query.filter_by(serial_number=str(issued.serial_number)).update(
        {'revoked': True}, synchronize_session=False)
    db.session.commit()
    try:
        assert protocol_renewal_status(ca, issued)[1] == REVOKED
    finally:
        Certificate.query.filter_by(serial_number=str(issued.serial_number)).update(
            {'revoked': False}, synchronize_session=False)
        db.session.commit()


def test_the_refusal_names_the_row_that_carries_the_profile(app, scep_ca, monkeypatch):
    """A plain live twin beside the archived Windows row: the audit reads the Windows one."""
    from types import SimpleNamespace
    from services.cert import issued_lookup
    ca, ca_cert = scep_ca
    cn = f'c11-twin-{uuid.uuid4().hex[:6]}.example.test'
    issued = _enroll(ca, ca_cert, rsa.generate_private_key(public_exponent=65537, key_size=2048), cn)
    plain = SimpleNamespace(revoked=False, archived=False, valid_to=None, windows_profile_id=None, source='scep')
    windows = SimpleNamespace(revoked=False, archived=True, valid_to=None, windows_profile_id=7, source='wstep')
    monkeypatch.setattr(issued_lookup, 'find_issued_rows', lambda *_: [plain, windows])
    assert issued_lookup.protocol_renewal_status(ca, issued) == (windows, issued_lookup.WINDOWS_PROFILE)

