from ._constants import REASON_MAP, DEFAULT_VALIDITY_DAYS
from .query import CRLQueryMixin
from .generation import CRLGenerationMixin
from .management import CRLManagementMixin


class CRLService(CRLQueryMixin, CRLGenerationMixin, CRLManagementMixin):
    DEFAULT_VALIDITY_DAYS = DEFAULT_VALIDITY_DAYS


__all__ = ['CRLService']
