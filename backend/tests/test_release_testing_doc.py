"""RELEASE_TESTING.md stays generic and names every deliverable of the matrix."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEXT = (ROOT / 'RELEASE_TESTING.md').read_text(encoding='utf-8')


def test_the_matrix_names_every_deliverable():
    for needle in ('DEB', 'Fedora', 'EL9', 'EL10', 'standard', '`-fips`', 'amd64', 'arm64', 'Helm chart',
                   'SQLite', 'PostgreSQL', 'UPGRADE.md', '2.254'):
        assert needle in TEXT, needle


def test_no_hand_written_count_or_lab_detail():
    assert '6/6' not in TEXT and not re.search(r'\d+ migrations', TEXT)
    addresses = set(re.findall(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', TEXT))
    # the cloud metadata address is the SSRF test input; no other literal address belongs here
    assert addresses <= {'169.254.169.254', '127.0.0.1'}, addresses
    assert not re.search(r'\.pew\.|ucmtest|/srv/', TEXT)


def test_the_rehearsal_and_the_run_outputs_are_described():
    """The rehearsal comes first; what a release run must produce is listed by name."""
    for needle in ('dry_run', 'release-rehearsal', 'full-stop-migrations.json', 'sbom-index.json', 'latest-fips',
                   'oci://ghcr.io/neyslim/charts/ucm', 'helm-chart', 'scripts/bump-version.sh'):
        assert needle in TEXT, needle
    assert TEXT.index('## Rehearsal') < TEXT.index('## Smoke and UI checks')
