"""Every documented example that mounts the data directory also mounts /etc/ucm.

An unmounted /etc/ucm becomes an anonymous volume, where the master key is not
created and private keys stay unencrypted.
"""
import pathlib
import re

import pytest
import yaml

from tests.test_docker_examples_no_dead_variables import ROOT, _ComposeLoader

DATA, CONFIG = '/opt/ucm/data', '/etc/ucm'
FENCE = re.compile(r'^```(\w*)\n(.*?)^```', re.M | re.S)


def _doc_files():
    files = list((ROOT / 'docs').rglob('*.md'))
    files += [ROOT / 'DOCKERHUB_README.md', ROOT / 'DOCKER_QUICKSTART.md']
    return sorted(files)


def _targets(mounts):
    return {str(m).split(':')[1] for m in mounts if ':' in str(m)}


def _problems(text):
    """Examples in `text` that mount the data directory but not the configuration one."""
    bad = []
    for lang, body in FENCE.findall(text):
        if lang in ('yaml', 'yml'):
            try:
                doc = yaml.load(body, Loader=_ComposeLoader)
            except yaml.YAMLError:
                continue
            services = doc.get('services') if isinstance(doc, dict) else None
            for name, svc in (services or {}).items():
                targets = _targets((svc or {}).get('volumes') or [])
                if DATA in targets and CONFIG not in targets:
                    bad.append(f'compose service {name}')
        elif lang in ('bash', 'sh', 'shell', ''):
            joined = re.sub(r'\\\n\s*', ' ', body)
            for line in joined.splitlines():
                if re.match(r'\s*docker run\b', line) and re.search(r':' + DATA + r'(?=\s|$)', line) \
                        and not re.search(r':' + CONFIG + r'(?=\s|$)', line):
                    bad.append(line.strip()[:80])
    return bad


@pytest.mark.parametrize('path', _doc_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_documented_examples_mount_the_configuration_volume(path):
    assert not _problems(path.read_text()), path


def test_the_checker_flags_a_recipe_without_the_configuration_volume():
    recipe = "```yaml\nservices:\n  ucm:\n    volumes:\n      - ucm-data:/opt/ucm/data\n```\n"
    assert _problems(recipe) == ['compose service ucm']
    assert _problems("```bash\ndocker run -d \\\n  -v ucm-data:/opt/ucm/data \\\n  img\n```\n")
    assert not _problems(recipe.replace('data\n', 'data\n      - ucm-config:/etc/ucm\n'))
