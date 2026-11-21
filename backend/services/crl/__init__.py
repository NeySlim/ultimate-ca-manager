from ._constants import REASON_MAP, DEFAULT_VALIDITY_DAYS
from .query import CRLQueryMixin
from .generation import CRLGenerationMixin, CRLSigningKeyMismatch
from .management import CRLManagementMixin
from .external import ExternalCRLMixin, ExternalCRLConflict


class CRLService(CRLQueryMixin, CRLGenerationMixin, CRLManagementMixin, ExternalCRLMixin):
    DEFAULT_VALIDITY_DAYS = DEFAULT_VALIDITY_DAYS


__all__ = ['CRLService', 'CRLSigningKeyMismatch', 'ExternalCRLConflict']
