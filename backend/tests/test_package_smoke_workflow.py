"""Every package built for a release is installed by the package smoke, in its distribution."""
import fnmatch
import pathlib
import shutil
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / '.github' / 'workflows'
SCRIPT = ROOT / 'scripts' / 'ci' / 'package-smoke.sh'


def _load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _built_assets():
    """Asset glob and build image of each package build-release.yml produces."""
    jobs = _load('build-release.yml')['jobs']
    assets = [('ucm_*_all.deb', 'deb')]
    for entry in jobs['build-rpm']['strategy']['matrix']['include']:
        assets.append((entry['asset_prefix'], entry['image']))
    return assets


def _smoked():
    matrix = _load('release-smoke.yml')['jobs']['smoke-packages']['strategy']['matrix']['include']
    return [(e['pattern'], e['image']) for e in matrix]


def test_every_built_rpm_has_a_smoke_in_its_own_image():
    smoked = _smoked()
    for prefix, image in _built_assets():
        if image == 'deb':
            continue
        assert any(p.startswith(prefix) and img == image for p, img in smoked), (prefix, image)


def test_the_deb_is_smoked_on_debian_and_ubuntu():
    images = {img for p, img in _smoked() if fnmatch.fnmatch('ucm_2.1_all.deb', p)}
    assert {'debian:13', 'ubuntu:24.04', 'ubuntu:26.04'} <= images


def test_smoke_matrix_does_not_stop_at_the_first_failure():
    job = _load('release-smoke.yml')['jobs']['smoke-packages']
    assert job['strategy']['fail-fast'] is False


def test_script_is_valid_shell():
    assert subprocess.run(['sh', '-n', str(SCRIPT)]).returncode == 0


@pytest.mark.skipif(not shutil.which('shellcheck'), reason='shellcheck not installed')
def test_script_passes_shellcheck():
    assert subprocess.run(['shellcheck', '-s', 'sh', str(SCRIPT)]).returncode == 0
