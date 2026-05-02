from ._constants import CATEGORIES
from .core import AuditCoreLoggingMixin
from .helpers import AuditHelpersMixin
from .query import AuditQueryMixin


class AuditService(
    AuditCoreLoggingMixin,
    AuditHelpersMixin,
    AuditQueryMixin,
):
    CATEGORIES = CATEGORIES


def audit_event(
    action: str,
    resource_type: str = None,
    resource_id=None,
    resource_name: str = None,
    details: str = None,
    success: bool = True,
    username: str = None,
    user_id: int = None,
):
    """Shorthand for inline AuditService.log_action() calls.

    Reduces 6-line keyword blocks to a single call::

        audit_event('cert_created', 'certificate', cert.id, cert.descr,
                    f'Created certificate {cert.descr}')
    """
    AuditService.log_action(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        details=details,
        success=success,
        username=username,
        user_id=user_id,
    )


# Decorator for automatic audit logging
def audit_log(action: str, resource_type: str = None):
    from functools import wraps

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                result = f(*args, **kwargs)

                res_id = None
                if isinstance(result, tuple) and len(result) >= 2:
                    pass
                elif hasattr(result, 'id'):
                    res_id = result.id
                elif 'id' in kwargs:
                    res_id = kwargs['id']

                AuditService.log_action(
                    action=action,
                    resource_type=resource_type,
                    resource_id=res_id,
                    details=f"Action {action} completed successfully",
                    success=True
                )
                return result

            except Exception as e:
                AuditService.log_action(
                    action=action,
                    resource_type=resource_type,
                    details=f"Action {action} failed: {str(e)}",
                    success=False
                )
                raise

        return wrapper
    return decorator
