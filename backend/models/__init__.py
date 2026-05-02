"""Database Models for Ultimate Certificate Manager"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Core models
from models.user import User, UserSession
from models.system_config import SystemConfig
from models.ca import CA
from models.certificate import Certificate
from models.crl_list import CRL
from models.scep import SCEPRequest
from models.audit_log import AuditLog

# Previously-split sub-models (already existed)
from models.certificate_template import CertificateTemplate
from models.truststore import TrustedCertificate
from models.group import Group, GroupMember
from models.email_notification import SMTPConfig, NotificationConfig, NotificationLog
from models.acme_models import AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, AcmeNonce, DnsProvider, AcmeClientOrder, AcmeDomain, AcmeLocalDomain, AcmeEabCredential
from models.api_key import APIKey
from models.auth_certificate import AuthCertificate
from models.crl import CRLMetadata
from models.ocsp import OCSPResponse
from models.webauthn import WebAuthnCredential, WebAuthnChallenge
from models.hsm import HsmProvider, HsmKey
from models.rbac import CustomRole, RolePermission
from models.sso import SSOProvider, SSOSession
from models.policy import CertificatePolicy, ApprovalRequest
from models.ssh import SSHCertificateAuthority, SSHCertificate
from models.msca import MicrosoftCA, MSCARequest
from models.discovered_certificate import ScanProfile, ScanRun, DiscoveredCertificate

from utils.datetime_utils import utc_now, utc_isoformat

# Note: WebhookEndpoint lives in services/webhook_service.py and is imported
# explicitly in app.py before db.create_all() runs. We can't import it here
# without creating a circular dependency (services -> models -> services).

__all__ = [
    "db", "User", "UserSession", "SystemConfig", "CA", "Certificate",
    "CRL", "SCEPRequest", "AuditLog",
    "CRLMetadata", "OCSPResponse", "CertificateTemplate",
    "AcmeAccount", "AcmeOrder", "AcmeAuthorization", "AcmeChallenge", "AcmeNonce",
    "DnsProvider", "AcmeClientOrder", "AcmeDomain", "AcmeLocalDomain", "AcmeEabCredential",
    "HsmProvider", "HsmKey",
    "ScanProfile", "ScanRun", "DiscoveredCertificate",
    "SSHCertificateAuthority", "SSHCertificate",
]
