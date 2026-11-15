"""README.md describes features only: relative links resolve and no roadmap or test-count badge remains."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEXT = (ROOT / 'README.md').read_text(encoding='utf-8')


def test_relative_links_resolve():
    targets = set(re.findall(r'\]\((?!https?:|#|mailto:)([^)\s#]+)', TEXT))
    assert targets
    missing = sorted(t for t in targets if not (ROOT / t).exists())
    assert missing == []


def test_no_roadmap_and_no_test_badge():
    assert not re.search(r'(?mi)^#+\s*roadmap', TEXT)
    assert 'badge/tests-' not in TEXT
