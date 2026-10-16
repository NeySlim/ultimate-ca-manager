#!/usr/bin/env python3
"""
Create complete demo database for certific.ate with real CAs
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from models import db, User, CA
from services.ca_service import CAService
from utils.password_hash import hash_password

app = create_app()

with app.app_context():
    print("🗑️  Dropping all tables...")
    db.drop_all()
    
    print("📦 Creating tables...")
    db.create_all()
    
    print("\n👥 Creating users...")
    users = [
        User(username='admin', password_hash=hash_password('admin'), 
             email='admin@certific.ate', role='admin'),
        User(username='alice', password_hash=hash_password('alice123'), 
             email='alice@certific.ate', role='user'),
        User(username='bob', password_hash=hash_password('bob123'), 
             email='bob@certific.ate', role='user'),
    ]
    db.session.add_all(users)
    db.session.commit()
    print(f"✅ {len(users)} users created")
    
    ca_service = CAService()
    
    print("\n📜 Creating Certificate Authorities...")
    print("   (This will take a few minutes - generating cryptographic keys...)")
    
    # Root CA
    print("\n  🔐 Generating Root CA (ECDSA P-384)...")
    root_ca = ca_service.create_internal_ca(
        descr='Certific.ate Root CA',
        dn={
            'CN': 'Certific.ate Root CA',
            'O': 'Certific.ate Security',
            'OU': 'Certificate Authority',
            'C': 'US',
            'ST': 'California',
            'L': 'San Francisco'
        },
        key_type='secp384r1',  # ECDSA P-384 (secp384r1 est le bon nom)
        validity_days=7300,
        digest='sha384',
        username='admin'
    )
    print(f"    ✅ {root_ca.descr} (ID: {root_ca.id}, RefID: {root_ca.refid})")
    
    # Web Services CA
    print("\n  🔐 Generating Web Services CA (ECDSA P-256)...")
    web_ca = ca_service.create_internal_ca(
        descr='Certific.ate Web Services CA',
        dn={
            'CN': 'Certific.ate Web Services CA',
            'O': 'Certific.ate Security',
            'OU': 'Web Security',
            'C': 'US',
            'ST': 'California',
            'L': 'San Francisco'
        },
        key_type='prime256v1',  # ECDSA P-256 (prime256v1 est le bon nom)
        validity_days=3650,
        digest='sha256',
        caref=root_ca.refid,  # Intermediate CA
        username='admin'
    )
    # Enable CDP
    web_ca.cdp_enabled = True
    web_ca.cdp_url = 'https://crl.certific.ate/cdp/{ca_refid}/crl.pem'
    db.session.commit()
    print(f"    ✅ {web_ca.descr} (ID: {web_ca.id}, CDP enabled)")
    
    # VPN Services CA
    print("\n  🔐 Generating VPN Services CA (RSA 4096)...")
    vpn_ca = ca_service.create_internal_ca(
        descr='Certific.ate VPN Services CA',
        dn={
            'CN': 'Certific.ate VPN Services CA',
            'O': 'Certific.ate Security',
            'OU': 'Network Security',
            'C': 'US',
            'ST': 'California',
            'L': 'San Francisco'
        },
        key_type='4096',  # RSA 4096
        validity_days=3650,
        digest='sha384',
        caref=root_ca.refid,
        username='admin'
    )
    vpn_ca.cdp_enabled = True
    vpn_ca.cdp_url = 'https://crl.certific.ate/cdp/{ca_refid}/crl.pem'
    db.session.commit()
    print(f"    ✅ {vpn_ca.descr} (ID: {vpn_ca.id}, CDP enabled)")
    
    # Code Signing CA
    print("\n  🔐 Generating Code Signing CA (RSA 4096)...")
    code_ca = ca_service.create_internal_ca(
        descr='Certific.ate Code Signing CA',
        dn={
            'CN': 'Certific.ate Code Signing CA',
            'O': 'Certific.ate Security',
            'OU': 'Software Security',
            'C': 'US',
            'ST': 'California',
            'L': 'San Francisco'
        },
        key_type='4096',  # RSA 4096
        validity_days=2555,
        digest='sha512',
        caref=root_ca.refid,
        username='admin'
    )
    print(f"    ✅ {code_ca.descr} (ID: {code_ca.id})")
    
    print("\n" + "="*70)
    print("✅ DEMO DATABASE COMPLETE!")
    print("="*70)
    print(f"🏢 Organization: Certific.ate Security")
    print(f"🌐 Domain: certific.ate")
    print(f"🔐 Slogan: 'We Certific-ate Your Security!'")
    print(f"\n📊 Statistics:")
    print(f"   CAs: {CA.query.count()}")
    print(f"     - Root CA: 1")
    print(f"     - Intermediate CAs: 3")
    print(f"     - CAs with CDP: 2")
    print(f"   Users: {User.query.count()}")
    print(f"\n🔑 Login: admin / admin")
    print(f"\n💡 Tip: You can now create certificates via the web interface!")
    print(f"   - Web certs: Use 'Web Services CA'")
    print(f"   - VPN certs: Use 'VPN Services CA'")
    print(f"   - Code signing: Use 'Code Signing CA'")
    print("="*70)
