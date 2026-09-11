"""The approval gate shared by every operator issuance path.

An issuance policy with ``requires_approval`` used to be consulted by the
issue form only: an operator signed a stored request, in bulk or one by one,
or renewed a certificate, without any approval. The gate below evaluates the
same policies (CA, template, name pattern scoping) for those paths and
queues an ``ApprovalRequest`` typed after the operation, which the approval
route then performs.
"""

import base64
import logging
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID, NameOID

from models.policy import ApprovalRequest, CertificatePolicy
from services.policy_service import PolicyEvaluationService

logger = logging.getLogger(__name__)


def certificate_identity(pem_b64: str) -> Tuple[Optional[str], list]:
    """``(cn, dns_names)`` of a stored certificate or request (base64 PEM)."""
    raw = base64.b64decode(pem_b64)
    try:
        obj = x509.load_pem_x509_certificate(raw, default_backend())
    except ValueError:
        obj = x509.load_pem_x509_csr(raw, default_backend())
    cn_attrs = obj.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = cn_attrs[0].value if cn_attrs else None
    try:
        dns = list(obj.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        dns = []
    return cn, dns


def queue_if_approval_required(user, *, ca_id, template_id, cn, san_list,
                               request_type: str, request_data: dict,
                               comment: Optional[str] = None
                               ) -> Tuple[Optional[CertificatePolicy], Optional[ApprovalRequest]]:
    """``(policy, approval)`` when a policy requires approval for this
    request (queued), else ``(None, None)``. Administrators bypass, as on
    the issue form. Any evaluation error propagates: the caller must fail
    closed (never issue on a policy it could not evaluate)."""
    if getattr(user, 'role', None) == 'admin':
        return None, None
    policy = PolicyEvaluationService.check_approval_required(
        ca_id=ca_id, template_id=template_id, cn=cn, san_list=list(san_list or []))
    if policy is None:
        return None, None
    approval = PolicyEvaluationService.create_approval_request(
        policy=policy, request_data=request_data, requester_id=user.id,
        comment=comment, request_type=request_type)
    return policy, approval


def approval_payload(policy: CertificatePolicy, approval: ApprovalRequest) -> dict:
    """The response body the issue form returns when a request is queued."""
    return {
        'approval_required': True,
        'approval_id': approval.id,
        'policy_name': policy.name,
        'status': 'pending_approval',
        'message': f'Request requires approval per policy "{policy.name}"',
    }
