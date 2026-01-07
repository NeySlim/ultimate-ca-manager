"""
WebAuthn Service
Handle FIDO2/U2F registration and authentication
"""
from typing import Optional, Tuple, List
from datetime import datetime, timedelta
import secrets
import base64
import json

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    AuthenticatorAttachment,
    ResidentKeyRequirement,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from models import db, User
from models.webauthn import WebAuthnCredential, WebAuthnChallenge
import logging

logger = logging.getLogger(__name__)


class WebAuthnService:
    """Service for WebAuthn/FIDO2 operations"""
    
    # Configuration
    RP_NAME = "Ultimate CA Manager"
    RP_ID = None  # Will be set from request hostname
    CHALLENGE_TIMEOUT_MINUTES = 5
    
    @staticmethod
    def set_rp_id(hostname: str):
        """Set Relying Party ID from hostname"""
        # Remove port if present
        if ':' in hostname:
            hostname = hostname.split(':')[0]
        WebAuthnService.RP_ID = hostname
        logger.info(f"WebAuthn RP ID set to: {hostname}")
    
    @staticmethod
    def generate_registration_options(user: User, hostname: str) -> dict:
        """
        Generate options for registering a new WebAuthn credential
        
        Args:
            user: User object
            hostname: Request hostname for RP ID
            
        Returns:
            Registration options dictionary
        """
        WebAuthnService.set_rp_id(hostname)
        
        # Generate challenge (as random bytes)
        challenge_bytes = secrets.token_bytes(32)
        challenge_b64 = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
        
        # Store challenge in database (as base64url string for easy comparison)
        challenge_record = WebAuthnChallenge(
            user_id=user.id,
            challenge=challenge_b64,
            challenge_type='registration',
            expires_at=datetime.utcnow() + timedelta(minutes=WebAuthnService.CHALLENGE_TIMEOUT_MINUTES)
        )
        db.session.add(challenge_record)
        db.session.commit()
        
        logger.info(f"Generated challenge (b64): {challenge_b64[:20]}...")
        
        # Get existing credentials to exclude
        existing_creds = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).all()
        exclude_credentials = [
            PublicKeyCredentialDescriptor(id=cred.credential_id)
            for cred in existing_creds
        ]
        
        # Generate registration options
        options = generate_registration_options(
            rp_id=WebAuthnService.RP_ID,
            rp_name=WebAuthnService.RP_NAME,
            user_id=str(user.id).encode('utf-8'),
            user_name=user.username,
            user_display_name=user.full_name or user.username,
            challenge=challenge_bytes,  # Pass raw bytes
            exclude_credentials=exclude_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.PREFERRED,
                resident_key=ResidentKeyRequirement.PREFERRED,
            ),
            supported_pub_key_algs=[
                COSEAlgorithmIdentifier.ECDSA_SHA_256,
                COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
            ],
        )
        
        return json.loads(options_to_json(options))
    
    @staticmethod
    def verify_registration(user_id: int, credential_data: dict, hostname: str, credential_name: str = None) -> Tuple[bool, str, Optional[WebAuthnCredential]]:
        """
        Verify registration response and create credential
        
        Args:
            user_id: User ID
            credential_data: Registration response from client
            hostname: Request hostname
            credential_name: Optional friendly name for credential
            
        Returns:
            (success, message, WebAuthnCredential)
        """
        WebAuthnService.set_rp_id(hostname)
        
        try:
            logger.info(f"Verifying registration for user {user_id}")
            logger.info(f"Credential data keys: {list(credential_data.keys())}")
            logger.info(f"Response keys: {list(credential_data.get('response', {}).keys())}")
            
            # Get and verify challenge
            client_data_b64 = credential_data['response']['clientDataJSON']
            logger.info(f"clientDataJSON length: {len(client_data_b64)}, sample: {client_data_b64[:50]}...")
            
            # Add padding if needed (base64url to base64)
            padding = '=' * (4 - len(client_data_b64) % 4)
            if padding != '====':
                client_data_b64 += padding
            
            challenge_str = base64.urlsafe_b64decode(client_data_b64).decode('utf-8')
            logger.info(f"Decoded clientDataJSON successfully")
            
            challenge_json = json.loads(challenge_str)
            challenge = challenge_json['challenge']
            logger.info(f"Challenge from client: {challenge[:20]}...")
            
            challenge_record = WebAuthnChallenge.query.filter_by(
                challenge=challenge,
                user_id=user_id,
                challenge_type='registration'
            ).first()
            
            if not challenge_record:
                logger.error(f"No challenge record found for: {challenge[:20]}...")
                # Debug: show all challenges for this user
                all_challenges = WebAuthnChallenge.query.filter_by(user_id=user_id, challenge_type='registration').all()
                logger.error(f"Found {len(all_challenges)} registration challenges for user {user_id}")
                for c in all_challenges[:3]:
                    logger.error(f"  - {c.challenge[:20]}... (valid: {c.is_valid()})")
                return False, "Invalid or expired challenge", None
            
            if not challenge_record.is_valid():
                logger.error(f"Challenge expired or already used")
                return False, "Invalid or expired challenge", None
            
            logger.info(f"Challenge verified successfully")
            
            # Verify registration response with the ORIGINAL challenge from database
            verification = verify_registration_response(
                credential=credential_data,
                expected_challenge=base64.urlsafe_b64decode(challenge_record.challenge + '==='),  # Add padding and decode
                expected_rp_id=WebAuthnService.RP_ID,
                expected_origin=f"https://{hostname}",
            )
            
            # Mark challenge as used
            challenge_record.used = True
            db.session.commit()
            
            # Create credential record
            credential = WebAuthnCredential(
                user_id=user_id,
                credential_id=verification.credential_id,
                public_key=verification.credential_public_key,
                sign_count=verification.sign_count,
                name=credential_name or "Security Key",
                aaguid=str(verification.aaguid) if verification.aaguid else None,
                transports=json.dumps(credential_data.get('response', {}).get('transports', [])),
                is_backup_eligible=verification.credential_backed_up if hasattr(verification, 'credential_backed_up') else False,
                user_verified=True,
                enabled=True
            )
            
            db.session.add(credential)
            db.session.commit()
            
            logger.info(f"WebAuthn credential registered: user_id={user_id}, name={credential_name}")
            return True, "Credential registered successfully", credential
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"WebAuthn registration error: {str(e)}")
            return False, f"Registration failed: {str(e)}", None
    
    @staticmethod
    def generate_authentication_options(username: str, hostname: str) -> Tuple[Optional[dict], Optional[int]]:
        """
        Generate options for authenticating with WebAuthn
        
        Args:
            username: Username to authenticate (or None for usernameless)
            hostname: Request hostname
            
        Returns:
            (options dict, user_id) or (None, None) if user not found
        """
        WebAuthnService.set_rp_id(hostname)
        
        user = User.query.filter_by(username=username).first()
        if not user:
            return None, None
        
        # Generate challenge (as random bytes)
        challenge_bytes = secrets.token_bytes(32)
        challenge_b64 = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
        
        # Store challenge
        challenge_record = WebAuthnChallenge(
            user_id=user.id,
            challenge=challenge_b64,
            challenge_type='authentication',
            expires_at=datetime.utcnow() + timedelta(minutes=WebAuthnService.CHALLENGE_TIMEOUT_MINUTES)
        )
        db.session.add(challenge_record)
        db.session.commit()
        
        logger.info(f"Generated auth challenge (b64): {challenge_b64[:20]}...")
        
        # Get user's credentials
        credentials = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).all()
        
        if not credentials:
            return None, None
        
        allow_credentials = [
            PublicKeyCredentialDescriptor(id=cred.credential_id)
            for cred in credentials
        ]
        
        # Generate authentication options
        options = generate_authentication_options(
            rp_id=WebAuthnService.RP_ID,
            challenge=challenge_bytes,  # Pass raw bytes
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        
        return json.loads(options_to_json(options)), user.id
    
    @staticmethod
    def verify_authentication(user_id: int, credential_data: dict, hostname: str) -> Tuple[bool, str, Optional[User]]:
        """
        Verify authentication response
        
        Args:
            user_id: User ID
            credential_data: Authentication response from client
            hostname: Request hostname
            
        Returns:
            (success, message, User)
        """
        WebAuthnService.set_rp_id(hostname)
        
        try:
            # Get credential ID
            cred_id = base64.urlsafe_b64decode(credential_data['id'] + '==')
            
            # Find credential
            credential = WebAuthnCredential.query.filter_by(
                credential_id=cred_id,
                user_id=user_id,
                enabled=True
            ).first()
            
            if not credential:
                return False, "Credential not found", None
            
            # Get and verify challenge
            challenge_str = base64.urlsafe_b64decode(
                credential_data['response']['clientDataJSON'] + '=='
            ).decode('utf-8')
            
            challenge_json = json.loads(challenge_str)
            challenge = challenge_json['challenge']
            
            challenge_record = WebAuthnChallenge.query.filter_by(
                challenge=challenge,
                user_id=user_id,
                challenge_type='authentication'
            ).first()
            
            if not challenge_record or not challenge_record.is_valid():
                return False, "Invalid or expired challenge", None
            
            # Verify authentication response with ORIGINAL challenge from database
            verification = verify_authentication_response(
                credential=credential_data,
                expected_challenge=base64.urlsafe_b64decode(challenge_record.challenge + '==='),  # Add padding and decode
                expected_rp_id=WebAuthnService.RP_ID,
                expected_origin=f"https://{hostname}",
                credential_public_key=credential.public_key,
                credential_current_sign_count=credential.sign_count,
            )
            
            # Update sign count and last used
            logger.info(f"WebAuthn: old sign_count={credential.sign_count}, new sign_count={verification.new_sign_count}")
            credential.sign_count = verification.new_sign_count
            credential.last_used_at = datetime.utcnow()
            
            # Mark challenge as used
            challenge_record.used = True
            
            db.session.commit()
            
            user = User.query.get(user_id)
            logger.info(f"WebAuthn authentication successful: user={user.username}")
            
            return True, "Authentication successful", user
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"WebAuthn authentication error: {str(e)}")
            return False, f"Authentication failed: {str(e)}", None
    
    @staticmethod
    def get_user_credentials(user_id: int) -> List[WebAuthnCredential]:
        """Get all WebAuthn credentials for a user"""
        return WebAuthnCredential.query.filter_by(user_id=user_id).all()
    
    @staticmethod
    def delete_credential(credential_id: int, user_id: int) -> Tuple[bool, str]:
        """Delete a WebAuthn credential"""
        credential = WebAuthnCredential.query.get(credential_id)
        
        if not credential:
            return False, "Credential not found"
        
        if credential.user_id != user_id:
            user = User.query.get(user_id)
            if not user or user.role != 'admin':
                return False, "Not authorized"
        
        db.session.delete(credential)
        db.session.commit()
        
        logger.info(f"WebAuthn credential deleted: id={credential_id}")
        return True, "Credential deleted successfully"
    
    @staticmethod
    def toggle_credential(credential_id: int, user_id: int, enabled: bool) -> Tuple[bool, str]:
        """Enable or disable a WebAuthn credential"""
        credential = WebAuthnCredential.query.get(credential_id)
        
        if not credential:
            return False, "Credential not found"
        
        if credential.user_id != user_id:
            user = User.query.get(user_id)
            if not user or user.role != 'admin':
                return False, "Not authorized"
        
        credential.enabled = enabled
        db.session.commit()
        
        action = "enabled" if enabled else "disabled"
        logger.info(f"WebAuthn credential {action}: id={credential_id}")
        return True, f"Credential {action} successfully"
