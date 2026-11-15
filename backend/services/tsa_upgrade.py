"""A 2.x TSA that signs with its CA certificate keeps doing so in 3.0.

One rule for migration 162 and the restore of a 2.x archive: the TSA is on (read as
``tsa_enabled_reads_on``), names a CA, has no dedicated signer and no
``tsa_require_dedicated_cert`` row 2.x read as true (``key_read_as_true``). The caller checks
that the CA exists.
"""

KEY = 'tsa_require_dedicated_cert'
READ = ('tsa_enabled', 'tsa_ca_refid', 'tsa_signer_cert_refid', KEY)


def tsa_enabled_reads_on(present: bool, value) -> bool:
    """The reading of 2.x and 3.0 alike: no row, or a value whose lower case is ``true``."""
    return not present or str(value).lower() == 'true'


def key_read_as_true(settings) -> bool:
    """2.x read the key as lower case ``true``; any other row, NULL included, was "no"."""
    return KEY in settings and str(settings[KEY]).lower() == 'true'


def ca_signer_refid_kept(settings):
    """The CA refid whose certificate signs the 2.x tokens, or None when the rule does not apply.
    A key row 2.x read as "no" counts as absent: 3.0 reads it as yes and must get ``false``."""
    if key_read_as_true(settings) or settings.get(KEY) == 'false':
        return None
    if not tsa_enabled_reads_on('tsa_enabled' in settings, settings.get('tsa_enabled')):
        return None
    if str(settings.get('tsa_signer_cert_refid') or '').strip():
        return None
    return str(settings.get('tsa_ca_refid') or '').strip() or None
