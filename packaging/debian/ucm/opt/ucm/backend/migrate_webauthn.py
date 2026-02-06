"""
Database Migration: Add WebAuthn/FIDO2 Tables
Creates tables for passwordless authentication
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db
from models.webauthn import WebAuthnCredential, WebAuthnChallenge

def migrate():
    """Run migration to add WebAuthn tables"""
    app = create_app()
    
    with app.app_context():
        print("Creating WebAuthn/FIDO2 tables...")
        
        # Create tables
        db.create_all()
        
        print("✓ Tables created successfully")
        
        print("\n" + "="*60)
        print("Migration completed successfully!")
        print("="*60)
        print("\nWebAuthn/FIDO2 Authentication Ready!")
        print("\nFeatures:")
        print("• Passwordless authentication with security keys")
        print("• Support for YubiKey, Windows Hello, TouchID, etc.")
        print("• FIDO2/U2F protocol compliance")
        print("• User verification (PIN/biometric)")
        print("• Passkey support (backup-eligible credentials)")
        print("\nNext steps:")
        print("1. Users can register WebAuthn credentials in Settings")
        print("2. Login with security key from login page")
        print("3. Manage credentials (enable/disable/delete)")
        print("\nSupported Authenticators:")
        print("• Hardware keys: YubiKey 5, Nitrokey, Solo Key")
        print("• Platform authenticators: Windows Hello, TouchID, Face ID")
        print("• Mobile authenticators: Android, iOS (via NFC/Bluetooth)")
        print("\nBrowser Requirements:")
        print("• Chrome/Edge 67+")
        print("• Firefox 60+")
        print("• Safari 13+")
        print("• Opera 54+")

if __name__ == '__main__':
    migrate()
