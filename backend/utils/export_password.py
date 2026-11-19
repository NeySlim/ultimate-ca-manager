"""The rule for a password that encrypts an export, in one place.

Six routes hand out an encrypted bundle and each had invented its own rule:
presence only for a certificate's PKCS#12, PFX and JKS; 4 to 256 for a CA's;
8 with three different wordings for the user-certificate, mTLS and
key-recovery routes; presence only again for the converter tool.

The dialog that drives most of them, `components/ExportModal.jsx`, refused
under 8 and knew of no ceiling, so it was stricter than the server on one
route and more permissive on another at the same time. Stricter is a feature
a user cannot reach; more permissive is a refusal they cannot explain. Only
the first can hide something, and it did: a script could encrypt a PKCS#12
with a one-character password through a route the dialog would never send.

* **8** is the floor, because the dialog and half the routes already
  required it, and because a bundle carrying a private key is exactly what a
  brute-force is for.
* **256** is the ceiling, and it is the one bound anybody wrote a reason
  for: `BestAvailableEncryption` and pyjks degrade sharply past a few
  hundred bytes.

An **empty** password is not a short one. On a private-key export it means
"hand it to me unencrypted", which is a deliberate answer; callers that
allow it pass ``allow_empty=True``, and every other caller refuses it.
"""
from typing import Optional

EXPORT_PASSWORD_MIN_LENGTH = 8
EXPORT_PASSWORD_MAX_LENGTH = 256
# A password that does not encode, or whose UTF-8 form is past this, breaks the encryption libraries.
EXPORT_PASSWORD_MAX_BYTES = 1023


def export_password_policy() -> dict:
    """What `GET /api/v2/export/password-policy` publishes."""
    return {
        'min_length': EXPORT_PASSWORD_MIN_LENGTH,
        'max_length': EXPORT_PASSWORD_MAX_LENGTH,
    }


def export_password_message() -> str:
    return (
        f'Export password must be between {EXPORT_PASSWORD_MIN_LENGTH} and '
        f'{EXPORT_PASSWORD_MAX_LENGTH} characters')


def validate_export_password(password, *, allow_empty: bool = False) -> Optional[str]:
    """Error string for *password*, or None when it may be used.

    ``allow_empty`` is for the private-key exports where no password means
    no encryption.
    """
    if password is None or password == '':
        if allow_empty:
            return None
        return 'Password required for this export format'
    if not isinstance(password, str):
        return 'password must be a string'
    if not (EXPORT_PASSWORD_MIN_LENGTH <= len(password)
            <= EXPORT_PASSWORD_MAX_LENGTH):
        return export_password_message()
    try:
        if len(password.encode('utf-8')) > EXPORT_PASSWORD_MAX_BYTES:
            return f'Export password must be at most {EXPORT_PASSWORD_MAX_BYTES} bytes in UTF-8'
    except UnicodeEncodeError:
        return 'Export password must be valid Unicode text'
    return None
