"""In a merge, a row revoked here stays revoked: the archive may only revoke more.

X.509 certificates and CAs keep theirs in restore_core (`_kept_revocation`, with the hold
rules). Every other table restored in a merge whose rows reach a final state is here: the
state is read before the archive's columns are applied and put back after them.
"""
from typing import Any, Dict, Optional

# section: columns of the state here kept when the archive's state outranks it (revoked > used)
_OUTRANKED = {
    'acme_eab_credentials': (lambda here, archive: here == 'used' and archive == 'revoked',
                             ('used_at', 'used_by_account_id')),
}

# section: (is the row in a final state here, columns that hold it, values that state implies)
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
    # Single-use: a credential consumed here never registers a second account
    'acme_eab_credentials': (lambda row: row.status in ('used', 'revoked'),
                             ('status', 'used_at', 'used_by_account_id', 'revoked_at',
                              'revoked_by_user_id'), {}),
    'acme_dns_update_keys': (lambda row: row.status == 'revoked', ('status', 'revoked_at'), {}),
    # A recovered key is handed out once: an 'approved' archive row would hand it out again
    'key_recovery_requests': (lambda row: row.status in ('recovered', 'rejected', 'cancelled'),
                              ('status', 'decided_by', 'decided_at', 'decision_note',
                               'recovered_by', 'recovered_at'), {}),
    # A request refused, expired or cancelled here never goes back to pending (approved is not kept)
    'approval_requests': (lambda row: row.status in ('rejected', 'expired', 'cancelled'),
                          ('status', 'resolved_at', 'approvals'), {}),
    'scep_requests': (lambda row: row.status == 'rejected',
                      ('status', 'rejection_reason', 'approved_by', 'approved_at'), {}),
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


def put_back(section_name: str, row: Any, held: Optional[Dict[str, Any]]) -> None:
    """Write the state held here back, but for what an outranking archive state replaces."""
    rule = _OUTRANKED.get(section_name)
    if held and rule is not None and rule[0](held.get('status'), getattr(row, 'status', None)):
        held = {column: held[column] for column in rule[1]}
    for column, value in (held or {}).items():
        setattr(row, column, value)
