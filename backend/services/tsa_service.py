"""
RFC 3161 Time-Stamp Protocol (TSP) Service

Provides timestamping authority (TSA) functionality for document
and code signing verification. Uses asn1crypto for proper CMS/PKCS7 encoding.
"""
import hashlib
import logging
import uuid
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID

from asn1crypto import tsp, cms, core, x509 as asn1_x509
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# RFC 5035 / RFC 3161 §2.4.2: register signing-certificate-v2 attribute OID
# into asn1crypto's CMS attribute map. asn1crypto >=1.5 ships ESSCertIDv2 and
# SigningCertificateV2 types but does not register the attribute OID itself.
_SIGNING_CERT_V2_OID = '1.2.840.113549.1.9.16.2.47'
if _SIGNING_CERT_V2_OID not in cms.CMSAttributeType._map:
    cms.CMSAttributeType._map[_SIGNING_CERT_V2_OID] = 'signing_certificate_v2'

    class _SetOfSigningCertificateV2(core.SetOf):
        _child_spec = tsp.SigningCertificateV2

    cms.CMSAttribute._oid_specs['signing_certificate_v2'] = _SetOfSigningCertificateV2

HASH_OIDS = {
    '2.16.840.1.101.3.4.2.1': 'sha256',
    '2.16.840.1.101.3.4.2.2': 'sha384',
    '2.16.840.1.101.3.4.2.3': 'sha512',
}

HASH_CLASSES = {
    'sha256': hashes.SHA256,
    'sha384': hashes.SHA384,
    'sha512': hashes.SHA512,
}


class TSAConfigurationError(ValueError):
    """Raised when the TSA signing certificate is not RFC 3161 compliant."""


class TSAService:
    """RFC 3161 Timestamp Authority Service"""

    def __init__(self, tsa_cert: x509.Certificate, tsa_key, policy_oid: str = '1.2.3.4.1'):
        self.validate_certificate(tsa_cert)
        self.tsa_cert = tsa_cert
        self.tsa_key = tsa_key
        self.policy_oid = policy_oid

    @staticmethod
    def validate_certificate(tsa_cert: x509.Certificate) -> None:
        """Validate the TSA signer. A dedicated end-entity TSA certificate
        (RFC 3161 §2.3: critical, exclusive timeStamping EKU) is the
        recommended setup, but UCM historically signs with the configured
        CA's own certificate — which carries no EKU at all. Refusing that
        broke every pre-2.200 deployment, so a CA certificate stays
        accepted (with a warning), and only an end-entity certificate
        lacking the timeStamping EKU is refused."""
        try:
            bc = tsa_cert.extensions.get_extension_for_oid(
                ExtensionOID.BASIC_CONSTRAINTS
            )
            is_ca = bool(bc.value.ca)
        except x509.ExtensionNotFound:
            is_ca = False

        try:
            eku_extension = tsa_cert.extensions.get_extension_for_oid(
                ExtensionOID.EXTENDED_KEY_USAGE
            )
        except x509.ExtensionNotFound:
            if is_ca:
                logger.warning(
                    'TSA is signing with a CA certificate (no timeStamping EKU). '
                    'Consider issuing a dedicated TSA certificate with a critical, '
                    'exclusive timeStamping EKU (RFC 3161 §2.3).'
                )
                return
            raise TSAConfigurationError(
                'TSA certificate is missing the timeStamping EKU'
            )

        eku_oids = set(eku_extension.value)
        if ExtendedKeyUsageOID.TIME_STAMPING not in eku_oids:
            raise TSAConfigurationError(
                'TSA certificate does not include the timeStamping EKU'
            )
        if not eku_extension.critical or eku_oids != {ExtendedKeyUsageOID.TIME_STAMPING}:
            logger.warning(
                'TSA certificate timeStamping EKU should be critical and exclusive '
                '(RFC 3161 §2.3); accepting for compatibility.'
            )

    def process_request(self, tsp_request_der: bytes) -> Tuple[bytes, int]:
        """Process a TimeStampReq and return a TimeStampResp."""
        try:
            req = tsp.TimeStampReq.load(tsp_request_der)

            version = req['version'].native
            if version != 'v1':
                # RFC 3161 §2.4.2: rejection + badRequest(2)
                return self._error_resp('rejection', 'bad_request',
                                        'Unsupported version'), 200

            msg_imprint = req['message_imprint']
            hash_oid = msg_imprint['hash_algorithm']['algorithm'].dotted
            if hash_oid not in HASH_OIDS:
                # RFC 3161 §2.4.2: rejection + badAlg(0)
                return self._error_resp('rejection', 'bad_alg',
                                        f'Unsupported hash: {hash_oid}'), 200

            # RFC 3161 §2.4.1: when reqPolicy is set the TSA must issue the
            # token under that policy or reject. Issuing under the requested
            # policy keeps clients with pinned policies (openssl ts -tspolicy,
            # code-signing configs) working, as pre-2.200 releases did.
            requested_policy = req['req_policy'].native
            token_policy = requested_policy if requested_policy is not None else self.policy_oid

            extensions = req['extensions']
            if extensions.native is not None:
                for extension in extensions:
                    if extension['critical'].native:
                        return self._error_resp(
                            'rejection',
                            'unaccepted_extensions',
                            f"Unsupported critical extension: {extension['extn_id'].dotted}",
                        ), 200

            digest = msg_imprint['hashed_message'].native
            # RFC 3161 §2.4.1: hashed_message length MUST match hash algorithm
            expected_len = {'sha256': 32, 'sha384': 48, 'sha512': 64}[HASH_OIDS[hash_oid]]
            if len(digest) != expected_len:
                return self._error_resp('rejection', 'bad_data_format',
                                        'Message imprint length mismatch'), 200

            nonce = req['nonce'].native if req['nonce'].native is not None else None
            cert_req = req['cert_req'].native

            tst_info = self._build_tst_info(hash_oid, digest, nonce,
                                            policy_oid=token_policy)
            tst_info_der = tst_info.dump()

            response_der = self._build_signed_response(
                tst_info_der, cert_req, HASH_OIDS[hash_oid]
            )
            return response_der, 200

        except Exception as e:
            logger.error(f"TSA request processing error: {e}", exc_info=True)
            return self._error_resp('rejection', 'system_failure',
                                    'Internal error'), 200

    def _build_tst_info(self, hash_oid: str, digest: bytes,
                        nonce: Optional[int] = None,
                        policy_oid: Optional[str] = None) -> tsp.TSTInfo:
        """Build TSTInfo (RFC 3161 §2.4.2)"""
        serial = uuid.uuid4().int >> 64  # Unique serial, no collision across workers
        now = datetime.now(timezone.utc)

        info = tsp.TSTInfo({
            'version': 'v1',
            'policy': policy_oid or self.policy_oid,
            'message_imprint': {
                'hash_algorithm': {'algorithm': hash_oid},
                'hashed_message': digest,
            },
            'serial_number': serial,
            'gen_time': now,
        })

        if nonce is not None:
            info['nonce'] = core.Integer(nonce)

        return info

    def _build_signed_response(
        self,
        tst_info_der: bytes,
        include_certs: bool,
        message_imprint_hash: str,
    ) -> bytes:
        """Build TimeStampResp wrapping a CMS SignedData."""
        signature_hash_name = (
            message_imprint_hash if message_imprint_hash in HASH_CLASSES else 'sha256'
        )
        signature_hash = HASH_CLASSES[signature_hash_name]()

        # Compute digest of TSTInfo content with the CMS signature digest.
        content_digest = hashlib.new(signature_hash_name, tst_info_der).digest()

        # Get certificate DER
        cert_der = self.tsa_cert.public_bytes(serialization.Encoding.DER)
        cert_asn1 = asn1_x509.Certificate.load(cert_der)

        # Build SignedAttributes (required per CMS when content type != data)
        TST_INFO_OID = '1.2.840.113549.1.9.16.1.4'

        # RFC 3161 §2.4.2 + RFC 5035: TSA SignerInfo MUST contain either
        # ESSCertID (signing-certificate, SHA-1 only) or ESSCertIDv2
        # (signing-certificate-v2, SHA-256+) to bind the TSA cert to the
        # signature and prevent cert-substitution attacks. We use v2.
        cert_sha256 = hashlib.sha256(cert_der).digest()
        ess_cert_id_v2 = tsp.ESSCertIDv2({
            'hash_algorithm': {'algorithm': 'sha256'},
            'cert_hash': cert_sha256,
        })
        signing_cert_v2 = tsp.SigningCertificateV2({
            'certs': [ess_cert_id_v2],
        })

        signed_attrs = cms.CMSAttributes([
            cms.CMSAttribute({
                'type': 'content_type',
                'values': [cms.ContentType(TST_INFO_OID)],
            }),
            cms.CMSAttribute({
                'type': 'message_digest',
                'values': [core.OctetString(content_digest)],
            }),
            cms.CMSAttribute({
                'type': 'signing_certificate_v2',
                'values': [signing_cert_v2],
            }),
        ])

        # Sign the DER-encoded signed attributes (with SET OF tag 0x31)
        signed_attrs_der = signed_attrs.dump()
        # Per CMS, signature is over the DER with EXPLICIT SET tag (0x31)
        tsa_key = self.tsa_key
        if isinstance(tsa_key.public_key(), ec.EllipticCurvePublicKey):
            raw_sig = tsa_key.sign(signed_attrs_der, ec.ECDSA(signature_hash))
            sig_alg = f'{signature_hash_name}_ecdsa'
        else:
            raw_sig = tsa_key.sign(signed_attrs_der, padding.PKCS1v15(), signature_hash)
            sig_alg = f'{signature_hash_name}_rsa'

        # Build SignerInfo
        issuer_and_serial = cms.IssuerAndSerialNumber({
            'issuer': cert_asn1.issuer,
            'serial_number': cert_asn1.serial_number,
        })

        signer_info = cms.SignerInfo({
            'version': 'v1',
            'sid': cms.SignerIdentifier({'issuer_and_serial_number': issuer_and_serial}),
            'digest_algorithm': {'algorithm': signature_hash_name},
            'signed_attrs': signed_attrs,
            'signature_algorithm': {'algorithm': sig_alg},
            'signature': raw_sig,
        })

        # Build SignedData — version MUST be v3 per RFC 5652 §5.1
        # because content type is not 'data'. This also fixes asn1crypto's
        # EXPLICIT [0] tag handling for EncapsulatedContentInfo.
        signed_data_value = cms.SignedData({
            'version': 'v3',
            'digest_algorithms': [{'algorithm': signature_hash_name}],
            'encap_content_info': {
                'content_type': TST_INFO_OID,
                'content': core.ParsableOctetString(tst_info_der),
            },
            'signer_infos': [signer_info],
        })

        if include_certs:
            signed_data_value['certificates'] = [
                cms.CertificateChoices({'certificate': cert_asn1})
            ]

        content_info = cms.ContentInfo({
            'content_type': 'signed_data',
            'content': signed_data_value,
        })

        resp = tsp.TimeStampResp({
            'status': {'status': 'granted'},
            'time_stamp_token': content_info,
        })

        return resp.dump()

    @staticmethod
    def issued_token_metadata(response_der: bytes) -> Optional[dict]:
        """Return serial and policy from a granted response, otherwise None."""
        try:
            response = tsp.TimeStampResp.load(response_der)
            status = response['status']['status'].native
        except ValueError:
            # asn1crypto marks time_stamp_token as required and therefore
            # rejects RFC-compliant status-only error responses.
            return None
        if status not in ('granted', 'granted_with_mods'):
            return None
        token = response['time_stamp_token']
        if token.native is None:
            return None
        tst_info = token['content']['encap_content_info']['content'].parsed
        return {
            'serial': tst_info['serial_number'].native,
            'policy_oid': tst_info['policy'].dotted,
        }

    def _error_resp(self, status: str, fail_info: Optional[str], message: str) -> bytes:
        """Build error TimeStampResp (PKIStatusInfo only, no token).

        RFC 3161 §2.4.2: TimeStampResp ::= SEQUENCE {
            status         PKIStatusInfo,
            timeStampToken TimeStampToken OPTIONAL
        }
        On error, timeStampToken is omitted entirely. PKIFailureInfo (BIT STRING)
        carries the specific failure reason: badAlg(0), badRequest(2),
        badDataFormat(5), timeNotAvailable(14), unacceptedPolicy(15),
        unacceptedExtension(16), addInfoNotAvailable(17), systemFailure(25).
        """
        psi_fields = {
            'status': status,
            'status_string': [message],
        }
        if fail_info:
            psi_fields['fail_info'] = {fail_info}
        status_info = tsp.PKIStatusInfo(psi_fields)
        # asn1crypto's TimeStampResp schema marks time_stamp_token as
        # required, so we hand-build the SEQUENCE wrapper with PKIStatusInfo
        # as the only element (which is RFC-compliant).
        status_der = status_info.dump()
        total_len = len(status_der)
        if total_len < 128:
            return b'\x30' + bytes([total_len]) + status_der
        if total_len < 256:
            return b'\x30\x81' + bytes([total_len]) + status_der
        return b'\x30\x82' + total_len.to_bytes(2, 'big') + status_der
