"""Adds module-level fixtures to a file's existing ``pytestmark`` (a mark or a list of marks)."""
import pytest


def with_fixtures(existing, *names):
    marks = list(existing) if isinstance(existing, (list, tuple)) else [existing]
    return [*marks, pytest.mark.usefixtures(*names)]
