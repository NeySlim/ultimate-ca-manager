"""A 2.x TSA that signs with its CA certificate keeps doing so in 3.0.

One rule for migration 162 and the restore of a 2.x archive: the TSA is on (no
``tsa_enabled`` row, or exactly ``true``), names a CA, has no dedicated signer and no
``tsa_require_dedicated_cert`` row. The caller checks that the CA exists.
"""

KEY = 'tsa_require_dedicated_cert'
READ = ('tsa_enabled', 'tsa_ca_refid', 'tsa_signer_cert_refid', KEY)


def ca_signer_refid_kept(settings):
    """The CA refid whose certificate signs the 2.x tokens, or None when the rule does not apply."""
    if KEY in settings:
        return None
    enabled = settings.get('tsa_enabled')
    if enabled is not None and str(enabled).strip().lower() != 'true':
        return None
    if str(settings.get('tsa_signer_cert_refid') or '').strip():
        return None
    return str(settings.get('tsa_ca_refid') or '').strip() or None
