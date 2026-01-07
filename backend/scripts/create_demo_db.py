#!/usr/bin/env python3
"""
Create demo database for certific.ate
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from models import db, User, CA, Certificate, CRLMetadata
from services.ca_service import CAService
from services.cert_service import CertificateService
from services.crl_service import CRLService
from werkzeug.security import generate_password_hash
import random

app = create_app()

with app.app_context():
    print("🗑️  Dropping all tables...")
    db.drop_all()
    
    print("📦 Creating tables...")
    db.create_all()
    
    print("\n👥 Creating users...")
    users = [
        User(username='admin', password_hash=generate_password_hash('admin'), 
             email='admin@certific.ate', role='admin'),
        User(username='alice', password_hash=generate_password_hash('alice123'), 
             email='alice@certific.ate', role='user'),
        User(username='bob', password_hash=generate_password_hash('bob123'), 
             email='bob@certific.ate', role='user'),
    ]
    db.session.add_all(users)
    db.session.commit()
    print(f"✅ {len(users)} users created")
    
    ca_service = CAService()
    cert_service = CertificateService()
    crl_service = CRLService()
    
    print("\n📜 Creating Certificate Authorities...")
    
    # Root CA
    root_ca = ca_service.create_internal_ca(
        common_name='Certific.ate Root CA',
        organization='Certific.ate Security',
        organizational_unit='Certificate Authority',
        country='US',
        state='California',
        locality='San Francisco',
        validity_days=7300,
        key_type='ECDSA_P384',
        hash_algorithm='SHA384'
    )
    print(f"  ✅ {root_ca.common_name}")
    
    # Web Services CA
    web_ca = ca_service.create_internal_ca(
        common_name='Certific.ate Web Services CA',
        organization='Certific.ate Security',
        organizational_unit='Web Security',
        country='US',
        state='California',
        locality='San Francisco',
        validity_days=3650,
        key_type='ECDSA_P256',
        hash_algorithm='SHA256',
        parent_ca_id=root_ca.id
    )
    web_ca.cdp_enabled = True
    web_ca.cdp_url = 'https://crl.certific.ate/cdp/{ca_refid}/crl.pem'
    db.session.commit()
    print(f"  ✅ {web_ca.common_name} (CDP enabled)")
    
    # VPN Services CA
    vpn_ca = ca_service.create_internal_ca(
        common_name='Certific.ate VPN Services CA',
        organization='Certific.ate Security',
        organizational_unit='Network Security',
        country='US',
        state='California',
        locality='San Francisco',
        validity_days=3650,
        key_type='RSA_4096',
        hash_algorithm='SHA384',
        parent_ca_id=root_ca.id
    )
    vpn_ca.cdp_enabled = True
    vpn_ca.cdp_url = 'https://crl.certific.ate/cdp/{ca_refid}/crl.pem'
    db.session.commit()
    print(f"  ✅ {vpn_ca.common_name} (CDP enabled)")
    
    # Code Signing CA
    code_ca = ca_service.create_internal_ca(
        common_name='Certific.ate Code Signing CA',
        organization='Certific.ate Security',
        organizational_unit='Software Security',
        country='US',
        state='California',
        locality='San Francisco',
        validity_days=2555,
        key_type='RSA_4096',
        hash_algorithm='SHA512',
        parent_ca_id=root_ca.id
    )
    print(f"  ✅ {code_ca.common_name}")
    
    print("\n📜 Creating Web Server Certificates...")
    
    # Wildcard
    wildcard = cert_service.create_certificate(
        common_name='*.certific.ate',
        organization='Certific.ate Security',
        organizational_unit='Web Services',
        country='US',
        validity_days=365,
        key_type='ECDSA_P256',
        hash_algorithm='SHA256',
        ca_id=web_ca.id,
        key_usage=['digitalSignature', 'keyEncipherment'],
        extended_key_usage=['serverAuth'],
        subject_alt_names=['DNS:*.certific.ate', 'DNS:certific.ate']
    )
    print(f"  ✅ {wildcard.common_name}")
    
    # Web servers
    web_servers = [
        ('www.certific.ate', ['DNS:www.certific.ate', 'DNS:certific.ate']),
        ('api.certific.ate', ['DNS:api.certific.ate']),
        ('dashboard.certific.ate', ['DNS:dashboard.certific.ate']),
        ('mail.certific.ate', ['DNS:mail.certific.ate', 'DNS:smtp.certific.ate']),
        ('shop.certific.ate', ['DNS:shop.certific.ate']),
    ]
    
    for cn, sans in web_servers:
        cert = cert_service.create_certificate(
            common_name=cn,
            organization='Certific.ate Security',
            country='US',
            validity_days=730,
            key_type='ECDSA_P256',
            hash_algorithm='SHA256',
            ca_id=web_ca.id,
            key_usage=['digitalSignature', 'keyEncipherment'],
            extended_key_usage=['serverAuth'],
            subject_alt_names=sans
        )
        print(f"  ✅ {cn}")
    
    print("\n📜 Creating VPN Certificates...")
    
    # VPN Server
    vpn_server = cert_service.create_certificate(
        common_name='vpn.certific.ate',
        organization='Certific.ate Security',
        country='US',
        validity_days=1095,
        key_type='RSA_2048',
        hash_algorithm='SHA256',
        ca_id=vpn_ca.id,
        key_usage=['digitalSignature', 'keyEncipherment'],
        extended_key_usage=['serverAuth'],
        subject_alt_names=['DNS:vpn.certific.ate', 'IP:10.0.0.1']
    )
    print(f"  ✅ {vpn_server.common_name}")
    
    # VPN Clients
    vpn_users = ['alice', 'bob', 'charlie', 'diana']
    for user in vpn_users:
        cert = cert_service.create_certificate(
            common_name=f'{user}@certific.ate',
            organization='Certific.ate Security',
            country='US',
            validity_days=365,
            key_type='RSA_2048',
            hash_algorithm='SHA256',
            ca_id=vpn_ca.id,
            key_usage=['digitalSignature'],
            extended_key_usage=['clientAuth'],
            subject_alt_names=[f'email:{user}@certific.ate']
        )
        print(f"  ✅ {user}@certific.ate")
    
    print("\n📜 Creating Code Signing Certificates...")
    
    code_signers = [
        'Certific.ate Developers',
        'Certific.ate Release',
        'Alice Developer',
    ]
    
    for cn in code_signers:
        cert = cert_service.create_certificate(
            common_name=cn,
            organization='Certific.ate Security',
            country='US',
            validity_days=1095,
            key_type='RSA_4096',
            hash_algorithm='SHA512',
            ca_id=code_ca.id,
            key_usage=['digitalSignature'],
            extended_key_usage=['codeSigning']
        )
        print(f"  ✅ {cn}")
    
    print("\n📜 Creating Email (S/MIME) Certificates...")
    
    emails = ['admin@certific.ate', 'alice@certific.ate', 'security@certific.ate']
    
    for email in emails:
        cert = cert_service.create_certificate(
            common_name=email,
            organization='Certific.ate Security',
            country='US',
            validity_days=730,
            key_type='RSA_2048',
            hash_algorithm='SHA256',
            ca_id=web_ca.id,
            key_usage=['digitalSignature', 'keyEncipherment'],
            extended_key_usage=['emailProtection'],
            subject_alt_names=[f'email:{email}']
        )
        print(f"  ✅ {email}")
    
    print("\n🔄 Generating CRLs...")
    crl_service.generate_crl(web_ca.id)
    crl_service.generate_crl(vpn_ca.id)
    print("  ✅ CRLs generated")
    
    print("\n🗑️  Revoking some certificates...")
    all_certs = Certificate.query.all()
    to_revoke = random.sample(all_certs, min(3, len(all_certs)))
    reasons = ['keyCompromise', 'superseded', 'cessationOfOperation']
    
    for i, cert in enumerate(to_revoke):
        cert_service.revoke_certificate(cert.id, reason=reasons[i])
        print(f"  ✅ Revoked: {cert.common_name} ({reasons[i]})")
    
    print("\n🔄 Regenerating CRLs after revocations...")
    crl_service.generate_crl(web_ca.id)
    crl_service.generate_crl(vpn_ca.id)
    print("  ✅ CRLs updated")
    
    print("\n" + "="*70)
    print("✅ DEMO DATABASE COMPLETE!")
    print("="*70)
    print(f"🏢 Organization: Certific.ate Security")
    print(f"🌐 Domain: certific.ate")
    print(f"🔐 Slogan: 'We Certific-ate Your Security!'")
    print(f"\n📊 Statistics:")
    print(f"   CAs: {CA.query.count()}")
    print(f"   Certificates: {Certificate.query.count()}")
    print(f"   Active: {Certificate.query.filter_by(revoked=False).count()}")
    print(f"   Revoked: {Certificate.query.filter_by(revoked=True).count()}")
    print(f"   Users: {User.query.count()}")
    print(f"\n🔑 Login: admin / admin")
    print("="*70)
