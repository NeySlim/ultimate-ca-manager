"""charts/ucm/README.md: every value of values.yaml has a row in the table (a row may cover a group)."""
import pathlib
import re

import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / 'charts' / 'ucm'


def _leaves(values, prefix=''):
    for key, value in values.items():
        if isinstance(value, dict) and value:
            yield from _leaves(value, f'{prefix}{key}.')
        else:
            yield f'{prefix}{key}'


def test_every_value_has_a_row_in_the_readme_table():
    rows = [line for line in (CHART / 'README.md').read_text().splitlines() if line.startswith('| `')]
    documented = {key for row in rows for key in re.findall(r'`([A-Za-z0-9_.]+)`', row.split('|')[1])}
    values = yaml.safe_load((CHART / 'values.yaml').read_text())
    missing = [key for key in _leaves(values)
               if not any(key == d or key.startswith(d + '.') for d in documented)]
    assert missing == []
