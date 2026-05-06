#!/usr/bin/env python3
"""
Audit static : détecte les noms appelés/référencés mais ni définis ni importés.
Cible : helpers `_xxx`, fonctions de module, classes — tout ce qui doit être
résolu au runtime mais qu'un import oublié peut casser silencieusement.

Limitations :
- Faux positifs possibles pour : noms définis dans une boucle/comprehension,
  builtins (filtrés), `self`/`cls`, attributs (filtrés).
- Ne suit pas les imports star (`from x import *`) — les modules concernés
  sont marqués SKIP pour éviter du bruit.

Exit code 1 si au moins une référence non résolue détectée.
"""
import ast
import builtins
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND
EXCLUDE_DIRS = {'__pycache__', 'venv', '.venv', 'migrations', 'tests', 'scripts'}
BUILTIN_NAMES = set(dir(builtins)) | {
    'self', 'cls', '__name__', '__file__', '__doc__', '__class__',
    '__init__', '__main__', '__path__', '__all__', '__version__',
    'True', 'False', 'None', 'NotImplemented', 'Ellipsis',
}


def _names_from_target(target, out):
    """Recursive : extrait tous les ast.Name d'un target (gère tuple/list nested)."""
    if isinstance(target, ast.Name):
        out.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _names_from_target(elt, out)
    elif isinstance(target, ast.Starred):
        _names_from_target(target.value, out)


def collect_module_symbols(tree):
    """Tous les noms définis ou importés au niveau module ET fonction."""
    defined = set()
    star_imports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            if node.names and node.names[0].name == '*':
                star_imports.append(node.module or '')
            for alias in node.names:
                defined.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # `import a.b.c` expose `a`
                defined.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                _names_from_target(target, defined)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _names_from_target(node.target, defined)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    _names_from_target(item.optional_vars, defined)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for gen in node.generators:
                _names_from_target(gen.target, defined)
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.Lambda):
            for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                defined.add(arg.arg)
            if node.args.vararg:
                defined.add(node.args.vararg.arg)
            if node.args.kwarg:
                defined.add(node.args.kwarg.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                defined.add(arg.arg)
            if node.args.vararg:
                defined.add(node.args.vararg.arg)
            if node.args.kwarg:
                defined.add(node.args.kwarg.arg)
    # Args des fonctions (ré-itère car non capturé ci-dessus pour walk)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                defined.add(arg.arg)
            if node.args.vararg:
                defined.add(node.args.vararg.arg)
            if node.args.kwarg:
                defined.add(node.args.kwarg.arg)
    return defined, star_imports


def collect_referenced_names(tree):
    """Noms utilisés en mode Load (lecture)."""
    refs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            refs.add(node.id)
    return refs


def audit_file(path: Path):
    try:
        src = path.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [('SYNTAX', f'{path}:{e.lineno}: {e.msg}')]

    defined, star_imports = collect_module_symbols(tree)
    refs = collect_referenced_names(tree)
    missing = refs - defined - BUILTIN_NAMES

    if star_imports:
        # `from x import *` peut tout exposer → on skip cette analyse pour ce fichier
        return [('SKIP_STAR', f'{path}: star imports from {star_imports}')]

    if missing:
        # Garde uniquement les noms "louches" : helpers privés ou capitalisés
        return [('UNDEFINED', f'{path}: {sorted(missing)}')]
    return []


def main():
    issues = []
    skipped = []
    for py in ROOT.rglob('*.py'):
        if any(part in EXCLUDE_DIRS for part in py.parts):
            continue
        result = audit_file(py)
        if not result:
            continue
        for kind, msg in result:
            if kind == 'SKIP_STAR':
                skipped.append(msg)
            else:
                issues.append((kind, msg))

    if skipped:
        print(f'SKIPPED {len(skipped)} files (star imports)', file=sys.stderr)

    if issues:
        for kind, msg in issues:
            print(f'[{kind}] {msg}')
        print(f'\n{len(issues)} potential undefined references found')
        sys.exit(1)
    print('OK: no undefined references in backend')


if __name__ == '__main__':
    main()
