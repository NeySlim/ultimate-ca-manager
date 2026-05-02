"""External Account Binding (EAB) mixin for ACME service"""
import json
import hashlib
import base64
import logging
from typing import Dict, Any, Optional, Tuple

from models import db

logger = logging.getLogger(__name__)


class EabMixin:
    def validate_eab(self, eab_data: Dict[str, Any], account_jwk: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate External Account Binding (RFC 8555 §7.3.4)
        
        The EAB is a JWS signed with a pre-shared HMAC key, binding
        the ACME account key to an external account.
        
        Args:
            eab_data: The externalAccountBinding JWS object
            account_jwk: The account JWK being registered
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            import hmac as hmac_lib
            
            # EAB must have protected, payload, signature
            if not all(k in eab_data for k in ('protected', 'payload', 'signature')):
                return False, "Missing required JWS fields"
            
            # Decode protected header
            protected_b64 = eab_data['protected']
            protected_json = base64.urlsafe_b64decode(protected_b64 + '==')
            protected = json.loads(protected_json)
            
            # Verify algorithm is HS256 (HMAC-SHA256) per RFC 8555
            alg = protected.get('alg', '')
            if alg not in ('HS256', 'HS384', 'HS512'):
                return False, f"Invalid EAB algorithm: {alg}. Must be HMAC-based"
            
            # Extract key ID (the external account identifier)
            kid = protected.get('kid', '')
            if not kid:
                return False, "EAB missing kid (external account ID)"
            
            # Look up the HMAC key for this external account.
            # Preferred path: dedicated AcmeEabCredential table (v2.139+).
            # Fallback: legacy SystemConfig 'acme_eab_keys' JSON blob.
            from models import SystemConfig, AcmeEabCredential
            from utils.datetime_utils import utc_now as _utc_now

            credential = AcmeEabCredential.query.filter_by(kid=kid).first()
            hmac_key_b64 = None
            legacy = False

            if credential is not None:
                if not credential.is_usable:
                    return False, f"EAB credential not usable (status={credential.status})"
                hmac_key_b64 = credential.hmac_key_b64
            else:
                eab_config = SystemConfig.query.filter_by(key='acme_eab_keys').first()
                eab_keys_json = eab_config.value if eab_config else '{}'
                try:
                    eab_keys = json.loads(eab_keys_json)
                except Exception:
                    eab_keys = {}
                hmac_key_b64 = eab_keys.get(kid)
                legacy = True

            if not hmac_key_b64:
                return False, "Unknown external account"

            # Decode the HMAC key
            hmac_key = base64.urlsafe_b64decode(hmac_key_b64 + '==')
            
            # Verify the payload is the account JWK
            payload_b64 = eab_data['payload']
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + '==')
            try:
                payload_jwk = json.loads(payload_bytes)
                # The payload should be the account public key
                if payload_jwk.get('kty') != account_jwk.get('kty'):
                    return False, "EAB payload does not match account key"
            except Exception:
                return False, "EAB payload is not valid JSON"
            
            # Verify HMAC signature
            signing_input = f"{protected_b64}.{payload_b64}".encode('ascii')
            
            if alg == 'HS256':
                mac = hmac_lib.new(hmac_key, signing_input, hashlib.sha256).digest()
            elif alg == 'HS384':
                mac = hmac_lib.new(hmac_key, signing_input, hashlib.sha384).digest()
            else:  # HS512
                mac = hmac_lib.new(hmac_key, signing_input, hashlib.sha512).digest()
            
            expected_sig = base64.urlsafe_b64encode(mac).rstrip(b'=').decode('ascii')
            actual_sig = eab_data['signature']
            
            if not hmac_lib.compare_digest(expected_sig, actual_sig):
                return False, "EAB signature verification failed"

            # Mark credential as used (single-use semantics, RFC 8555 §7.3.4).
            # The actual binding to the freshly-created AcmeAccount is done
            # by the caller (new_account handler) via mark_eab_used().
            try:
                if legacy:
                    eab_config = SystemConfig.query.filter_by(key='acme_eab_keys').first()
                    eab_keys_json = eab_config.value if eab_config else '{}'
                    try:
                        eab_keys = json.loads(eab_keys_json)
                    except Exception:
                        eab_keys = {}
                    eab_keys.pop(kid, None)
                    if eab_config:
                        eab_config.value = json.dumps(eab_keys)
                    else:
                        db.session.add(SystemConfig(key='acme_eab_keys', value=json.dumps(eab_keys)))
                else:
                    credential.status = 'used'
                    credential.used_at = _utc_now()
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.error(f"Failed to persist EAB key consumption: {commit_err}")
            
            return True, None
            
        except Exception as e:
            logger.error(f"EAB validation error: {e}")
            return False, str(e)

    def mark_eab_used(self, kid: str, account_id: str) -> None:
        """Bind an EAB credential to the ACME account that consumed it.

        Called from the new-account handler once the account row is
        committed. Best-effort: does nothing for legacy SystemConfig
        credentials or unknown kids.
        """
        try:
            from models import AcmeEabCredential
            cred = AcmeEabCredential.query.filter_by(kid=kid).first()
            if cred is not None and cred.used_by_account_id is None:
                cred.used_by_account_id = account_id
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Failed to bind EAB credential {kid} to account {account_id}: {e}")
