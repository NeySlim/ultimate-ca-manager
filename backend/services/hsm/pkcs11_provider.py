"""
PKCS#11 HSM Provider
Supports SoftHSM, Thales, nCipher, AWS CloudHSM (via PKCS#11 library)

Based on python-pkcs11 library and PKCS#11 v3.0 standard (OASIS)
"""

import hashlib
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from services.hsm.base_provider import (
    BaseHsmProvider, HsmKeyInfo,
    HsmConnectionError, HsmOperationError, HsmKeyNotFoundError, HsmConfigError
)
from utils.key_algorithms import label_for_curve_name
from utils.pkcs11_config import normalize_pkcs11_config
from utils.request_helpers import safe_call

logger = logging.getLogger(__name__)

# Try to import pkcs11 - it's optional
PKCS11_AVAILABLE = False
ALGORITHM_TO_PKCS11 = {}
SIGN_MECHANISMS = {}

try:
    import pkcs11
    from pkcs11 import KeyType, Attribute, Mechanism, MechanismFlag, ObjectClass
    from pkcs11.util.rsa import encode_rsa_public_key
    from pkcs11.util.ec import encode_ec_public_key, encode_named_curve_parameters
    PKCS11_AVAILABLE = True
    
    # Algorithm mappings (only defined if pkcs11 is available)
    ALGORITHM_TO_PKCS11 = {
        'RSA-2048': (KeyType.RSA, 2048),
        'RSA-3072': (KeyType.RSA, 3072),
        'RSA-4096': (KeyType.RSA, 4096),
        'EC-P256': (KeyType.EC, 'secp256r1'),
        'EC-P384': (KeyType.EC, 'secp384r1'),
        'EC-P521': (KeyType.EC, 'secp521r1'),
        'EC-BP256': (KeyType.EC, 'brainpoolP256r1'),
        'EC-BP384': (KeyType.EC, 'brainpoolP384r1'),
        'EC-BP512': (KeyType.EC, 'brainpoolP512r1'),
        'AES-128': (KeyType.AES, 128),
        'AES-256': (KeyType.AES, 256),
    }
    
    # Signature mechanisms
    SIGN_MECHANISMS = {
        'RSA-2048': Mechanism.SHA256_RSA_PKCS,
        'RSA-3072': Mechanism.SHA384_RSA_PKCS,
        'RSA-4096': Mechanism.SHA512_RSA_PKCS,
        'EC-P256': Mechanism.ECDSA_SHA256,
        'EC-P384': Mechanism.ECDSA_SHA384,
        'EC-P521': Mechanism.ECDSA_SHA512,
        'EC-BP256': Mechanism.ECDSA_SHA256,
        'EC-BP384': Mechanism.ECDSA_SHA384,
        'EC-BP512': Mechanism.ECDSA_SHA512,
    }

    # Digest to apply locally when a token lacks the hashed ECDSA mechanism
    _ECDSA_DIGEST = {
        Mechanism.ECDSA_SHA256: 'sha256',
        Mechanism.ECDSA_SHA384: 'sha384',
        Mechanism.ECDSA_SHA512: 'sha512',
    }

    # RSASSA-PSS: (mechanism, hash, MGF1 hash, salt = digest length)
    from pkcs11 import MGF
    _PSS_MECHANISMS = {
        'sha256': (Mechanism.SHA256_RSA_PKCS_PSS, Mechanism.SHA256, MGF.SHA256, 32),
        'sha384': (Mechanism.SHA384_RSA_PKCS_PSS, Mechanism.SHA384, MGF.SHA384, 48),
        'sha512': (Mechanism.SHA512_RSA_PKCS_PSS, Mechanism.SHA512, MGF.SHA512, 64),
    }
except ImportError:
    pkcs11 = None


class Pkcs11Provider(BaseHsmProvider):
    """
    PKCS#11 HSM Provider
    
    Config:
        module_path: Path to PKCS#11 library (.so/.dll)
        token_label: Token label to use
        user_pin: User PIN for authentication
        slot_index: Slot index (optional, default: auto-detect)
    """

    SIGNS_PSS = True
    SIGNS_BRAINPOOL = True
    
    def __init__(self, config: Dict[str, Any]):
        if not PKCS11_AVAILABLE:
            raise HsmConfigError(
                "python-pkcs11 library not installed. "
                "Install with: pip install python-pkcs11"
            )
        
        config = normalize_pkcs11_config(config)
        if not config.get('user_pin') and config.get('hsm_user') and config.get('hsm_password'):
            # AWS CloudHSM logs a crypto user in with the PIN "<user>:<password>".
            config['user_pin'] = f"{config['hsm_user']}:{config['hsm_password']}"
        super().__init__(config)

        # Validate config
        self.module_path = config.get('module_path')
        self.token_label = config.get('token_label')
        self.user_pin = config.get('user_pin')
        self.slot_index = config.get('slot_index')
        
        if not self.module_path:
            raise HsmConfigError("module_path is required")
        if not self.token_label:
            raise HsmConfigError("token_label is required")
        if not self.user_pin:
            raise HsmConfigError("user_pin is required")
        
        # Check module exists
        if not Path(self.module_path).exists():
            raise HsmConfigError(f"PKCS#11 module not found: {self.module_path}")
        
        self._lib = None
        self._token = None
        self._session = None
        self.list_errors: List[str] = []
    
    def connect(self) -> bool:
        """Connect to HSM and open session"""
        try:
            # Load PKCS#11 library
            self._lib = pkcs11.lib(self.module_path)
            
            # Find token
            if self.slot_index is not None:
                slots = self._lib.get_slots()
                if self.slot_index >= len(slots):
                    raise HsmConnectionError(f"Slot {self.slot_index} not found")
                self._token = slots[self.slot_index].get_token()
            else:
                self._token = self._lib.get_token(token_label=self.token_label)
            
            # Open session
            self._session = self._token.open(rw=True, user_pin=self.user_pin)
            self._connected = True
            
            logger.info(f"Connected to PKCS#11 token: {self.token_label}")
            return True
            
        except pkcs11.PKCS11Error as e:
            self._connected = False
            raise HsmConnectionError(f"PKCS#11 connection failed: {str(e)}")
        except Exception as e:
            self._connected = False
            raise HsmConnectionError(f"Connection failed: {str(e)}")
    
    def disconnect(self) -> None:
        """Close session"""
        if self._session:
            safe_call(self._session.close)
        self._session = None
        self._token = None
        self._lib = None
        self._connected = False
        logger.debug(f"Disconnected from PKCS#11 token: {self.token_label}")
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection and return token info"""
        try:
            self.connect()
            
            # Get token info
            info = {
                'success': True,
                'message': 'Connection successful',
                'details': {
                    'token_label': str(self._token.label).strip(),
                    'manufacturer': str(self._token.manufacturer_id).strip(),
                    'model': str(self._token.model).strip(),
                    'serial': self._token.serial.hex() if isinstance(self._token.serial, bytes) else str(self._token.serial),
                }
            }
            
            self.disconnect()
            return info
            
        except HsmConnectionError as e:
            return {
                'success': False,
                'message': str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Test failed: {str(e)}"
            }
    
    def list_keys(self) -> List[HsmKeyInfo]:
        """List all keys in the token; keys that could not be read land in ``list_errors``."""
        if not self._session:
            raise HsmOperationError("Not connected")

        keys = []
        self.list_errors = []

        try:
            # Find all private keys (we use private keys as reference)
            for obj in self._session.get_objects({
                Attribute.CLASS: ObjectClass.PRIVATE_KEY
            }):
                key_info = self._object_to_key_info(obj, 'asymmetric')
                if key_info:
                    keys.append(key_info)

            # Find all secret keys
            for obj in self._session.get_objects({
                Attribute.CLASS: ObjectClass.SECRET_KEY
            }):
                key_info = self._object_to_key_info(obj, 'symmetric')
                if key_info:
                    keys.append(key_info)

            return keys

        except pkcs11.PKCS11Error as e:
            raise HsmOperationError(f"Failed to list keys: {str(e)}")

    @staticmethod
    def _attr(obj, attribute, default=None):
        """Attribute value, or *default* when the token does not expose it."""
        try:
            return obj[attribute]
        except pkcs11.PKCS11Error:
            return default

    def _ec_algorithm(self, obj, key_id: Optional[bytes]) -> str:
        """Label of the key's curve, read from EC_PARAMS on the key or its public half."""
        params = self._attr(obj, Attribute.EC_PARAMS)
        if not params and key_id:
            for pub in self._session.get_objects({
                Attribute.CLASS: ObjectClass.PUBLIC_KEY, Attribute.ID: key_id
            }):
                params = self._attr(pub, Attribute.EC_PARAMS)
                break
        if not params:
            return 'UNKNOWN'
        try:
            from asn1crypto.keys import ECDomainParameters
            domain = ECDomainParameters.load(bytes(params))
            if domain.name != 'named':
                return 'UNKNOWN'
            return label_for_curve_name(domain.chosen.native) or 'UNKNOWN'
        except Exception:
            return 'UNKNOWN'

    def _object_to_key_info(self, obj, key_type: str) -> Optional[HsmKeyInfo]:
        """Convert PKCS#11 object to HsmKeyInfo"""
        try:
            raw_id = self._attr(obj, Attribute.ID)
            label = self._attr(obj, Attribute.LABEL) or ''
            key_id = raw_id.hex() if raw_id else label
            if not key_id:
                raise ValueError('key has neither ID nor LABEL')

            pkcs11_key_type = self._attr(obj, Attribute.KEY_TYPE)

            if pkcs11_key_type == KeyType.RSA:
                # Private keys carry MODULUS; MODULUS_BITS is a public-key attribute.
                modulus = self._attr(obj, Attribute.MODULUS)
                bits = int.from_bytes(modulus, 'big').bit_length() if modulus else \
                    self._attr(obj, Attribute.MODULUS_BITS)
                algorithm = f'RSA-{bits}' if bits else 'UNKNOWN'
            elif pkcs11_key_type == KeyType.EC:
                algorithm = self._ec_algorithm(obj, raw_id)
            elif pkcs11_key_type == KeyType.AES:
                value_len = self._attr(obj, Attribute.VALUE_LEN)
                algorithm = f'AES-{value_len * 8}' if value_len else 'UNKNOWN'
            else:
                algorithm = 'UNKNOWN'

            # Determine purpose (private keys expose DECRYPT/UNWRAP, secret keys ENCRYPT/WRAP)
            can_sign = bool(self._attr(obj, Attribute.SIGN, False))
            can_encrypt = any(self._attr(obj, a, False) for a in (
                Attribute.ENCRYPT, Attribute.DECRYPT, Attribute.WRAP, Attribute.UNWRAP))

            if can_sign and can_encrypt:
                purpose = 'all'
            elif can_sign:
                purpose = 'signing'
            elif can_encrypt:
                purpose = 'encryption'
            else:
                purpose = 'all'

            is_extractable = bool(self._attr(obj, Attribute.EXTRACTABLE, False))

            return HsmKeyInfo(
                key_identifier=key_id,
                label=label or key_id,
                algorithm=algorithm,
                key_type=key_type,
                purpose=purpose,
                is_extractable=is_extractable
            )

        except Exception as e:
            logger.warning(f"Failed to parse key object: {e}")
            self.list_errors.append(str(e) or type(e).__name__)
            return None
    def generate_key(
        self,
        label: str,
        algorithm: str,
        purpose: str = 'signing',
        extractable: bool = False
    ) -> HsmKeyInfo:
        """Generate a new key in the HSM"""
        if not self._session:
            raise HsmOperationError("Not connected")
        
        if algorithm not in ALGORITHM_TO_PKCS11:
            raise HsmOperationError(f"Unsupported algorithm: {algorithm}")
        
        key_type_enum, param = ALGORITHM_TO_PKCS11[algorithm]
        
        try:
            # Generate unique ID
            import secrets
            key_id = secrets.token_bytes(16)
            
            if key_type_enum == KeyType.RSA:
                # Build MechanismFlag capabilities
                caps = MechanismFlag(0)
                if purpose in ('signing', 'all'):
                    caps |= MechanismFlag.SIGN | MechanismFlag.VERIFY
                if purpose in ('encryption', 'all'):
                    caps |= MechanismFlag.ENCRYPT | MechanismFlag.DECRYPT

                pub, priv = self._session.generate_keypair(
                    KeyType.RSA,
                    param,
                    store=True,
                    label=label,
                    id=key_id,
                    capabilities=caps,
                    private_template={Attribute.EXTRACTABLE: extractable}
                )
                
                public_key_pem = self._export_rsa_public_key(pub)
                
            elif key_type_enum == KeyType.EC:
                # asn1crypto names the Brainpool curves in lower case
                ecparams = self._session.create_domain_parameters(
                    KeyType.EC,
                    {Attribute.EC_PARAMS: encode_named_curve_parameters(param.lower())},
                    local=True
                )
                
                caps = MechanismFlag(0)
                if purpose in ('signing', 'all'):
                    caps |= MechanismFlag.SIGN | MechanismFlag.VERIFY

                pub, priv = ecparams.generate_keypair(
                    store=True,
                    label=label,
                    id=key_id,
                    capabilities=caps,
                    private_template={Attribute.EXTRACTABLE: extractable}
                )
                
                public_key_pem = self._export_ec_public_key(pub)
                
            elif key_type_enum == KeyType.AES:
                caps = MechanismFlag.ENCRYPT | MechanismFlag.DECRYPT
                if purpose in ('wrapping', 'all'):
                    caps |= MechanismFlag.WRAP | MechanismFlag.UNWRAP

                key = self._session.generate_key(
                    KeyType.AES,
                    param,
                    store=True,
                    label=label,
                    id=key_id,
                    capabilities=caps,
                    template={Attribute.EXTRACTABLE: extractable}
                )
                public_key_pem = None
                
            else:
                raise HsmOperationError(f"Unsupported key type: {key_type_enum}")
            
            key_type = 'symmetric' if key_type_enum == KeyType.AES else 'asymmetric'
            
            logger.info(f"Generated key '{label}' ({algorithm}) in HSM")
            
            return HsmKeyInfo(
                key_identifier=key_id.hex(),
                label=label,
                algorithm=algorithm,
                key_type=key_type,
                purpose=purpose,
                public_key_pem=public_key_pem,
                is_extractable=extractable
            )
            
        except pkcs11.PKCS11Error as e:
            raise HsmOperationError(f"PKCS#11 error: {type(e).__name__}: {str(e) or 'see logs'}")
    
    def _export_rsa_public_key(self, pub_key) -> str:
        """Export RSA public key as PEM"""
        try:
            # python-pkcs11 encodes PKCS#1; "PUBLIC KEY" PEM must hold a SubjectPublicKeyInfo
            from cryptography.hazmat.primitives import serialization
            spki = serialization.load_der_public_key(encode_rsa_public_key(pub_key)).public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            return self._der_to_pem(spki, 'PUBLIC KEY')
        except Exception as e:
            logger.warning(f"Failed to export RSA public key: {e}")
            return None
    
    def _export_ec_public_key(self, pub_key) -> str:
        """Export EC public key as PEM"""
        try:
            der = encode_ec_public_key(pub_key)
            return self._der_to_pem(der, 'PUBLIC KEY')
        except Exception as e:
            logger.warning(f"Failed to export EC public key: {e}")
            return None
    
    def _der_to_pem(self, der_bytes: bytes, label: str) -> str:
        """Convert DER to PEM format"""
        import base64
        b64 = base64.b64encode(der_bytes).decode('ascii')
        lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
        return f"-----BEGIN {label}-----\n" + '\n'.join(lines) + f"\n-----END {label}-----\n"
    
    def delete_key(self, key_identifier: str) -> bool:
        """Delete a key from the HSM"""
        if not self._session:
            raise HsmOperationError("Not connected")
        
        try:
            key_id = bytes.fromhex(key_identifier)
            
            # Find and delete private key
            for obj in self._session.get_objects({
                Attribute.CLASS: ObjectClass.PRIVATE_KEY,
                Attribute.ID: key_id
            }):
                obj.destroy()
            
            # Find and delete public key
            for obj in self._session.get_objects({
                Attribute.CLASS: ObjectClass.PUBLIC_KEY,
                Attribute.ID: key_id
            }):
                obj.destroy()
            
            # Find and delete secret key
            for obj in self._session.get_objects({
                Attribute.CLASS: ObjectClass.SECRET_KEY,
                Attribute.ID: key_id
            }):
                obj.destroy()
            
            logger.info(f"Deleted key {key_identifier} from HSM")
            return True
            
        except pkcs11.PKCS11Error as e:
            raise HsmOperationError(f"Failed to delete key: {str(e)}")
    
    def get_public_key(self, key_identifier: str) -> str:
        """Get public key in PEM format"""
        if not self._session:
            raise HsmOperationError("Not connected")
        
        try:
            key_id = bytes.fromhex(key_identifier)
            
            # Find public key
            for pub_key in self._session.get_objects({
                Attribute.CLASS: ObjectClass.PUBLIC_KEY,
                Attribute.ID: key_id
            }):
                key_type = pub_key[Attribute.KEY_TYPE]
                
                if key_type == KeyType.RSA:
                    return self._export_rsa_public_key(pub_key)
                elif key_type == KeyType.EC:
                    return self._export_ec_public_key(pub_key)
                else:
                    raise HsmOperationError(f"Unsupported key type: {key_type}")
            
            raise HsmKeyNotFoundError(f"Public key not found: {key_identifier}")
            
        except pkcs11.PKCS11Error as e:
            raise HsmOperationError(f"Failed to get public key: {str(e)}")
    
    def sign(
        self,
        key_identifier: str,
        data: bytes,
        algorithm: Optional[str] = None,
        hash_algorithm: Optional[str] = None,
        padding: Optional[str] = None
    ) -> bytes:
        """Sign data using HSM key"""
        if not self._session:
            raise HsmOperationError("Not connected")
        
        try:
            key_id = bytes.fromhex(key_identifier)
            
            # Find private key
            priv_key = None
            for obj in self._session.get_objects({
                Attribute.CLASS: ObjectClass.PRIVATE_KEY,
                Attribute.ID: key_id
            }):
                priv_key = obj
                break
            
            if not priv_key:
                raise HsmKeyNotFoundError(f"Private key not found: {key_identifier}")
            
            # Determine mechanism: the digest the caller declares in the
            # signature first, the key-size default otherwise
            key_type = priv_key[Attribute.KEY_TYPE]
            by_digest = {
                KeyType.RSA: {'sha256': Mechanism.SHA256_RSA_PKCS, 'sha384': Mechanism.SHA384_RSA_PKCS,
                              'sha512': Mechanism.SHA512_RSA_PKCS},
                KeyType.EC: {'sha256': Mechanism.ECDSA_SHA256, 'sha384': Mechanism.ECDSA_SHA384,
                             'sha512': Mechanism.ECDSA_SHA512},
            }
            mechanism_param = None
            if padding == 'pss':
                if key_type != KeyType.RSA or hash_algorithm not in _PSS_MECHANISMS:
                    raise HsmOperationError(f"RSA-PSS needs an RSA key and SHA-2, not {hash_algorithm}")
                mechanism, hash_mech, mgf, salt = _PSS_MECHANISMS[hash_algorithm]
                mechanism_param = (hash_mech, mgf, salt)
            elif hash_algorithm and key_type in by_digest and hash_algorithm in by_digest[key_type]:
                mechanism = by_digest[key_type][hash_algorithm]
            elif algorithm:
                mechanism = SIGN_MECHANISMS.get(algorithm)
            else:
                # Default mechanism based on key type
                if key_type == KeyType.RSA:
                    mechanism = Mechanism.SHA256_RSA_PKCS
                elif key_type == KeyType.EC:
                    mechanism = Mechanism.ECDSA_SHA256
                else:
                    raise HsmOperationError(f"Unsupported key type for signing: {key_type}")
            
            # Sign
            try:
                signature = priv_key.sign(data, mechanism=mechanism, mechanism_param=mechanism_param)
            except pkcs11.exceptions.MechanismInvalid:
                # SoftHSM and some tokens offer only raw ECDSA: hash here and
                # sign the digest, which is the same signature.
                digest_name = _ECDSA_DIGEST.get(mechanism)
                if digest_name is None:
                    raise
                signature = priv_key.sign(getattr(hashlib, digest_name)(data).digest(),
                                          mechanism=Mechanism.ECDSA)

            logger.debug(f"Signed {len(data)} bytes with key {key_identifier}")
            return signature
            
        except pkcs11.PKCS11Error as e:
            raise HsmOperationError(f"Signing failed: {str(e)}")


# Export availability flag
def is_available() -> bool:
    """Check if PKCS#11 provider is available"""
    return PKCS11_AVAILABLE
