"""External Account Binding (EAB) mixin for ACME service"""
import json
import hashlib
import base64
import logging
from typing import Dict, Any, Optional, Tuple

from sqlalchemy import or_

from models import db

logger = logging.getLogger(__name__)


class EabMixin:
    def validate_eab(
        self,
        eab_data: Dict[str, Any],
        account_jwk: Dict[str, Any],
        new_account_url: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate External Account Binding (RFC 8555 §7.3.4)
        
        The EAB is a JWS signed with a pre-shared HMAC key, binding
        the ACME account key to an external account.
        
        Args:
            eab_data: The externalAccountBinding JWS object
            account_jwk: The account JWK being registered
            new_account_url: URL from the outer newAccount JWS protected header
            
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
            
            # The EAB JWS is bound to the newAccount request URL.
            if new_account_url is not None and protected.get('url') != new_account_url:
                return False, 'EAB protected url does not match newAccount URL'

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

            credential = AcmeEabCredential.query.filter_by(kid=kid).first()
            hmac_key_b64 = None

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

            if not hmac_key_b64:
                return False, "Unknown external account"

            # Decode the HMAC key
            hmac_key = base64.urlsafe_b64decode(hmac_key_b64 + '==')
            
            # Verify the payload is the account JWK (RFC 8555 §7.3.4):
            # "The 'payload' field of the JWS object MUST contain the public
            # key of the ACME account being created. This is the same value
            # as the 'jwk' field of the outer JWS."
            payload_b64 = eab_data['payload']
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + '==')
            try:
                payload_jwk = json.loads(payload_bytes)
            except Exception:
                return False, "EAB payload is not valid JSON"

            # Full JWK match — compare canonical thumbprints (RFC 7638) so
            # equivalent JWKs differing only by member ordering still match,
            # but an attacker cannot swap the account key while keeping the
            # same kty.
            try:
                if self._compute_jwk_thumbprint(payload_jwk) != \
                   self._compute_jwk_thumbprint(account_jwk):
                    return False, "EAB payload does not match account key"
            except (KeyError, ValueError) as e:
                return False, f"EAB payload JWK invalid: {e}"
            
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

            # Validation is intentionally side-effect free. The credential is
            # consumed only after the account row has committed successfully.
            return True, None
            
        except Exception as e:
            logger.error(f"EAB validation error: {e}")
            return False, str(e)

    def mark_eab_used(self, kid: str, account_id: str) -> bool:
        """Consume and bind an EAB credential after account creation commits."""
        try:
            from models import AcmeEabCredential, SystemConfig
            from utils.datetime_utils import utc_now

            credential = AcmeEabCredential.query.filter_by(kid=kid).first()
            if credential is not None:
                now = utc_now()
                consumed = AcmeEabCredential.query.filter(
                    AcmeEabCredential.kid == kid,
                    AcmeEabCredential.status == 'active',
                    AcmeEabCredential.used_by_account_id.is_(None),
                    or_(
                        AcmeEabCredential.expires_at.is_(None),
                        AcmeEabCredential.expires_at > now,
                    ),
                ).update({
                    'status': 'used',
                    'used_at': now,
                    'used_by_account_id': account_id,
                }, synchronize_session=False)
                if consumed == 0:
                    db.session.rollback()
                    current = AcmeEabCredential.query.filter_by(kid=kid).first()
                    return bool(
                        current
                        and current.status == 'used'
                        and current.used_by_account_id == account_id
                    )
            else:
                config = SystemConfig.query.filter_by(key='acme_eab_keys').first()
                if config is None:
                    return False
                try:
                    keys = json.loads(config.value or '{}')
                except Exception:
                    return False
                if kid not in keys:
                    return False
                keys.pop(kid)
                config.value = json.dumps(keys)

            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Failed to consume EAB credential {kid}: {e}")
            return False
