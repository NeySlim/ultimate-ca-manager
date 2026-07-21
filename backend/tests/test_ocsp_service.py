"""Tests for the OCSP responder service (previously 0 coverage)."""
import base64
from datetime import datetime, timedelta, timezone

import pytest
from asn1crypto import core as asn1_core
from asn1crypto import ocsp as asn1_ocsp
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from api.ocsp_routes import OCSP_REQUEST_TYPE, _find_ca_by_issuer_hash
from models import db, CA, Certificate, OCSPResponse, SystemConfig
from services.cert_service import CertificateService
from services.ocsp_service import OCSPService


def _ca_model(ca_dict):
    return db.session.get(CA, ca_dict['id'])


def _cert_model(cert_dict):
    return db.session.get(Certificate, cert_dict['id'])


def _load_x509(model):
    return x509.load_pem_x509_certificate(base64.b64decode(model.crt))


def _cache_entries(ca_id, serial):
    prefix = f'{format(serial, "x")}:'
    return OCSPResponse.query.filter(
        OCSPResponse.ca_id == ca_id,
        OCSPResponse.cert_serial.startswith(prefix),
    ).all()


def _cert_id(cert, issuer, algorithm):
    request_der = (
        ocsp.OCSPRequestBuilder()
        .add_certificate(cert, issuer, algorithm)
        .build()
        .public_bytes(serialization.Encoding.DER)
    )
    parsed = asn1_ocsp.OCSPRequest.load(request_der)
    return parsed['tbs_request']['request_list'][0]['req_cert']


def _build_asn1_request(cert_ids, extension=None):
    tbs_request = {
        'request_list': [
            asn1_ocsp.Request({'req_cert': cert_id}) for cert_id in cert_ids
        ],
    }
    if extension is not None:
        tbs_request['request_extensions'] = [extension]
    return asn1_ocsp.OCSPRequest({'tbs_request': tbs_request}).dump()


def _request_extension(oid, critical):
    return asn1_ocsp.TBSRequestExtension({
        'extn_id': oid,
        'critical': critical,
        'extn_value': asn1_core.ParsableOctetString(b'test'),
    })


def _delegated_certificate(
    ca_cert, ca_key, responder_key, *, issuer=None, signer_key=None,
    not_before=None, not_after=None,
):
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(x509.NameOID.COMMON_NAME, 'OCSP Responder')
        ]))
        .issuer_name(issuer or ca_cert.subject)
        .public_key(responder_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or now - timedelta(minutes=5))
        .not_valid_after(not_after or now + timedelta(days=30))
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING]),
            critical=False,
        )
        .add_extension(x509.OCSPNoCheck(), critical=False)
        .sign(signer_key or ca_key, hashes.SHA256())
    )


def _configure_delegated_responder(ca_obj, cert_obj, responder_cert, responder_key):
    cert_obj.crt = base64.b64encode(
        responder_cert.public_bytes(serialization.Encoding.PEM)
    ).decode()
    cert_obj.prv = base64.b64encode(
        responder_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    ).decode()
    db.session.add(SystemConfig(
        key=f'ocsp_responder_cert_{ca_obj.id}', value=str(cert_obj.id)
    ))
    db.session.commit()


class TestParseRequest:
    def test_parse_valid_request(self, app, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='OCSP Parse CA')
            cert = create_cert(cn='leaf.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            cert_obj = _cert_model(cert)

            # Build a real OCSP request against the issued cert
            issuer = _load_x509(ca_obj)
            leaf = _load_x509(cert_obj)
            req = ocsp.OCSPRequestBuilder().add_certificate(
                leaf, issuer, hashes.SHA256()).build()
            der = req.public_bytes(serialization.Encoding.DER)

            parsed = OCSPService().parse_request(der)
            assert parsed is not None
            assert parsed.serial_number == leaf.serial_number

    def test_parse_garbage_returns_none(self, app):
        with app.app_context():
            assert OCSPService().parse_request(b'\x00\x01\x02not-a-request') is None


class TestGenerateResponse:
    def test_good_certificate(self, app, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='OCSP Good CA')
            cert = create_cert(cn='good.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            serial = int(_cert_model(cert).serial_number, 16)

            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'good'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            assert resp.certificate_status == ocsp.OCSPCertStatus.GOOD

    def test_revoked_certificate(self, app, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='OCSP Revoked CA')
            cert = create_cert(cn='revoked.example.com', ca_id=ca['id'])
            CertificateService.revoke_certificate(cert['id'], reason='keyCompromise', username='test')
            ca_obj = _ca_model(ca)
            serial = int(_cert_model(cert).serial_number, 16)

            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'revoked'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.certificate_status == ocsp.OCSPCertStatus.REVOKED

    @pytest.mark.parametrize('nonce', [b'abc123nonce', b''])
    def test_nonce_echoed_and_never_cached(self, app, create_ca, create_cert, nonce):
        with app.app_context():
            ca = create_ca(cn=f'OCSP Nonce CA {len(nonce)}')
            cert = create_cert(cn=f'nonce-{len(nonce)}.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            serial = _load_x509(_cert_model(cert)).serial_number

            der, _ = OCSPService().generate_response(
                ca_obj, serial, request_nonce=nonce)

            resp = ocsp.load_der_ocsp_response(der)
            assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            nonce_ext = resp.extensions.get_extension_for_class(x509.OCSPNonce)
            assert nonce_ext.value.nonce == nonce
            assert _cache_entries(ca_obj.id, serial) == []

    def test_nonce_request_bypasses_and_does_not_replace_cache(
        self, app, client, create_ca, create_cert
    ):
        with app.app_context():
            ca = create_ca(cn='OCSP Route Nonce CA')
            cert = create_cert(cn='route-nonce.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_obj.ocsp_enabled = True
            db.session.commit()
            cert_obj = _cert_model(cert)
            issuer = _load_x509(ca_obj)
            leaf = _load_x509(cert_obj)

            service = OCSPService()
            cached_der, _ = service.generate_response(
                ca_obj, leaf.serial_number, hash_algorithm=hashes.SHA256())
            cached_row = _cache_entries(ca_obj.id, leaf.serial_number)[0]
            assert cached_row.response_der == cached_der

            nonce = b'route-nonce'
            request_der = (
                ocsp.OCSPRequestBuilder()
                .add_certificate(leaf, issuer, hashes.SHA256())
                .add_extension(x509.OCSPNonce(nonce), critical=False)
                .build()
                .public_bytes(serialization.Encoding.DER)
            )
            response = client.post(
                '/ocsp', data=request_der, content_type=OCSP_REQUEST_TYPE)

            assert response.status_code == 200
            parsed = ocsp.load_der_ocsp_response(response.data)
            nonce_ext = parsed.extensions.get_extension_for_class(x509.OCSPNonce)
            assert nonce_ext.value.nonce == nonce
            db.session.expire_all()
            cached_after = _cache_entries(ca_obj.id, leaf.serial_number)[0]
            assert cached_after.response_der == cached_der

    def test_response_echoes_request_hash_algorithm(self, app, create_ca, create_cert):
        """Regression for #143: Cisco ASA sends a SHA-1 CertID; the response
        SingleResponse MUST use the same hash algorithm (and the same issuer
        name/key hashes) so the client can match the status to its request."""
        with app.app_context():
            ca = create_ca(cn='OCSP SHA1 CA')
            cert = create_cert(cn='sha1.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            cert_obj = _cert_model(cert)
            issuer = _load_x509(ca_obj)
            leaf = _load_x509(cert_obj)
            serial = leaf.serial_number

            # Build a SHA-1 request exactly like Cisco ASA does
            req = ocsp.OCSPRequestBuilder().add_certificate(
                leaf, issuer, hashes.SHA1()).build()
            der_req = req.public_bytes(serialization.Encoding.DER)
            parsed = OCSPService().parse_request(der_req)
            assert parsed is not None
            assert isinstance(parsed.hash_algorithm, hashes.SHA1)

            der, status = OCSPService().generate_response(
                ca_obj, serial,
                hash_algorithm=parsed.hash_algorithm,
                issuer_name_hash=parsed.issuer_name_hash,
                issuer_key_hash=parsed.issuer_key_hash,
            )
            assert status == 'good'
            resp = ocsp.load_der_ocsp_response(der)
            sr = next(iter(resp.responses))
            assert isinstance(sr.hash_algorithm, hashes.SHA1)
            assert sr.issuer_name_hash == parsed.issuer_name_hash
            assert sr.issuer_key_hash == parsed.issuer_key_hash
            assert sr.serial_number == serial

    def test_serial_from_different_ca_is_unknown(self, app, create_ca, create_cert):
        with app.app_context():
            queried_ca = create_ca(cn='OCSP Queried CA')
            other_ca = create_ca(cn='OCSP Other CA')
            other_cert = create_cert(
                cn='other-issuer.example.com', ca_id=other_ca['id'])
            queried_ca_obj = _ca_model(queried_ca)
            serial = _load_x509(_cert_model(other_cert)).serial_number

            der, status = OCSPService().generate_response(queried_ca_obj, serial)

            assert status == 'unknown'
            response = ocsp.load_der_ocsp_response(der)
            assert response.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            assert response.certificate_status == ocsp.OCSPCertStatus.UNKNOWN

    def test_configurable_response_validity(self, app, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='OCSP Validity CA')
            cert = create_cert(cn='validity.example.com', ca_id=ca['id'])
            db.session.add(SystemConfig(
                key='ocsp_response_validity_hours', value='6'
            ))
            db.session.commit()

            der, status = OCSPService().generate_response(
                _ca_model(ca), _load_x509(_cert_model(cert)).serial_number
            )

            assert status == 'good'
            response = ocsp.load_der_ocsp_response(der)
            assert (
                response.next_update_utc - response.this_update_utc
                == timedelta(hours=6)
            )


class TestMultiCertificateRequest:
    def test_response_contains_status_for_each_requested_cert_id(
        self, app, client, create_ca, create_cert
    ):
        with app.app_context():
            ca = create_ca(cn='OCSP Multi CA')
            good = create_cert(cn='multi-good.example.com', ca_id=ca['id'])
            revoked = create_cert(cn='multi-revoked.example.com', ca_id=ca['id'])
            seed = create_cert(cn='multi-seed.example.com', ca_id=ca['id'])
            CertificateService.revoke_certificate(
                revoked['id'], reason='keyCompromise', username='test'
            )
            ca_obj = _ca_model(ca)
            ca_obj.ocsp_enabled = True
            db.session.commit()
            issuer = _load_x509(ca_obj)
            good_cert = _load_x509(_cert_model(good))
            revoked_cert = _load_x509(_cert_model(revoked))
            seed_cert = _load_x509(_cert_model(seed))

            good_id = _cert_id(good_cert, issuer, hashes.SHA1())
            revoked_id = _cert_id(revoked_cert, issuer, hashes.SHA256())
            unknown_id = asn1_ocsp.CertId.load(
                _cert_id(seed_cert, issuer, hashes.SHA384()).dump()
            )
            unknown_serial = x509.random_serial_number()
            unknown_id['serial_number'] = unknown_serial
            request_der = _build_asn1_request(
                [good_id, revoked_id, unknown_id]
            )

            response = client.post(
                '/ocsp', data=request_der, content_type=OCSP_REQUEST_TYPE
            )

            assert response.status_code == 200
            parsed = ocsp.load_der_ocsp_response(response.data)
            assert parsed.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            single_responses = list(parsed.responses)
            assert len(single_responses) == 3
            by_serial = {item.serial_number: item for item in single_responses}
            assert by_serial[good_cert.serial_number].certificate_status == (
                ocsp.OCSPCertStatus.GOOD
            )
            assert isinstance(
                by_serial[good_cert.serial_number].hash_algorithm, hashes.SHA1
            )
            assert by_serial[revoked_cert.serial_number].certificate_status == (
                ocsp.OCSPCertStatus.REVOKED
            )
            assert isinstance(
                by_serial[revoked_cert.serial_number].hash_algorithm, hashes.SHA256
            )
            assert by_serial[unknown_serial].certificate_status == (
                ocsp.OCSPCertStatus.UNKNOWN
            )
            assert isinstance(
                by_serial[unknown_serial].hash_algorithm, hashes.SHA384
            )


class TestRequestExtensions:
    @pytest.mark.parametrize('critical', [False, True])
    def test_unknown_extension_is_rejected_only_when_critical(
        self, app, client, create_ca, create_cert, critical
    ):
        with app.app_context():
            ca = create_ca(cn=f'OCSP Extension CA {critical}')
            cert = create_cert(
                cn=f'extension-{critical}.example.com', ca_id=ca['id']
            )
            ca_obj = _ca_model(ca)
            ca_obj.ocsp_enabled = True
            db.session.commit()
            request_der = _build_asn1_request(
                [_cert_id(
                    _load_x509(_cert_model(cert)),
                    _load_x509(ca_obj),
                    hashes.SHA256(),
                )],
                extension=_request_extension('1.2.3.4.5.6.7', critical),
            )

            response = client.post(
                '/ocsp', data=request_der, content_type=OCSP_REQUEST_TYPE
            )

            parsed = ocsp.load_der_ocsp_response(response.data)
            expected = (
                ocsp.OCSPResponseStatus.MALFORMED_REQUEST
                if critical else ocsp.OCSPResponseStatus.SUCCESSFUL
            )
            assert parsed.response_status == expected


class TestDelegatedResponderValidation:
    def test_accepts_valid_ca_issued_responder(
        self, app, create_ca, create_cert, monkeypatch
    ):
        with app.app_context():
            ca = create_ca(cn='OCSP Delegated Valid CA')
            record = create_cert(cn='delegated-valid.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            ca_key = OCSPService()._load_ca_key(ca_obj)
            responder_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )
            responder_cert = _delegated_certificate(
                ca_cert, ca_key, responder_key
            )
            _configure_delegated_responder(
                ca_obj, _cert_model(record), responder_cert, responder_key
            )
            monkeypatch.setattr(
                'security.encryption.decrypt_private_key', lambda value: value
            )

            loaded_cert, loaded_key = OCSPService()._get_delegated_responder(ca_obj)

            assert loaded_cert.fingerprint(hashes.SHA256()) == (
                responder_cert.fingerprint(hashes.SHA256())
            )
            assert loaded_key.public_key().public_numbers() == (
                responder_key.public_key().public_numbers()
            )

    @pytest.mark.parametrize('invalid_kind', ['issuer', 'signature', 'expired'])
    def test_rejects_responder_not_validly_issued_by_ca(
        self, app, create_ca, create_cert, caplog, invalid_kind
    ):
        with app.app_context():
            ca = create_ca(cn=f'OCSP Delegated Invalid CA {invalid_kind}')
            record = create_cert(
                cn=f'delegated-invalid-{invalid_kind}.example.com', ca_id=ca['id']
            )
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            ca_key = OCSPService()._load_ca_key(ca_obj)
            responder_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )
            kwargs = {}
            if invalid_kind == 'issuer':
                kwargs['issuer'] = x509.Name([
                    x509.NameAttribute(x509.NameOID.COMMON_NAME, 'Other CA')
                ])
            elif invalid_kind == 'signature':
                kwargs['signer_key'] = rsa.generate_private_key(
                    public_exponent=65537, key_size=2048
                )
            else:
                now = datetime.now(timezone.utc)
                kwargs['not_before'] = now - timedelta(days=2)
                kwargs['not_after'] = now - timedelta(days=1)
            responder_cert = _delegated_certificate(
                ca_cert, ca_key, responder_key, **kwargs
            )
            _configure_delegated_responder(
                ca_obj, _cert_model(record), responder_cert, responder_key
            )

            loaded_cert, loaded_key = OCSPService()._get_delegated_responder(ca_obj)

            assert (loaded_cert, loaded_key) == (None, None)
            assert any(
                invalid_kind in message.lower() for message in caplog.messages
            )


class TestCacheInvalidation:
    def test_revoke_invalidates_every_cached_algorithm(
        self, app, create_ca, create_cert
    ):
        with app.app_context():
            ca = create_ca(cn='OCSP Revoke Cache CA')
            cert = create_cert(cn='revoke-cache.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            serial = _load_x509(_cert_model(cert)).serial_number
            service = OCSPService()
            service.generate_response(ca_obj, serial, hash_algorithm=hashes.SHA1())
            service.generate_response(ca_obj, serial, hash_algorithm=hashes.SHA256())
            assert len(_cache_entries(ca_obj.id, serial)) == 2

            CertificateService.revoke_certificate(cert['id'], username='test')

            assert _cache_entries(ca_obj.id, serial) == []

    def test_unhold_invalidates_every_cached_algorithm(
        self, app, auth_client, create_ca, create_cert
    ):
        with app.app_context():
            ca = create_ca(cn='OCSP Unhold Cache CA')
            cert = create_cert(cn='unhold-cache.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            cert_obj = _cert_model(cert)
            cert_obj.revoked = True
            cert_obj.revoke_reason = 'certificateHold'
            db.session.commit()
            serial = _load_x509(cert_obj).serial_number
            service = OCSPService()
            service.generate_response(ca_obj, serial, hash_algorithm=hashes.SHA1())
            service.generate_response(ca_obj, serial, hash_algorithm=hashes.SHA256())
            assert len(_cache_entries(ca_obj.id, serial)) == 2

            response = auth_client.post(
                f'/api/v2/certificates/{cert["id"]}/unhold')

            assert response.status_code == 200, response.data
            assert _cache_entries(ca_obj.id, serial) == []


class TestIssuerHashLookup:
    def test_sha224_issuer_hash_is_supported(
        self, app, client, create_ca, create_cert
    ):
        with app.app_context():
            ca = create_ca(cn='OCSP SHA224 CA')
            cert = create_cert(cn='sha224.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_obj.ocsp_enabled = True
            db.session.commit()
            issuer = _load_x509(ca_obj)
            leaf = _load_x509(_cert_model(cert))
            request = ocsp.OCSPRequestBuilder().add_certificate(
                leaf, issuer, hashes.SHA224()).build()

            found = _find_ca_by_issuer_hash(
                request.issuer_name_hash,
                request.issuer_key_hash,
                request.hash_algorithm,
            )
            response = client.post(
                '/ocsp',
                data=request.public_bytes(serialization.Encoding.DER),
                content_type=OCSP_REQUEST_TYPE,
            )

            assert found is not None
            assert found.id == ca_obj.id
            parsed = ocsp.load_der_ocsp_response(response.data)
            assert parsed.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            assert isinstance(parsed.hash_algorithm, hashes.SHA224)


class TestCleanup:
    def test_cleanup_runs(self, app):
        with app.app_context():
            # Should not raise even with nothing to clean
            OCSPService().cleanup_expired_responses()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
