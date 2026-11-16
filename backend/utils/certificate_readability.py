"""Refusal of a certificate that loads but whose extensions cannot be read."""
from cryptography import x509


class UnreadableCertificate(ValueError):
    """The certificate's extensions cannot be read: the message names the defect."""


def require_readable_extensions(cert):
    """Raise UnreadableCertificate when *cert* repeats an extension (RFC 5280 4.2) or carries a malformed one."""
    try:
        cert.extensions
    except x509.DuplicateExtension as e:
        name = getattr(e.oid, '_name', None)
        label = f'{name} ({e.oid.dotted_string})' if name and name != 'Unknown OID' else e.oid.dotted_string
        raise UnreadableCertificate(
            f'The certificate cannot be imported: its {label} extension appears more than once '
            '(RFC 5280 section 4.2)') from e
    except Exception as e:  # noqa: BLE001  # ValueError, UnsupportedGeneralNameType: the extension does not decode
        raise UnreadableCertificate(
            'The certificate cannot be imported: one of its extensions is malformed') from e
    return cert


def stored_pem_refusal(encoded_crt):
    """The refusal of a base64-encoded PEM certificate (an OPNsense row) whose extensions cannot be read, else None."""
    import base64
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(encoded_crt or ''))
    except Exception:  # noqa: BLE001  # a certificate that does not load is not this check's to refuse
        return None
    try:
        require_readable_extensions(cert)
    except UnreadableCertificate as e:
        return str(e)
    return None
