"""Common name pattern of a Windows enrollment template: fixed text and directory variables.

The values come from the requester's directory object, never from the request; each
variable's value fills one CN RDN as text, so its commas or equals signs add no RDN.
"""
import unicodedata

USER_VARIABLES = ('username', 'upn', 'mail', 'displayName', 'givenName', 'surname')
MACHINE_VARIABLES = ('hostname', 'fqdn')
COMMON_VARIABLES = ('domain', 'realm')
# Not unique in a directory: the editor warns when they are added to a unique variable
NON_UNIQUE_VARIABLES = ('displayName', 'givenName', 'surname', 'mail')
# RFC 5280 4.1.2.6: one subject per entity of a CA. Unique across domains on their own, or
# unique within a domain and so needing {domain} or the directory path beside them
UNIQUE_VARIABLES = {'machine': 'fqdn', 'directory': 'upn'}
DOMAIN_UNIQUE_VARIABLES = {'machine': 'hostname', 'directory': 'username'}
# RFC 5280 appendix A: ub-common-name
MAX_COMMON_NAME = 64
MAX_PATTERN_LENGTH = 255


class PatternError(ValueError):
    """The pattern does not parse; the message names the offending part."""


def parse(pattern):
    """The pattern as a list of literal strings and ``('var', name)`` tuples; ``{{`` and
    ``}}`` stand for literal braces. Raises :class:`PatternError`."""
    parts, literal, i, n = [], [], 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c in '{}' and pattern[i:i + 2] == c * 2:
            literal.append(c)
            i += 2
            continue
        if c == '}':
            raise PatternError("A lone '}' in the common name pattern must be written '}}'")
        if c == '{':
            end = pattern.find('}', i + 1)
            if end < 0:
                raise PatternError("A '{' in the common name pattern is never closed; write '{{' for a brace")
            name = pattern[i + 1:end]
            if not name or '{' in name:
                raise PatternError("A '{' in the common name pattern names no variable; write '{{' for a brace")
            if literal:
                parts.append(''.join(literal))
                literal = []
            parts.append(('var', name))
            i = end + 1
            continue
        literal.append(c)
        i += 1
    if literal:
        parts.append(''.join(literal))
    return parts


def variables(pattern):
    return [p[1] for p in parse(pattern) if isinstance(p, tuple)]


def allowed_variables(kind):
    """The variables a template of ``kind`` ('machine' or 'directory') may use."""
    own = MACHINE_VARIABLES if kind == 'machine' else USER_VARIABLES
    return own + COMMON_VARIABLES


def validation_error(pattern, kind, keep_path=False):
    """Why ``pattern`` cannot be saved on a template whose subject source is ``kind``
    ('machine', 'directory' or 'request'), with ``keep_path`` the directory path option, else None."""
    if not pattern:
        return None
    if len(pattern) > MAX_PATTERN_LENGTH:
        return f'The common name pattern is longer than {MAX_PATTERN_LENGTH} characters'
    if any(unicodedata.category(c) == 'Cc' for c in pattern):
        return 'The common name pattern contains a control character'
    if kind == 'request':
        return ('A common name pattern needs a template whose subject the CA builds: a computer '
                'template, or a user template with "Build subject from Active Directory" on')
    try:
        names = variables(pattern)
    except PatternError as e:
        return str(e)
    allowed = allowed_variables(kind)
    for name in names:
        if name in allowed:
            continue
        if name in USER_VARIABLES + MACHINE_VARIABLES:
            other = 'user' if name in USER_VARIABLES else 'computer'
            this = 'computer' if kind == 'machine' else 'user'
            return f'Variable {{{name}}} is for {other} templates; this is a {this} template'
        return f'Unknown variable {{{name}}} in the common name pattern'
    unique, in_domain = UNIQUE_VARIABLES[kind], DOMAIN_UNIQUE_VARIABLES[kind]
    if unique in names or (in_domain in names and (keep_path or 'domain' in names)):
        return None
    who = 'computers' if kind == 'machine' else 'users'
    return (f'The common name pattern does not tell {who} apart (RFC 5280 \u00a74.1.2.6): it needs '
            f'{{{unique}}}, or {{{in_domain}}} with {{domain}} or "Keep the directory path"')


def domain_of_dn(dn_components):
    """The DNS name of the domain from the DC components of an object's DN, or None."""
    labels = [value for attr, value in dn_components if attr.upper() == 'DC' and value]
    return '.'.join(labels) or None


def render(pattern, values):
    """``(common_name, None)``, or ``(None, refusal)`` naming the variable that has no value
    or why the result cannot be a common name. Nothing is truncated or dropped."""
    out = []
    for part in parse(pattern):
        if isinstance(part, tuple):
            value = values.get(part[1])
            if not value or not str(value).strip():
                return None, f'{{{part[1]}}} has no value in the directory for the requester'
            out.append(str(value))
        else:
            out.append(part)
    result = ''.join(out)
    if not result.strip():
        return None, 'the result is empty'
    if any(unicodedata.category(c) == 'Cc' for c in result):
        return None, 'the result contains a control character'
    if len(result) > MAX_COMMON_NAME:
        return None, f'the result is longer than {MAX_COMMON_NAME} characters'
    return result, None


def template_error(template_type, ad_derived_subject, pattern, keep_path=False):
    """``validation_error`` for a template of these settings, as WSTEP would serve it."""
    from types import SimpleNamespace
    from services.wstep.wstep_service import _subject_source
    kind = _subject_source(SimpleNamespace(template_type=template_type,
                                           ad_derived_subject=bool(ad_derived_subject),
                                           subject_cn_pattern=pattern))
    return validation_error(pattern, kind, keep_path=bool(keep_path))
