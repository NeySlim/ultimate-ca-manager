"""
HSM Service - Main service layer for HSM operations
Factory pattern for provider instantiation and database operations.
"""

from typing import Dict, List, Optional, Any, Type
from datetime import datetime
from pathlib import Path
import json
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from sqlalchemy import or_

import fips_mode
from config.settings import Config
from models import db
from models.hsm import HsmProvider, HsmKey
from services import compliance_signer
from services.hsm.ecdsa_signature import coordinate_bytes, ecdsa_to_der
from services.hsm.base_provider import (
    BaseHsmProvider, HsmKeyInfo, brainpool_refusal, mldsa_refusal,
    HsmError, HsmConnectionError, HsmOperationError, HsmConfigError
)
from utils import key_algorithms
from utils.datetime_utils import utc_now
from utils.ha import SOFTHSM_LOCAL, ha_enabled, refuse_softhsm_in_ha
from utils.process_lock import LockBusyError, process_lock
from utils import hsm_check, pkcs11_config

logger = logging.getLogger(__name__)

# Seconds a key generation waits for another on the same provider (RSA-4096 on a device is slow)
GENERATE_LOCK_TIMEOUT = 60



def _parses_as_spki(pem) -> bool:
    try:
        serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)
        return True
    except Exception:
        return False


def _spki_from_pkcs1_pem(pem):
    """SubjectPublicKeyInfo PEM for a cached PKCS#11 RSA key that earlier
    versions stored as PKCS#1 under a "PUBLIC KEY" label; None if it loads."""
    import base64
    from cryptography.hazmat.primitives import serialization
    try:
        serialization.load_pem_public_key(pem.encode())
        return None
    except ValueError:
        pass
    try:
        body = ''.join(line for line in pem.strip().splitlines() if not line.startswith('-----'))
        public_key = serialization.load_der_public_key(base64.b64decode(body))
    except (ValueError, TypeError):
        return None
    return public_key.public_bytes(serialization.Encoding.PEM,
                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()

class HsmService:
    """
    HSM Service - manages providers and keys
    Uses factory pattern to instantiate appropriate provider based on type.
    """
    
    # Registry of provider implementations
    _provider_registry: Dict[str, Type[BaseHsmProvider]] = {}
    
    @classmethod
    def register_provider(cls, provider_type: str, provider_class: Type[BaseHsmProvider]) -> None:
        """
        Register a provider implementation.
        
        Args:
            provider_type: Provider type string (pkcs11, azure-keyvault, etc.)
            provider_class: Provider class implementing BaseHsmProvider
        """
        cls._provider_registry[provider_type] = provider_class
        provider_class.PROVIDER_TYPE = provider_type
        logger.info(f"Registered HSM provider: {provider_type}")
    
    @classmethod
    def signs_pss(cls, provider_type: str) -> bool:
        """Whether keys of this provider type can sign RSASSA-PSS."""
        provider_class = cls._provider_registry.get(provider_type)
        return bool(provider_class and provider_class.SIGNS_PSS)

    @classmethod
    def brainpool_refusal(cls, provider_type: str, algorithm: Optional[str]) -> Optional[str]:
        """Why this provider type cannot hold a Brainpool *algorithm* key, or None."""
        provider_class = cls._provider_registry.get(provider_type)
        supported = bool(provider_class and provider_class.SIGNS_BRAINPOOL)
        return brainpool_refusal(f"provider type '{provider_type}'", algorithm, supported)

    @classmethod
    def mldsa_refusal(cls, provider_type: str, algorithm: Optional[str]) -> Optional[str]:
        """Why this provider type cannot hold an ML-DSA *algorithm* key, or None."""
        provider_class = cls._provider_registry.get(provider_type)
        supported = bool(provider_class and provider_class.SIGNS_ML_DSA)
        library = getattr(provider_class, 'ML_DSA_LIBRARY', None)
        return mldsa_refusal(f"provider type '{provider_type}'", algorithm, supported, library)

    @staticmethod
    def refuse_in_fips_mode(algorithm: Optional[str]) -> None:
        """The HSM signs, not the loaded module: FIPS mode takes only what every module
        approves (RSA, NIST curves), whatever the loaded one approves on top."""
        registered = key_algorithms.get(algorithm) if algorithm else None
        if registered is not None and not registered.fips_static:
            fips_mode.refuse(f'{registered.display} keys')

    @staticmethod
    def eddsa_refusal(algorithm: Optional[str]) -> Optional[str]:
        """Why an EdDSA *algorithm* key is not used on any HSM, or None: no provider wrapper signs with one."""
        alg = key_algorithms.get(algorithm) if algorithm else None
        if alg is not None and alg.family in ('ED25519', 'ED448'):
            return f'{alg.display} keys are not supported on an HSM: an EdDSA CA key is a software key'
        return None

    @classmethod
    def algorithm_refusal(cls, provider_type: str, algorithm: Optional[str]) -> Optional[str]:
        """Why this provider type cannot hold an *algorithm* key (EdDSA, Brainpool, ML-DSA), or None."""
        return (cls.eddsa_refusal(algorithm) or cls.brainpool_refusal(provider_type, algorithm)
                or cls.mldsa_refusal(provider_type, algorithm))

    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available (registered) provider types"""
        return list(cls._provider_registry.keys())
    
    @classmethod
    def _get_provider_instance(cls, provider: HsmProvider) -> BaseHsmProvider:
        """
        Get provider instance for a given HsmProvider model.
        
        Args:
            provider: HsmProvider model instance
            
        Returns:
            Configured provider instance
            
        Raises:
            HsmConfigError: If provider type not registered
        """
        if provider.type not in cls._provider_registry:
            available = ', '.join(cls._provider_registry.keys()) or 'none'
            raise HsmConfigError(
                f"Provider type '{provider.type}' not available. "
                f"Available types: {available}"
            )
        
        provider_class = cls._provider_registry[provider.type]
        config = provider.get_config()
        return provider_class(config)
    
    # =========================================================================
    # Provider CRUD
    # =========================================================================
    
    @staticmethod
    def list_providers() -> List[Dict]:
        """List all HSM providers"""
        providers = HsmProvider.query.order_by(HsmProvider.name).all()
        return [p.to_dict() for p in providers]
    
    @staticmethod
    def get_provider(provider_id: int) -> Optional[HsmProvider]:
        """Get provider by ID"""
        return db.session.get(HsmProvider, provider_id)
    
    @staticmethod
    def get_provider_by_name(name: str) -> Optional[HsmProvider]:
        """Get provider by name"""
        return HsmProvider.query.filter_by(name=name).first()
    
    @staticmethod
    def create_provider(
        name: str,
        provider_type: str,
        config: Dict[str, Any],
        created_by: Optional[int] = None,
        certification: Optional[str] = None
    ) -> HsmProvider:
        """
        Create a new HSM provider.
        
        Args:
            name: Unique provider name
            provider_type: Provider type (pkcs11, azure-keyvault, etc.)
            config: Provider configuration dict
            created_by: User ID who created the provider
            certification: Certification the operator declares (not verified)
            
        Returns:
            Created HsmProvider instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validate type
        if provider_type not in HsmProvider.VALID_TYPES:
            raise ValueError(f"Invalid provider type: {provider_type}")
        
        certification, error = compliance_signer.normalize_certification(certification)
        if error:
            raise ValueError(error)
        if compliance_signer.softhsm_config(provider_type, config, name):
            fips_mode.refuse_softhsm()
            refuse_softhsm_in_ha()

        # Check name uniqueness
        if HsmProvider.query.filter_by(name=name).first():
            raise ValueError(f"Provider with name '{name}' already exists")
        
        # Create provider
        provider = HsmProvider(
            name=name,
            type=provider_type,
            config='{}',
            status='unknown',
            certification=certification,
            created_by=created_by
        )
        provider.set_config(config or {})
        
        db.session.add(provider)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/hsm/hsm_service.py:133: {_commit_err}", exc_info=True)
            raise
        
        logger.info(f"Created HSM provider: {name} ({provider_type})")
        return provider
    
    @staticmethod
    def update_provider(
        provider_id: int,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        certification: Optional[str] = None
    ) -> HsmProvider:
        """
        Update an existing provider. *certification*: None keeps it, blank clears it.
        
        Args:
            provider_id: Provider ID
            name: New name (optional)
            config: New configuration (optional)
            
        Returns:
            Updated HsmProvider instance
            
        Raises:
            ValueError: If provider not found or validation fails
        """
        provider = db.session.get(HsmProvider, provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")

        certification_given = certification is not None
        if certification_given:
            certification, error = compliance_signer.normalize_certification(certification)
            if error:
                raise ValueError(error)
        # Turning a provider into SoftHSM is creating one; editing an existing one is not
        if not compliance_signer.softhsm_provider(provider) and compliance_signer.softhsm_config(
                provider.type, provider.get_config() if config is None else config, name or provider.name):
            fips_mode.refuse_softhsm()
            refuse_softhsm_in_ha()

        if name:
            # Check name uniqueness
            existing = HsmProvider.query.filter_by(name=name).first()
            if existing and existing.id != provider_id:
                raise ValueError(f"Provider with name '{name}' already exists")
            provider.name = name
        
        if config is not None:
            # The form never carries the PIN kept when a new SoftHSM token took over.
            previous_pin = provider.get_config().get('previous_user_pin')
            if previous_pin and 'previous_user_pin' not in config:
                config = {**config, 'previous_user_pin': previous_pin}
            # set_config encrypts sensitive fields and drops mask sentinels
            # ('***'/'********') so an operator updating non-secret fields
            # via the UI doesn't wipe stored credentials.
            provider.set_config(config)
            # Reset status when config changes; the module read last may not be this one
            provider.status = 'unknown'
            provider.error_message = None
            provider.module_info = None
        
        if certification_given:
            provider.certification = certification

        provider.updated_at = utc_now()
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/hsm/hsm_service.py:176: {_commit_err}", exc_info=True)
            raise
        
        logger.info(f"Updated HSM provider: {provider.name}")
        return provider
    
    @staticmethod
    def delete_provider(provider_id: int) -> bool:
        """
        Delete a provider and all its keys.
        
        Args:
            provider_id: Provider ID
            
        Returns:
            True if deleted
            
        Raises:
            ValueError: If provider not found
        """
        provider = db.session.get(HsmProvider, provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        
        name = provider.name
        db.session.delete(provider)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/hsm/hsm_service.py:201: {_commit_err}", exc_info=True)
            raise
        
        logger.info(f"Deleted HSM provider: {name}")
        return True
    
    @classmethod
    def test_provider(cls, provider_id: int) -> Dict[str, Any]:
        """
        Test connection to an HSM provider.
        
        Args:
            provider_id: Provider ID
            
        Returns:
            Dict with 'success', 'message', 'details'
        """
        provider = db.session.get(HsmProvider, provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        
        try:
            hsm = cls._get_provider_instance(provider)
            result = hsm.test_connection()
            
            # Update provider status
            provider.status = 'connected' if result.get('success') else 'error'
            provider.last_tested_at = utc_now()
            provider.error_message = None if result.get('success') else result.get('message')
            if result.get('success'):
                provider.module_info = json.dumps(result['module']) if result.get('module') else None
            db.session.commit()
            
            return result
            
        except HsmError as e:
            provider.status = 'error'
            provider.last_tested_at = utc_now()
            provider.error_message = str(e)
            db.session.commit()
            
            return {
                'success': False,
                'message': str(e)
            }
        except Exception as e:
            provider.status = 'error'
            provider.last_tested_at = utc_now()
            provider.error_message = f"Unexpected error: {str(e)}"
            db.session.commit()
            
            logger.exception(f"HSM test failed for provider {provider.name}")
            return {
                'success': False,
                'message': f"Unexpected error: {str(e)}"
            }
    
    # =========================================================================
    # Key CRUD
    # =========================================================================
    
    @staticmethod
    def list_keys(provider_id: Optional[int] = None) -> List[Dict]:
        """
        List HSM keys, optionally filtered by provider.
        
        Args:
            provider_id: Filter by provider (optional)
            
        Returns:
            List of key dicts
        """
        query = HsmKey.query
        if provider_id:
            query = query.filter_by(provider_id=provider_id)
        
        keys = query.order_by(HsmKey.label).all()
        return [k.to_dict() for k in keys]
    
    @staticmethod
    def get_key(key_id: int) -> Optional[HsmKey]:
        """Get key by ID"""
        return db.session.get(HsmKey, key_id)
    
    @classmethod
    def generate_key(
        cls,
        provider_id: int,
        label: str,
        algorithm: str,
        purpose: str = 'signing',
        extractable: bool = False
    ) -> HsmKey:
        """
        Generate a new key in the HSM.
        
        Args:
            provider_id: Provider ID
            label: Human-readable key label
            algorithm: Key algorithm (RSA-2048, EC-P256, etc.)
            purpose: Key purpose
            extractable: Whether key can be exported
            
        Returns:
            Created HsmKey instance
        """
        provider = db.session.get(HsmProvider, provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        if compliance_signer.softhsm_provider(provider):
            refuse_softhsm_in_ha()
        
        # Validate algorithm
        if algorithm not in HsmKey.VALID_ALGORITHMS:
            raise ValueError(f"Invalid algorithm: {algorithm}")
        refusal = cls.algorithm_refusal(provider.type, algorithm)
        if refusal:
            raise HsmOperationError(refusal)
        registered = key_algorithms.get(algorithm)
        if registered is None and key_algorithms.is_post_quantum(algorithm):
            raise ValueError(f'{algorithm} keys are not available on this build: '
                             'they need OpenSSL 3.5 or later')
        cls.refuse_in_fips_mode(algorithm)
        
        # Validate purpose
        if purpose not in HsmKey.VALID_PURPOSES:
            raise ValueError(f"Invalid purpose: {purpose}")
        
        # Determine key type
        key_type = 'symmetric' if algorithm.startswith('AES') else 'asymmetric'
        
        try:
            # A request queued behind another must not hold a database connection while it waits
            db.session.commit()
            # Providers check a name, then create it: one generation at a time per provider,
            # or two requests both find the name free (one instance; Key Vault cannot do better)
            with process_lock(Path(Config.DATA_DIR) / f'.ucm_hsm_generate_{provider_id}.lock',
                              timeout=GENERATE_LOCK_TIMEOUT, purpose='generating an HSM key',
                              subject='HSM key generation'):
                hsm = cls._get_provider_instance(provider)
                with hsm:
                    key_info = hsm.generate_key(
                        label=label,
                        algorithm=algorithm,
                        purpose=purpose,
                        extractable=extractable
                    )

                # Save to database
                key = HsmKey(
                    provider_id=provider_id,
                    key_identifier=key_info.key_identifier,
                    label=key_info.label,
                    algorithm=key_info.algorithm,
                    key_type=key_info.key_type,
                    purpose=key_info.purpose,
                    public_key_pem=key_info.public_key_pem,
                    is_extractable=key_info.is_extractable,
                    extra_data=json.dumps(key_info.metadata) if key_info.metadata else None
                )

                try:
                    db.session.add(key)
                    db.session.commit()
                except Exception:
                    cls._drop_unrecorded_key(provider, key_info)
                    raise

            logger.info(f"Generated HSM key: {label} ({algorithm}) in {provider.name}")
            return key

        except (HsmError, LockBusyError):
            raise
        except Exception as e:
            logger.exception(f"Failed to generate HSM key: {label}")
            raise HsmOperationError(f"Failed to generate key: {str(e)}")
    
    @classmethod
    def _drop_unrecorded_key(cls, provider, key_info) -> None:
        """A key whose row could not be stored leaves the HSM, unless a row holds its name:
        deleting by name would then take someone else's key (Azure ids differ by version)."""
        try:
            db.session.rollback()
            held = HsmKey.query.filter(
                HsmKey.provider_id == provider.id,
                or_(HsmKey.key_identifier == key_info.key_identifier, HsmKey.label == key_info.label),
            ).first()
            if held:
                logger.warning("HSM key %s has no row of its own, kept: another row holds its name",
                               key_info.key_identifier)
                return
            with cls._get_provider_instance(provider) as hsm:
                hsm.delete_key(key_info.key_identifier)
        except Exception:
            logger.warning("HSM key %s was not recorded and could not be deleted",
                           key_info.key_identifier, exc_info=True)

    @classmethod
    def delete_key(cls, key_id: int) -> bool:
        """
        Delete a key from the HSM and database.
        
        Args:
            key_id: Key ID
            
        Returns:
            True if deleted
        """
        key = db.session.get(HsmKey, key_id)
        if not key:
            raise ValueError(f"Key not found: {key_id}")
        
        provider = key.provider
        label = key.label
        
        try:
            # Delete from HSM
            hsm = cls._get_provider_instance(provider)
            with hsm:
                hsm.delete_key(key.key_identifier)
            
            # Delete from database
            db.session.delete(key)
            db.session.commit()
            cls.forget_signing_hash(key_id)
            
            logger.info(f"Deleted HSM key: {label} from {provider.name}")
            return True
            
        except HsmError:
            raise
        except Exception as e:
            logger.exception(f"Failed to delete HSM key: {label}")
            raise HsmOperationError(f"Failed to delete key: {str(e)}")
    
    @classmethod
    def get_public_key(cls, key_id: int) -> str:
        """
        Get public key in PEM format.
        
        Args:
            key_id: Key ID
            
        Returns:
            Public key PEM string
        """
        key = db.session.get(HsmKey, key_id)
        if not key:
            raise ValueError(f"Key not found: {key_id}")
        
        # Return cached public key if available
        if key.public_key_pem:
            repaired = _spki_from_pkcs1_pem(key.public_key_pem)
            if repaired:
                key.public_key_pem = repaired
                db.session.flush()
            return key.public_key_pem
        
        # Fetch from HSM
        provider = key.provider
        try:
            hsm = cls._get_provider_instance(provider)
            with hsm:
                pem = hsm.get_public_key(key.key_identifier)
            
            # Cache it. Flushed, not committed: the lookup runs inside the
            # caller's transaction (issuance, import) and a commit here would
            # persist that caller's half-done work (self-review of #347)
            key.public_key_pem = pem
            db.session.flush()
            
            return pem
            
        except HsmError:
            raise
        except Exception as e:
            logger.exception(f"Failed to get public key: {key.label}")
            raise HsmOperationError(f"Failed to get public key: {str(e)}")
    
    _signing_hash_cache: dict = {}

    @classmethod
    def forget_signing_hash(cls, key_id: int) -> None:
        """Drop the cached digest of a deleted key: SQLite may reuse its id."""
        for cache_key in [k for k in cls._signing_hash_cache if k[0] == key_id]:
            del cls._signing_hash_cache[cache_key]

    @classmethod
    def signing_hash(cls, key_id: int, key_algorithm: Optional[str], requested: str = 'sha256') -> str:
        """The digest the key's provider signs with when *requested* is asked
        for. Providers that hash with any digest return the request; those
        that bind the digest to the key (curve-matched ECDSA, a KMS key
        version) return that one. Cached per key and request."""
        cache_key = (key_id, requested)
        if cache_key in cls._signing_hash_cache:
            return cls._signing_hash_cache[cache_key]
        key = db.session.get(HsmKey, key_id)
        if not key:
            raise ValueError(f"Key not found: {key_id}")
        try:
            hsm = cls._get_provider_instance(key.provider)
            name = hsm.hash_for_key(key.key_identifier, key_algorithm or key.algorithm, requested) or requested
        except Exception as e:
            # An unreachable or unavailable provider cannot bind anything:
            # the request stands, and signing itself will say what is wrong
            logger.debug(f"Signing digest for HSM key {key_id} left as requested: {e}")
            return requested
        cls._signing_hash_cache[cache_key] = name
        return name

    @staticmethod
    def _cached_public_key(key: HsmKey):
        try:
            pem = key.public_key_pem
            return serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)
        except Exception:
            return None

    @classmethod
    def _registered_algorithm(cls, key: HsmKey):
        """Registry entry of *key*, read off its public key before its stored label."""
        public = cls._cached_public_key(key)
        label = key_algorithms.label_for_public_key(public) if public is not None else None
        return key_algorithms.get(label) or key_algorithms.get(key.algorithm)

    @classmethod
    def fips_signing_refusal(cls, key: HsmKey) -> Optional[str]:
        """What FIPS mode refuses to sign with *key* ('RSA 1024 keys'), or None: only RSA 2048+
        and the registered algorithms every module approves sign. Cached public key, then label."""
        public = cls._cached_public_key(key)
        if isinstance(public, rsa.RSAPublicKey):
            return None if public.key_size >= 2048 else f'RSA {public.key_size} keys'
        registered = cls._registered_algorithm(key)
        if registered is not None:
            return None if registered.fips_static else f'{registered.display} keys'
        if isinstance(public, ec.EllipticCurvePublicKey):
            return f'EC {public.curve.name} keys'
        return f'{key.algorithm or "UNKNOWN"} keys'

    @classmethod
    def refuse_signing_in_fips_mode(cls, key: HsmKey, fetch: bool = True) -> None:
        """FipsRestricted unless *key* signs in FIPS mode; with *fetch*, a public key missing
        from the cache is asked of the provider first, and its label decides if none comes."""
        if not fips_mode.enabled():
            return
        if fetch and not key.public_key_pem:
            try:
                cls.get_public_key(key.id)
            except Exception as e:
                logger.debug(f"Public key of HSM key {key.id} unavailable, judged on its label: {e}")
        refusal = cls.fips_signing_refusal(key)
        if refusal:
            fips_mode.refuse(refusal)

    @classmethod
    def sign(cls, key_id: int, data: bytes, algorithm: Optional[str] = None,
             hash_algorithm: Optional[str] = None, padding: Optional[str] = None) -> bytes:
        """
        Sign data using HSM key.
        
        Args:
            key_id: Key ID
            data: Data to sign
            algorithm: Key algorithm (optional, uses default for key type)
            hash_algorithm: Digest to sign with ('sha256', 'sha384', 'sha512'),
                the one the signature's AlgorithmIdentifier names
            padding: 'pss' for RSASSA-PSS, refused by a provider that cannot
            
        Returns:
            Signature bytes
        """
        key = db.session.get(HsmKey, key_id)
        if not key:
            raise ValueError(f"Key not found: {key_id}")
        
        if key.purpose not in ('signing', 'all'):
            raise ValueError(f"Key {key.label} is not for signing")
        # The HSM signs, not the module: a key bound before the switch or restored after it
        # signs in FIPS mode only if every module approves its algorithm
        cls.refuse_signing_in_fips_mode(key)
        registered = cls._registered_algorithm(key)
        pure = registered is not None and not registered.needs_digest
        if pure and (hash_algorithm or padding):
            raise ValueError(f"{registered.label} signs the data itself: no digest or padding applies")
        
        provider = key.provider
        try:
            hsm = cls._get_provider_instance(provider)
            extra = {}
            if padding == 'pss':
                if not getattr(hsm, 'SIGNS_PSS', False):
                    raise HsmOperationError(f"HSM provider type '{provider.type}' does not sign RSA-PSS")
                extra['padding'] = 'pss'
            with hsm:
                signature = hsm.sign(key.key_identifier, data, algorithm,
                                     hash_algorithm=hash_algorithm, **extra)

            # PKCS#11 and Azure return ECDSA as raw r || s; X.509 needs DER (#366).
            if not pure:
                signature = ecdsa_to_der(
                    signature, coordinate_bytes(key.algorithm, key.public_key_pem))

            logger.debug(f"Signed data with HSM key: {key.label}")
            return signature
            
        except HsmError:
            raise
        except Exception as e:
            logger.exception(f"Failed to sign with HSM key: {key.label}")
            raise HsmOperationError(f"Failed to sign: {str(e)}")
    
    # =========================================================================
    # Sync keys from HSM
    # =========================================================================
    
    @classmethod
    def _refresh_reading(cls, known: HsmKey, key_info: HsmKeyInfo) -> None:
        """Take a valid label and a public key the row could not parse from a newer
        listing; an UNKNOWN reading never overwrites what the row holds."""
        if key_info.algorithm in HsmKey.VALID_ALGORITHMS and key_info.algorithm != known.algorithm:
            known.algorithm = key_info.algorithm
            cls.forget_signing_hash(known.id)
        if key_info.public_key_pem and not _parses_as_spki(known.public_key_pem) \
                and _parses_as_spki(key_info.public_key_pem):
            known.public_key_pem = key_info.public_key_pem

    @classmethod
    def sync_keys(cls, provider_id: int) -> Dict[str, int]:
        """
        Sync keys from HSM to database.
        Adds new keys found in HSM and removes missing ones, except keys another
        row references (kept, counted in 'missing_kept') and except when the
        listing reported errors ('listing_errors' > 0: nothing is removed).

        Args:
            provider_id: Provider ID

        Returns:
            Dict with 'added', 'removed', 'unchanged', 'missing_kept' and
            'listing_errors' counts
        """
        provider = db.session.get(HsmProvider, provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        # Rows synced from a SoftHSM token would only be valid on the node that answered
        if compliance_signer.softhsm_provider(provider):
            refuse_softhsm_in_ha()
        
        try:
            hsm = cls._get_provider_instance(provider)
            with hsm:
                hsm_keys = hsm.list_keys()
            listing_errors = len(getattr(hsm, 'list_errors', None) or [])

            # Get existing keys in DB
            db_keys = {k.key_identifier: k for k in provider.keys}
            hsm_key_ids = {k.key_identifier for k in hsm_keys}
            
            added = 0
            removed = 0
            unchanged = 0
            
            # Add new keys from HSM
            for key_info in hsm_keys:
                if key_info.key_identifier not in db_keys:
                    key = HsmKey(
                        provider_id=provider_id,
                        key_identifier=key_info.key_identifier,
                        label=key_info.label,
                        algorithm=key_info.algorithm,
                        key_type=key_info.key_type,
                        purpose=key_info.purpose,
                        public_key_pem=key_info.public_key_pem,
                        is_extractable=key_info.is_extractable,
                        extra_data=json.dumps(key_info.metadata) if key_info.metadata else None
                    )
                    db.session.add(key)
                    added += 1
                else:
                    known = db_keys[key_info.key_identifier]
                    level = (key_info.metadata or {}).get('protection_level')
                    if level:
                        known.set_metadata({**known.get_metadata(), 'protection_level': level})
                    cls._refresh_reading(known, key_info)
                    unchanged += 1
            
            # A partial listing proves nothing missing; a referenced key is never dropped
            # (deleting it would null the CA's hsm_key_id).
            referenced = cls._referenced_hsm_key_ids()
            missing_kept = 0
            for key_id, key in db_keys.items():
                if key_id in hsm_key_ids:
                    continue
                if listing_errors or key.id in referenced:
                    missing_kept += 1
                    continue
                db.session.delete(key)
                removed += 1

            db.session.commit()

            if listing_errors or missing_kept:
                logger.warning(
                    f"HSM sync for {provider.name}: {listing_errors} unreadable key(s), "
                    f"{missing_kept} missing key(s) kept")
            logger.info(f"Synced HSM keys for {provider.name}: +{added} -{removed} ={unchanged}")
            return {'added': added, 'removed': removed, 'unchanged': unchanged,
                    'missing_kept': missing_kept, 'listing_errors': listing_errors}

        except HsmError:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            logger.exception(f"Failed to sync HSM keys for {provider.name}")
            raise HsmOperationError(f"Failed to sync keys: {str(e)}")

    @staticmethod
    def _referenced_hsm_key_ids() -> set:
        """Ids of hsm_keys rows that any foreign key in the schema points to."""
        ids = set()
        for table in db.metadata.tables.values():
            if table.name == 'hsm_keys':
                continue
            for fk in table.foreign_keys:
                if fk.target_fullname == 'hsm_keys.id':
                    column = fk.parent
                    ids.update(row[0] for row in db.session.execute(
                        db.select(column).where(column.isnot(None))))
        return ids

    @staticmethod
    def repair_pkcs11_provider_config(provider: HsmProvider) -> bool:
        """Rewrite legacy PKCS#11 config keys (library_path/pin) in-place."""
        if provider.type != 'pkcs11':
            return False
        raw = provider.get_config()
        if not pkcs11_config.pkcs11_config_needs_normalization(raw):
            return False
        provider.set_config(pkcs11_config.normalize_pkcs11_config(raw))
        return True

    @staticmethod
    def warn_local_softhsm():
        """HA node start: say once that SoftHSM providers only work where their token is."""
        if not ha_enabled():
            return []
        names = []
        for provider in HsmProvider.query.all():
            try:
                if compliance_signer.softhsm_provider(provider):
                    names.append(provider.name)
            except Exception as exc:
                # One unreadable configuration must not hide the others
                logger.warning("HA: HSM provider %s could not be read: %s", provider.name, type(exc).__name__)
        if names:
            logger.warning("HA: SoftHSM provider(s) %s keep their token on this node only; "
                           "CAs on those keys cannot sign elsewhere", ", ".join(names))
        return names

    @staticmethod
    def auto_register_softhsm():
        """
        Auto-register SoftHSM provider from Docker entrypoint env vars.
        Called at app startup — creates an HsmProvider record if:
          - HSM_DEFAULT_PIN env var is set (entrypoint initialized a token)
          - No provider named 'SoftHSM-Default' already exists
          - SoftHSM library is available on disk

        Also repairs legacy config keys on an existing SoftHSM-Default row
        (library_path/pin → module_path/user_pin). When the entrypoint has just
        created UCM-Default (HSM_TOKEN_CREATED), a row aimed at it takes the new PIN
        and keeps the old one; when it has carried tokens over from the old path
        (HSM_TOKENS_MOVED), the row opens them with that old PIN again.
        """
        import os

        pin = os.environ.get('HSM_DEFAULT_PIN')
        existing = HsmProvider.query.filter_by(name='SoftHSM-Default').first()
        if existing:
            config = existing.get_config()
            aimed_at_default = config.get('token_label', 'UCM-Default') == 'UCM-Default'
            takeover = bool(pin and os.environ.get('HSM_TOKEN_CREATED') == '1' and aimed_at_default)
            restore = bool(
                not takeover and os.environ.get('HSM_TOKENS_MOVED') == '1'
                and aimed_at_default and config.get('previous_user_pin')
            )
            if takeover:
                # The oldest PIN is kept: it opens the token a moved volume would bring back.
                if config.get('user_pin') and config['user_pin'] != pin:
                    config.setdefault('previous_user_pin', config['user_pin'])
                config['user_pin'] = pin
                config['token_label'] = 'UCM-Default'
            elif restore:
                config['user_pin'] = config.pop('previous_user_pin')
            if takeover or restore:
                existing.set_config(config)
                existing.status = 'unknown'
                existing.error_message = None
            repaired = HsmService.repair_pkcs11_provider_config(existing)
            if repaired or takeover or restore:
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.warning("Failed to update the SoftHSM-Default provider: %s", e)
                    return
                if repaired:
                    logger.info("Repaired PKCS#11 config keys for SoftHSM-Default provider")
                if takeover:
                    logger.warning(
                        "SoftHSM token 'UCM-Default' was created anew: SoftHSM-Default now opens it, "
                        "keys of the previous token are gone; its PIN is kept in case that token is restored"
                    )
                if restore:
                    logger.warning(
                        "SoftHSM tokens were carried over from /var/lib/softhsm/tokens: "
                        "SoftHSM-Default opens them with the PIN it had before"
                    )
            return

        if not pin:
            return

        lib_path = hsm_check._find_softhsm()
        if not lib_path:
            logger.debug("HSM_DEFAULT_PIN set but SoftHSM library not found, skipping auto-register")
            return
        try:
            fips_mode.refuse_softhsm()
        except fips_mode.FipsRestricted as e:
            logger.warning("SoftHSM-Default not registered: %s", e)
            return
        if ha_enabled():
            logger.warning("SoftHSM-Default not registered: %s", SOFTHSM_LOCAL)
            return

        try:
            provider = HsmProvider(
                name='SoftHSM-Default',
                type='pkcs11',
                config='{}',
                status='connected',
            )
            provider.set_config({
                'module_path': lib_path,
                'token_label': 'UCM-Default',
                'user_pin': pin,
            })
            db.session.add(provider)
            db.session.commit()
            logger.info("Auto-registered SoftHSM provider 'SoftHSM-Default'")
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Failed to auto-register SoftHSM provider: {e}")
