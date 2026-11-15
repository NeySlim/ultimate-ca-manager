"""The Dockerfile uses BuildKit-only steps (RUN --mount): the documented build says so."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_documented_docker_build_names_its_buildkit_requirement():
    dockerfile = (ROOT / 'Dockerfile').read_text()
    assert re.search(r'^RUN --mount=', dockerfile, re.M), 'no BuildKit step left: revisit the docs'
    assert 'BuildKit' in dockerfile.split('ARG UCM_FIPS_BUILD')[0]
    guide = (ROOT / 'docs' / 'installation' / 'README.md').read_text()
    build = guide.index('docker build -t ucm:local .')
    around = guide[build - 800:build + 600]
    assert 'BuildKit' in around and 'docker buildx version' in around
