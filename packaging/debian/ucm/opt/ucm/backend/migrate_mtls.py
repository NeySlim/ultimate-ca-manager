"""
Database Migration: Add mTLS Authentication Tables
Creates tables for client certificate authentication
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, SystemConfig
from models.auth_certificate import AuthCertificate

def migrate():
    """Run migration to add mTLS tables"""
    app = create_app()
    
    with app.app_context():
        print("Creating mTLS authentication tables...")
        
        # Create tables
        db.create_all()
        
        print("✓ Tables created successfully")
        
        # Create default mTLS settings
        print("\nCreating default mTLS configuration...")
        
        settings = [
            ('mtls_enabled', 'false', 'Enable mTLS client certificate authentication'),
            ('mtls_required', 'false', 'Require client certificate (no password fallback)'),
            ('mtls_trusted_ca_path', '', 'Path to trusted CA bundle for client certificates')
        ]
        
        for key, value, description in settings:
            config = SystemConfig.query.filter_by(key=key).first()
            if not config:
                config = SystemConfig(
                    key=key,
                    value=value,
                    description=description
                )
                db.session.add(config)
                print(f"✓ Created {key} config")
            else:
                print(f"- {key} config already exists")
        
        db.session.commit()
        
        print("\n" + "="*60)
        print("Migration completed successfully!")
        print("="*60)
        print("\nmTLS Authentication System Ready!")
        print("\nNext steps:")
        print("1. Configure reverse proxy (Nginx/Apache) for client cert validation")
        print("2. Enable mTLS in UI: Settings → mTLS Authentication")
        print("3. Users can enroll certificates in Settings → My Certificates")
        print("\nReverse Proxy Configuration:")
        print("\nNginx example:")
        print("  ssl_client_certificate /path/to/ca-bundle.pem;")
        print("  ssl_verify_client optional;")
        print("  proxy_set_header X-SSL-Client-Cert $ssl_client_cert;")
        print("  proxy_set_header X-SSL-Client-Verify $ssl_client_verify;")
        print("  proxy_set_header X-SSL-Client-S-DN $ssl_client_s_dn;")
        print("\nApache example:")
        print("  SSLCACertificateFile /path/to/ca-bundle.pem")
        print("  SSLVerifyClient optional")
        print("  RequestHeader set X-SSL-Client-Cert \"%{SSL_CLIENT_CERT}s\"")
        print("  RequestHeader set X-SSL-Client-Verify \"%{SSL_CLIENT_VERIFY}s\"")
        print("  RequestHeader set X-SSL-Client-S-DN \"%{SSL_CLIENT_S_DN}s\"")

if __name__ == '__main__':
    migrate()
