"""Text written into the served sh and PowerShell scripts: data only ever lands as a literal."""
import re

# Every character a shell or PowerShell may read as the end of a line, and the other controls
_CONTROL = re.compile(r'[\x00-\x1f\x7f\x85  ]')


def has_control_character(text):
    return bool(_CONTROL.search(text or ''))


def one_line(text):
    """*text* with every control or line-break character turned into a space."""
    return _CONTROL.sub(' ', text or '')


def sh_literal(text):
    """A POSIX sh single-quoted word holding *text*, which sh expands in no way."""
    return "'" + one_line(text).replace("'", "'\\''") + "'"


def ps_literal(text):
    """A PowerShell string expression holding *text*: no variable, subexpression or escape.
    Pure ASCII, since Windows PowerShell reads a BOM-less script in the ANSI code page, where
    UTF-8 bytes can decode to a quote: each non-ASCII UTF-16 unit becomes [char]0xHHHH."""
    parts, run = [], []
    for c in one_line(text):
        if c.isascii():
            run.append("''" if c == "'" else c)
            continue
        if run or not parts:
            parts.append("'" + ''.join(run) + "'")
            run = []
        units = c.encode('utf-16-le', 'surrogatepass')
        parts.extend('[char]0x%04X' % int.from_bytes(units[k:k + 2], 'little') for k in range(0, len(units), 2))
    if not parts:
        return "'" + ''.join(run) + "'"
    if run:
        parts.append("'" + ''.join(run) + "'")
    return '(' + ' + '.join(parts) + ')'


def ps_help_comment(text):
    """*text* for one line of a <# #> block, which a #> inside would close."""
    return one_line(text).replace('#>', '# >')
