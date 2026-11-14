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
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == MARK for t in targets):
            found.append(node)
    if not found:
        return None
    # Read without running the file: one literal at module level, the value Python keeps too
    node = found[0]
    if len(found) == 1 and node in tree.body and isinstance(node, ast.Assign | ast.AnnAssign) \
            and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) \
            and node.value.value.strip():
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
