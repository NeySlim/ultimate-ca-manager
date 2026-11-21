"""The hook's import check uses the same isolated environment as other tests."""
from scripts.audit_imports import audit_imports


def test_backend_module_imports():
    errors = audit_imports()
    assert not errors, '\n'.join(errors)
