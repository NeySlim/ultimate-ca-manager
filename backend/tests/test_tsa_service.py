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


def _self_signed_tsa(include_eku=True, eku_critical=True, basic_constraints_ca=False,
                     eku_oids=None, not_before=None, not_after=None):
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
               .not_valid_before(not_before or datetime.now(timezone.utc) - timedelta(days=1))
               .not_valid_after(not_after or datetime.now(timezone.utc) + timedelta(days=365)))
    if include_eku:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage(
                eku_oids or [x509.oid.ExtendedKeyUsageOID.TIME_STAMPING]
            ),
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
        assert _failure_info_native(resp_der) == {'bad_data_format'}

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

    def test_unknown_noncritical_extension_is_rejected(self):
        # RFC 3161 §2.4.1: an unrecognized extension, critical or not, gets no token
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

        assert _status_native(resp_der) == 'rejection'
        assert _failure_info_native(resp_der) == {'unaccepted_extensions'}

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


class TestDedicatedSignerToken:
    """#312: a dedicated signer embeds its issuer chain; the CA-signer path
    (no chain) stays byte-for-byte what it was."""

    def _issue_chain(self):
        """Return (leaf_cert, leaf_key, [intermediate, root])."""
        from cryptography import x509
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        def _mk(cn, signer_key=None, signer_name=None, ca=False, eku=None):
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
            b = (x509.CertificateBuilder()
                 .subject_name(name)
                 .issuer_name(signer_name or name)
                 .public_key(key.public_key())
                 .serial_number(x509.random_serial_number())
                 .not_valid_before(now - timedelta(days=1))
                 .not_valid_after(now + timedelta(days=365)))
            if ca:
                b = b.add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            if eku:
                b = b.add_extension(x509.ExtendedKeyUsage(eku), True)
            return b.sign(signer_key or key, hashes.SHA256()), key

        root, root_key = _mk('Test Root', ca=True)
        inter, inter_key = _mk('Test Intermediate', signer_key=root_key,
                               signer_name=root.subject, ca=True)
        leaf, leaf_key = _mk('Test TSA Signer', signer_key=inter_key,
                             signer_name=inter.subject,
                             eku=[ExtendedKeyUsageOID.TIME_STAMPING])
        return leaf, leaf_key, [inter, root]

    def test_ca_signer_path_embeds_exactly_one_certificate(self):
        # Regression guard for NeySlim's byte-for-byte constraint: with no
        # dedicated signer configured, chain_certs defaults to empty and the
        # token carries only the signer certificate.
        from services.tsa_service import TSAService

        cert, key = _self_signed_tsa()
        svc = TSAService(cert, key)
        resp_der, _ = svc.process_request(
            _build_tsq(hashlib.sha256(b'no chain').digest())
        )
        signed_data = tsp.TimeStampResp.load(resp_der)['time_stamp_token']['content']
        assert len(signed_data['certificates']) == 1

    def test_dedicated_signer_embeds_leaf_then_issuer_chain(self):
        from services.tsa_service import TSAService

        leaf, leaf_key, chain = self._issue_chain()
        svc = TSAService(leaf, leaf_key, chain_certs=chain)
        resp_der, _ = svc.process_request(
            _build_tsq(hashlib.sha256(b'with chain').digest())
        )
        signed_data = tsp.TimeStampResp.load(resp_der)['time_stamp_token']['content']
        certs = signed_data['certificates']
        assert len(certs) == 3
        # CMS 'certificates' is a SET (DER reorders it); all three must be
        # present so a strict verifier can build leaf -> intermediate -> root.
        subjects = {c.chosen.subject.native['common_name'] for c in certs}
        assert subjects == {'Test TSA Signer', 'Test Intermediate', 'Test Root'}

        # ESSCertIDv2 / SignerInfo.sid still bind the leaf, not a chain cert.
        signer = signed_data['signer_infos'][0]
        assert signer['sid'].chosen['serial_number'].native == leaf.serial_number

    def test_chain_is_omitted_when_client_did_not_request_certs(self):
        from services.tsa_service import TSAService

        leaf, leaf_key, chain = self._issue_chain()
        svc = TSAService(leaf, leaf_key, chain_certs=chain)
        tsq = _build_tsq(hashlib.sha256(b'no certreq').digest())
        # flip cert_req off
        req = tsp.TimeStampReq.load(tsq)
        fields = {
            'version': 1,
            'message_imprint': req['message_imprint'],
            'cert_req': False,
        }
        resp_der, _ = svc.process_request(tsp.TimeStampReq(fields).dump())
        signed_data = tsp.TimeStampResp.load(resp_der)['time_stamp_token']['content']
        assert signed_data['certificates'].native is None


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

    def test_ca_certificate_with_non_timestamping_eku_is_accepted(self):
        # #309: a constrained sub-CA carries an EKU that does not list
        # timeStamping. It is still the configured CA's own certificate, so
        # signing with it stays allowed (with a warning).
        from cryptography.x509.oid import ExtendedKeyUsageOID
        from services.tsa_service import TSAService

        cert, key = _self_signed_tsa(
            include_eku=True, basic_constraints_ca=True,
            eku_oids=[ExtendedKeyUsageOID.SERVER_AUTH,
                      ExtendedKeyUsageOID.CLIENT_AUTH],
        )
        assert TSAService(cert, key).tsa_cert is cert

    def test_end_entity_with_non_timestamping_eku_is_rejected(self):
        # An end-entity cert lacking timeStamping is not a valid TSA signer.
        from cryptography.x509.oid import ExtendedKeyUsageOID
        from services.tsa_service import TSAConfigurationError, TSAService

        cert, key = _self_signed_tsa(
            include_eku=True, basic_constraints_ca=False,
            eku_oids=[ExtendedKeyUsageOID.SERVER_AUTH],
        )
        with pytest.raises(TSAConfigurationError, match='timeStamping'):
            TSAService(cert, key)

    def test_ca_with_non_timestamping_eku_refused_when_dedicated_required(
        self, monkeypatch,
    ):
        from cryptography.x509.oid import ExtendedKeyUsageOID
        from services.tsa_service import TSAConfigurationError, TSAService

        monkeypatch.setattr(
            TSAService, '_require_dedicated_tsa_cert', staticmethod(lambda: True),
        )
        cert, key = _self_signed_tsa(
            include_eku=True, basic_constraints_ca=True,
            eku_oids=[ExtendedKeyUsageOID.SERVER_AUTH],
        )
        with pytest.raises(TSAConfigurationError, match='dedicated'):
            TSAService(cert, key)


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


class TestTsaDedicatedSignerApi:
    """#312: selecting an already-issued certificate as the TSA signer."""

    TS_OID = '1.3.6.1.5.5.7.3.8'

    def test_candidates_list_only_offers_timestamping_certs_with_a_local_key(
        self, auth_client, create_cert
    ):
        ts_cert = create_cert(cn='ucm-tsa-signer', extra_ekus=[self.TS_OID])
        plain = create_cert(cn='ucm-plain-server')

        r = auth_client.get('/api/v2/tsa/signer-candidates')
        assert r.status_code == 200
        refids = {c['refid'] for c in json.loads(r.data)['data']}
        assert ts_cert['refid'] in refids
        assert plain['refid'] not in refids

    def test_patch_rejects_a_certificate_without_the_timestamping_eku(
        self, auth_client, create_cert
    ):
        plain = create_cert(cn='ucm-not-a-signer')
        r = auth_client.patch(
            '/api/v2/tsa/config',
            data=json.dumps({'signer_cert_refid': plain['refid']}),
            content_type='application/json',
        )
        assert r.status_code == 400

    def test_patch_accepts_a_valid_signer_and_config_reports_it(
        self, app, auth_client, create_cert
    ):
        from models import SystemConfig, db

        ts_cert = create_cert(cn='ucm-tsa-signer-2', extra_ekus=[self.TS_OID])
        try:
            r = auth_client.patch(
                '/api/v2/tsa/config',
                data=json.dumps({'signer_cert_refid': ts_cert['refid']}),
                content_type='application/json',
            )
            assert r.status_code == 200

            cfg = json.loads(auth_client.get('/api/v2/tsa/config').data)['data']
            assert cfg['signer_cert_refid'] == ts_cert['refid']
            assert cfg['signer']['configured'] is True
            assert cfg['signer']['usable'] is True

            # Clearing it returns to the CA-certificate signer.
            r = auth_client.patch(
                '/api/v2/tsa/config',
                data=json.dumps({'signer_cert_refid': ''}),
                content_type='application/json',
            )
            assert r.status_code == 200
            cfg = json.loads(auth_client.get('/api/v2/tsa/config').data)['data']
            assert cfg['signer_cert_refid'] == ''
            assert cfg['signer'] == {'configured': False}
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(
                    key='tsa_signer_cert_refid'
                ).delete(synchronize_session=False)
                db.session.commit()

    def test_tsa_signs_with_the_dedicated_signer_and_embeds_its_chain(
        self, app, client, auth_client, create_ca, create_cert
    ):
        from models import SystemConfig, db

        ca = create_ca(cn='TSA Dedicated Signer CA')
        ts_cert = create_cert(
            cn='ucm-tsa-dedicated', ca_id=ca['id'], extra_ekus=[self.TS_OID],
        )
        with app.app_context():
            for k, v in (('tsa_enabled', 'true'),
                         ('tsa_signer_cert_refid', ts_cert['refid'])):
                row = SystemConfig.query.filter_by(key=k).first() or SystemConfig(key=k)
                row.value = v
                db.session.add(row)
            db.session.commit()
        try:
            digest = hashlib.sha256(b'dedicated signer token').digest()
            resp = client.post(
                '/tsa', data=_build_tsq(digest),
                content_type='application/timestamp-query',
            )
            assert resp.status_code == 200
            signed_data = tsp.TimeStampResp.load(
                resp.data
            )['time_stamp_token']['content']
            assert _status_native(resp.data) == 'granted'
            subjects = {
                c.chosen.subject.native.get('common_name')
                for c in signed_data['certificates']
            }
            # signer leaf + its issuing CA are both present
            assert 'ucm-tsa-dedicated' in subjects
            assert 'TSA Dedicated Signer CA' in subjects
        finally:
            with app.app_context():
                SystemConfig.query.filter(
                    SystemConfig.key.in_(['tsa_enabled', 'tsa_signer_cert_refid'])
                ).delete(synchronize_session=False)
                db.session.commit()

    def test_missing_signer_fails_hard_without_falling_back_to_the_ca(
        self, app, client
    ):
        """A configured-but-unusable signer must 503, never sign with the CA."""
        from models import SystemConfig, db

        with app.app_context():
            for k, v in (('tsa_enabled', 'true'),
                         ('tsa_signer_cert_refid', 'cert-does-not-exist')):
                row = SystemConfig.query.filter_by(key=k).first() or SystemConfig(key=k)
                row.value = v
                db.session.add(row)
            db.session.commit()
        try:
            resp = client.post(
                '/tsa', data=_build_tsq(hashlib.sha256(b'x').digest()),
                content_type='application/timestamp-query',
            )
            assert resp.status_code == 503
        finally:
            with app.app_context():
                SystemConfig.query.filter(
                    SystemConfig.key.in_(['tsa_enabled', 'tsa_signer_cert_refid'])
                ).delete(synchronize_session=False)
                db.session.commit()


class TestTsaSignerOneClickIssuance:
    """#312 follow-up: POST /api/v2/tsa/signer-certificate issues a purpose-built
    RFC 3161 signer (critical, exclusive timeStamping EKU) the generic issue
    path cannot produce."""

    TS_OID = '1.3.6.1.5.5.7.3.8'

    @staticmethod
    def _parse(cert_str):
        """Parse a certificate given either a raw PEM string or base64-of-PEM."""
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        if '-----BEGIN CERTIFICATE-----' in cert_str:
            data = cert_str.encode()
        else:
            data = base64.b64decode(cert_str)
        return x509.load_pem_x509_certificate(data, default_backend())

    def _issue(self, auth_client, ca_id, **body):
        body.setdefault('ca_id', ca_id)
        return auth_client.post(
            '/api/v2/tsa/signer-certificate',
            data=json.dumps(body), content_type='application/json',
        )

    def _cleanup(self, app):
        from models import SystemConfig, db
        with app.app_context():
            SystemConfig.query.filter(
                SystemConfig.key.in_(['tsa_enabled', 'tsa_signer_cert_refid'])
            ).delete(synchronize_session=False)
            db.session.commit()

    def test_issued_certificate_is_a_strict_rfc3161_signer(
        self, app, auth_client, create_ca
    ):
        from cryptography import x509
        from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID

        ca = create_ca(cn='One-Click TSA CA 1')
        try:
            r = self._issue(auth_client, ca['id'], cn='ucm-oneclick-signer')
            assert r.status_code == 200, r.data
            data = json.loads(r.data)['data']
            cert = self._parse(data['certificate']['pem'])

            bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
            assert bc.value.ca is False and bc.critical is True

            ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
            assert ku.critical is True
            assert ku.value.digital_signature is True
            assert ku.value.key_cert_sign is False
            assert ku.value.key_encipherment is False

            eku = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
            assert eku.critical is True
            assert set(eku.value) == {ExtendedKeyUsageOID.TIME_STAMPING}
        finally:
            self._cleanup(app)

    def test_candidate_list_reports_it_as_critical_exclusive(
        self, app, auth_client, create_ca
    ):
        ca = create_ca(cn='One-Click TSA CA 2')
        try:
            r = self._issue(auth_client, ca['id'], cn='ucm-oneclick-2')
            refid = json.loads(r.data)['data']['certificate']['refid']

            cands = json.loads(
                auth_client.get('/api/v2/tsa/signer-candidates').data
            )['data']
            mine = next(c for c in cands if c['refid'] == refid)
            assert mine['eku_critical_exclusive'] is True
        finally:
            self._cleanup(app)

    def test_auto_selects_when_no_dedicated_signer_configured(
        self, app, auth_client, create_ca
    ):
        ca = create_ca(cn='One-Click TSA CA 3')
        try:
            r = self._issue(auth_client, ca['id'], cn='ucm-oneclick-3')
            data = json.loads(r.data)['data']
            assert data['selected'] is True
            assert data['signer']['configured'] is True
            assert data['signer']['usable'] is True

            cfg = json.loads(auth_client.get('/api/v2/tsa/config').data)['data']
            assert cfg['signer_cert_refid'] == data['certificate']['refid']
        finally:
            self._cleanup(app)

    def test_does_not_swap_a_healthy_signer_without_explicit_select(
        self, app, auth_client, create_ca
    ):
        ca = create_ca(cn='One-Click TSA CA 4')
        try:
            first = json.loads(self._issue(auth_client, ca['id'],
                                           cn='ucm-oneclick-4a').data)['data']
            assert first['selected'] is True
            keep = first['certificate']['refid']

            second = json.loads(self._issue(auth_client, ca['id'],
                                            cn='ucm-oneclick-4b').data)['data']
            assert second['selected'] is False
            cfg = json.loads(auth_client.get('/api/v2/tsa/config').data)['data']
            assert cfg['signer_cert_refid'] == keep

            third = json.loads(self._issue(auth_client, ca['id'], cn='ucm-oneclick-4c',
                                           select=True).data)['data']
            assert third['selected'] is True
            cfg = json.loads(auth_client.get('/api/v2/tsa/config').data)['data']
            assert cfg['signer_cert_refid'] == third['certificate']['refid']
        finally:
            self._cleanup(app)

    def test_validity_is_clamped_to_ca_expiry_not_rejected(
        self, app, auth_client, create_ca
    ):
        from models import CA, db

        # Short-lived CA so its own expiry is the bound that fires, not the
        # 3650-day issuance cap.
        ca = create_ca(cn='One-Click TSA CA 5', validityYears=1)
        try:
            r = self._issue(auth_client, ca['id'], cn='ucm-oneclick-5',
                            validity_days=3000)
            assert r.status_code == 200, r.data
            cert = self._parse(json.loads(r.data)['data']['certificate']['pem'])
            with app.app_context():
                ca_cert = self._parse(db.session.get(CA, ca['id']).crt)
            assert cert.not_valid_after_utc <= ca_cert.not_valid_after_utc
            # 3000 days was asked for; the ~1-year CA must have clamped it well short.
            span_days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
            assert span_days < 400
        finally:
            self._cleanup(app)

    def test_full_tsa_roundtrip_with_the_generated_signer(
        self, app, client, auth_client, create_ca
    ):
        from models import SystemConfig, db

        ca = create_ca(cn='One-Click Roundtrip CA')
        try:
            data = json.loads(self._issue(auth_client, ca['id'],
                                          cn='ucm-oneclick-roundtrip').data)['data']
            assert data['selected'] is True
            with app.app_context():
                row = (SystemConfig.query.filter_by(key='tsa_enabled').first()
                       or SystemConfig(key='tsa_enabled'))
                row.value = 'true'
                db.session.add(row)
                db.session.commit()

            resp = client.post(
                '/tsa', data=_build_tsq(hashlib.sha256(b'one-click roundtrip').digest()),
                content_type='application/timestamp-query',
            )
            assert resp.status_code == 200
            assert _status_native(resp.data) == 'granted'
            token = tsp.TimeStampResp.load(resp.data)['time_stamp_token']['content']
            subjects = {
                c.chosen.subject.native.get('common_name')
                for c in token['certificates']
            }
            assert 'ucm-oneclick-roundtrip' in subjects
        finally:
            self._cleanup(app)

    def test_requires_write_permissions(self, app, viewer_client, create_ca):
        ca = create_ca(cn='One-Click TSA CA Perms')
        try:
            # Guard: confirm this client is genuinely restricted (conftest's
            # viewer_client falls back to admin if viewer creation ever fails).
            guard = viewer_client.patch(
                '/api/v2/tsa/config',
                data=json.dumps({'policy_oid': '1.2.3.4.9'}),
                content_type='application/json',
            )
            assert guard.status_code == 403, 'viewer_client is not read-only'

            r = viewer_client.post(
                '/api/v2/tsa/signer-certificate',
                data=json.dumps({'ca_id': ca['id']}),
                content_type='application/json',
            )
            assert r.status_code == 403
        finally:
            self._cleanup(app)

    def test_missing_ca_is_rejected(self, app, auth_client):
        try:
            r = auth_client.post(
                '/api/v2/tsa/signer-certificate',
                data=json.dumps({}), content_type='application/json',
            )
            assert r.status_code == 400
        finally:
            self._cleanup(app)

    def test_non_boolean_select_is_rejected(self, app, auth_client, create_ca):
        """#314 review: bool("false") is True, so a string must not reach the
        select branch and swap a healthy signer."""
        ca = create_ca(cn='One-Click TSA CA Select')
        try:
            r = self._issue(auth_client, ca['id'], cn='ucm-oneclick-selstr',
                            select='false')
            assert r.status_code == 400
            assert b'select' in r.data.lower()
        finally:
            self._cleanup(app)

    def test_non_string_cn_is_rejected_with_400_not_500(
        self, app, auth_client, create_ca
    ):
        """#314 review: a non-string cn reached (cn or DEFAULT_CN).strip() and
        raised AttributeError -> 500."""
        ca = create_ca(cn='One-Click TSA CA Cn')
        try:
            r = self._issue(auth_client, ca['id'], cn=123)
            assert r.status_code == 400
        finally:
            self._cleanup(app)

    def test_explicit_zero_validity_is_rejected_not_defaulted(
        self, app, auth_client, create_ca
    ):
        """#314 review: an explicit 0 must surface the backend's own error, not
        silently become the 397-day default."""
        ca = create_ca(cn='One-Click TSA CA Zero')
        try:
            r = self._issue(auth_client, ca['id'], cn='ucm-oneclick-zero',
                            validity_days=0)
            assert r.status_code == 400
            assert b'positive' in r.data.lower()
        finally:
            self._cleanup(app)


_SHA256_ALG_ABSENT = bytes.fromhex('300b0609608648016503040201')
_SHA256_ALG_NULL = bytes.fromhex('300d06096086480165030402010500')


def _imprint_der(alg_der, digest):
    body = alg_der + b'\x04' + bytes([len(digest)]) + digest
    return b'\x30' + bytes([len(body)]) + body


class TestRfc3161Conformance:
    @pytest.mark.parametrize('alg_der', [_SHA256_ALG_ABSENT, _SHA256_ALG_NULL],
                             ids=['params-absent', 'params-null'])
    def test_message_imprint_is_copied_byte_for_byte(self, alg_der):
        # RFC 3161 §2.4.2: the token's messageImprint MUST equal the request's
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        imprint = _imprint_der(alg_der, hashlib.sha256(b'imprint').digest())
        tsq = tsp.TimeStampReq({
            'version': 1,
            'message_imprint': tsp.MessageImprint.load(imprint),
        }).dump()

        resp_der, _ = TSAService(cert, key).process_request(tsq)

        assert _status_native(resp_der) == 'granted'
        assert _tst_info(resp_der)['message_imprint'].dump() == imprint

    @pytest.mark.parametrize('payload', [
        b'\x30\x00',
        b'\x04\x02ab',
        bytes(range(40)),
        _build_tsq(hashlib.sha256(b'cut').digest())[:-5],
        # SHA-256 AlgorithmIdentifier carrying INTEGER parameters
        tsp.TimeStampReq({'version': 1, 'message_imprint': tsp.MessageImprint.load(
            _imprint_der(bytes.fromhex('300e0609608648016503040201020101'),
                         hashlib.sha256(b'int').digest()))}).dump(),
        # A valid request followed by extra bytes
        _build_tsq(hashlib.sha256(b'trailing').digest()) + b'\x00\x00',
    ], ids=['empty-seq', 'octet-string', 'garbage', 'truncated', 'int-params', 'trailing'])
    def test_unparsable_request_is_bad_data_format_without_a_trace(self, payload, caplog):
        import logging
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()

        with caplog.at_level(logging.WARNING, logger='services.tsa_service'):
            resp_der, http = TSAService(cert, key).process_request(payload)

        assert http == 200
        assert _status_native(resp_der) == 'rejection'
        assert _failure_info_native(resp_der) == {'bad_data_format'}
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR or r.exc_info]

    def test_token_announces_one_second_accuracy_on_a_whole_second(self):
        from services.tsa_service import TSAService
        cert, key = _self_signed_tsa()
        resp_der, _ = TSAService(cert, key).process_request(
            _build_tsq(hashlib.sha256(b'accuracy').digest()))

        tst = _tst_info(resp_der)
        assert tst['accuracy'].native == {'seconds': 1, 'millis': None, 'micros': None}
        assert tst['gen_time'].native.microsecond == 0


def _configure_ca_signer(app, create_ca, cert, key, cn):
    """Point the CA-certificate TSA path at *cert*/*key*; returns the cleanup."""
    from cryptography.hazmat.primitives import serialization
    from models import CA, db, SystemConfig

    ca_data = create_ca(cn=cn)
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        ca.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
        ca.prv = base64.b64encode(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )).decode()
        for config_key, value in (('tsa_enabled', 'true'), ('tsa_ca_refid', ca.refid),
                                  ('tsa_signer_cert_refid', '')):
            row = SystemConfig.query.filter_by(key=config_key).first()
            if row is None:
                row = SystemConfig(key=config_key)
                db.session.add(row)
            row.value = value
        db.session.commit()

    def cleanup():
        with app.app_context():
            SystemConfig.query.filter(SystemConfig.key.in_(
                ['tsa_enabled', 'tsa_ca_refid', 'tsa_signer_cert_refid'])
            ).delete(synchronize_session=False)
            db.session.commit()
    return cleanup


class TestTsaProtocolHttp:
    @pytest.mark.parametrize('window', ['expired', 'not-yet-valid'])
    def test_ca_outside_its_validity_does_not_sign(self, app, client, create_ca, window):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        bounds = ({'not_before': now - timedelta(days=30), 'not_after': now - timedelta(days=1)}
                  if window == 'expired' else
                  {'not_before': now + timedelta(days=1), 'not_after': now + timedelta(days=30)})
        cert, key = _self_signed_tsa(include_eku=False, basic_constraints_ca=True, **bounds)
        cleanup = _configure_ca_signer(app, create_ca, cert, key, f'TSA {window} CA')
        try:
            response = client.post(
                '/tsa', data=_build_tsq(hashlib.sha256(b'late').digest()),
                content_type='application/timestamp-query')
            assert response.status_code == 503
            assert response.mimetype == 'text/plain'
        finally:
            cleanup()

    @pytest.mark.parametrize('window', ['expired', 'not-yet-valid'])
    def test_dedicated_signer_outside_its_validity_does_not_sign(
        self, app, client, create_cert, window,
    ):
        from datetime import datetime, timedelta, timezone
        from cryptography.hazmat.primitives import serialization
        from models import Certificate, SystemConfig, db

        now = datetime.now(timezone.utc)
        bounds = ({'not_before': now - timedelta(days=30), 'not_after': now - timedelta(days=1)}
                  if window == 'expired' else
                  {'not_before': now + timedelta(days=1), 'not_after': now + timedelta(days=30)})
        cert, key = _self_signed_tsa(**bounds)
        record = create_cert(cn=f'ucm-tsa-signer-{window}',
                             extra_ekus=['1.3.6.1.5.5.7.3.8'])
        with app.app_context():
            row = Certificate.query.filter_by(refid=record['refid']).first()
            row.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
            row.prv = base64.b64encode(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())).decode()
            for k, v in (('tsa_enabled', 'true'), ('tsa_signer_cert_refid', record['refid'])):
                cfg = SystemConfig.query.filter_by(key=k).first() or SystemConfig(key=k)
                cfg.value = v
                db.session.add(cfg)
            db.session.commit()
        try:
            response = client.post(
                '/tsa', data=_build_tsq(hashlib.sha256(b'signer window').digest()),
                content_type='application/timestamp-query')
            assert response.status_code == 503
        finally:
            with app.app_context():
                SystemConfig.query.filter(SystemConfig.key.in_(
                    ['tsa_enabled', 'tsa_signer_cert_refid'])).delete(synchronize_session=False)
                db.session.commit()

    def test_media_type_is_matched_exactly_and_without_case(self, app, client, create_ca):
        cert, key = _self_signed_tsa(include_eku=False, basic_constraints_ca=True)
        cleanup = _configure_ca_signer(app, create_ca, cert, key, 'TSA media type CA')
        tsq = _build_tsq(hashlib.sha256(b'media type').digest())
        try:
            ok = client.post('/tsa', data=tsq, content_type='Application/Timestamp-Query')
            assert ok.status_code == 200
            assert _status_native(ok.data) == 'granted'

            refused = client.post('/tsa', data=tsq,
                                  content_type='application/x-not-a-timestamp-query')
            assert refused.status_code == 400
            assert refused.mimetype == 'text/plain'
        finally:
            cleanup()

    def test_rejected_request_counts_as_failed(self, app, client, auth_client, create_ca):
        from models import AuditLog, db
        cert, key = _self_signed_tsa(include_eku=False, basic_constraints_ca=True)
        cleanup = _configure_ca_signer(app, create_ca, cert, key, 'TSA failed stats CA')
        try:
            before = auth_client.get('/api/v2/tsa/stats').get_json()['data']
            response = client.post(
                '/tsa', data=_build_tsq(b'\x00' * 16, hash_oid='1.2.840.113549.2.5'),
                content_type='application/timestamp-query')
            assert _status_native(response.data) == 'rejection'
            after = auth_client.get('/api/v2/tsa/stats').get_json()['data']

            assert after['failed'] == before['failed'] + 1
            assert after['total'] == before['total'] + 1
            with app.app_context():
                row = AuditLog.query.filter_by(action='tsa.timestamp_rejected').order_by(
                    AuditLog.id.desc()).first()
                assert row is not None and row.success is False
                assert 'bad_alg' in row.details
        finally:
            cleanup()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
