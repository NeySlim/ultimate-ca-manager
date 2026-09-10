"""Tests for the OCSP responder service (previously 0 coverage)."""
import base64
import hashlib
import json
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


class TestKeylessCASigning:
    """A key-less/offline CA must still answer OCSP through its delegated
    responder, and answer 'unauthorized' (not internalError) without one."""

    def _keyless_with_responder(self, create_ca, create_cert, monkeypatch, cn):
        ca = create_ca(cn=cn)
        target = create_cert(cn=f'{cn.lower().replace(" ", "-")}-t.example.com',
                             ca_id=ca['id'])
        responder_record = create_cert(
            cn=f'{cn.lower().replace(" ", "-")}-r.example.com', ca_id=ca['id'])
        ca_obj = _ca_model(ca)
        ca_cert = _load_x509(ca_obj)
        ca_key = OCSPService()._load_ca_key(ca_obj)
        responder_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        responder_cert = _delegated_certificate(ca_cert, ca_key, responder_key)
        _configure_delegated_responder(
            ca_obj, _cert_model(responder_record), responder_cert, responder_key)
        monkeypatch.setattr(
            'security.encryption.decrypt_private_key', lambda value: value)
        # Wipe the CA key AFTER issuing the responder — simulates a
        # file-exported offline CA / certificate-only import.
        ca_obj.prv = None
        ca_obj.ocsp_enabled = True
        db.session.commit()
        return ca_obj, ca_cert, target, responder_cert

    def test_single_response_signed_by_delegated_responder(
        self, app, create_ca, create_cert, monkeypatch
    ):
        with app.app_context():
            ca_obj, _, target, responder_cert = self._keyless_with_responder(
                create_ca, create_cert, monkeypatch, 'Keyless Single CA')
            serial = int(_cert_model(target).serial_number, 16)

            der, status = OCSPService().generate_response(ca_obj, serial)

            assert status == 'good'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            assert resp.certificates  # responder cert embedded for verification
            assert resp.certificates[0].fingerprint(hashes.SHA256()) == (
                responder_cert.fingerprint(hashes.SHA256())
            )

    def test_multi_response_signed_by_delegated_responder(
        self, app, client, create_ca, create_cert, monkeypatch
    ):
        with app.app_context():
            ca_obj, ca_cert, target, _ = self._keyless_with_responder(
                create_ca, create_cert, monkeypatch, 'Keyless Multi CA')
            target_cert = _load_x509(_cert_model(target))
            id_a = _cert_id(target_cert, ca_cert, hashes.SHA1())
            id_b = _cert_id(target_cert, ca_cert, hashes.SHA256())
            request_der = _build_asn1_request([id_a, id_b])

            response = client.post(
                '/ocsp', data=request_der, content_type=OCSP_REQUEST_TYPE)

            assert response.status_code == 200
            parsed = ocsp.load_der_ocsp_response(response.data)
            assert parsed.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            assert all(item.certificate_status == ocsp.OCSPCertStatus.GOOD
                       for item in parsed.responses)

    def test_keyless_without_responder_is_unauthorized(
        self, app, create_ca, create_cert
    ):
        with app.app_context():
            ca = create_ca(cn='Keyless Unauthorized CA')
            target = create_cert(cn='keyless-unauth.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            serial = int(_cert_model(target).serial_number, 16)
            ca_obj.prv = None
            db.session.commit()

            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'unauthorized'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.response_status == ocsp.OCSPResponseStatus.UNAUTHORIZED

    @pytest.mark.parametrize('offline_mode,wipe_key', [
        ('password_protected', False),  # key kept, PEM password-encrypted
        ('file_exported', True),        # key wiped from the database
    ])
    def test_offline_ca_without_responder_is_unauthorized(
        self, app, create_ca, create_cert, offline_mode, wipe_key
    ):
        """R-02: both offline modes must answer 'unauthorized' — the
        password-protected mode used to leak a TypeError into internalError,
        and an offline CA must never sign OCSP with its own key."""
        with app.app_context():
            ca = create_ca(cn=f'Offline OCSP CA {offline_mode}')
            target = create_cert(
                cn=f'offline-{offline_mode}.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            serial = int(_cert_model(target).serial_number, 16)
            ca_obj.offline = True
            ca_obj.offline_mode = offline_mode
            if wipe_key:
                ca_obj.prv = None
            db.session.commit()

            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'unauthorized'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.response_status == ocsp.OCSPResponseStatus.UNAUTHORIZED

    def test_hsm_fault_stays_internal_error(
        self, app, create_ca, create_cert, monkeypatch
    ):
        """A real fault (HSM/key-load failure) is NOT an expected no-identity
        state: it must surface as internalError, never as unauthorized.
        Simulated by faulting the key loader — no FK-violating DB state
        (CA.hsm_key_id carries a real FK that PostgreSQL enforces)."""
        with app.app_context():
            ca = create_ca(cn='HSM Fault OCSP CA')
            target = create_cert(cn='hsm-fault.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            serial = int(_cert_model(target).serial_number, 16)

            def _hsm_down(self, ca_arg):
                raise ValueError('HSM signing failed: provider unreachable')
            monkeypatch.setattr(OCSPService, '_load_ca_key', _hsm_down)

            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'error'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.response_status == ocsp.OCSPResponseStatus.INTERNAL_ERROR

    def test_offline_ca_with_responder_still_signs(
        self, app, create_ca, create_cert, monkeypatch
    ):
        """An offline CA with a delegated responder kept online keeps
        answering signed OCSP — the offline gate applies to the CA key only."""
        with app.app_context():
            ca_obj, _, target, responder_cert = self._keyless_with_responder(
                create_ca, create_cert, monkeypatch, 'Offline Responder CA')
            ca_obj.offline = True
            ca_obj.offline_mode = 'file_exported'
            db.session.commit()
            serial = int(_cert_model(target).serial_number, 16)

            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'good'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
            assert resp.certificates[0].fingerprint(hashes.SHA256()) == (
                responder_cert.fingerprint(hashes.SHA256())
            )


class TestCleanup:
    def test_cleanup_runs(self, app):
        with app.app_context():
            # Should not raise even with nothing to clean
            OCSPService().cleanup_expired_responses()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestResponderIdRfc6960:
    """RFC 6960 §4.2.1: byKey is the SHA-1 of the responder's own public key.

    A delegated responder's AKI is its issuer's key hash, so publishing the
    AKI there makes every client that recomputes the hash reject the
    signature (#347)."""

    @staticmethod
    def _responder_id_by_key(der):
        parsed = asn1_ocsp.OCSPResponse.load(der)
        rdata = parsed['response_bytes']['response'].parsed['tbs_response_data']
        rid = rdata['responder_id']
        assert rid.name == 'by_key', rid.name
        return rid.chosen.native

    @staticmethod
    def _key_hash(cert):
        """SHA-1 of the subjectPublicKey BIT STRING, RFC 5280 method 1."""
        spki = cert.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        from asn1crypto import keys as asn1_keys
        loaded = asn1_keys.PublicKeyInfo.load(spki)
        return hashlib.sha1(loaded['public_key'].contents[1:]).digest()

    @staticmethod
    def _aki(cert):
        ext = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
        return ext.key_identifier

    def test_ca_signed_response_uses_the_ca_key_hash(self, app, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='ResponderID CA')
            cert = create_cert(cn='responder-id.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            serial = int(_cert_model(cert).serial_number, 16)

            der, _ = OCSPService().generate_response(ca_obj, serial)
            assert self._responder_id_by_key(der) == self._key_hash(ca_cert)

    def test_delegated_response_uses_the_responder_key_hash(self, app, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='ResponderID Delegated CA')
            cert = create_cert(cn='responder-id-deleg.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca_obj)
            responder_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            responder_cert = _delegated_certificate(ca_cert, ca_key, responder_key)
            _configure_delegated_responder(ca_obj, _cert_model(cert), responder_cert, responder_key)
            serial = int(_cert_model(cert).serial_number, 16)

            der, _ = OCSPService().generate_response(ca_obj, serial)
            responder_id = self._responder_id_by_key(der)
            assert responder_id == self._key_hash(responder_cert)
            # The responder's AKI is the CA's key hash: publishing it there is
            # exactly what breaks client-side verification
            assert responder_id != self._key_hash(ca_cert)

    def test_multi_response_uses_the_same_responder_id(self, app, create_ca, create_cert):
        """The multi-CertID response is assembled by hand, so it carries its
        own copy of the rule and has to agree with the single one."""
        with app.app_context():
            ca = create_ca(cn='ResponderID Multi CA')
            first = create_cert(cn='multi-a.example.com', ca_id=ca['id'])
            second = create_cert(cn='multi-b.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            ids = [
                _cert_id(_load_x509(_cert_model(c)), ca_cert, hashes.SHA1())
                for c in (first, second)
            ]
            request_der = _build_asn1_request(ids)
            parsed = OCSPService().parse_request_details(request_der)
            assert parsed is not None and len(parsed.requests) == 2

            der, statuses = OCSPService().generate_multi_response(
                ca=ca_obj, request_items=parsed.requests
            )
            assert len(statuses) == 2
            assert self._responder_id_by_key(der) == self._key_hash(ca_cert)

    def test_multi_response_delegated_uses_the_responder_key_hash(self, app, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='ResponderID Multi Delegated CA')
            first = create_cert(cn='multi-deleg-a.example.com', ca_id=ca['id'])
            second = create_cert(cn='multi-deleg-b.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca_obj)
            responder_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            responder_cert = _delegated_certificate(ca_cert, ca_key, responder_key)
            _configure_delegated_responder(ca_obj, _cert_model(first), responder_cert, responder_key)
            ids = [
                _cert_id(_load_x509(_cert_model(c)), ca_cert, hashes.SHA1())
                for c in (first, second)
            ]
            parsed = OCSPService().parse_request_details(_build_asn1_request(ids))
            der, _ = OCSPService().generate_multi_response(
                ca=ca_obj, request_items=parsed.requests
            )
            responder_id = self._responder_id_by_key(der)
            assert responder_id == self._key_hash(responder_cert)
            assert responder_id != self._key_hash(ca_cert)


class TestDelegatedResponderIssuance:
    """A certificate issued for the responder role must be usable as one.

    UCM's responder refuses a certificate without id-pkix-ocsp-nocheck and
    keeps signing with the CA key, so a certificate issued without it made
    the configured responder silently inert: the responses carried the CA's
    identity, which is the responder certificate's AKI (#347)."""

    @staticmethod
    def _issue(auth_client, ca_id, cn, **extra):
        payload = {'cn': cn, 'ca_id': ca_id, 'validity_days': 60,
                   'key_type': 'RSA 2048', 'cert_type': 'server'}
        payload.update(extra)
        r = auth_client.post('/api/v2/certificates', data=json.dumps(payload),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        return json.loads(r.data)['data']

    @staticmethod
    def _x509(cert_dict):
        return x509.load_pem_x509_certificate(cert_dict['pem'].encode())

    def test_ocsp_signing_certificate_carries_nocheck(self, app, auth_client, create_ca):
        with app.app_context():
            ca = create_ca(cn='Responder Issuance CA')
            cert = self._issue(auth_client, ca['id'], 'responder-issued.example.com',
                               extra_ekus=['1.3.6.1.5.5.7.3.9'])
            parsed = self._x509(cert)
            eku = parsed.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            assert x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING in eku
            parsed.extensions.get_extension_for_class(x509.OCSPNoCheck)  # raises if absent

    def test_a_plain_certificate_does_not_carry_nocheck(self, app, auth_client, create_ca):
        with app.app_context():
            ca = create_ca(cn='Plain Issuance CA')
            cert = self._issue(auth_client, ca['id'], 'plain-issued.example.com')
            with pytest.raises(x509.ExtensionNotFound):
                self._x509(cert).extensions.get_extension_for_class(x509.OCSPNoCheck)

    def test_such_a_certificate_is_offered_and_accepted(self, app, auth_client, create_ca):
        with app.app_context():
            ca = create_ca(cn='Responder Config CA')
            cert = self._issue(auth_client, ca['id'], 'responder-config.example.com',
                               extra_ekus=['1.3.6.1.5.5.7.3.9'])
            r = auth_client.get(f"/api/v2/cas/{ca['id']}/eligible-ocsp-responders")
            assert cert['id'] in {c['id'] for c in json.loads(r.data)['data']}
            r = auth_client.post(f"/api/v2/cas/{ca['id']}/ocsp-responder",
                                 data=json.dumps({'certificate_id': cert['id']}),
                                 content_type='application/json')
            assert r.status_code == 200, r.data

    def test_a_certificate_without_nocheck_is_refused_not_ignored(self, app, auth_client, create_ca):
        """It used to be accepted and then ignored at answer time."""
        with app.app_context():
            ca = create_ca(cn='Responder Refusal CA')
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca_obj)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            now = datetime.now(timezone.utc)
            bare = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'No nocheck')]))
                .issuer_name(ca_cert.subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=30))
                .add_extension(
                    x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING]),
                    critical=False)
                .sign(ca_key, hashes.SHA256())
            )
            row = Certificate(
                refid='no-nocheck-responder', descr='No nocheck',
                caref=ca_obj.refid,
                crt=base64.b64encode(bare.public_bytes(serialization.Encoding.PEM)).decode(),
                prv=base64.b64encode(key.private_bytes(
                    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption())).decode(),
                serial_number=str(bare.serial_number),
            )
            db.session.add(row)
            db.session.commit()

            r = auth_client.get(f"/api/v2/cas/{ca['id']}/eligible-ocsp-responders")
            assert row.id not in {c['id'] for c in json.loads(r.data)['data']}
            r = auth_client.post(f"/api/v2/cas/{ca['id']}/ocsp-responder",
                                 data=json.dumps({'certificate_id': row.id}),
                                 content_type='application/json')
            assert r.status_code == 400, r.data
            assert 'nocheck' in json.loads(r.data)['message'].lower()

    def test_a_configured_responder_actually_signs(self, app, auth_client, create_ca, create_cert):
        """End of the chain: responderID is the responder's key hash, which
        is what a client recomputes to verify the signature."""
        with app.app_context():
            ca = create_ca(cn='Responder Signs CA')
            leaf = create_cert(cn='signed-by-responder.example.com', ca_id=ca['id'])
            responder = self._issue(auth_client, ca['id'], 'active-responder.example.com',
                                    extra_ekus=['1.3.6.1.5.5.7.3.9'])
            r = auth_client.post(f"/api/v2/cas/{ca['id']}/ocsp-responder",
                                 data=json.dumps({'certificate_id': responder['id']}),
                                 content_type='application/json')
            assert r.status_code == 200, r.data

            ca_obj = _ca_model(ca)
            serial = int(_cert_model(leaf).serial_number, 16)
            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'good'
            resp = ocsp.load_der_ocsp_response(der)
            responder_cert = self._x509(responder)
            # responderID is the responder's own key hash, not the CA's
            assert resp.responder_key_hash == TestResponderIdRfc6960._key_hash(responder_cert)
            assert resp.responder_key_hash != TestResponderIdRfc6960._key_hash(_load_x509(ca_obj))
            # and the response carries the responder certificate, as RFC 6960 asks
            assert any(c.serial_number == responder_cert.serial_number
                       for c in resp.certificates)


class TestDelegatedResponderLifecycle:
    """Second review of #347: a revoked responder stops signing, the cache
    follows the signing identity, a request already carrying ocsp-nocheck
    signs once, and a responder with no certificate is refused."""

    @staticmethod
    def _responder(auth_client, ca_id, cn):
        r = auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': cn, 'ca_id': ca_id, 'validity_days': 60, 'key_type': 'RSA 2048',
            'cert_type': 'server', 'extra_ekus': ['1.3.6.1.5.5.7.3.9']}),
            content_type='application/json')
        assert r.status_code in (200, 201), r.data
        return json.loads(r.data)['data']

    @staticmethod
    def _assign(auth_client, ca_id, cert_id):
        return auth_client.post(f'/api/v2/cas/{ca_id}/ocsp-responder',
                                data=json.dumps({'certificate_id': cert_id}),
                                content_type='application/json')

    @staticmethod
    def _responder_id(der):
        return ocsp.load_der_ocsp_response(der).responder_key_hash

    def test_revoked_responder_stops_signing_and_its_answers_are_dropped(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='Revoked Responder CA')
            leaf = create_cert(cn='leaf-rr.example.com', ca_id=ca['id'])
            responder = self._responder(auth_client, ca['id'], 'rr.example.com')
            assert self._assign(auth_client, ca['id'], responder['id']).status_code == 200
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            serial = int(_cert_model(leaf).serial_number, 16)
            responder_cert = x509.load_pem_x509_certificate(responder['pem'].encode())

            der, _ = OCSPService().generate_response(ca_obj, serial)
            assert self._responder_id(der) == TestResponderIdRfc6960._key_hash(responder_cert)
            assert _cache_entries(ca['id'], serial), 'the answer is cached'

            r = auth_client.post(f"/api/v2/certificates/{responder['id']}/revoke",
                                 data=json.dumps({'reason': 'keyCompromise'}),
                                 content_type='application/json')
            assert r.status_code == 200, r.data
            db.session.expire_all()
            # Everything it signed is gone from the cache
            assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() == 0
            # And the CA signs again, with its own identity
            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'good'
            assert self._responder_id(der) == TestResponderIdRfc6960._key_hash(ca_cert)

    def test_assigning_or_removing_a_responder_drops_the_cache(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='Cache Responder CA')
            leaf = create_cert(cn='leaf-cache.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca)
            ca_cert = _load_x509(ca_obj)
            serial = int(_cert_model(leaf).serial_number, 16)

            der, _ = OCSPService().generate_response(ca_obj, serial)
            assert self._responder_id(der) == TestResponderIdRfc6960._key_hash(ca_cert)
            assert _cache_entries(ca['id'], serial)

            responder = self._responder(auth_client, ca['id'], 'cache-resp.example.com')
            assert self._assign(auth_client, ca['id'], responder['id']).status_code == 200
            db.session.expire_all()
            assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() == 0
            der, _ = OCSPService().generate_response(ca_obj, serial)
            responder_cert = x509.load_pem_x509_certificate(responder['pem'].encode())
            assert self._responder_id(der) == TestResponderIdRfc6960._key_hash(responder_cert)
            assert _cache_entries(ca['id'], serial)

            r = auth_client.delete(f"/api/v2/cas/{ca['id']}/ocsp-responder")
            assert r.status_code in (200, 204), r.data
            db.session.expire_all()
            assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() == 0
            der, _ = OCSPService().generate_response(ca_obj, serial)
            assert self._responder_id(der) == TestResponderIdRfc6960._key_hash(ca_cert)

    def test_request_already_carrying_nocheck_signs_once(self, app, auth_client, create_ca):
        with app.app_context():
            ca = create_ca(cn='Nocheck CSR CA')
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            csr = (
                x509.CertificateSigningRequestBuilder()
                .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'csr-resp.example.com')]))
                .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING]), critical=False)
                .add_extension(x509.OCSPNoCheck(), critical=False)
                .sign(key, hashes.SHA256())
            )
            r = auth_client.post('/api/v2/csrs/upload',
                                 data=json.dumps({'pem': csr.public_bytes(serialization.Encoding.PEM).decode()}),
                                 content_type='application/json')
            assert r.status_code in (200, 201), r.data
            csr_id = json.loads(r.data)['data']['id']
            r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                                 data=json.dumps({'ca_id': ca['id'], 'validity_days': 30}),
                                 content_type='application/json')
            assert r.status_code == 200, r.data
            issued = x509.load_pem_x509_certificate(json.loads(r.data)['data']['pem'].encode())
            nocheck = [e for e in issued.extensions if e.oid == x509.oid.ExtensionOID.OCSP_NO_CHECK]
            assert len(nocheck) == 1
            eku = issued.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            assert x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING in eku

    def test_a_responder_without_a_certificate_is_refused(self, app, auth_client, create_ca):
        with app.app_context():
            ca = create_ca(cn='No Cert Responder CA')
            ca_obj = _ca_model(ca)
            r = auth_client.post('/api/v2/csrs', data=json.dumps({'cn': 'pending-resp.example.com', 'key_type': 'RSA 2048'}),
                                 content_type='application/json')
            pending = json.loads(r.data)['data']
            row = _cert_model(pending)
            row.caref = ca_obj.refid   # a key, a link to the CA, no certificate
            db.session.commit()
            assert row.prv and not row.crt
            r = self._assign(auth_client, ca['id'], pending['id'])
            assert r.status_code == 400, r.data
            assert 'no certificate' in json.loads(r.data)['message'].lower()
            assert SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{ca['id']}").first() is None

    def test_a_revoked_certificate_is_refused_as_responder(self, app, auth_client, create_ca):
        with app.app_context():
            ca = create_ca(cn='Revoked Assign CA')
            responder = self._responder(auth_client, ca['id'], 'revoked-assign.example.com')
            r = auth_client.post(f"/api/v2/certificates/{responder['id']}/revoke",
                                 data=json.dumps({'reason': 'unspecified'}), content_type='application/json')
            assert r.status_code == 200
            r = self._assign(auth_client, ca['id'], responder['id'])
            assert r.status_code == 400, r.data
            r = auth_client.get(f"/api/v2/cas/{ca['id']}/eligible-ocsp-responders")
            assert responder['id'] not in {c['id'] for c in json.loads(r.data)['data']}


class TestDelegatedResponderStrictness:
    """Third review of #347: the assignment applies the runtime rule in full,
    and a responder coming off hold takes the cache with it."""

    @staticmethod
    def _store(ca_obj, cert, key, refid):
        row = Certificate(
            refid=refid, descr=refid, caref=ca_obj.refid,
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            prv=base64.b64encode(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())).decode(),
            serial_number=str(cert.serial_number),
        )
        db.session.add(row); db.session.commit()
        return row

    @staticmethod
    def _assign(auth_client, ca_id, cert_id):
        return auth_client.post(f'/api/v2/cas/{ca_id}/ocsp-responder',
                                data=json.dumps({'certificate_id': cert_id}),
                                content_type='application/json')

    @staticmethod
    def _full_responder(ca_cert, signer_key, key, **kw):
        cert = _delegated_certificate(ca_cert, signer_key, key, **kw)
        return cert

    def test_expired_future_and_foreign_signed_are_refused_at_assignment(self, app, auth_client, create_ca):
        with app.app_context():
            ca = create_ca(cn='Strict Assign CA')
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca_obj)
            now = datetime.now(timezone.utc)
            cases = {
                'expired': dict(not_before=now - timedelta(days=60), not_after=now - timedelta(days=1)),
                'not yet valid': dict(not_before=now + timedelta(days=1), not_after=now + timedelta(days=30)),
                'foreign signature': dict(signer_key=rsa.generate_private_key(public_exponent=65537, key_size=2048)),
            }
            for label, kw in cases.items():
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                cert = _delegated_certificate(ca_cert, ca_key, key, **kw)
                row = self._store(ca_obj, cert, key, f'strict-{label.replace(" ", "-")}')
                r = self._assign(auth_client, ca['id'], row.id)
                assert r.status_code == 400, (label, r.data)
                assert SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{ca['id']}").first() is None, label
                r = auth_client.get(f"/api/v2/cas/{ca['id']}/eligible-ocsp-responders")
                assert row.id not in {c['id'] for c in json.loads(r.data)['data']}, label

    def test_assignment_and_runtime_apply_the_same_rule(self, app, auth_client, create_ca):
        """Whatever the assignment accepts, the responder uses; whatever it
        refuses, the responder would have refused too."""
        with app.app_context():
            ca = create_ca(cn='Same Rule CA')
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca_obj)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            good = _delegated_certificate(ca_cert, ca_key, key)
            row = self._store(ca_obj, good, key, 'same-rule-good')
            assert OCSPService().check_delegated_responder(ca_obj, row) is None
            assert self._assign(auth_client, ca['id'], row.id).status_code == 200
            resp_cert, resp_key = OCSPService()._get_delegated_responder(ca_obj)
            assert resp_cert is not None and resp_cert.serial_number == good.serial_number

    def test_unhold_of_a_responder_drops_the_ca_signed_answers(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='Unhold Responder CA')
            leaf = create_cert(cn='leaf-unhold.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            r = auth_client.post('/api/v2/certificates', data=json.dumps({
                'cn': 'unhold-resp.example.com', 'ca_id': ca['id'], 'validity_days': 60,
                'key_type': 'RSA 2048', 'cert_type': 'server', 'extra_ekus': ['1.3.6.1.5.5.7.3.9']}),
                content_type='application/json')
            responder = json.loads(r.data)['data']
            responder_cert = x509.load_pem_x509_certificate(responder['pem'].encode())
            assert self._assign(auth_client, ca['id'], responder['id']).status_code == 200
            serial = int(_cert_model(leaf).serial_number, 16)

            # On hold: the CA signs, and that answer is cached
            r = auth_client.post(f"/api/v2/certificates/{responder['id']}/revoke",
                                 data=json.dumps({'reason': 'certificateHold'}), content_type='application/json')
            assert r.status_code == 200, r.data
            der, _ = OCSPService().generate_response(ca_obj, serial)
            assert ocsp.load_der_ocsp_response(der).responder_key_hash == TestResponderIdRfc6960._key_hash(ca_cert)
            assert _cache_entries(ca['id'], serial)

            # Off hold: the responder signs again, and the CA-signed answer is gone
            r = auth_client.post(f"/api/v2/certificates/{responder['id']}/unhold")
            assert r.status_code == 200, r.data
            db.session.expire_all()
            assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() == 0
            der, _ = OCSPService().generate_response(ca_obj, serial)
            assert ocsp.load_der_ocsp_response(der).responder_key_hash == TestResponderIdRfc6960._key_hash(responder_cert)


class TestResponderKeyOwnership:
    """Fourth review of #347: the responder's key has to be the certificate's."""

    @staticmethod
    def _stored(ca_obj, cert, key, refid):
        row = Certificate(
            refid=refid, descr=refid, caref=ca_obj.refid,
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            prv=base64.b64encode(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())).decode(),
            serial_number=str(cert.serial_number),
        )
        db.session.add(row); db.session.commit()
        return row

    def test_a_foreign_key_is_refused_everywhere(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='Key Ownership CA')
            leaf = create_cert(cn='leaf-keyown.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca_obj)
            real_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            cert = _delegated_certificate(ca_cert, ca_key, real_key)
            row = self._stored(ca_obj, cert, other_key, 'keyown-foreign')

            reason = OCSPService().check_delegated_responder(ca_obj, row)
            assert reason and 'does not match' in reason
            r = auth_client.get(f"/api/v2/cas/{ca['id']}/eligible-ocsp-responders")
            assert row.id not in {c['id'] for c in json.loads(r.data)['data']}
            r = auth_client.post(f"/api/v2/cas/{ca['id']}/ocsp-responder",
                                 data=json.dumps({'certificate_id': row.id}), content_type='application/json')
            assert r.status_code == 400, r.data
            assert 'does not match' in json.loads(r.data)['message']

            # Forced into the configuration anyway: the responder still refuses it
            db.session.add(SystemConfig(key=f"ocsp_responder_cert_{ca['id']}", value=str(row.id)))
            db.session.commit()
            serial = int(_cert_model(leaf).serial_number, 16)
            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'good'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.responder_key_hash == TestResponderIdRfc6960._key_hash(ca_cert)
            # and a client verifies that answer against the CA
            ca_cert.public_key().verify(resp.signature, resp.tbs_response_bytes,
                                        __import__('cryptography.hazmat.primitives.asymmetric.padding', fromlist=['PKCS1v15']).PKCS1v15(),
                                        resp.signature_hash_algorithm)

    def test_the_right_key_passes(self, app, create_ca):
        with app.app_context():
            ca = create_ca(cn='Key Ownership OK CA')
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            cert = _delegated_certificate(ca_cert, get_ca_signing_key(ca_obj), key)
            row = self._stored(ca_obj, cert, key, 'keyown-right')
            assert OCSPService().check_delegated_responder(ca_obj, row) is None

    def test_an_unloadable_key_is_a_reason(self, app, create_ca):
        with app.app_context():
            ca = create_ca(cn='Key Ownership Broken CA')
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            cert = _delegated_certificate(ca_cert, get_ca_signing_key(ca_obj), key)
            row = self._stored(ca_obj, cert, key, 'keyown-broken')
            row.prv = base64.b64encode(b'not a key').decode(); db.session.commit()
            reason = OCSPService().check_delegated_responder(ca_obj, row)
            assert reason and 'could not be loaded' in reason
