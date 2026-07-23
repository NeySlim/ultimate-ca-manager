"""Tests for RFC 3161 Time-Stamp Authority processing and protocol handling."""
import base64
import hashlib
import json

import pytest

from asn1crypto import tsp, algos, core


def _status_info(resp_der):
    """Load PKIStatusInfo from granted or token-less rejection responses."""
    try:
        return tsp.TimeStampResp.load(resp_der)['status']
    except ValueError:
        inner = core.Sequence.load(resp_der).contents
        return tsp.PKIStatusInfo.load(inner)


def _status_native(resp_der):
    return _status_info(resp_der)['status'].native


def _failure_info_native(resp_der):
    return _status_info(resp_der)['fail_info'].native


def _self_signed_tsa(include_eku=True, eku_critical=True, basic_constraints_ca=False):
    """Build a self-signed cert + key, optionally with a valid TSA EKU."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test TSA')])
    builder = (x509.CertificateBuilder()
               .subject_name(subject).issuer_name(issuer)
               .public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
               .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365)))
    if include_eku:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.TIME_STAMPING]),
            critical=eku_critical,
        )
    if basic_constraints_ca:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        )
    return builder.sign(key, hashes.SHA256()), key


def _build_tsq(
    digest: bytes,
    hash_oid='2.16.840.1.101.3.4.2.1',
    req_policy=None,
    extensions=None,
):
    """Build a DER TimeStampReq for the supplied message imprint."""
    fields = {
        'version': 1,
        'message_imprint': tsp.MessageImprint({
            'hash_algorithm': algos.DigestAlgorithm({'algorithm': hash_oid}),
            'hashed_message': digest,
        }),
        'cert_req': True,
    }
    if req_policy is not None:
        fields['req_policy'] = req_policy
    if extensions is not None:
        fields['extensions'] = extensions
    return tsp.TimeStampReq(fields).dump()


def _tst_info(resp_der):
    resp = tsp.TimeStampResp.load(resp_der)
    return resp['time_stamp_token']['content']['encap_content_info']['content'].parsed


class TestProcessRequest:
    def test_valid_request_granted(self):
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key, policy_oid='1.2.3.4.1')

        digest = hashlib.sha256(b'hello world').digest()
        resp_der, http = svc.process_request(_build_tsq(digest))
        assert http == 200
        resp = tsp.TimeStampResp.load(resp_der)
        status = resp['status']['status'].native
        assert status in ('granted', 'granted_with_mods')
        # A granted response must carry a timeStampToken
        assert resp['time_stamp_token'].native is not None

    def test_malformed_request_rejected(self):
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key)
        resp_der, http = svc.process_request(b'\x30\x03not-a-tsq')
        assert http == 200
        assert _status_native(resp_der) == 'rejection'

    def test_unsupported_hash_rejected(self):
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key)
        # MD5 OID — not in the allowed set
        tsq = _build_tsq(b'\x00' * 16, hash_oid='1.2.840.113549.2.5')
        resp_der, http = svc.process_request(tsq)
        assert _status_native(resp_der) == 'rejection'
        assert _failure_info_native(resp_der) == {'bad_alg'}

    def test_matching_requested_policy_is_preserved(self):
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        policy = '1.2.3.4.1'
        svc = TSAService(cert, key, policy_oid=policy)

        digest = hashlib.sha256(b'policy match').digest()
        resp_der, _ = svc.process_request(_build_tsq(digest, req_policy=policy))

        assert _status_native(resp_der) == 'granted'
        assert _tst_info(resp_der)['policy'].dotted == policy

    def test_different_requested_policy_is_issued_under_that_policy(self):
        # RFC 3161 §2.4.1: reqPolicy set → issue under it (or reject). Issuing
        # keeps clients with pinned policies working (pre-2.200 behaviour).
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key, policy_oid='1.2.3.4.1')

        digest = hashlib.sha256(b'policy mismatch').digest()
        resp_der, _ = svc.process_request(
            _build_tsq(digest, req_policy='1.2.3.4.999')
        )

        assert _status_native(resp_der) == 'granted'
        assert _tst_info(resp_der)['policy'].dotted == '1.2.3.4.999'
        meta = svc.issued_token_metadata(resp_der)
        assert meta is not None and meta['policy_oid'] == '1.2.3.4.999'

    def test_unknown_critical_extension_is_rejected(self):
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key)
        extension = tsp.Extension({
            'extn_id': '1.2.3.4.999',
            'critical': True,
            'extn_value': b'unsupported',
        })

        digest = hashlib.sha256(b'critical extension').digest()
        resp_der, _ = svc.process_request(
            _build_tsq(digest, extensions=[extension])
        )

        assert _status_native(resp_der) == 'rejection'
        assert _failure_info_native(resp_der) == {'unaccepted_extensions'}

    def test_unknown_noncritical_extension_is_ignored(self):
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key)
        extension = tsp.Extension({
            'extn_id': '1.2.3.4.999',
            'critical': False,
            'extn_value': b'unsupported',
        })

        digest = hashlib.sha256(b'noncritical extension').digest()
        resp_der, _ = svc.process_request(
            _build_tsq(digest, extensions=[extension])
        )

        assert _status_native(resp_der) == 'granted'

    @pytest.mark.parametrize(
        ('hash_name', 'hash_oid', 'digest_size'),
        [
            ('sha256', '2.16.840.1.101.3.4.2.1', 32),
            ('sha384', '2.16.840.1.101.3.4.2.2', 48),
            ('sha512', '2.16.840.1.101.3.4.2.3', 64),
        ],
    )
    def test_cms_signature_uses_message_imprint_algorithm(
        self, hash_name, hash_oid, digest_size
    ):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from services.tsa_service import TSAService

        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key)
        resp_der, _ = svc.process_request(
            _build_tsq(b'\x5a' * digest_size, hash_oid=hash_oid)
        )

        signed_data = tsp.TimeStampResp.load(resp_der)['time_stamp_token']['content']
        signer = signed_data['signer_infos'][0]
        assert signer['digest_algorithm']['algorithm'].native == hash_name
        assert signer['signature_algorithm']['algorithm'].native == f'{hash_name}_rsa'

        signed_attrs_der = signer['signed_attrs'].dump()
        signed_attrs_der = b'\x31' + signed_attrs_der[1:]
        key.public_key().verify(
            signer['signature'].native,
            signed_attrs_der,
            padding.PKCS1v15(),
            getattr(hashes, hash_name.upper())(),
        )


class TestTsaCertificateValidation:
    def test_end_entity_without_eku_is_rejected(self):
        from services.tsa_service import TSAConfigurationError, TSAService

        cert, key = _self_signed_tsa(include_eku=False)
        with pytest.raises(TSAConfigurationError, match='timeStamping'):
            TSAService(cert, key)

    def test_non_critical_timestamping_eku_is_accepted(self):
        # Compat: non-critical/non-exclusive EKU logs a warning but signs
        from services.tsa_service import TSAService

        cert, key = _self_signed_tsa(include_eku=True, eku_critical=False)
        assert TSAService(cert, key).tsa_cert is cert

    def test_ca_certificate_without_eku_is_accepted(self):
        # Pre-2.200 deployments sign with the configured CA's own cert
        from cryptography import x509
        from services.tsa_service import TSAService

        cert, key = _self_signed_tsa(include_eku=False, basic_constraints_ca=True)
        assert TSAService(cert, key).tsa_cert is cert


class TestTsaManagementApi:
    def test_invalid_policy_oid_is_rejected(self, app, auth_client):
        from models import SystemConfig

        with app.app_context():
            row = SystemConfig.query.filter_by(key='tsa_policy_oid').first()
            previous = row.value if row else None

        response = auth_client.patch(
            '/api/v2/tsa/config',
            data=json.dumps({'policy_oid': '1.40.not-an-oid'}),
            content_type='application/json',
        )

        assert response.status_code == 400
        with app.app_context():
            row = SystemConfig.query.filter_by(key='tsa_policy_oid').first()
            assert (row.value if row else None) == previous


class TestTsaProtocolAudit:
    def test_issued_token_is_audited_with_serial_policy_and_client_ip(
        self, app, client, create_ca
    ):
        from cryptography.hazmat.primitives import serialization
        from models import AuditLog, CA, db, SystemConfig

        ca_data = create_ca(cn='TSA Audit CA')
        cert, key = _self_signed_tsa()
        policy = '1.2.3.4.55'
        client_address = '203.0.113.55'

        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            ca.crt = base64.b64encode(
                cert.public_bytes(serialization.Encoding.PEM)
            ).decode()
            ca.prv = base64.b64encode(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )).decode()
            for config_key, value in (
                ('tsa_enabled', 'true'),
                ('tsa_ca_refid', ca.refid),
                ('tsa_policy_oid', policy),
            ):
                row = SystemConfig.query.filter_by(key=config_key).first()
                if row is None:
                    row = SystemConfig(key=config_key)
                    db.session.add(row)
                row.value = value
            db.session.commit()

        try:
            digest = hashlib.sha384(b'audited timestamp').digest()
            response = client.post(
                '/tsa',
                data=_build_tsq(
                    digest,
                    hash_oid='2.16.840.1.101.3.4.2.2',
                    req_policy=policy,
                ),
                content_type='application/timestamp-query',
                environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
                headers={'X-Forwarded-For': client_address},
            )
            assert response.status_code == 200
            serial = str(_tst_info(response.data)['serial_number'].native)

            with app.app_context():
                audit = AuditLog.query.filter_by(
                    action='tsa.timestamp_issued', resource_id=serial
                ).one()
                assert audit.success is True
                assert audit.ip_address == client_address
                assert policy in audit.details
                assert client_address in audit.details
        finally:
            with app.app_context():
                SystemConfig.query.filter(
                    SystemConfig.key.in_([
                        'tsa_enabled', 'tsa_ca_refid', 'tsa_policy_oid'
                    ])
                ).delete(synchronize_session=False)
                db.session.commit()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
