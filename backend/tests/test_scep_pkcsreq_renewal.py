"""A client that renews with PKCSReq signs it with the certificate it holds
(RFC 8894 §2.3 case 3, left to CA policy). Signed by a certificate this
endpoint issued, it is a renewal: the challenge is still compared (§2.4),
only its expiry is waived, and the old certificate is replaced."""
import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7

from models import Certificate, SCEPRequest, db
from services.scep.scep_service import SCEPService
from tests.test_scep_intune_validation import _FakeIntuneClient
from tests.test_scep_renewal_challenge import (  # noqa: F401
    ORIGINAL, _csr, _enroll, _enroll_via, _message, scep_ca,
)
from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, PKI_STATUS_OID, _client_identity, _decrypt_response,
    _load_ca_material, _response_attributes,
)
from tests.test_windows_profile_protocol_renewal import _bind, _refusals, windows_profile  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

BAD_MESSAGE_CHECK = str(SCEPService.FAIL_BAD_MESSAGE_CHECK)


def _new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _cn(tag):
    return f'pkcsreq-{tag}-{uuid.uuid4().hex[:6]}.example.test'


def _row(cert):
    return Certificate.query.filter_by(serial_number=str(cert.serial_number)).one()


@pytest.fixture
def webhooks(monkeypatch):
    calls = []
    import services.webhook_service as hooks
    monkeypatch.setattr(hooks, 'emit_cert_renewed', lambda *a, **k: calls.append('renewed'))
    monkeypatch.setattr(hooks, 'emit_cert_issued', lambda *a, **k: calls.append('issued'))
    return calls


def _service(ca, expired=True, **kwargs):
    kwargs.setdefault('auto_approve', True)
    return SCEPService(ca.refid, challenge_password=ORIGINAL, challenge_expired=expired, **kwargs)


def test_pkcsreq_signed_by_an_issued_cert_renews_past_challenge_expiry(app, scep_ca, webhooks,
                                                                       monkeypatch):
    ca, ca_cert = scep_ca
    from services import protocol_approval
    gate, gated = protocol_approval.gate_protocol_issuance, []
    monkeypatch.setattr(protocol_approval, 'gate_protocol_issuance',
                        lambda *a, **k: gated.append(k['renewal']) or gate(*a, **k))
    cn = _cn('renew')
    old_key = _new_key()
    issued = _enroll(ca, ca_cert, old_key, cn)
    webhooks.clear()
    gated.clear()
    new_key = _new_key()
    request = _message(ca_cert, issued, old_key, 19, _csr(new_key, cn, ORIGINAL))

    response, _ = _service(ca).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '0', attrs.get(FAIL_INFO_OID)
    renewed = pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, old_key, issued))[0]
    assert renewed.public_key().public_numbers() == new_key.public_key().public_numbers()
    assert _row(issued).archived is True
    stored = SCEPRequest.query.filter_by(cert_refid=_row(renewed).refid).one()
    assert stored.renewal_of
    assert webhooks == ['renewed']
    assert gated == [True]


@pytest.mark.parametrize('expired', [True, False], ids=['expired', 'fresh'])
@pytest.mark.parametrize('sent', [None, 'wrong secret'], ids=['absent', 'wrong'])
def test_pkcsreq_renewal_still_compares_the_challenge(app, scep_ca, sent, expired):
    ca, ca_cert = scep_ca
    cn = _cn('challenge')
    old_key = _new_key()
    issued = _enroll(ca, ca_cert, old_key, cn)
    before = Certificate.query.count()
    request = _message(ca_cert, issued, old_key, 19, _csr(_new_key(), cn, sent))

    response, _ = _service(ca, expired=expired).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_OID] == BAD_MESSAGE_CHECK
    assert Certificate.query.count() == before
    assert _row(issued).archived is not True


@pytest.mark.parametrize('signer', ['other-profile', 'other-ca', 'self-signed'])
def test_pkcsreq_of_any_other_signer_keeps_the_expiry(app, scep_ca, create_ca, signer):
    ca, ca_cert = scep_ca
    cn = _cn(signer)
    key = _new_key()
    if signer == 'other-profile':
        signer_cert = _enroll_via(ca, ca_cert, key, cn, 9201, ORIGINAL)
    elif signer == 'other-ca':
        other, other_cert, _ = _load_ca_material(create_ca(cn=f'Other {cn}')['id'])
        signer_cert = _enroll(other, other_cert, key, cn)
    else:
        signer_cert, _ = _client_identity(cn, key=key)
    before = Certificate.query.count()
    request = _message(ca_cert, signer_cert, key, 19, _csr(_new_key(), cn, ORIGINAL))

    response, _ = _service(ca, profile_id=9202).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_OID] == BAD_MESSAGE_CHECK
    assert Certificate.query.count() == before


@pytest.mark.parametrize('message_type', [17, 19], ids=['RenewalReq', 'PKCSReq'])
@pytest.mark.parametrize('state', ['revoked', 'expired', 'superseded', 'windows'])
def test_pkcsreq_renewal_refused_as_a_renewalreq(app, scep_ca, windows_profile, monkeypatch,
                                                  state, message_type):
    """Same failInfo, same audit; a fresh challenge does not turn the refusal into an issuance."""
    ca, ca_cert = scep_ca
    cn = _cn(state)
    old_key = _new_key()
    issued = _enroll(ca, ca_cert, old_key, cn)
    row = _row(issued)
    if state == 'revoked':
        row.revoked = True
    elif state == 'superseded':
        row.archived = True
    elif state == 'expired':
        later = issued.not_valid_after_utc.replace(tzinfo=None) + timedelta(days=1)
        monkeypatch.setattr('services.scep.scep_service.utc_now', lambda: later)
    db.session.commit()
    if state == 'windows':
        _bind(issued, windows_profile[0], 'enabled')
    before = Certificate.query.count()
    request = _message(ca_cert, issued, old_key, message_type, _csr(_new_key(), cn, ORIGINAL))

    response, _ = _service(ca, expired=False).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_OID] == BAD_MESSAGE_CHECK
    assert Certificate.query.count() == before
    assert len(_refusals(cn)) == (1 if state == 'windows' else 0)


@pytest.mark.parametrize('message_type', [17, 19], ids=['RenewalReq', 'PKCSReq'])
def test_pkcsreq_renewal_with_another_subject_is_refused(app, scep_ca, message_type):
    ca, ca_cert = scep_ca
    cn = _cn('subject')
    old_key = _new_key()
    issued = _enroll(ca, ca_cert, old_key, cn)
    before = Certificate.query.count()
    request = _message(ca_cert, issued, old_key, message_type,
                       _csr(_new_key(), 'other-' + cn, ORIGINAL))

    response, _ = _service(ca, expired=False).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_OID] == BAD_MESSAGE_CHECK
    assert Certificate.query.count() == before


@pytest.mark.parametrize('revoked', [False, True], ids=['approved', 'revoked-meanwhile'])
def test_held_pkcsreq_renewal_is_approved_as_a_renewal(app, scep_ca, revoked):
    ca, ca_cert = scep_ca
    cn = _cn('held')
    old_key = _new_key()
    issued = _enroll(ca, ca_cert, old_key, cn)
    request = _message(ca_cert, issued, old_key, 19, _csr(_new_key(), cn, ORIGINAL))
    service = _service(ca, auto_approve=False)

    response, _ = service.process_pkcs_req(request, '127.0.0.1')

    assert _response_attributes(response)[PKI_STATUS_OID] == '3'
    held = SCEPRequest.query.filter_by(ca_refid=ca.refid, status='pending').filter(
        SCEPRequest.subject.contains(cn)).one()
    assert held.renewal_of
    if revoked:
        _row(issued).revoked = True
        db.session.commit()
        before = Certificate.query.count()
        with pytest.raises(Exception, match='revoked'):
            service.approve_request(held.transaction_id, 'admin')
        db.session.rollback()
        assert Certificate.query.count() == before
        assert _row(issued).archived is not True
    else:
        service.approve_request(held.transaction_id, 'admin')
        assert _row(issued).archived is True


def test_intune_profile_pkcsreq_is_unchanged(app, scep_ca, webhooks):
    """Intune validates every request itself: a PKCSReq stays a new enrollment there."""
    ca, ca_cert = scep_ca
    cn = _cn('intune')
    old_key = _new_key()
    issued = _enroll_via(ca, ca_cert, old_key, cn, 9301, ORIGINAL)
    webhooks.clear()
    fake = _FakeIntuneClient()
    request = _message(ca_cert, issued, old_key, 19, _csr(_new_key(), 'renamed-' + cn))

    response, _ = SCEPService(ca.refid, auto_approve=True, intune_client=fake,
                              profile_id=9301).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '0', attrs.get(FAIL_INFO_OID)
    assert len(fake.validate_calls) == 1
    assert _row(issued).archived is not True
    stored = SCEPRequest.query.filter(SCEPRequest.subject.contains('renamed-' + cn)).one()
    assert stored.renewal_of is None
    assert webhooks == ['issued']


@pytest.mark.parametrize('message_type', [17, 19], ids=['RenewalReq', 'PKCSReq'])
@pytest.mark.parametrize('held', [False, True], ids=['auto', 'approved'])
@pytest.mark.parametrize('expired', [False, True], ids=['fresh', 'expired'])
def test_replayed_renewal_returns_the_certificate_issued(app, scep_ca, message_type, held,
                                                         expired):
    """The renewed certificate is archived once served: a resend still gets its answer (§5.2)."""
    ca, ca_cert = scep_ca
    cn = _cn('replay')
    old_key = _new_key()
    issued = _enroll(ca, ca_cert, old_key, cn)
    new_key = _new_key()
    request = _message(ca_cert, issued, old_key, message_type, _csr(new_key, cn, ORIGINAL))
    service = _service(ca, expired=expired, auto_approve=not held)

    first, _ = service.process_pkcs_req(request, '127.0.0.1')
    if held:
        assert _response_attributes(first)[PKI_STATUS_OID] == '3'
        pending = SCEPRequest.query.filter_by(ca_refid=ca.refid, status='pending').filter(
            SCEPRequest.subject.contains(cn)).one()
        service.approve_request(pending.transaction_id, 'admin')
    assert _row(issued).archived is True
    before = Certificate.query.count()

    response, _ = service.process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '0', attrs.get(FAIL_INFO_OID)
    renewed = pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, old_key, issued))[0]
    assert renewed.public_key().public_numbers() == new_key.public_key().public_numbers()
    assert Certificate.query.count() == before


def test_replay_shortcut_needs_the_certificate_it_renewed(app, scep_ca, monkeypatch):
    """Another issued certificate resending the transaction is judged as a renewal of its own."""
    import types
    import tests.test_scep_renewal_challenge as helpers
    ca, ca_cert = scep_ca
    cn = _cn('replay-other')
    old_key, other_key, new_key = _new_key(), _new_key(), _new_key()
    issued = _enroll(ca, ca_cert, old_key, cn)
    other = _enroll(ca, ca_cert, other_key, 'other-' + cn)
    csr = _csr(new_key, cn, ORIGINAL)
    monkeypatch.setattr(helpers, 'uuid', types.SimpleNamespace(
        uuid4=lambda: types.SimpleNamespace(hex='replay-' + cn[:24])))
    service = _service(ca, expired=False)
    first, _ = service.process_pkcs_req(_message(ca_cert, issued, old_key, 19, csr), '127.0.0.1')
    assert _response_attributes(first)[PKI_STATUS_OID] == '0'

    response, _ = service.process_pkcs_req(_message(ca_cert, other, other_key, 19, csr), '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_OID] == BAD_MESSAGE_CHECK
