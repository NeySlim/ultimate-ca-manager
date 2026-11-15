## [2.254.1] - 2026-11-14

### Security

- Account: disabling 2FA or regenerating recovery codes now counts its TOTP or recovery code against the login's second-factor lockout, so a stolen session can no longer guess the code without limit; past `max_login_attempts` both answer 429 and the account's next login waits for the lock to expire. `POST /api/v2/account/2fa/confirm` answers 409 once TOTP is enabled, instead of checking a code and issuing new recovery codes.
- Dependencies: dnspython 2.9.2, which bounds the services of a WKS record (CVE-2026-128089). UCM parses record text only for TXT values it computes, so no UCM path was exposed.

## [2.254] - 2026-11-13

### Fixed

- CA import: an imported CA is linked at once to the stored CA whose key signed it (CA import, certificate import, OPNsense and smart import, whatever the order of a batch), so SCEP `GetCACert` in chain mode serves the chain without waiting for the hourly repair. Smart import prefers that CA over a same-name one, and still links by name when no stored CA verifies the signature.
- Kerberos: a Kerberos Microsoft CA connection pointed `KRB5_KTNAME` at its own keytab for the whole process, so XCEP and WSTEP could then accept with the wrong keys; it now sets its client keytab only.
- ACME: `revoke-cert` with reason 8 (removeFromCRL, a delta CRL entry only) is refused with `badRevocationReason`, on the server and the proxy, which also answered `malformed` for any invalid reason.
- Backup: a revocation record archived under a hexadecimal spelling of its serial (`0x`, colons) is restored in a spelling the CRL reads, and two spellings of one serial in an archive both stay, the gravest reason answering.
- WSTEP, EST and SCEP: a renewed certificate keeps the SID security extension (KB5014754 strong mapping) of the certificate it renews when the CA signed that certificate, never one from the CSR, so it still maps to its account on a domain controller enforcing strong mapping; with the AD Connector enabled, a SID that names no account is refused.
- Packages: the DEB installation no longer fails on a host without sudo; the unused sudoers file is no longer written and is removed from both the DEB and the RPM.

### Security

- Backup: a merge restore no longer turns a certificate or a CA revoked for good here back into a hold or a valid one, nor its revocation record into a hold.
- Certificates: an imported certificate is now linked to a CA only when that CA's signature on it verifies, and renewal, re-enrolment and status checks only treat as issued by a CA a stored certificate it signed.
- OCSP: a serial the CA revoked answers `revoked`, as on its CRL, even when a non-revoked record of that serial is stored again.
- Certificates: a certificate imported again after its revocation and deletion comes back revoked, and a certificate its CA's revocation record names is no longer renewed in place.
- Revocation: a certificate its CA recorded as revoked is now shown and treated as revoked everywhere, and an hourly pass marks such certificates revoked, with an audit entry.
- Revocation: when a final revocation is recorded, on the certificate or on its CA's record, lifting a hold is refused with one code (409) and one message; otherwise it removes the hold's record in each unambiguous spelling of its serial and under every record of the CA key.
- Revocation: revoking or suspending a certificate its CA already recorded as revoked for good answers that it is already revoked; a recorded hold can still be made final.
- Revocation: the upgrade deletes once the suspension records that lifting a hold used to leave behind.
- Revocation: a hold its CA recorded but the certificate does not show yet can be lifted, and the certificate details and list show the revocation the CA recorded.
- Backup: restored certificates take the revocation their CA recorded at once, with an audit entry, and an archive from a release before 2.254 no longer brings back as holds the records a lifted hold left behind (the restore result counts them).
- mTLS: an administrator importing a certificate for a user can no longer enrol a revoked certificate.
- Renewal: a certificate whose signature no longer verifies with its CA's current key (CA re-keyed or replaced under the same name) is refused with a message asking for a new certificate.

## [2.253] - 2026-11-11

### Fixed

- Certificate Transparency: `POST /api/v2/certificates/<id>/submit-ct` always failed with a server error, as it read an attribute the certificate model does not have, and the chain it built stopped at the direct issuer; the submission now sends the leaf with its full issuer chain up to the root, or the chain stored inline with the certificate, one element per certificate (RFC 6962 §4.1). Reported by Chris by e-mail.
- Users: deleting a user, alone or in bulk, dropped its mTLS enrolments without revoking their certificates, which stayed valid for anything else trusting the CA; each is now revoked (cessationOfOperation) and deleted as when removing the enrolment, and a certificate that cannot be revoked no longer blocks the deletion but is named in the answer and the audit log.
- mTLS: the self-service routes that list, assign and enrol a user's own certificates relied on the username alone; a certificate recorded before the current account was created is no longer treated as its own, and an administrator can still assign it.
- Sessions: a session is now bound to the account it was opened for, not only to its id, so it no longer outlives that account on SQLite; sessions opened before the update stay open, but a login waiting on its second factor at the update has to enter the password again.
- Import: re-importing a certificate under a new serial updated the stored one but left its deploy bindings idle; it now counts as a renewal and queues them, while re-importing the same serial stays silent (discussion #440).

