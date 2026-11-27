"""In a merge, a row revoked here stays revoked: the archive may only revoke more.

X.509 certificates and CAs keep theirs in restore_core (`_kept_revocation`, with the hold
rules). Every other table restored in a merge whose rows reach a final revoked state is here:
the state is read before the archive's columns are applied and put back after them.
"""
from typing import Any, Dict, Optional

# section: (is the row revoked here, columns that hold the revocation, values the revocation set)
KEPT_STATES = {
    # The KRL is rebuilt from these rows: a lifted one would leave it and sshd accept it again
    'ssh_certificates': (lambda row: bool(row.revoked),
                         ('revoked', 'revoked_at', 'revoke_reason'), {}),
    # revoke_host: renewals ended for good, the pending challenge dropped
    'ssh_hosts': (lambda row: row.revoked_at is not None, ('revoked_at',),
                  {'auto_renew': False, 'challenge': None, 'challenge_expires_at': None}),
    # cross_certs.revoke: no hold for a cross-certificate, and it is no longer served
    'ca_cross_certificates': (lambda row: bool(row.revoked),
                              ('revoked', 'revoked_at', 'revoke_reason'), {'served': False}),
    'api_keys': (lambda row: row.is_active is False, ('is_active',), {}),
    'auth_certificates': (lambda row: row.enabled is False, ('enabled',), {}),
    # RFC 8555 §7.3.6: a deactivated account is never reactivated; 'revoked' is the server's
    'acme_accounts': (lambda row: row.status in ('deactivated', 'revoked'), ('status',), {}),
    'acme_eab_credentials': (lambda row: row.status == 'revoked',
                             ('status', 'revoked_at', 'revoked_by_user_id'), {}),
    'acme_dns_update_keys': (lambda row: row.status == 'revoked', ('status', 'revoked_at'), {}),
}


def held_here(section_name: str, row: Any, merging: bool) -> Optional[Dict[str, Any]]:
    """The revoked state *row* holds here, to put back after a merge applies the archive."""
    entry = KEPT_STATES.get(section_name)
    if not merging or entry is None or row is None:
        return None
    revoked, columns, implied = entry
    if not revoked(row):
        return None
    return {**{column: getattr(row, column) for column in columns}, **implied}


def put_back(row: Any, held: Optional[Dict[str, Any]]) -> None:
    for column, value in (held or {}).items():
        setattr(row, column, value)
