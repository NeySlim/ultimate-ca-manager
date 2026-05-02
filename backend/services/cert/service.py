"""CertificateService — aggregates all cert operation mixins"""
from .mixins.lifecycle import LifecycleMixin
from .mixins.csr import CSRMixin
from .mixins.import_export import ImportExportMixin
from .mixins.inspection import InspectionMixin
from .mixins.query import QueryMixin


class CertificateService(LifecycleMixin, CSRMixin, ImportExportMixin, InspectionMixin, QueryMixin):
    """Service for Certificate operations"""
