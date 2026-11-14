"""The full-stop mark of a migration, read from its source without importing it.

A migration that removes or narrows something the release before it reads or writes sets, at
module level, ``requires_full_stop = "<why>"`` (CONTRIBUTING.md, "Migrations and rolling
updates"). The runner refuses to apply it in HA while a node of another version beats; a
rolling update reads the marks the release publishes as FULL_STOP_ASSET and refuses before
installing anything.

``python3 migration_marks.py <migrations dir>`` prints that asset. Standard library only.
"""
import ast
import json
import sys
from pathlib import Path

MARK = 'requires_full_stop'
FULL_STOP_ASSET = 'full-stop-migrations.json'


def full_stop_reason(path):
    """The reason a migration file gives for requiring every node stopped, or None."""
    path = Path(path)
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    # Every way a module can bind the name: an assignment, a loop or with target, an import
    bound = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == MARK
             and isinstance(n.ctx, ast.Store)]
    bound += [a for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)
              for a in n.names if (a.asname or a.name) == MARK]
    if not bound:
        return None
    # Read without running the file: one literal at module level, the value Python keeps too
    for node in tree.body if len(bound) == 1 else ():
        target = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, ast.AnnAssign) else []
        if target == bound and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str) and node.value.value.strip():
            return node.value.value.strip()
    raise ValueError(f"{path.stem}: {MARK} must be set once, at module level, "
                     f"to a non-empty string literal giving the reason")


def full_stop_marks(directory):
    """{migration name: reason} of every marked migration in *directory*."""
    marks = {}
    for f in sorted(Path(directory).glob('*.py')):
        if f.name.startswith('_'):
            continue
        reason = full_stop_reason(f)
        if reason:
            marks[f.stem] = reason
    return marks


def manifest(directory):
    return {'full_stop': full_stop_marks(directory)}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <migrations dir>")
    print(json.dumps(manifest(sys.argv[1]), indent=2, sort_keys=True))
