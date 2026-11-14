"""Database Models for Ultimate Certificate Manager"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Core models
from models.user import User, UserSession
from models.system_config import SystemConfig
from models.ca import CA
from models.certificate import Certificate
from models.crl_list import CRL
from models.scep import SCEPRequest, ScepProfile, IntuneApp
from models.audit_log import AuditLog

# Previously-split sub-models (already existed)
from models.certificate_template import CertificateTemplate
from models.truststore import TrustedCertificate
from models.group import Group, GroupMember
from models.email_notification import SMTPConfig, NotificationConfig, NotificationLog
from models.acme_models import AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, AcmeNonce, DnsProvider, AcmeClientOrder, AcmeDomain, AcmeLocalDomain, AcmeEabCredential, AcmeProxyChallengeLink
from models.acme_client_account import AcmeClientAccount
from models.acme_dns_update import AcmeDnsUpdateKey, AcmeProxyDnsChallenge
from models.api_key import APIKey
from models.auth_certificate import AuthCertificate
from models.crl import CRLMetadata, CRLNumberCounter
from models.ocsp import OCSPResponse
from models.webauthn import WebAuthnCredential, WebAuthnChallenge
from models.hsm import HsmProvider, HsmKey
from models.rbac import CustomRole, RolePermission
from models.sso import SSOProvider, SSOSession, SAMLMessageId
from models.policy import CertificatePolicy, ApprovalRequest
from models.ssh import SSHCertificateAuthority, SSHCertificate
from models.msca import MicrosoftCA, MSCARequest
from models.ad_connector import ADConnectorConfig
from models.windows_profile import WindowsEnrollmentProfile, WindowsProfileTemplate
from models.discovered_certificate import ScanProfile, ScanRun, DiscoveredCertificate
from models.ca_template_pin import CATemplatePin
from models.ca_cross_certificate import CACrossCertificate
from models.related_cert_request import RelatedCertRequestUse
from models.webhook_delivery import WebhookDelivery
from models.key_recovery import KeyRecoveryRequest
from models.revoked_serial import RevokedSerial
from models.compromised_key import CompromisedKeyRecord
from models.est_signer_cert import EstSignerCert
from models.deploy import DeployTarget, DeployBinding, CRLDeployBinding, DeployDelivery
from models.cluster import ClusterCommand, ClusterNode, SchedulerRequest
from models.encryption_key import EncryptionKey
from models.websocket_relay import WebsocketRelayEvent
from models.shared_file import SharedFile
from models.backup_archive import BackupArchive, BackupArchiveChunk

from utils.datetime_utils import utc_now, utc_isoformat

# Note: WebhookEndpoint lives in services/webhook_service.py and is imported
# explicitly in app.py before db.create_all() runs. We can't import it here
# without creating a circular dependency (services -> models -> services).

__all__ = [
    "db", "User", "UserSession", "SystemConfig", "CA", "Certificate",
    "CRL", "SCEPRequest", "AuditLog",
    "CRLMetadata", "CRLNumberCounter", "OCSPResponse", "CertificateTemplate",
    "AcmeAccount", "AcmeOrder", "AcmeAuthorization", "AcmeChallenge", "AcmeNonce",
    "DnsProvider", "AcmeClientOrder", "AcmeDomain", "AcmeLocalDomain", "AcmeEabCredential",
    "AcmeProxyChallengeLink",
    "AcmeClientAccount", "AcmeDnsUpdateKey", "AcmeProxyDnsChallenge",
    "HsmProvider", "HsmKey",
    "ScanProfile", "ScanRun", "DiscoveredCertificate",
    "SSHCertificateAuthority", "SSHCertificate",
    "CATemplatePin",
    "WebhookDelivery",
    "KeyRecoveryRequest",
    "ADConnectorConfig", "WindowsEnrollmentProfile", "WindowsProfileTemplate",
    "RevokedSerial", "CompromisedKeyRecord", "EstSignerCert",
    "DeployTarget", "DeployBinding", "CRLDeployBinding", "DeployDelivery",
    "ClusterCommand", "ClusterNode", "SchedulerRequest", "EncryptionKey", "WebsocketRelayEvent",
    "SharedFile", "BackupArchive", "BackupArchiveChunk",
]
