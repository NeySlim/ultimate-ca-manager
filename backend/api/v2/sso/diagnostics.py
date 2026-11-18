"""What an SSO sign-in refused for want of a role tells the administrator.

The group values read, where they were read from and, when none was, the NAMES of what
the IdP sent that may carry them. Nothing else of a token, assertion or directory entry:
these texts go to the server log and the audit log, never to the person signing in.
"""
from dataclasses import dataclass, field

MAX_VALUES = 20
VALUE_LENGTH = 64
MAX_NAMES = 20
NAME_LENGTH = 128
REMEDY = 'add a role mapping rule for one of these values, or set a default role'
MAP_HINT = 'map one of them to groups in the attribute mapping'
_GROUP_WORDS = ('group', 'role', 'member')
# Claims that are lists by definition and never carry groups (RFC 7519 §4.1.3; OIDC
# Core §2 and §5.6.2: aggregated and distributed claims).
_NOT_GROUP_CLAIMS = frozenset({'aud', 'amr', '_claim_names', '_claim_sources'})
_CLAIM_DEPTH = 3


@dataclass
class GroupSource:
    """Where the groups of a sign-in were looked for, and the names the IdP sent
    that may carry them; ``candidates`` is ``None`` for LDAP and for OIDC or SAML
    once group values were read."""
    label: str
    candidates: list = field(default=None)
    kind: str = 'attributes'


def shown(value, limit=VALUE_LENGTH):
    """``value`` cut to ``limit`` characters with an ellipsis, then quoted by ``repr``,
    which escapes every non-printable character: one log line, the exact value."""
    text = str(value)
    if len(text) > limit:
        text = text[:limit - 1] + '…'
    return repr(text)


def shown_list(values, count=MAX_VALUES, limit=VALUE_LENGTH):
    values = list(values)
    text = ', '.join(shown(v, limit) for v in values[:count])
    if len(values) > count:
        text += f' (+{len(values) - count} more)'
    return text


def _group_like(name):
    lowered = str(name).casefold()
    return any(word in lowered for word in _GROUP_WORDS)


def claim_candidates(*claim_sets, exclude=()):
    """Dotted names of the claims that hold a list or whose name speaks of groups,
    roles or members, through nested objects, but those in ``exclude`` (already read);
    values are never returned."""
    names = {}

    def walk(data, prefix, depth):
        for key, value in data.items():
            if not isinstance(key, str) or (not prefix and key in _NOT_GROUP_CLAIMS):
                continue
            name = f'{prefix}{key}'
            if isinstance(value, dict):
                if depth < _CLAIM_DEPTH:
                    walk(value, f'{name}.', depth + 1)
            elif isinstance(value, list) or _group_like(key):
                names[name] = None

    for claims in claim_sets:
        if isinstance(claims, dict):
            walk(claims, '', 1)
    return [name for name in names if name not in exclude]


def saml_candidates(attrs, friendly_names=None, exclude=()):
    """SAML attribute Names with several values or a group-like Name or FriendlyName,
    the FriendlyName shown in parentheses: it only helps find the Name (SAML Core
    §2.7.3.1 forbids identifying an attribute by it)."""
    friendly_names = friendly_names if isinstance(friendly_names, dict) else {}
    names = []
    for name, values in (attrs if isinstance(attrs, dict) else {}).items():
        if name in exclude:
            continue
        friendly = friendly_names.get(name)
        friendly = friendly if isinstance(friendly, str) and friendly and friendly != name else None
        several = isinstance(values, (list, tuple)) and len(values) > 1
        if several or _group_like(name) or (friendly and _group_like(friendly)):
            names.append(f'{name} ({friendly})' if friendly else str(name))
    return names


def refusal_diagnosis(values, source):
    """What was read and from where, the names to map when nothing was, and the remedy."""
    parts = []
    if values:
        parts.append(f'groups read from {source.label}: {shown_list(values)}')
    else:
        parts.append(f'no group value was read from {source.label}')
        if source.candidates:
            parts.append(f'received {source.kind} that may carry groups: '
                         f'{shown_list(source.candidates, MAX_NAMES, NAME_LENGTH)}: {MAP_HINT}')
        elif source.candidates is not None:
            parts.append(f'no received {source.kind[:-1]} looks like a group list')
    parts.append(REMEDY)
    return '; '.join(parts)
