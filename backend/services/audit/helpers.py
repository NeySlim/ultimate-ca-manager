from typing import Optional
from .core import AuditCoreLoggingMixin


class AuditHelpersMixin:

    @staticmethod
    def log_certificate(action: str, cert, details: str = None, success: bool = True, username: str = None):
        name = getattr(cert, 'descr', None) or getattr(cert, 'subject', None) or f'Cert #{cert.id}'
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='certificate',
            resource_id=cert.id if hasattr(cert, 'id') else str(cert),
            resource_name=name,
            details=details or f'{action.replace("_", " ").title()}: {name}',
            success=success,
            username=username,
        )

    @staticmethod
    def log_ca(action: str, ca, details: str = None, success: bool = True, username: str = None):
        name = getattr(ca, 'descr', None) or getattr(ca, 'subject', None) or f'CA #{ca.id}'
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='ca',
            resource_id=ca.id if hasattr(ca, 'id') else str(ca),
            resource_name=name,
            details=details or f'{action.replace("_", " ").title()}: {name}',
            success=success,
            username=username,
        )

    @staticmethod
    def log_csr(action: str, csr, details: str = None, success: bool = True, username: str = None):
        name = getattr(csr, 'descr', None) or getattr(csr, 'subject', None) or f'CSR #{csr.id}'
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='csr',
            resource_id=csr.id if hasattr(csr, 'id') else str(csr),
            resource_name=name,
            details=details or f'{action.replace("_", " ").title()}: {name}',
            success=success,
            username=username,
        )

    @staticmethod
    def log_user(action: str, user, details: str = None, success: bool = True):
        name = getattr(user, 'username', None) or f'User #{user.id}'
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='user',
            resource_id=user.id if hasattr(user, 'id') else str(user),
            resource_name=name,
            details=details or f'{action.replace("_", " ").title()}: {name}',
            success=success
        )

    @staticmethod
    def log_auth(action: str, username: str, user_id: int = None, details: str = None, success: bool = True):
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='user',
            resource_id=user_id,
            resource_name=username,
            details=details or f'{action.replace("_", " ").title()} for {username}',
            success=success,
            username=username
        )

    @staticmethod
    def log_acme(action: str, resource_name: str, resource_id: str = None, details: str = None, success: bool = True, username: str = 'acme'):
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='acme',
            resource_id=resource_id,
            resource_name=resource_name,
            details=details or f'ACME {action.replace("_", " ")}: {resource_name}',
            success=success,
            username=username
        )

    @staticmethod
    def log_scep(action: str, resource_name: str, resource_id: str = None, details: str = None, success: bool = True, username: str = 'scep'):
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='scep',
            resource_id=resource_id,
            resource_name=resource_name,
            details=details or f'SCEP {action.replace("_", " ")}: {resource_name}',
            success=success,
            username=username
        )

    @staticmethod
    def log_system(action: str, details: str, success: bool = True):
        return AuditCoreLoggingMixin.log_action(
            action=action,
            resource_type='system',
            details=details,
            success=success,
            username='system'
        )
