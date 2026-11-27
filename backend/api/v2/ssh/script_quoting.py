"""Text written into the served sh and PowerShell scripts: data only ever lands as a literal."""
import re

# Every character a shell or PowerShell may read as the end of a line, and the other controls
_CONTROL = re.compile(r'[\x00-\x1f\x7f\x85  ]')
# PowerShell closes a single-quoted string on any of these; doubling one keeps it literal
_PS_SINGLE_QUOTES = "'‘’‚‛"


def has_control_character(text):
    return bool(_CONTROL.search(text or ''))


def one_line(text):
    """*text* with every control or line-break character turned into a space."""
    return _CONTROL.sub(' ', text or '')


def sh_literal(text):
    """A POSIX sh single-quoted word holding *text*, which sh expands in no way."""
    return "'" + one_line(text).replace("'", "'\\''") + "'"


def ps_literal(text):
    """A PowerShell single-quoted string holding *text*: no variable, subexpression or escape."""
    return "'" + ''.join(c * 2 if c in _PS_SINGLE_QUOTES else c for c in one_line(text)) + "'"


def ps_help_comment(text):
    """*text* for one line of a <# #> block, which a #> inside would close."""
    return one_line(text).replace('#>', '# >')
