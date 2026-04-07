"""
RFC 3161 Time-Stamp Protocol (TSP) Service

Provides timestamping authority (TSA) functionality for document
and code signing verification. Uses asn1crypto for proper CMS/PKCS7 encoding.
"""
import hashlib
import logging
import os
import uuid
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding

from asn1crypto import tsp, cms, core, x509 as asn1_x509
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

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


class TSAService:
    """RFC 3161 Timestamp Authority Service"""

    def __init__(self, tsa_cert: x509.Certificate, tsa_key, policy_oid: str = '1.2.3.4.1'):
        self.tsa_cert = tsa_cert
        self.tsa_key = tsa_key
        self.policy_oid = policy_oid

    def process_request(self, tsp_request_der: bytes) -> Tuple[bytes, int]:
        """Process a TimeStampReq and return a TimeStampResp."""
        try:
            req = tsp.TimeStampReq.load(tsp_request_der)

            version = req['version'].native
            if version != 'v1':
                return self._error_resp(2, 'Unsupported version'), 200

            msg_imprint = req['message_imprint']
            hash_oid = msg_imprint['hash_algorithm']['algorithm'].dotted
            if hash_oid not in HASH_OIDS:
                return self._error_resp(0, f'Unsupported hash: {hash_oid}'), 200

            digest = msg_imprint['hashed_message'].native
            nonce = req['nonce'].native if req['nonce'].native is not None else None
            cert_req = req['cert_req'].native

            tst_info = self._build_tst_info(hash_oid, digest, nonce)
            tst_info_der = tst_info.dump()

            response_der = self._build_signed_response(tst_info_der, cert_req)
            return response_der, 200

        except Exception as e:
            logger.error(f"TSA request processing error: {e}", exc_info=True)
            return self._error_resp(2, 'Internal error'), 200

    def _build_tst_info(self, hash_oid: str, digest: bytes,
                        nonce: Optional[int] = None) -> tsp.TSTInfo:
        """Build TSTInfo (RFC 3161 §2.4.2)"""
        serial = uuid.uuid4().int >> 64  # Unique serial, no collision across workers
        now = datetime.now(timezone.utc)

        info = tsp.TSTInfo({
            'version': 'v1',
            'policy': self.policy_oid,
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

    def _build_signed_response(self, tst_info_der: bytes, include_certs: bool) -> bytes:
        """Build TimeStampResp wrapping a CMS SignedData."""
        # Compute digest of TSTInfo content
        content_digest = hashlib.sha256(tst_info_der).digest()

        # Get certificate DER
        cert_der = self.tsa_cert.public_bytes(serialization.Encoding.DER)
        cert_asn1 = asn1_x509.Certificate.load(cert_der)

        # Build SignedAttributes (required per CMS when content type != data)
        TST_INFO_OID = '1.2.840.113549.1.9.16.1.4'
        signed_attrs = cms.CMSAttributes([
            cms.CMSAttribute({
                'type': 'content_type',
                'values': [cms.ContentType(TST_INFO_OID)],
            }),
            cms.CMSAttribute({
                'type': 'message_digest',
                'values': [core.OctetString(content_digest)],
            }),
        ])

        # Sign the DER-encoded signed attributes (with SET OF tag 0x31)
        signed_attrs_der = signed_attrs.dump()
        # Per CMS, signature is over the DER with EXPLICIT SET tag (0x31)
        tsa_key = self.tsa_key
        if isinstance(tsa_key.public_key(), ec.EllipticCurvePublicKey):
            raw_sig = tsa_key.sign(signed_attrs_der, ec.ECDSA(hashes.SHA256()))
            sig_alg = 'sha256_ecdsa'
        else:
            raw_sig = tsa_key.sign(signed_attrs_der, padding.PKCS1v15(), hashes.SHA256())
            sig_alg = 'sha256_rsa'

        # Build SignerInfo
        issuer_and_serial = cms.IssuerAndSerialNumber({
            'issuer': cert_asn1.issuer,
            'serial_number': cert_asn1.serial_number,
        })

        signer_info = cms.SignerInfo({
            'version': 'v1',
            'sid': cms.SignerIdentifier({'issuer_and_serial_number': issuer_and_serial}),
            'digest_algorithm': {'algorithm': 'sha256'},
            'signed_attrs': signed_attrs,
            'signature_algorithm': {'algorithm': sig_alg},
            'signature': raw_sig,
        })

        # Build SignedData — version MUST be v3 per RFC 5652 §5.1
        # because content type is not 'data'. This also fixes asn1crypto's
        # EXPLICIT [0] tag handling for EncapsulatedContentInfo.
        signed_data_value = cms.SignedData({
            'version': 'v3',
            'digest_algorithms': [{'algorithm': 'sha256'}],
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

    def _error_resp(self, status: int, message: str) -> bytes:
        """Build error TimeStampResp (status only, no token)"""
        status_map = {0: 'granted', 2: 'rejection', 5: 'system_failure'}
        status_info = tsp.PKIStatusInfo({
            'status': status_map.get(status, 'rejection'),
            'status_string': [message],
        })
        # asn1crypto doesn't handle optional time_stamp_token properly,
        # so we build the SEQUENCE manually: just PKIStatusInfo, no token
        status_der = status_info.dump()
        total_len = len(status_der)
        if total_len < 128:
            return b'\x30' + bytes([total_len]) + status_der
        return b'\x30\x81' + bytes([total_len]) + status_der
