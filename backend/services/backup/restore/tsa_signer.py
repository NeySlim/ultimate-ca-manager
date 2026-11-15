"""A 2.x archive whose TSA signs with its CA certificate keeps doing so once restored.

The same rule as migration 162 (services.tsa_upgrade), applied to the archived settings before
the plan is built: the explicit ``tsa_require_dedicated_cert = false`` joins them.
"""
from services.tsa_upgrade import KEY, ca_signer_refid_kept

PROFILES = 'windows_enrollment_profiles'


def _ca_known(backup_data, refid) -> bool:
    rows = backup_data.get('certificate_authorities')
    if isinstance(rows, list) and any(isinstance(r, dict) and r.get('refid') == refid for r in rows):
        return True
    from models import CA
    return CA.query.filter_by(refid=refid).first() is not None


def upgrade_archived_tsa_signer(backup_data) -> bool:
    """Write the compatibility setting into a 2.x archive; True when it did. Before the Windows
    profile conversion, which adds the section that marks a 3.0 archive."""
    if PROFILES in backup_data:
        return False
    configuration = backup_data.get('configuration')
    settings = configuration.get('settings') if isinstance(configuration, dict) else None
    if not isinstance(settings, dict):
        return False
    refid = ca_signer_refid_kept(settings)
    if not refid or not _ca_known(backup_data, refid):
        return False
    settings[KEY] = 'false'
    return True
