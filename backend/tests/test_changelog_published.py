"""CHANGELOG.md keeps the sections of the published 2.x releases word for word, newest first."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
REFERENCE = pathlib.Path(__file__).parent / 'data' / 'changelog_published_2_253_to_2_254_1.md'
PUBLISHED = ('2.254.1', '2.254', '2.253')


def _sections(text):
    parts = re.split(r'(?m)^(?=## \[)', text)
    return {m.group(1): p for p in parts if (m := re.match(r'## \[([^\]]+)\]', p))}


def _numeric(v):
    return tuple(int(x) for x in v.split('-')[0].split('.'))


def test_published_sections_match_the_releases():
    current = _sections((ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'))
    reference = _sections(REFERENCE.read_text(encoding='utf-8'))
    assert tuple(reference) == PUBLISHED
    for version in PUBLISHED:
        assert current[version].rstrip('\n') == reference[version].rstrip('\n'), version


def test_sections_are_in_descending_order():
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    heads = re.findall(r'(?m)^## \[([^\]]+)\]', text)
    assert heads[0] == 'Unreleased'
    versions = [_numeric(h) for h in heads[1:]]
    assert versions == sorted(versions, reverse=True)
