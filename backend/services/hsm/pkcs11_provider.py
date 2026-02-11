"""
PKCS#11 HSM Provider
Supports SoftHSM, Thales, nCipher, AWS CloudHSM (via PKCS#11 library)

Based on python-pkcs11 library and PKCS#11 v3.0 standard (OASIS)
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from services.hsm.base_provider import (
    BaseHsmProvider, HsmKeyInfo,
    HsmConnectionError, HsmOperationError, HsmKeyNotFoundError, HsmConfigError
)

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
    
    def __init__(self, config: Dict[str, Any]):
        if not PKCS11_AVAILABLE:
            raise HsmConfigError(
                "python-pkcs11 library not installed. "
                "Install with: pip install python-pkcs11"
            )
        
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
            try:
                self._session.close()
            except Exception:
                pass
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
        """List all keys in the token"""
        if not self._session:
            raise HsmOperationError("Not connected")
        
        keys = []
        
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
    
    def _object_to_key_info(self, obj, key_type: str) -> Optional[HsmKeyInfo]:
        """Convert PKCS#11 object to HsmKeyInfo"""
        try:
            label = obj[Attribute.LABEL]
            key_id = obj[Attribute.ID].hex() if obj[Attribute.ID] else label
            
            # Determine algorithm
            pkcs11_key_type = obj[Attribute.KEY_TYPE]
            
            if pkcs11_key_type == KeyType.RSA:
                modulus_bits = obj[Attribute.MODULUS_BITS] if hasattr(obj, '__getitem__') else 2048
                algorithm = f'RSA-{modulus_bits}'
            elif pkcs11_key_type == KeyType.EC:
                algorithm = 'EC-P256'  # Simplified, could parse EC params
            elif pkcs11_key_type == KeyType.AES:
                value_len = obj.get(Attribute.VALUE_LEN, 32) * 8
                algorithm = f'AES-{value_len}'
            else:
                algorithm = 'UNKNOWN'
            
            # Determine purpose
            can_sign = obj.get(Attribute.SIGN, False)
            can_encrypt = obj.get(Attribute.ENCRYPT, False) or obj.get(Attribute.WRAP, False)
            
            if can_sign and can_encrypt:
                purpose = 'all'
            elif can_sign:
                purpose = 'signing'
            elif can_encrypt:
                purpose = 'encryption'
            else:
                purpose = 'all'
            
            is_extractable = obj.get(Attribute.EXTRACTABLE, False)
            
            return HsmKeyInfo(
                key_identifier=key_id,
                label=label,
                algorithm=algorithm,
                key_type=key_type,
                purpose=purpose,
                is_extractable=is_extractable
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse key object: {e}")
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
                ecparams = self._session.create_domain_parameters(
                    KeyType.EC,
                    {Attribute.EC_PARAMS: encode_named_curve_parameters(param)},
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
            der = encode_rsa_public_key(pub_key)
            return self._der_to_pem(der, 'PUBLIC KEY')
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
        algorithm: Optional[str] = None
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
            
            # Determine mechanism
            key_type = priv_key[Attribute.KEY_TYPE]
            
            if algorithm:
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
            signature = priv_key.sign(data, mechanism=mechanism)
            
            logger.debug(f"Signed {len(data)} bytes with key {key_identifier}")
            return signature
            
        except pkcs11.PKCS11Error as e:
            raise HsmOperationError(f"Signing failed: {str(e)}")


# Export availability flag
def is_available() -> bool:
    """Check if PKCS#11 provider is available"""
    return PKCS11_AVAILABLE
