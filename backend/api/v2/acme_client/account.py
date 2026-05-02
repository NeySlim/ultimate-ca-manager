"""
ACME Client Account Management Routes
POST /api/v2/acme/client/account
"""

import logging
from flask import request

from api.v2.acme_client import bp, _set_config
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from services.acme.acme_client_service import AcmeClientService
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


@bp.route('/api/v2/acme/client/account', methods=['POST'])
@require_auth(['write:acme'])
def register_account():
    """
    Register ACME account with Let's Encrypt.

    Body:
    {
        "email": "admin@example.com",
        "environment": "staging"  // or "production"
    }
    """
    data = request.json
    if not data:
        return error_response('Request body required', 400)

    email = data.get('email')
    if not email:
        return error_response('Email is required', 400)

    environment = data.get('environment', 'staging')
    if environment not in ['staging', 'production']:
        return error_response('Environment must be staging or production', 400)

    try:
        client = AcmeClientService(environment=environment)
        success, message, account_url = client.register_account(email)

        if success:
            # Save email as default
            _set_config('acme.client.email', email, 'ACME client contact email')
            db.session.commit()

            AuditService.log_action(
                action='acme_account_register',
                resource_type='acme_account',
                resource_name=email,
                details=f'Registered ACME account for {email} ({environment})',
                success=True
            )

            return success_response(
                data={'account_url': account_url},
                message=message
            )
        else:
            return error_response(message, 400)

    except Exception as e:
        db.session.rollback()
        logger.error(f'ACME account registration failed: {e}')
        return error_response('Registration failed', 500)
