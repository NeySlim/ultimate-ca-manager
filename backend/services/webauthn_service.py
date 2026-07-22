"""
WebAuthn Service
Handle FIDO2/U2F registration and authentication
"""
from typing import Optional, Tuple, List
from datetime import datetime, timedelta
import secrets
import base64
import hashlib
import hmac
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
    AuthenticatorTransport,
    AuthenticatorAttachment,
    ResidentKeyRequirement,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from models import db, User
from models.webauthn import WebAuthnCredential, WebAuthnChallenge
import logging
from utils.datetime_utils import utc_now
from utils.db_transaction import commit_or_rollback

logger = logging.getLogger(__name__)


def base64url_decode(data: str) -> bytes:
    """Decode base64url string with proper padding"""
    padding = '=' * (4 - len(data) % 4)
    if padding == '====':
        padding = ''
    return base64.urlsafe_b64decode(data + padding)


def base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url without padding"""
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


def get_rp_id(hostname: str) -> str:
    """Extract RP ID from hostname (remove port)"""
    if ':' in hostname:
        return hostname.split(':')[0]
    return hostname


class WebAuthnService:
    """Service for WebAuthn/FIDO2 operations"""
    
    # Configuration
    RP_NAME = "Ultimate Certificate Manager"
    CHALLENGE_TIMEOUT_MINUTES = 5
    
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
        rp_id = get_rp_id(hostname)
        
        # Generate challenge (as random bytes)
        challenge_bytes = secrets.token_bytes(32)
        challenge_b64 = base64url_encode(challenge_bytes)
        
        # Clean up old unused challenges for this user
        WebAuthnChallenge.query.filter(
            WebAuthnChallenge.user_id == user.id,
            WebAuthnChallenge.challenge_type == 'registration',
            (WebAuthnChallenge.used == True) | (WebAuthnChallenge.expires_at < utc_now())
        ).delete()
        
        # Store challenge in database
        challenge_record = WebAuthnChallenge(
            user_id=user.id,
            challenge=challenge_b64,
            challenge_type='registration',
            expires_at=utc_now() + timedelta(minutes=WebAuthnService.CHALLENGE_TIMEOUT_MINUTES)
        )
        db.session.add(challenge_record)
        if not commit_or_rollback(logger, f"Failed to persist WebAuthn registration challenge for user_id={user.id}"):
            return None
        
        # Get existing credentials to exclude
        existing_creds = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).all()
        exclude_credentials = []
        for cred in existing_creds:
            transports = []
            if cred.transports:
                try:
                    transport_list = json.loads(cred.transports)
                    transports = [AuthenticatorTransport(t) for t in transport_list if t]
                except (json.JSONDecodeError, ValueError):
                    pass
            exclude_credentials.append(
                PublicKeyCredentialDescriptor(id=cred.credential_id, transports=transports or None)
            )
        
        # Generate registration options
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=WebAuthnService.RP_NAME,
            user_id=str(user.id).encode('utf-8'),
            user_name=user.username,
            user_display_name=user.full_name or user.username,
            challenge=challenge_bytes,
            exclude_credentials=exclude_credentials if exclude_credentials else None,
            authenticator_selection=AuthenticatorSelectionCriteria(
                # Don't restrict authenticator type - allow both platform (Bitwarden) and cross-platform (Yubikey)
                user_verification=UserVerificationRequirement.PREFERRED,
                resident_key=ResidentKeyRequirement.PREFERRED,  # PREFERRED allows non-discoverable credentials too
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
        """
        rp_id = get_rp_id(hostname)
        
        try:
            # Decode clientDataJSON to get challenge
            client_data_json = base64url_decode(credential_data['response']['clientDataJSON']).decode('utf-8')
            challenge_json = json.loads(client_data_json)
            challenge = challenge_json['challenge']
            
            # Find challenge record
            challenge_record = WebAuthnChallenge.query.filter_by(
                challenge=challenge,
                user_id=user_id,
                challenge_type='registration',
                used=False
            ).first()
            
            if not challenge_record or not challenge_record.is_valid():
                logger.error(f"Challenge not found or invalid for user {user_id}")
                return False, "Invalid or expired challenge", None
            
            # Verify registration response
            verification = verify_registration_response(
                credential=credential_data,
                expected_challenge=base64url_decode(challenge_record.challenge),
                expected_rp_id=rp_id,
                expected_origin=f"https://{hostname}",
            )
            
            # Mark challenge as used and delete it
            db.session.delete(challenge_record)
            
            # Extract transports from response
            transports = credential_data.get('response', {}).get('transports', [])
            if not transports:
                # Try to get from authenticator response
                transports = getattr(credential_data.get('response', {}), 'transports', [])
            
            # Create credential record
            credential = WebAuthnCredential(
                user_id=user_id,
                credential_id=verification.credential_id,
                public_key=verification.credential_public_key,
                sign_count=verification.sign_count,
                name=credential_name or "Security Key",
                aaguid=str(verification.aaguid) if verification.aaguid else None,
                transports=json.dumps(transports) if transports else '[]',
                is_backup_eligible=getattr(verification, 'credential_backed_up', False),
                user_verified=True,
                enabled=True
            )
            
            db.session.add(credential)
            db.session.commit()
            
            logger.info(f"WebAuthn credential registered: user_id={user_id}, cred_id={verification.credential_id.hex()[:16]}...")
            return True, "Credential registered successfully", credential
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"WebAuthn registration error: {str(e)}", exc_info=True)
            return False, f"Registration failed: {str(e)}", None
    
    @staticmethod
    def generate_authentication_options(username: str, hostname: str) -> Tuple[Optional[dict], Optional[int]]:
        """
        Generate options for authenticating with WebAuthn
        """
        rp_id = get_rp_id(hostname)
        
        user = User.query.filter_by(username=username).first()
        if not user:
            return None, None
        
        # Generate challenge
        challenge_bytes = secrets.token_bytes(32)
        challenge_b64 = base64url_encode(challenge_bytes)
        
        # Clean up old challenges
        WebAuthnChallenge.query.filter(
            WebAuthnChallenge.user_id == user.id,
            WebAuthnChallenge.challenge_type == 'authentication',
            (WebAuthnChallenge.used == True) | (WebAuthnChallenge.expires_at < utc_now())
        ).delete()
        
        # Store challenge
        challenge_record = WebAuthnChallenge(
            user_id=user.id,
            challenge=challenge_b64,
            challenge_type='authentication',
            expires_at=utc_now() + timedelta(minutes=WebAuthnService.CHALLENGE_TIMEOUT_MINUTES)
        )
        db.session.add(challenge_record)
        if not commit_or_rollback(logger, "Failed to persist WebAuthn authentication challenge"):
            return None, None
        
        # Get user's credentials with transports
        credentials = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).all()
        
        if not credentials:
            return None, None
        
        allow_credentials = []
        for cred in credentials:
            transports = []
            if cred.transports:
                try:
                    transport_list = json.loads(cred.transports)
                    transports = [AuthenticatorTransport(t) for t in transport_list if t]
                except (json.JSONDecodeError, ValueError):
                    pass
            allow_credentials.append(
                PublicKeyCredentialDescriptor(id=cred.credential_id, transports=transports or None)
            )
        
        # Generate authentication options
        options = generate_authentication_options(
            rp_id=rp_id,
            challenge=challenge_bytes,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        
        return json.loads(options_to_json(options)), user.id

    @staticmethod
    def generate_decoy_authentication_options(username: str, hostname: str, secret: bytes) -> dict:
        """Return well-formed authentication options for a phantom user.

        Anti-enumeration: a request for an unknown username (or a user without
        enabled credentials) must be indistinguishable from a real one. We emit
        a random challenge (never stored, so verify fails generically) plus a
        single decoy credential whose id is HMAC(secret, username) — stable per
        username across probes and unguessable without the server secret, so an
        attacker cannot tell it apart from a genuine credential id.
        """
        rp_id = get_rp_id(hostname)
        challenge_bytes = secrets.token_bytes(32)
        decoy_id = hmac.new(
            secret or b'ucm-webauthn-decoy',
            b'webauthn-decoy:' + username.strip().lower().encode('utf-8'),
            hashlib.sha256,
        ).digest()
        options = generate_authentication_options(
            rp_id=rp_id,
            challenge=challenge_bytes,
            allow_credentials=[PublicKeyCredentialDescriptor(id=decoy_id)],
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        return json.loads(options_to_json(options))

    @staticmethod
    def verify_authentication(user_id: int, credential_data: dict, hostname: str) -> Tuple[bool, str, Optional[User]]:
        """
        Verify authentication response
        """
        rp_id = get_rp_id(hostname)
        
        try:
            # Decode credential ID
            cred_id = base64url_decode(credential_data['id'])
            
            # Find credential
            credential = WebAuthnCredential.query.filter_by(
                credential_id=cred_id,
                user_id=user_id,
                enabled=True
            ).first()
            
            if not credential:
                logger.warning(f"Credential not found: {cred_id.hex()[:16]}... for user {user_id}")
                return False, "Credential not found", None
            
            # Decode clientDataJSON to get challenge
            client_data_json = base64url_decode(credential_data['response']['clientDataJSON']).decode('utf-8')
            challenge_json = json.loads(client_data_json)
            challenge = challenge_json['challenge']
            
            # Find challenge record
            challenge_record = WebAuthnChallenge.query.filter_by(
                challenge=challenge,
                user_id=user_id,
                challenge_type='authentication',
                used=False
            ).first()
            
            if not challenge_record or not challenge_record.is_valid():
                return False, "Invalid or expired challenge", None
            
            # Signature-counter (clone) check is enforced here rather than by the
            # library, which refuses whenever *either* side is non-zero and the
            # response is not greater. Many authenticators — Apple passkeys,
            # Windows Hello, plenty of FIDO2 keys — always report 0: they simply
            # do not implement a counter. For those, a stored value above 0 can
            # never be beaten, so library-side enforcement locks the user out of
            # their own credential permanently. A response of 0 carries no
            # anti-cloning information, so it is not evidence of a clone.
            verification = verify_authentication_response(
                credential=credential_data,
                expected_challenge=base64url_decode(challenge_record.challenge),
                expected_rp_id=rp_id,
                expected_origin=f"https://{hostname}",
                credential_public_key=credential.public_key,
                credential_current_sign_count=0,  # enforced below instead
            )

            stored_count = credential.sign_count or 0
            if verification.new_sign_count > 0 and verification.new_sign_count <= stored_count:
                # The authenticator *does* keep a counter and it did not move
                # forward — the RFC-intended signal that the credential may have
                # been cloned (WebAuthn L2 §6.1.1 step 17).
                logger.warning(
                    "WebAuthn: possible cloned authenticator for credential %s "
                    "(response counter %s did not exceed stored %s)",
                    credential.id, verification.new_sign_count, stored_count,
                )
                return False, "Authentication failed", None

            # Persist the authenticator's actual counter for the next check.
            credential.sign_count = verification.new_sign_count
            credential.last_used_at = utc_now()
            
            # Delete used challenge
            db.session.delete(challenge_record)
            db.session.commit()
            
            user = db.session.get(User, user_id)
            logger.info(f"WebAuthn auth successful: user={user.username}")
            
            return True, "Authentication successful", user
            
        except Exception as e:
            db.session.rollback()
            # A non-increasing sign counter (cloned/replayed authenticator) is
            # surfaced by the verifier as an exception here — log the detail
            # (incl. possible clone detection) but never leak the library's
            # message to the client (generic-error rule).
            logger.error(f"WebAuthn auth error: {str(e)}", exc_info=True)
            return False, "Authentication failed", None
    
    @staticmethod
    def get_user_credentials(user_id: int) -> List[WebAuthnCredential]:
        """Get all WebAuthn credentials for a user"""
        return WebAuthnCredential.query.filter_by(user_id=user_id).all()
    
    @staticmethod
    def delete_credential(credential_id: int, user_id: int) -> Tuple[bool, str]:
        """Delete a WebAuthn credential"""
        credential = db.session.get(WebAuthnCredential, credential_id)
        
        if not credential:
            return False, "Credential not found"
        
        if credential.user_id != user_id:
            user = db.session.get(User, user_id)
            if not user or user.role != 'admin':
                return False, "Not authorized"
        
        db.session.delete(credential)
        if not commit_or_rollback(logger, f"Failed to delete WebAuthn credential id={credential_id}"):
            return False, "Failed to delete credential"
        
        logger.info(f"WebAuthn credential deleted: id={credential_id}")
        return True, "Credential deleted successfully"
    
    @staticmethod
    def toggle_credential(credential_id: int, user_id: int, enabled: bool) -> Tuple[bool, str]:
        """Enable or disable a WebAuthn credential"""
        credential = db.session.get(WebAuthnCredential, credential_id)
        
        if not credential:
            return False, "Credential not found"
        
        if credential.user_id != user_id:
            user = db.session.get(User, user_id)
            if not user or user.role != 'admin':
                return False, "Not authorized"
        
        credential.enabled = enabled
        if not commit_or_rollback(logger, f"Failed to toggle WebAuthn credential id={credential_id}"):
            return False, "Failed to update credential"
        
        action = "enabled" if enabled else "disabled"
        logger.info(f"WebAuthn credential {action}: id={credential_id}")
        return True, f"Credential {action} successfully"
