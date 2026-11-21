"""Convention: no API module spells the default key type; it comes from issuance_defaults.
Docstrings are exempt."""
import ast
import pathlib

API = pathlib.Path(__file__).resolve().parent.parent / 'api'


def _literals(path):
    tree = ast.parse(path.read_text())
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == 'RSA-2048'
            and id(n) not in docs]


def test_api_modules_carry_no_rsa_2048_literal():
    offenders = [str(p.relative_to(API)) for p in API.rglob('*.py') if _literals(p)]
    assert offenders == []
