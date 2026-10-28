"""One bounded walk of the CA hierarchy, for every place that builds a chain.

Nothing in the schema forbids a loop: ``CA.caref`` holds the parent's
``refid`` as a plain string, with no foreign key, so a repaired or imported
hierarchy can point a CA at itself or at one of its own descendants. Every
consumer used to inline its own ``while ca:`` walk, and they did not agree on
what to do about it — some raised, some stopped, and several had no guard at
all and span forever on the same rows.

This module holds the walk once. Callers keep their own output format and
their own contract for a chain that cannot be completed:

- ``on_cycle='stop'`` / ``on_missing='stop'`` end the walk (the chain comes
  back short, which is what the export paths have always done);
- ``on_cycle='raise'`` / ``on_missing='raise'`` raise ``ValueError`` with the
  caller's own message, which is what the SCEP chain does.

The depth ceiling is the one ``CA.revoked_in_chain`` already enforces: a
hierarchy deeper than that is refused at issuance, so no chain this walk can
legitimately meet is longer.
"""

import base64
from typing import NamedTuple

MAX_CHAIN_DEPTH = 64
PRIMARY = 'primary'
AUTO = 'auto'


class ChainVariantError(ValueError):
    """A chain variant id that is malformed or not part of the chain asked for."""


class ChainLink(NamedTuple):
    """One certificate of a chain: the CA it belongs to, the cross-certificate row if it is one, its PEM."""
    ca: object
    cross: object
    pem: bytes


def walk_ca_chain(start, *, include_start=True, max_depth=MAX_CHAIN_DEPTH,
                  on_cycle='stop', on_missing='stop',
                  cycle_message='CA chain loops on itself',
                  missing_message='CA chain is incomplete'):
    """Yield *start* and then each parent resolved through ``caref``.

    Parameters
    ----------
    start:
        The CA to walk up from. ``None`` yields nothing (or raises, when
        ``on_missing='raise'``).
    include_start:
        ``False`` walks the ancestors only. *start* is still marked visited,
        so a parent pointing back at it counts as a loop.
    max_depth:
        Ceiling on the number of CAs visited, *start* included.
    on_cycle, on_missing:
        ``'stop'`` (default) or ``'raise'``.

    Yields
    ------
    CA
        Each CA of the chain, nearest first, at most once.
    """
    from models import CA

    if start is None:
        if on_missing == 'raise':
            raise ValueError(missing_message)
        return

    seen = set()
    ca = start
    depth = 0

    while ca is not None:
        refid = getattr(ca, 'refid', None)
        if refid is not None:
            if refid in seen:
                if on_cycle == 'raise':
                    raise ValueError(cycle_message)
                return
            seen.add(refid)

        depth += 1
        if depth > max_depth:
            if on_cycle == 'raise':
                raise ValueError(cycle_message)
            return

        if include_start or ca is not start:
            yield ca

        caref = getattr(ca, 'caref', None)
        if not caref:
            return

        parent = CA.query.filter_by(refid=caref).first()
        if parent is None:
            if on_missing == 'raise':
                raise ValueError(missing_message)
            return
        ca = parent


def parse_variant(value):
    """``'auto'``, ``'primary'`` or ``('cross', id)``; ChainVariantError for anything else."""
    if value is None or value == '':
        return AUTO
    if isinstance(value, str):
        if value in (AUTO, PRIMARY):
            return value
        head, _, tail = value.partition(':')
        if head == 'cross' and tail.isascii() and tail.isdigit():
            return ('cross', int(tail))
    raise ChainVariantError('Unknown chain variant: use auto, primary or cross:<id>')


def _cross_for(ca, wanted):
    """The cross-certificate of *ca* that variant *wanted* substitutes for it, or None."""
    from services.ca import cross_certs
    if wanted == PRIMARY:
        return None
    if wanted == AUTO:
        return cross_certs.served_for(ca)
    return next((row for row in ca.cross_certificates if row.id == wanted[1]), None)


def _issuer_pem(ca):
    return base64.b64decode(ca.crt) if ca.crt else b''


def issuer_chain(start, variant=AUTO, include_root=True, include_start=True, substitute_start=True):
    """The certificates presenting *start*'s chain, nearest first, as ``ChainLink`` entries.

    At most one CA's certificate is replaced by a cross-certificate of the same key; the
    chain then continues with the cross-certificate's issuer when it is held, else ends.
    ``auto`` replaces the CA nearest *start* that serves a valid cross-certificate;
    ``cross:<id>`` replaces its CA whatever the state of that row (it is the caller's explicit choice).
    ``substitute_start=False`` keeps *start*'s own certificate and applies the rule to the CAs above it.
    """
    from services.ca.cross_certs import issuer_of
    from models import CA

    wanted = parse_variant(variant)
    links, seen, substituted, ca = [], set(), False, start
    while ca is not None and len(seen) < MAX_CHAIN_DEPTH and ca.refid not in seen:
        seen.add(ca.refid)
        row = None if substituted or (ca is start and not substitute_start) else _cross_for(ca, wanted)
        if row is not None:
            substituted = True
            nxt = issuer_of(row)
            pem = base64.b64decode(row.crt)
        else:
            nxt = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None
            pem = _issuer_pem(ca)
        if pem and (include_start or ca is not start):
            links.append(ChainLink(ca, row, pem))
        ca = nxt
    if wanted not in (AUTO, PRIMARY) and not substituted:
        raise ChainVariantError(f'Chain variant cross:{wanted[1]} is not part of this chain')
    if not include_root and links:
        from cryptography import x509
        from utils.cert_issuer import is_self_signed
        try:
            if is_self_signed(x509.load_pem_x509_certificate(links[-1].pem)):
                links.pop()
        except Exception:
            pass
    return links


def anchor_chain(start):
    """The primary chain of *start* followed by the served cross-certificate of each of its CAs.

    For bags of trust anchors (EST ``/cacerts``): a cross-certificate is added, never substituted."""
    from services.ca import cross_certs
    links = issuer_chain(start, PRIMARY)
    extra = []
    for link in links:
        row = cross_certs.served_for(link.ca)
        if row is not None:
            extra.append(ChainLink(link.ca, row, base64.b64decode(row.crt)))
    return links + extra


def chain_variants(start):
    """Every chain *start* can present: ``primary`` plus one per cross-certificate on its path.

    Each entry: ``id`` (``primary`` / ``cross:<id>``), ``ca_id``, ``cross_certificate_id``,
    ``served``, ``servable`` and ``default`` (the one ``auto`` resolves to)."""
    variants = [{'id': PRIMARY, 'ca_id': getattr(start, 'id', None), 'cross_certificate_id': None,
                 'served': False, 'servable': True, 'default': False}]
    for ca in walk_ca_chain(start):
        for row in ca.cross_certificates:
            variants.append({'id': f'cross:{row.id}', 'ca_id': ca.id, 'cross_certificate_id': row.id,
                             'served': bool(row.served), 'servable': row.servable, 'default': False})
    chosen = next((link.cross.id for link in issuer_chain(start) if link.cross is not None), None)
    wanted = f'cross:{chosen}' if chosen is not None else PRIMARY
    for entry in variants:
        entry['default'] = entry['id'] == wanted
    return variants


def variant_ids(start):
    """The variant ids valid for *start*, ``auto`` included."""
    return [AUTO] + [v['id'] for v in chain_variants(start)]


__all__ = ['AUTO', 'PRIMARY', 'MAX_CHAIN_DEPTH', 'ChainLink', 'ChainVariantError', 'anchor_chain',
           'chain_variants',
           'issuer_chain', 'parse_variant', 'variant_ids', 'walk_ca_chain']
