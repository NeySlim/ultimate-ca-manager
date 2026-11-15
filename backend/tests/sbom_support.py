"""Fixtures of the release SBOM tests: a frontend build, extracted packages and exported images, all
written under a temporary directory. scripts/ci/sbom.py runs on them as a subprocess, as in CI."""
import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'ci' / 'sbom.py'
VERSION = '3.0-rc1'
COMMIT = 'c0ffee' * 6 + 'c0ff'
DIGEST = {('standard', 'amd64'): 'a' * 64, ('standard', 'arm64'): 'b' * 64,
          ('fips', 'amd64'): 'c' * 64, ('fips', 'arm64'): 'd' * 64}
REPO = 'ghcr.io/example/ucm'
FONT = b'wOF2 not a real font, only its bytes are hashed'
SECRET = 'leak-marker-7f3a'

LOCK = {
    'name': 'ucm-radix', 'lockfileVersion': 3,
    'packages': {
        '': {'name': 'ucm-radix', 'license': 'AGPL-3.0-only'},
        'node_modules/react': {'version': '18.3.1', 'license': 'MIT', 'integrity': 'sha512-react',
                               'resolved': 'https://registry.npmjs.org/react/-/react-18.3.1.tgz'},
        'node_modules/engine.io-client': {'version': '6.6.3', 'license': 'MIT'},
        'node_modules/engine.io-client/node_modules/ws': {'version': '8.17.1', 'license': 'MIT'},
        'node_modules/xmlhttprequest-ssl': {'version': '2.1.2'},
        'node_modules/nolicense': {'version': '1.0.0'},
        'node_modules/cookie': {'version': '1.0.2', 'license': 'MIT'},
        'node_modules/vite': {'version': '7.3.7', 'license': 'MIT', 'dev': True},
    },
}


def run(*args, env=None):
    """scripts/ci/sbom.py with this interpreter, which holds the schema validator in the tests."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          env={**clean, **(env or {})}, timeout=120)


def ok(*args):
    proc = run(*args)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return proc


def frontend(tmp, modules=None, lock=None):
    fe = tmp / 'frontend'
    dist = fe / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'fonts').mkdir()
    (dist / 'assets' / 'vendor.js').write_text('/* react */')
    (dist / 'assets' / 'index.js').write_text('/* app */')
    (dist / 'assets' / 'index.css').write_text('body{}')
    (dist / 'index.html').write_text('<html></html>')
    (dist / 'fonts' / 'Inter-Regular.woff2').write_bytes(FONT)
    (dist / 'fonts' / 'Unknown.woff2').write_bytes(b'another font')
    (fe / 'package-lock.json').write_text(json.dumps(lock or LOCK))
    pkg = fe / 'node_modules' / 'xmlhttprequest-ssl'
    pkg.mkdir(parents=True)
    (pkg / 'package.json').write_text(json.dumps({'name': 'xmlhttprequest-ssl', 'licenses': [{'type': 'MIT'}]}))
    record = {'format': 'ucm-bundle-modules', 'version': 1, 'modules': modules if modules is not None else [
        {'id': 'node_modules/react/index.js', 'virtual': False, 'emitted': True, 'chunks': ['assets/vendor.js']},
        {'id': 'node_modules/react/index.js', 'virtual': True, 'emitted': True, 'chunks': ['assets/vendor.js']},
        {'id': 'node_modules/engine.io-client/node_modules/ws/browser.js', 'virtual': False, 'emitted': True,
         'chunks': ['assets/index.js']},
        {'id': 'node_modules/cookie/dist/index.js', 'virtual': False, 'emitted': False, 'chunks': []},
        {'id': 'src/main.jsx', 'virtual': False, 'emitted': True, 'chunks': ['assets/index.js']},
        {'id': 'vite/preload-helper.js', 'virtual': True, 'emitted': True, 'chunks': ['assets/index.js']},
    ]}
    (fe / 'bundle-modules.json').write_text(json.dumps(record))
    fonts = tmp / 'fonts.json'
    fonts.write_text(json.dumps({'format': 'ucm-font-registry', 'version': 1, 'fonts': [
        {'file': 'fonts/Inter-Regular.woff2', 'sha256': hashlib.sha256(FONT).hexdigest(), 'family': 'Inter',
         'postscript_name': 'Inter-Regular', 'version': '4.001', 'license': 'OFL-1.1',
         'copyright': 'Copyright 2016 The Inter Project Authors', 'source': 'https://github.com/rsms/inter',
         'license_file': 'fonts/LICENSE-Inter.txt'}]}))
    out = tmp / 'frontend-build.json'
    ok('frontend', '--frontend-dir', fe, '--dist', dist, '--modules', fe / 'bundle-modules.json',
       '--fonts', fonts, '-o', out)
    return out


REQUIREMENTS = """# comment
Flask==3.1.0
SQLAlchemy>=2.0.45,<2.2
psycopg[binary]>=3.2.3,<4
xmlsec>=1.3.13
pyspnego>=0.11 ; sys_platform != "win32"
"""


# Where each package format puts the legal texts: debian/rules, %license of the RPM spec
LEGAL_DIRS = {'deb': ('usr', 'share', 'doc', 'ucm'), 'rpm': ('usr', 'share', 'licenses', 'ucm')}


def package_tree(tmp, dist_from, name='deb-root', fmt='deb'):
    root = tmp / name
    app = root / 'opt' / 'ucm'
    shutil.copytree(dist_from, app / 'frontend' / 'dist')
    (app / 'backend').mkdir(parents=True)
    (app / 'backend' / 'requirements-dev.txt').write_text('-r requirements.txt\npytest==9.0.3\n')
    (app / 'backend' / 'app.py').write_text('print(1)\n')
    (app / 'requirements.txt').write_text(REQUIREMENTS)
    (app / 'scripts').mkdir()
    shutil.copy(ROOT / 'packaging' / 'scripts' / 'native-setup.sh', app / 'scripts' / 'native-setup.sh')
    doc = root.joinpath(*LEGAL_DIRS[fmt])
    doc.mkdir(parents=True)
    for f in ('LICENSE', 'NOTICE', 'COMMERCIAL-LICENSE.md'):
        (doc / f).write_text(f)
    return root


DEB_DEPENDS = 'Depends: python3 (>= 3.12), python3-venv,\n openssl (>= 1.1.1), adduser\nRecommends: softhsm2\n'
RPM_DEPENDS = 'Requires: python3 >= 3.12\nRequires: /bin/sh\nRecommends: softhsm\n'


def package_sbom(tmp, frag, file_name, fmt='deb', tree=None, out_dir=None, body=None, depends=None):
    tree = tree or package_tree(tmp, tmp / 'frontend' / 'dist', name=f'root-{file_name}', fmt=fmt)
    out_dir = out_dir or tmp
    pkg = out_dir / file_name
    pkg.write_bytes(body or f'package {file_name}'.encode())
    deps = tmp / f'{file_name}.depends'
    deps.write_text(depends or (DEB_DEPENDS if fmt == 'deb' else RPM_DEPENDS))
    out = out_dir / (file_name.replace('~', '.') + '.cdx.json')
    proc = run('package', '--format', fmt, '--file', pkg, '--root', tree, '--depends', deps, '--frontend', frag,
               '--version', VERSION, '--commit', COMMIT, '-o', out)
    return proc, out, pkg


def _tar_add(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def metadata(name, version, license_=None, expression=None, classifiers=()):
    lines = ['Metadata-Version: 2.1', f'Name: {name}', f'Version: {version}']
    if expression:
        lines.append(f'License-Expression: {expression}')
    if license_:
        lines.append(f'License: {license_}')
    lines += [f'Classifier: {c}' for c in classifiers]
    return ('\n'.join(lines) + '\n\nlong description\n').encode()


SITE = 'opt/ucm/venv/lib/python3.13/site-packages'


def rootfs(tmp, dist_from, variant='standard', arch='amd64', psycopg='psycopg_binary', extra=(), fips=True):
    path = tmp / f'rootfs-{variant}-{arch}.tar'
    triplet = {'amd64': 'x86_64-linux-gnu', 'arm64': 'aarch64-linux-gnu'}[arch]
    with tarfile.open(path, 'w') as tar:
        _tar_add(tar, f'{SITE}/flask-3.1.0.dist-info/METADATA', metadata('Flask', '3.1.0', expression='BSD-3-Clause'))
        _tar_add(tar, f'{SITE}/sqlalchemy-2.0.46.dist-info/METADATA', metadata('SQLAlchemy', '2.0.46', license_='MIT'))
        _tar_add(tar, f'{SITE}/pyjks-20.0.0.dist-info/METADATA',
                 metadata('pyjks', '20.0.0', classifiers=['License :: OSI Approved :: MIT License']))
        _tar_add(tar, f'{SITE}/pip-25.3.dist-info/METADATA', metadata('pip', '25.3', license_='MIT'))
        _tar_add(tar, f'{SITE}/nolic-1.0.dist-info/METADATA', metadata('nolic', '1.0'))
        if psycopg == 'psycopg_binary':
            _tar_add(tar, f'{SITE}/psycopg_binary-3.2.3.dist-info/METADATA',
                     metadata('psycopg-binary', '3.2.3', license_='LGPL-3.0-only'))
            _tar_add(tar, f'{SITE}/psycopg_binary.libs/libpq-9d1a2b.so.5.17', b'bundled libpq')
        else:
            _tar_add(tar, f'{SITE}/psycopg_c-3.2.3.dist-info/METADATA',
                     metadata('psycopg-c', '3.2.3', license_='LGPL-3.0-only'))
        _tar_add(tar, 'usr/local/lib/python3.13/site-packages/setuptools-80.0.dist-info/METADATA',
                 metadata('setuptools', '80.0', license_='MIT'))
        if variant == 'fips' and fips:
            _tar_add(tar, f'usr/lib/{triplet}/ossl-modules/fips.so', b'fips provider binary ' + arch.encode())
        _tar_add(tar, f'usr/lib/{triplet}/ossl-modules/legacy.so', b'legacy')
        for p in sorted(pathlib.Path(dist_from).rglob('*')):
            if p.is_file():
                _tar_add(tar, f'opt/ucm/frontend/dist/{p.relative_to(dist_from).as_posix()}', p.read_bytes())
        for f in ('LICENSE', 'NOTICE', 'COMMERCIAL-LICENSE.md'):
            _tar_add(tar, f'opt/ucm/{f}', f.encode())
        _tar_add(tar, 'opt/ucm/data/secret.key', SECRET.encode())
        _tar_add(tar, 'etc/pip.conf', f'[global]\nindex-url = https://user:{SECRET}@pypi.example/simple\n'.encode())
        for name, data in extra:
            _tar_add(tar, name, data)
    return path


def image_config(tmp, digest, arch='amd64', repo_digests=None):
    path = tmp / f'config-{digest[:8]}-{arch}.json'
    path.write_text(json.dumps([{'Architecture': arch, 'RepoDigests': repo_digests or [f'{REPO}@sha256:{digest}'],
                                 'Config': {'Env': ['PATH=/usr/local/bin', 'PYTHON_VERSION=3.13.9',
                                                    f'UCM_SECRET={SECRET}']}}]))
    return path


def trivy(tmp, digest, arch='amd64', components=None, scanned=None):
    ref = f'pkg:oci/ucm@sha256%3A{digest}?arch={arch}'
    doc = {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'serialNumber': 'urn:uuid:3ff14136-e09f-4df9-80ea-000000000001',
           'version': 1,
           'metadata': {'component': {'type': 'container', 'bom-ref': ref, 'name': f'{REPO}@sha256:{digest}',
                                      'purl': ref, 'properties': [
                                          {'name': 'aquasecurity:trivy:RepoDigest',
                                           'value': f'{REPO}@sha256:{scanned or digest}'}]}},
           'components': components if components is not None else [
               {'type': 'operating-system', 'bom-ref': 'os', 'name': 'debian', 'version': '13.2'},
               {'type': 'library', 'bom-ref': 'pkg:deb/debian/libssl3t64@3.5.4-1', 'name': 'libssl3t64',
                'version': '3.5.4-1', 'purl': 'pkg:deb/debian/libssl3t64@3.5.4-1',
                'licenses': [{'license': {'name': 'Apache-2.0'}}]}],
           'dependencies': [{'ref': ref, 'dependsOn': ['os']}, {'ref': 'os', 'dependsOn': []}]}
    path = tmp / f'trivy-{digest[:8]}-{arch}.json'
    path.write_text(json.dumps(doc))
    return path


def image_sbom(tmp, frag, variant='standard', arch='amd64', out=None, digest=None, tar=None, config=None,
               trivy_doc=None, dockerfile=None):
    digest = digest or DIGEST[(variant, arch)]
    out = out or tmp
    return run('image', '--rootfs-tar', tar or rootfs(tmp, tmp / 'frontend' / 'dist', variant, arch),
               '--image-config', config or image_config(tmp, digest, arch),
               '--trivy', trivy_doc or trivy(tmp, digest, arch), '--digest', f'sha256:{digest}',
               '--repository', REPO, '--variant', variant, '--arch', arch,
               '--dockerfile', dockerfile or ROOT / 'Dockerfile', '--version', VERSION, '--frontend', frag,
               '--commit', COMMIT, '-o', out)


PACKAGES = (('ucm_3.0~rc1_all.deb', 'deb'), ('ucm-3.0~rc1-1.fc43.noarch.rpm', 'rpm'),
            ('ucm-el9-3.0~rc1-1.el9.noarch.rpm', 'rpm'), ('ucm-el10-3.0~rc1-1.el10.noarch.rpm', 'rpm'))


def release_dir(tmp):
    """A release directory as the release job assembles it, and the digest artifacts it downloads."""
    frag = frontend(tmp)
    art = tmp / 'artifacts'
    art.mkdir()
    for name, fmt in PACKAGES:
        proc, _, pkg = package_sbom(tmp, frag, name, fmt, out_dir=art)
        assert proc.returncode == 0, proc.stderr
        (art / f'{name}.sha256').write_text(f'{hashlib.sha256(pkg.read_bytes()).hexdigest()}  {name.replace("~", ".")}\n')
    digests = tmp / 'digests'
    for (variant, arch), digest in DIGEST.items():
        d = digests / f"{'std' if variant == 'standard' else 'fips'}-digest-{arch}"
        d.mkdir(parents=True)
        (d / digest).touch()
        proc = image_sbom(tmp, frag, variant, arch, out=art)
        assert proc.returncode == 0, proc.stderr
    (art / 'full-stop-migrations.json').write_text('{}\n')
    return art, digests
