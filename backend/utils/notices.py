"""What the server decided differently from what was asked, said out loud.

A request that is neither refused nor honoured as written is the one case a
caller cannot see: the answer is a 200 or a 201, and the difference only shows
up later, in the expiry date of a certificate somebody is relying on. These
notices travel in the response ``meta.notices`` so the interface can show them
next to the result, and read the same way in a log.

They are not errors. A refusal goes through ``error_response``; a notice says
the thing was done, and on what terms.
"""
from __future__ import annotations

from typing import List, Optional


def validity_shortened(requested_days: int, granted_days: int,
                       reason: str) -> str:
    """The certificate was issued for less than the caller asked for."""
    return (f'Issued for {granted_days} day(s) instead of the '
            f'{requested_days} requested: {reason}.')


def policy_validity_reason(policy_name: str, max_days: int) -> str:
    """Why a policy shortened it."""
    return f'policy "{policy_name}" caps validity at {max_days} day(s)'


def issuer_expiry_reason(not_after) -> str:
    """Why the issuing CA shortened it."""
    return (f'the issuing CA certificate expires on '
            f'{not_after.strftime("%Y-%m-%d")} and no certificate may outlive it')


def collect(*notices) -> List[str]:
    """The notices that are actually there, in order, without blanks; a list
    among them (policy advisories) is spread."""
    out = []
    for n in notices:
        out += [x for x in n if x] if isinstance(n, (list, tuple)) else [n] if n else []
    return out


def meta_with_notices(notices, meta: Optional[dict] = None) -> Optional[dict]:
    """``meta`` carrying *notices*, or the meta unchanged when there are none."""
    kept = [n for n in (notices or []) if n]
    if not kept:
        return meta
    out = dict(meta or {})
    out['notices'] = kept
    return out


__all__ = [
    'validity_shortened',
    'policy_validity_reason',
    'issuer_expiry_reason',
    'collect',
    'meta_with_notices',
]
