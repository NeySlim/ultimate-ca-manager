"""Shared by every route that exports several certificates or CAs as PEM or P7B.

An unreadable or empty row is skipped, logged and named in the response; the others are exported.
"""
import base64
import logging

from cryptography import x509

from utils.response import error_response
from utils.trust_pem import certificate_blocks

logger = logging.getLogger(__name__)

SKIPPED_LIST_LIMIT = 100


def readable_pems(rows, what='certificate', load=x509.load_pem_x509_certificates, operation='Bulk export'):
    """``(pems, skipped)`` for *rows*, an iterable of ``(identifier, PEM text or its base64, or None)``.

    PEM text may follow other text (``openssl pkcs12`` attributes); base64 never holds a dash.
    Only the row's CERTIFICATE blocks are handed out, never a key or text stored with them.
    A row is readable when *load* accepts those blocks; *operation* names the caller in the log."""
    pems, skipped = [], []
    for ident, raw in rows:
        try:
            if not raw:
                raise ValueError('empty')
            pem = certificate_blocks(raw.encode() if isinstance(raw, str) and '-----BEGIN' in raw
                                     else base64.b64decode(raw))
            if not pem:
                raise ValueError('no certificate')
            load(pem)
        except Exception as exc:
            logger.warning('%s skips %s %s: unreadable (%s)', operation, what, ident, type(exc).__name__)
            skipped.append(str(ident))
            continue
        pems.append(pem)
    return pems, skipped


def skipped_headers(skipped, name='Certificates'):
    """``X-Skipped-<name>`` (first 100 identifiers) and its ``-Count`` (the total), or nothing."""
    if not skipped:
        return {}
    return {f'X-Skipped-{name}': ','.join(skipped[:SKIPPED_LIST_LIMIT]),
            f'X-Skipped-{name}-Count': str(len(skipped))}


def nothing_readable(skipped, what='certificate'):
    """The answer of a selection none of whose rows could be read, the same for PEM and P7B."""
    return error_response(f'No readable {what} to export', 404,
                          {'skipped': skipped[:SKIPPED_LIST_LIMIT], 'skipped_count': len(skipped)})
