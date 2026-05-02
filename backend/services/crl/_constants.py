from cryptography import x509

DEFAULT_VALIDITY_DAYS = 7

REASON_MAP = {
    'unspecified': x509.ReasonFlags.unspecified,
    'keyCompromise': x509.ReasonFlags.key_compromise,
    'CACompromise': x509.ReasonFlags.ca_compromise,
    'affiliationChanged': x509.ReasonFlags.affiliation_changed,
    'superseded': x509.ReasonFlags.superseded,
    'cessationOfOperation': x509.ReasonFlags.cessation_of_operation,
    'certificateHold': x509.ReasonFlags.certificate_hold,
    'removeFromCRL': x509.ReasonFlags.remove_from_crl,
    'privilegeWithdrawn': x509.ReasonFlags.privilege_withdrawn,
    'aACompromise': x509.ReasonFlags.aa_compromise,
}
