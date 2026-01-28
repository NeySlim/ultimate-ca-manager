"""
Pytest Configuration and Fixtures
"""
import os
import sys
import pytest
import tempfile

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

@pytest.fixture(scope='session')
def app():
    """Create test Flask application"""
    # Set test environment
    os.environ['SECRET_KEY'] = 'test-secret-key-12345678901234567890'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-12345678901234567890'
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['FQDN'] = 'test.local'
    os.environ['HTTPS_PORT'] = '8443'
    os.environ['HTTP_REDIRECT'] = 'false'  # Disable HTTPS redirect for tests
    
    from app import create_app
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TRAP_HTTP_EXCEPTIONS'] = False
    
    # Create database tables
    with app.app_context():
        from models import db
        db.create_all()
        
        # Create test user
        from models import User
        from werkzeug.security import generate_password_hash
        
        test_user = User(
            username='testuser',
            email='test@example.com',
            password_hash=generate_password_hash('testpass123'),
            role='admin',
            active=True
        )
        db.session.add(test_user)
        db.session.commit()
    
    yield app
    
    # Cleanup
    with app.app_context():
        from models import db
        db.drop_all()


@pytest.fixture
def client(app):
    """Test client"""
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    """Authenticated test client"""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'testuser'
        sess['role'] = 'admin'
    return client


@pytest.fixture
def auth_headers(app):
    """Generate auth headers with valid JWT"""
    import jwt
    from datetime import datetime, timedelta
    
    payload = {
        'sub': 1,
        'username': 'testuser',
        'role': 'admin',
        'exp': datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def sample_ca(app):
    """Create a sample CA for testing"""
    with app.app_context():
        from models import db, CA
        import uuid
        
        ca = CA(
            refid=str(uuid.uuid4())[:8],
            descr='Test Root CA',
            subject='CN=Test Root CA,O=Test Org',
            issuer='CN=Test Root CA,O=Test Org',
            serial='1',
            crt='LS0tLS1CRUdJTi...',  # Base64 placeholder
            prv='LS0tLS1CRUdJTi...',
        )
        db.session.add(ca)
        db.session.commit()
        
        yield ca
        
        db.session.delete(ca)
        db.session.commit()


@pytest.fixture
def sample_certificate(app, sample_ca):
    """Create a sample certificate for testing"""
    with app.app_context():
        from models import db, Certificate
        from datetime import datetime, timedelta
        import uuid
        
        cert = Certificate(
            refid=str(uuid.uuid4())[:8],
            caref=sample_ca.refid,
            descr='Test Certificate',
            cert_type='server',
            subject='CN=test.example.com',
            issuer=sample_ca.subject,
            serial_number='100',
            valid_from=datetime.utcnow(),
            valid_to=datetime.utcnow() + timedelta(days=365),
            crt='LS0tLS1CRUdJTi...',
            prv='LS0tLS1CRUdJTi...',
        )
        db.session.add(cert)
        db.session.commit()
        
        yield cert
        
        db.session.delete(cert)
        db.session.commit()
