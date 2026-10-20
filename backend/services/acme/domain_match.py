"""Which registered entry covers a domain.

Two tables map a domain to what should issue for it: ``acme_local_domains``
for the internal ACME server, ``acme_domains`` for DNS-provider issuance.
Both accept a wildcard spelling on the way in, and neither could ever find one
again: the lookup stripped the wildcard from the domain it was asked about and
then compared the result to the stored text, so an entry registered as
``*.custom`` matched nothing at all, not even ``*.custom`` itself, and every
order for that zone fell through to the default CA (#352).

The two halves disagreed rather than one of them being wrong: the validator
accepts ``*.local`` on purpose, so the lookup is what has to understand it.
"""
import string
from typing import List, Optional

_WILDCARD = '*.'
_LABEL_CHARS = frozenset(string.ascii_letters + string.digits + '-')


def is_valid_entry(domain: Optional[str], *, allow_single_label: bool) -> bool:
    """Whether ``domain`` is a well-formed entry for one of the two tables.

    Accepts a domain, a subdomain, and a single leading wildcard label.

    ``allow_single_label`` is the only axis between the two tables, and it is
    the local one that sets it: a bare private TLD ("local", "internal") is a
    registrable entry there, so that ``find``'s parent-walking covers every
    name under it (#290). The DNS-provider table has no such case -- a zone it
    can answer a challenge in is one a provider hosts -- so it refuses them.
    """
    if not isinstance(domain, str) or not domain:
        return False
    body = domain[len(_WILDCARD):] if domain.startswith(_WILDCARD) else domain
    labels = body.split('.')
    if len(labels) < (1 if allow_single_label else 2):
        return False
    if not all(_is_label(label) for label in labels):
        return False
    # A numeric or one-letter last label is no TLD that can ever exist.
    top = labels[-1]
    return len(top) >= 2 and top.isalpha()


def _is_label(label: str) -> bool:
    """An LDH label: 1 to 63 ASCII letters, digits or hyphens, no hyphen at either end."""
    return (0 < len(label) <= 63
            and all(char in _LABEL_CHARS for char in label)
            and label[0] != '-' and label[-1] != '-')


def normalize(domain: Optional[str]) -> str:
    """The bare form of a domain: lower-case, no wildcard label, no trailing dot.

    Used on the way in as well as on the way out, so that ``custom`` and
    ``*.custom`` cannot be registered as two entries fighting over the same
    zone.
    """
    if not domain:
        return ''
    bare = domain.strip().lower()
    if bare.startswith(_WILDCARD):
        bare = bare[len(_WILDCARD):]
    bare = bare.rstrip('.')
    # A star anywhere else is not a zone this can reason about, and turning
    # it into a candidate would let it match by accident.
    if '*' in bare:
        return ''
    return bare


def candidates(domain: Optional[str]) -> List[str]:
    """Every stored spelling that covers ``domain``, most specific first.

    An entry covers itself and everything under it, which is how the
    parent-walking has always worked. ``*.X`` is read as naming the same zone
    as ``X`` rather than as a stricter form of it: an operator who registered
    ``*.custom`` to say "this CA signs for custom" has no second entry to
    cover the apex with, since the two spellings are the same entry, and
    sending it to the default CA is the surprise this module exists to remove.
    """
    bare = normalize(domain)
    if not bare:
        return []

    parts = bare.split('.')
    ordered: List[str] = []
    for index in range(len(parts)):
        level = '.'.join(parts[index:])
        ordered.append(level)
        ordered.append(_WILDCARD + level)
    return ordered


def find(model, domain: Optional[str]):
    """Return the most specific row of ``model`` covering ``domain``, or None.

    One query rather than one per level: the rows are fetched together and
    ranked here, so a deep name does not cost a round trip per label.
    """
    wanted = candidates(domain)
    if not wanted:
        return None

    rows = model.query.filter(model.domain.in_(wanted)).all()
    if not rows:
        return None

    rank = {name: position for position, name in enumerate(wanted)}
    return min(rows, key=lambda row: rank.get((row.domain or '').lower(),
                                              len(wanted)))


def wildcard_refused(identifiers) -> List[str]:
    """Wildcard identifiers whose ``acme_domains`` entry has "Allow wildcard" off."""
    from models.acme_models import AcmeDomain

    refused = []
    for identifier in identifiers or []:
        value = identifier.get('value') if isinstance(identifier, dict) else None
        if not isinstance(value, str) or not value.startswith(_WILDCARD):
            continue
        entry = find(AcmeDomain, value)
        if entry is not None and entry.is_wildcard_allowed is False:
            refused.append(value)
    return refused
