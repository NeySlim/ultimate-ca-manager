"""
HSM Service - Main service layer for HSM operations
Factory pattern for provider instantiation and database operations.
"""

from typing import Dict, List, Optional, Any, Type
from datetime import datetime
import json
import logging

from models import db
from models.hsm import HsmProvider, HsmKey
from services.hsm.base_provider import (
    BaseHsmProvider, HsmKeyInfo,
    HsmError, HsmConnectionError, HsmOperationError, HsmConfigError
)

logger = logging.getLogger(__name__)


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
        logger.info(f"Registered HSM provider: {provider_type}")
    
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
        return HsmProvider.query.get(provider_id)
    
    @staticmethod
    def get_provider_by_name(name: str) -> Optional[HsmProvider]:
        """Get provider by name"""
        return HsmProvider.query.filter_by(name=name).first()
    
    @staticmethod
    def create_provider(
        name: str,
        provider_type: str,
        config: Dict[str, Any],
        created_by: Optional[int] = None
    ) -> HsmProvider:
        """
        Create a new HSM provider.
        
        Args:
            name: Unique provider name
            provider_type: Provider type (pkcs11, azure-keyvault, etc.)
            config: Provider configuration dict
            created_by: User ID who created the provider
            
        Returns:
            Created HsmProvider instance
            
        Raises:
            ValueError: If validation fails
        """
        # Validate type
        if provider_type not in HsmProvider.VALID_TYPES:
            raise ValueError(f"Invalid provider type: {provider_type}")
        
        # Check name uniqueness
        if HsmProvider.query.filter_by(name=name).first():
            raise ValueError(f"Provider with name '{name}' already exists")
        
        # Create provider
        provider = HsmProvider(
            name=name,
            type=provider_type,
            config=json.dumps(config),
            status='unknown',
            created_by=created_by
        )
        
        db.session.add(provider)
        db.session.commit()
        
        logger.info(f"Created HSM provider: {name} ({provider_type})")
        return provider
    
    @staticmethod
    def update_provider(
        provider_id: int,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> HsmProvider:
        """
        Update an existing provider.
        
        Args:
            provider_id: Provider ID
            name: New name (optional)
            config: New configuration (optional)
            
        Returns:
            Updated HsmProvider instance
            
        Raises:
            ValueError: If provider not found or validation fails
        """
        provider = HsmProvider.query.get(provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        
        if name:
            # Check name uniqueness
            existing = HsmProvider.query.filter_by(name=name).first()
            if existing and existing.id != provider_id:
                raise ValueError(f"Provider with name '{name}' already exists")
            provider.name = name
        
        if config:
            provider.config = json.dumps(config)
            # Reset status when config changes
            provider.status = 'unknown'
            provider.error_message = None
        
        provider.updated_at = datetime.utcnow()
        db.session.commit()
        
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
        provider = HsmProvider.query.get(provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        
        name = provider.name
        db.session.delete(provider)
        db.session.commit()
        
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
        provider = HsmProvider.query.get(provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        
        try:
            hsm = cls._get_provider_instance(provider)
            result = hsm.test_connection()
            
            # Update provider status
            provider.status = 'connected' if result.get('success') else 'error'
            provider.last_tested_at = datetime.utcnow()
            provider.error_message = None if result.get('success') else result.get('message')
            db.session.commit()
            
            return result
            
        except HsmError as e:
            provider.status = 'error'
            provider.last_tested_at = datetime.utcnow()
            provider.error_message = str(e)
            db.session.commit()
            
            return {
                'success': False,
                'message': str(e)
            }
        except Exception as e:
            provider.status = 'error'
            provider.last_tested_at = datetime.utcnow()
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
        return HsmKey.query.get(key_id)
    
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
        provider = HsmProvider.query.get(provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        
        # Validate algorithm
        if algorithm not in HsmKey.VALID_ALGORITHMS:
            raise ValueError(f"Invalid algorithm: {algorithm}")
        
        # Validate purpose
        if purpose not in HsmKey.VALID_PURPOSES:
            raise ValueError(f"Invalid purpose: {purpose}")
        
        # Determine key type
        key_type = 'symmetric' if algorithm.startswith('AES') else 'asymmetric'
        
        try:
            # Generate key in HSM
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
            
            db.session.add(key)
            db.session.commit()
            
            logger.info(f"Generated HSM key: {label} ({algorithm}) in {provider.name}")
            return key
            
        except HsmError:
            raise
        except Exception as e:
            logger.exception(f"Failed to generate HSM key: {label}")
            raise HsmOperationError(f"Failed to generate key: {str(e)}")
    
    @classmethod
    def delete_key(cls, key_id: int) -> bool:
        """
        Delete a key from the HSM and database.
        
        Args:
            key_id: Key ID
            
        Returns:
            True if deleted
        """
        key = HsmKey.query.get(key_id)
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
        key = HsmKey.query.get(key_id)
        if not key:
            raise ValueError(f"Key not found: {key_id}")
        
        # Return cached public key if available
        if key.public_key_pem:
            return key.public_key_pem
        
        # Fetch from HSM
        provider = key.provider
        try:
            hsm = cls._get_provider_instance(provider)
            with hsm:
                pem = hsm.get_public_key(key.key_identifier)
            
            # Cache it
            key.public_key_pem = pem
            db.session.commit()
            
            return pem
            
        except HsmError:
            raise
        except Exception as e:
            logger.exception(f"Failed to get public key: {key.label}")
            raise HsmOperationError(f"Failed to get public key: {str(e)}")
    
    @classmethod
    def sign(cls, key_id: int, data: bytes, algorithm: Optional[str] = None) -> bytes:
        """
        Sign data using HSM key.
        
        Args:
            key_id: Key ID
            data: Data to sign
            algorithm: Signature algorithm (optional, uses default for key type)
            
        Returns:
            Signature bytes
        """
        key = HsmKey.query.get(key_id)
        if not key:
            raise ValueError(f"Key not found: {key_id}")
        
        if key.purpose not in ('signing', 'all'):
            raise ValueError(f"Key {key.label} is not for signing")
        
        provider = key.provider
        try:
            hsm = cls._get_provider_instance(provider)
            with hsm:
                signature = hsm.sign(key.key_identifier, data, algorithm)
            
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
    def sync_keys(cls, provider_id: int) -> Dict[str, int]:
        """
        Sync keys from HSM to database.
        Adds new keys found in HSM, marks missing keys.
        
        Args:
            provider_id: Provider ID
            
        Returns:
            Dict with 'added', 'removed', 'unchanged' counts
        """
        provider = HsmProvider.query.get(provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        
        try:
            hsm = cls._get_provider_instance(provider)
            with hsm:
                hsm_keys = hsm.list_keys()
            
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
                    unchanged += 1
            
            # Remove keys no longer in HSM
            for key_id, key in db_keys.items():
                if key_id not in hsm_key_ids:
                    db.session.delete(key)
                    removed += 1
            
            db.session.commit()
            
            logger.info(f"Synced HSM keys for {provider.name}: +{added} -{removed} ={unchanged}")
            return {'added': added, 'removed': removed, 'unchanged': unchanged}
            
        except HsmError:
            raise
        except Exception as e:
            logger.exception(f"Failed to sync HSM keys for {provider.name}")
            raise HsmOperationError(f"Failed to sync keys: {str(e)}")
