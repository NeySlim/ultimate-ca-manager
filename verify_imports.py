
import sys
sys.path.insert(0, "/opt/ucm/backend")

try:
    print("Importing modules...")
    import josepy
    print("josepy imported")
    
    from services.acme.acme_proxy_service import AcmeProxyService
    print("AcmeProxyService imported")
    
    from api.acme.acme_proxy_api import acme_proxy_bp
    print("acme_proxy_bp imported")
    
    # Mock app context for DB access
    from flask import Flask
    from models import db
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        print("DB context created")
        
        # Instantiate service
        svc = AcmeProxyService("https://localhost")
        print("Service instantiated")
        
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
