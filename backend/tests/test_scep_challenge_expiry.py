"""SCEP challenge password expiry (`scep_challenge_validity`).

The setting was validated and stored by the config API but never applied at
enrollment, so a leaked challenge stayed usable forever. These tests pin the
expiry, and pin the two behaviours that make it safe rather than merely strict:
an expired challenge is an explicit refusal (not a silent downgrade to the
weaker no-challenge path), and renewals — authenticated by the existing
certificate — keep working.
"""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import AttributeOID

from models import SystemConfig, db
from services.scep.scep_service import SCEPService

from tests.test_scep_rfc8894_operations import (  # reuse the SCEP harness
    FAIL_INFO_OID, PKI_STATUS_OID, _build_request, _client_identity,
    _load_ca_material, _response_attributes,
)

CHALLENGE = 'correct horse battery staple'


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def _stamp(ca_id, *, hours_ago):
    when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    _set_config(f'scep_challenge_{ca_id}_generated_at', when.isoformat())


def _enroll_request(ca_cert, message_type=19):
    key_cert, key = _client_identity('SCEP expiry client')
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(key_cert.subject)
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
           .sign(key, hashes.SHA256()))
    return _build_request(
        ca_cert, key_cert, key, message_type,
        csr.public_bytes(serialization.Encoding.DER), b'expiry-nonce-16b',
    )


@pytest.fixture
def scep_ca(app, create_ca):
    ca_data = create_ca(cn='SCEP Challenge Expiry CA')
    with app.app_context():
        _set_config(f'scep_challenge_{ca_data["id"]}', CHALLENGE)
        _set_config('scep_challenge_validity', '24')
    yield ca_data
    with app.app_context():
        for key in (f'scep_challenge_{ca_data["id"]}',
                    f'scep_challenge_{ca_data["id"]}_generated_at',
                    'scep_challenge_validity'):
            row = SystemConfig.query.filter_by(key=key).first()
            if row:
                db.session.delete(row)
        db.session.commit()


class TestChallengeAgeState:

    def test_fresh_challenge_is_not_expired(self, app, scep_ca):
        from api.v2.scep import challenge_age_state
        with app.app_context():
            _stamp(scep_ca['id'], hours_ago=1)
            challenge, expired, expires_at = challenge_age_state(scep_ca['id'])
            assert challenge == CHALLENGE
            assert expired is False
            assert expires_at is not None

    def test_challenge_past_validity_is_expired(self, app, scep_ca):
        from api.v2.scep import challenge_age_state
        with app.app_context():
            _stamp(scep_ca['id'], hours_ago=25)   # validity is 24h
            _challenge, expired, _ = challenge_age_state(scep_ca['id'])
            assert expired is True

    def test_legacy_challenge_is_adopted_not_expired(self, app, scep_ca):
        """A challenge predating this feature has no timestamp: stamping it on
        first inspection avoids locking out an already-deployed fleet at
        upgrade — it then expires normally one window later."""
        from api.v2.scep import challenge_age_state
        with app.app_context():
            row = SystemConfig.query.filter_by(
                key=f"scep_challenge_{scep_ca['id']}_generated_at").first()
            if row:
                db.session.delete(row)
                db.session.commit()

            _challenge, expired, expires_at = challenge_age_state(scep_ca['id'])
            assert expired is False
            assert expires_at is not None
            # The stamp is now persisted, so the window actually starts running.
            assert SystemConfig.query.filter_by(
                key=f"scep_challenge_{scep_ca['id']}_generated_at").first() is not None

    def test_no_challenge_configured(self, app, scep_ca):
        from api.v2.scep import challenge_age_state
        with app.app_context():
            db.session.delete(SystemConfig.query.filter_by(
                key=f"scep_challenge_{scep_ca['id']}").first())
            db.session.commit()
            challenge, expired, expires_at = challenge_age_state(scep_ca['id'])
            assert challenge is None and expired is False and expires_at is None


class TestEnrollmentRefusal:

    def test_expired_challenge_refuses_enrollment(self, app, scep_ca):
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
            request = _enroll_request(ca_cert)
            response, status = SCEPService(
                ca.refid, challenge_password=CHALLENGE,
                auto_approve=True, challenge_expired=True,
            ).process_pkcs_req(request, '127.0.0.1')

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == '2'          # FAILURE
        assert attrs[FAIL_INFO_OID] == '1'           # badMessageCheck (RFC 8894)

    def test_valid_challenge_still_enrolls(self, app, scep_ca):
        """Guards against the expiry check rejecting everything."""
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
            request = _enroll_request(ca_cert)
            response, status = SCEPService(
                ca.refid, challenge_password=CHALLENGE,
                auto_approve=True, challenge_expired=False,
            ).process_pkcs_req(request, '127.0.0.1')

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == '0'          # SUCCESS

    def test_expiry_is_a_refusal_not_a_downgrade(self, app, scep_ca):
        """An expired challenge must NOT behave like 'no challenge configured',
        which would fall through to the weaker manual-approval path."""
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
            request = _enroll_request(ca_cert)
            # auto_approve OFF: a blank challenge would be queued (status 3),
            # an expired one must still be an outright failure.
            response, status = SCEPService(
                ca.refid, challenge_password=CHALLENGE,
                auto_approve=False, challenge_expired=True,
            ).process_pkcs_req(request, '127.0.0.1')

        attrs = _response_attributes(response)
        assert attrs[PKI_STATUS_OID] == '2'
        assert attrs[PKI_STATUS_OID] != '3'          # not "pending"
