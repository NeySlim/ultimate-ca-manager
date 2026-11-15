"""Reading GitHub workflows in tests: YAML loading and a small evaluator of `${{ }}` expressions.

The evaluator covers the subset the workflows use (contexts, literals, ==, !=, !, &&, ||, parentheses,
startsWith, endsWith, contains and the status functions); anything else raises, never guesses.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / '.github' / 'workflows'


def load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def triggers(workflow):
    # PyYAML reads the bare key `on` as the boolean True
    return workflow.get('on', workflow.get(True))


_TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>\d+(?:\.\d+)?)|(?P<op>==|!=|&&|\|\||[!().,\[\]])"
                    r"|(?P<name>[A-Za-z_][\w-]*))")


def _tokens(text):
    out, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f'cannot read expression at {text[pos:]!r}')
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
    return out


def _truthy(v):
    return v not in (None, False, 0, '') and v == v


def _eq(a, b):
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


def _contains(hay, needle):
    if isinstance(hay, (list, tuple)):
        return any(_eq(x, needle) for x in hay)
    return str(needle).lower() in str(hay or '').lower()


_FUNCS = {
    'startswith': lambda s, p: str(s or '').lower().startswith(str(p).lower()),
    'endswith': lambda s, p: str(s or '').lower().endswith(str(p).lower()),
    'contains': _contains,
}


class _Parser:
    def __init__(self, text, context, status):
        self.toks = _tokens(text)
        self.i = 0
        self.ctx = context
        self.status = status

    def peek(self):
        return self.toks[self.i][1] if self.i < len(self.toks) else None

    def take(self, want=None):
        tok = self.toks[self.i]
        if want is not None and tok[1] != want:
            raise ValueError(f'expected {want!r}, got {tok[1]!r}')
        self.i += 1
        return tok

    def parse(self):
        value = self.or_()
        if self.i != len(self.toks):
            raise ValueError(f'trailing tokens: {self.toks[self.i:]}')
        return value

    def or_(self):
        value = self.and_()
        while self.peek() == '||':
            self.take()
            right = self.and_()
            value = value if _truthy(value) else right
        return value

    def and_(self):
        value = self.unary()
        while self.peek() == '&&':
            self.take()
            right = self.unary()
            value = right if _truthy(value) else value
        return value

    def unary(self):
        if self.peek() == '!':
            self.take()
            return not _truthy(self.unary())
        left = self.primary()
        if self.peek() in ('==', '!='):
            op = self.take()[1]
            right = self.primary()
            return _eq(left, right) if op == '==' else not _eq(left, right)
        return left

    def primary(self):
        kind, text = self.take()
        if text == '(':
            value = self.or_()
            self.take(')')
            return value
        if kind == 'str':
            return text[1:-1].replace("''", "'")
        if kind == 'num':
            return float(text)
        if kind != 'name':
            raise ValueError(f'unexpected {text!r}')
        if text in ('true', 'false', 'null'):
            return {'true': True, 'false': False, 'null': None}[text]
        if self.peek() == '(':
            self.take()
            args = []
            while self.peek() != ')':
                args.append(self.or_())
                if self.peek() == ',':
                    self.take()
            self.take(')')
            name = text.lower()
            if name in ('success', 'failure', 'cancelled', 'always'):
                return {'always': True}.get(name, self.status == name)
            if name not in _FUNCS:
                raise ValueError(f'unsupported function {text}')
            return _FUNCS[name](*args)
        if text not in self.ctx:
            raise ValueError(f'unknown context {text}')
        value = self.ctx[text]
        while self.peek() in ('.', '['):
            if self.take()[1] == '.':
                key = self.take()[1]
            else:
                key = self.or_()
                self.take(']')
            value = value.get(key) if isinstance(value, dict) else None
        return value


def evaluate(expr, context, status='success'):
    """Value of a workflow expression, bare (`if:`) or wrapped in one `${{ }}`."""
    text = str(expr).strip()
    m = re.fullmatch(r'\$\{\{(.*)\}\}', text, re.S)
    if m:
        text = m.group(1)
    elif '${{' in text:
        raise ValueError(f'mixed text and expression: {text!r}')
    return _Parser(text, context, status).parse()


def render(text, context):
    """A string with each `${{ }}` replaced by its value, as GitHub interpolates `with:` and `env:`."""
    def one(m):
        value = _Parser(m.group(1), context, 'success').parse()
        return '' if value is None else str(value).lower() if isinstance(value, bool) else str(value)
    return re.sub(r'\$\{\{(.*?)\}\}', one, str(text), flags=re.S)


def github_context(event_name, ref, **extra):
    """The `github` context of a run for `event_name` on `ref` (refs/heads/x or refs/tags/x)."""
    name = ref.split('/', 2)[2] if ref.startswith('refs/') else ref
    ctx = {'event_name': event_name, 'ref': ref, 'ref_name': name, 'event': {}}
    ctx.update(extra)
    return ctx
