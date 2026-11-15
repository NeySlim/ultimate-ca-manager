"""The release SBOMs say what each deliverable holds, and nothing it does not: scripts/ci/sbom.py run for
real on temporary packages, image filesystems and release directories."""
import hashlib
import json
import shutil
import subprocess

import pytest

from tests import sbom_support as s


def _doc(path):
    return json.loads(path.read_text())


def _by_name(doc, name):
    return [c for c in doc['components'] if c['name'] == name]


def _props(c):
    out = {}
    for p in c.get('properties', []):
        out.setdefault(p['name'], []).append(p.get('value'))
    return out


def _role(c):
    return _props(c)['ucm:role'][0]


def _rewrite(path, doc):
    path.write_text(json.dumps(doc))
    path.with_name(path.name + '.sha256').write_text(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n')


# ---- frontend record --------------------------------------------------------------------------------

def test_the_frontend_record_names_what_the_bundle_holds(tmp_path):
    frag = _doc(s.frontend(tmp_path))
    roles = {p['name']: p['role'] for p in frag['packages']}
    assert roles['react'] == 'content'
    # A transitive package, nested in the lock, is attributed to its own entry
    assert roles['ws'] == 'content' and frag['packages'][[p['name'] for p in frag['packages']].index('ws')][
        'key'] == 'node_modules/engine.io-client/node_modules/ws'
    # Tree-shaken or never imported: a production entry is a build input, never content
    assert roles['cookie'] == roles['xmlhttprequest-ssl'] == roles['engine.io-client'] == 'build-input'
    assert 'vite' not in roles
    assert frag['unattributed_modules'] == ['vite/preload-helper.js']
    assert frag['first_party_modules'] == 1
    assert frag['dist']['assets/vendor.js'] == hashlib.sha256(b'/* react */').hexdigest()


def test_the_bundle_record_written_by_the_build_keeps_a_nested_package_apart(tmp_path):
    # Contract between frontend/scripts/bundle-modules.js and sbom.py: the nested copy is the shipped one
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    js = s.ROOT / 'frontend' / 'scripts' / 'bundle-modules.js'
    nested = '/elsewhere/shared/node_modules/mdast-util-find-and-replace/node_modules/escape-string-regexp/index.js'
    bundle = {'a': {'type': 'chunk', 'fileName': 'assets/index.js', 'modules': {nested: {'renderedLength': 9}}}}
    out = subprocess.run(
        [node, '--input-type=module', '-e',
         f'import {{ collectModules }} from {json.dumps("file://" + str(js))};'
         f'console.log(JSON.stringify(collectModules({json.dumps(bundle)}, "/work/frontend")))'],
        capture_output=True, text=True, timeout=60, check=True)
    lock = {'name': 'ucm', 'lockfileVersion': 3, 'packages': {
        'node_modules/escape-string-regexp': {'version': '4.0.0', 'license': 'MIT', 'dev': True},
        'node_modules/mdast-util-find-and-replace': {'version': '3.0.2', 'license': 'MIT'},
        'node_modules/mdast-util-find-and-replace/node_modules/escape-string-regexp': {
            'version': '5.0.0', 'license': 'MIT'}}}
    frag = _doc(s.frontend(tmp_path, modules=json.loads(out.stdout)['modules'], lock=lock))
    by_key = {p['key']: p for p in frag['packages']}
    shipped = by_key['node_modules/mdast-util-find-and-replace/node_modules/escape-string-regexp']
    assert shipped['role'] == 'content' and shipped['version'] == '5.0.0'
    assert 'node_modules/escape-string-regexp' not in by_key


def test_a_bundled_module_outside_the_lock_is_refused(tmp_path):
    proc_tmp = tmp_path / 'x'
    proc_tmp.mkdir()
    with pytest.raises(AssertionError, match='no package-lock.json entry'):
        s.frontend(proc_tmp, modules=[{'id': 'node_modules/leftpad/index.js', 'emitted': True,
                                       'chunks': ['assets/index.js']}])


def test_a_chunk_absent_from_dist_is_refused(tmp_path):
    with pytest.raises(AssertionError, match='absent from'):
        s.frontend(tmp_path, modules=[{'id': 'node_modules/react/index.js', 'emitted': True,
                                       'chunks': ['assets/other.js']}])


def test_licenses_come_from_the_lock_then_the_installed_package_else_unknown(tmp_path):
    frag = {p['name']: p for p in _doc(s.frontend(tmp_path))['packages']}
    assert frag['react']['licenses'] == ['MIT'] and frag['react']['license_source'] == 'package-lock.json'
    assert frag['xmlhttprequest-ssl']['licenses'] == ['MIT']
    assert frag['xmlhttprequest-ssl']['license_source'] == 'package.json licenses'
    assert frag['nolicense']['licenses'] == [] and frag['nolicense']['license_source'] is None


def test_fonts_are_listed_from_dist_by_hash_with_or_without_a_registry_entry(tmp_path):
    fonts = {f['path']: f for f in _doc(s.frontend(tmp_path))['fonts']}
    assert set(fonts) == {'fonts/Inter-Regular.woff2', 'fonts/Unknown.woff2'}
    assert fonts['fonts/Inter-Regular.woff2']['license'] == 'OFL-1.1'
    assert 'license' not in fonts['fonts/Unknown.woff2']


def test_the_repository_font_registry_covers_every_shipped_font():
    reg = json.loads((s.ROOT / 'scripts' / 'ci' / 'sbom-data' / 'fonts.json').read_text())
    shipped = sorted((s.ROOT / 'frontend' / 'public' / 'fonts').glob('*.woff2'))
    assert len(shipped) == 7
    by_hash = {f['sha256']: f for f in reg['fonts']}
    for p in shipped:
        entry = by_hash[hashlib.sha256(p.read_bytes()).hexdigest()]
        assert entry['file'] == f'fonts/{p.name}'
        assert (s.ROOT / 'frontend' / 'public' / entry['license_file']).is_file()


# ---- packages ---------------------------------------------------------------------------------------

@pytest.fixture
def deb(tmp_path):
    frag = s.frontend(tmp_path)
    proc, out, pkg = s.package_sbom(tmp_path, frag, 'ucm_3.0~rc1_all.deb')
    assert proc.returncode == 0, proc.stderr
    return _doc(out), out, pkg


def test_the_package_sbom_names_its_file_by_hash_and_published_name(deb):
    doc, out, pkg = deb
    assert out.name == 'ucm_3.0.rc1_all.deb.cdx.json'
    subject = doc['metadata']['component']
    assert subject['hashes'] == [{'alg': 'SHA-256', 'content': hashlib.sha256(pkg.read_bytes()).hexdigest()}]
    assert _props(subject)['ucm:asset'] == ['ucm_3.0.rc1_all.deb']
    assert out.with_name(out.name + '.sha256').read_text().split() == [
        hashlib.sha256(out.read_bytes()).hexdigest(), out.name]


def test_a_package_declares_python_without_claiming_it_installed(deb):
    doc, _, _ = deb
    for name in ('Flask', 'SQLAlchemy', 'psycopg[binary]', 'xmlsec', 'pyspnego'):
        (c,) = _by_name(doc, name)
        assert _role(c) == 'install-requirement' and 'version' not in c, name
    (sa,) = _by_name(doc, 'SQLAlchemy')
    assert _props(sa)['ucm:requirement'] == ['SQLAlchemy>=2.0.45,<2.2']
    (flask,) = _by_name(doc, 'Flask')
    assert _props(flask)['ucm:requirement'] == ['Flask==3.1.0']
    assert not [c for c in doc['components'] if _role(c) == 'content' and c['name'].lower() in ('flask', 'psycopg')]


def test_the_package_sbom_reads_the_requirements_the_package_ships(deb):
    doc, _, _ = deb
    assert not _by_name(doc, 'pytest')  # requirements-dev.txt is a file in the tree, not a runtime
    (pyjks,) = _by_name(doc, 'pyjks')
    assert _props(pyjks)['ucm:requirement'] == ['pyjks==20.0.0']
    assert _props(pyjks)['ucm:install-option'] == ['--no-deps']
    assert not _by_name(doc, 'twofish')
    (psy,) = _by_name(doc, 'psycopg[binary]')
    assert _props(psy)['ucm:fips-native-build'] == ['psycopg[c]>=3.2.3,<4 (UCM_FIPS_BUILD=1)']
    (xmlsec,) = _by_name(doc, 'xmlsec')
    assert _props(xmlsec)['ucm:fips-native-build'] == ['xmlsec==1.3.13 (UCM_FIPS_BUILD=1, EL9)']


def test_host_dependencies_keep_their_relation_and_constraint(deb):
    doc, _, _ = deb
    host = {(_props(c)['ucm:relation'][0], _props(c)['ucm:requirement'][0]) for c in doc['components']
            if _props(c).get('ucm:ecosystem')}
    assert host == {('Depends', 'python3 (>= 3.12)'), ('Depends', 'python3-venv'),
                    ('Depends', 'openssl (>= 1.1.1)'), ('Depends', 'adduser'), ('Recommends', 'softhsm2')}


def test_an_rpm_lists_one_requirement_per_line(tmp_path):
    frag = s.frontend(tmp_path)
    proc, out, _ = s.package_sbom(tmp_path, frag, 'ucm-el9-3.0~rc1-1.el9.noarch.rpm', 'rpm')
    assert proc.returncode == 0, proc.stderr
    reqs = {_props(c)['ucm:requirement'][0] for c in _doc(out)['components'] if _props(c).get('ucm:ecosystem')}
    assert reqs == {'python3 >= 3.12', '/bin/sh', 'softhsm'}


def test_the_package_content_is_the_bundle_fonts_and_legal_texts(deb):
    doc, _, _ = deb
    content = {c['name']: c for c in doc['components'] if _role(c) == 'content'}
    assert content['react']['version'] == '18.3.1'
    assert 'opt/ucm/frontend/dist/assets/vendor.js' in _props(content['react'])['ucm:emitted-in']
    assert 'cookie' not in content and 'xmlhttprequest-ssl' not in content
    font = content['Inter (opt/ucm/frontend/dist/fonts/Inter-Regular.woff2)']
    assert font['licenses'] == [{'license': {'id': 'OFL-1.1'}}] and font['version'] == '4.001'
    unknown = content['opt/ucm/frontend/dist/fonts/Unknown.woff2']
    assert 'licenses' not in unknown and _props(unknown)['ucm:license'] == ['unknown']
    assert {'usr/share/doc/ucm/LICENSE', 'usr/share/doc/ucm/NOTICE'} <= set(content)


def test_no_license_is_ever_filled_in_with_the_project_one(deb):
    doc, _, _ = deb
    agpl = [c['name'] for c in doc['components'] if 'AGPL-3.0-only' in json.dumps(c.get('licenses', []))]
    assert agpl == ['ucm']
    (nolic,) = _by_name(doc, 'nolicense')
    assert 'licenses' not in nolic and _props(nolic)['ucm:license'] == ['unknown']
    (xhr,) = _by_name(doc, 'xmlhttprequest-ssl')
    assert xhr['licenses'] == [{'license': {'id': 'MIT'}}] and _role(xhr) == 'build-input'


def test_a_package_with_a_python_environment_is_refused(tmp_path):
    frag = s.frontend(tmp_path)
    tree = s.package_tree(tmp_path, tmp_path / 'frontend' / 'dist')
    site = tree / 'opt' / 'ucm' / 'venv' / 'lib' / 'python3.13' / 'site-packages' / 'flask-3.1.0.dist-info'
    site.mkdir(parents=True)
    (site / 'METADATA').write_text('Name: Flask\n')
    proc, out, _ = s.package_sbom(tmp_path, frag, 'ucm_3.0~rc1_all.deb', tree=tree)
    assert proc.returncode == 1 and 'carries a Python environment' in proc.stderr
    assert not out.with_name(out.name + '.sha256').exists()


def test_a_package_whose_interface_is_another_build_is_refused(tmp_path):
    frag = s.frontend(tmp_path)
    tree = s.package_tree(tmp_path, tmp_path / 'frontend' / 'dist')
    (tree / 'opt' / 'ucm' / 'frontend' / 'dist' / 'assets' / 'vendor.js').write_text('/* another build */')
    proc, _, _ = s.package_sbom(tmp_path, frag, 'ucm_3.0~rc1_all.deb', tree=tree)
    assert proc.returncode == 1 and 'differs from the recorded build' in proc.stderr


def test_a_package_without_its_requirements_is_refused(tmp_path):
    frag = s.frontend(tmp_path)
    tree = s.package_tree(tmp_path, tmp_path / 'frontend' / 'dist')
    (tree / 'opt' / 'ucm' / 'requirements.txt').unlink()
    proc, _, _ = s.package_sbom(tmp_path, frag, 'ucm_3.0~rc1_all.deb', tree=tree)
    assert proc.returncode == 1 and 'requirements.txt' in proc.stderr


@pytest.mark.parametrize('fmt,name,missing', [
    ('deb', 'ucm_3.0~rc1_all.deb', 'usr/share/doc/ucm/LICENSE'),
    ('rpm', 'ucm-el9-3.0~rc1-1.el9.noarch.rpm', 'usr/share/licenses/ucm/LICENSE'),
    ('rpm', 'ucm-el9-3.0~rc1-1.el9.noarch.rpm', 'usr/share/licenses/ucm/NOTICE'),
])
def test_a_package_without_its_legal_text_is_refused(tmp_path, fmt, name, missing):
    frag = s.frontend(tmp_path)
    tree = s.package_tree(tmp_path, tmp_path / 'frontend' / 'dist', fmt=fmt)
    (tree / missing).unlink()
    proc, out, _ = s.package_sbom(tmp_path, frag, name, fmt, tree=tree)
    assert proc.returncode == 1 and missing in proc.stderr
    assert not out.exists()


def test_an_rpm_with_its_legal_texts_in_the_deb_place_is_refused(tmp_path):
    # %license puts them under /usr/share/licenses: a doc directory alone is the wrong package
    frag = s.frontend(tmp_path)
    tree = s.package_tree(tmp_path, tmp_path / 'frontend' / 'dist', fmt='deb')
    proc, _, _ = s.package_sbom(tmp_path, frag, 'ucm-el9-3.0~rc1-1.el9.noarch.rpm', 'rpm', tree=tree)
    assert proc.returncode == 1 and 'usr/share/licenses/ucm/LICENSE' in proc.stderr


# ---- images -----------------------------------------------------------------------------------------

def _image(tmp_path, variant='standard', arch='amd64', **kw):
    frag = s.frontend(tmp_path)
    proc = s.image_sbom(tmp_path, frag, variant, arch, **kw)
    return proc, tmp_path / f'ucm-3.0.rc1-image-{variant}-{arch}.cdx.json'


def test_the_image_sbom_names_its_digest_variant_and_arch(tmp_path):
    proc, out = _image(tmp_path, 'standard', 'arm64')
    assert proc.returncode == 0, proc.stderr
    subject = _doc(out)['metadata']['component']
    assert subject['hashes'] == [{'alg': 'SHA-256', 'content': 'b' * 64}]
    assert _props(subject)['ucm:image-digest'] == ['sha256:' + 'b' * 64]
    assert (_props(subject)['ucm:variant'], _props(subject)['ucm:arch']) == (['standard'], ['arm64'])
    assert subject['purl'].endswith('?arch=arm64')


def test_python_versions_and_licenses_come_from_the_installed_metadata(tmp_path):
    proc, out = _image(tmp_path)
    assert proc.returncode == 0, proc.stderr
    doc = _doc(out)
    (flask,) = _by_name(doc, 'Flask')
    assert flask['version'] == '3.1.0' and flask['licenses'] == [{'license': {'id': 'BSD-3-Clause'}}]
    (sa,) = _by_name(doc, 'SQLAlchemy')
    assert sa['version'] == '2.0.46' and sa['licenses'] == [{'license': {'id': 'MIT'}}]
    (pyjks,) = _by_name(doc, 'pyjks')
    assert pyjks['licenses'] == [{'license': {'name': 'MIT License'}}]
    assert not _by_name(doc, 'twofish')
    # The tools left in the environment are components too, in both locations
    (pip,) = _by_name(doc, 'pip')
    assert _props(pip)['ucm:location'] == [s.SITE]
    (st,) = _by_name(doc, 'setuptools')
    assert _props(st)['ucm:location'] == ['usr/local/lib/python3.13/site-packages']
    (nolic,) = _by_name(doc, 'nolic')
    assert 'licenses' not in nolic and _props(nolic)['ucm:license'] == ['unknown']
    (lib,) = [c for c in doc['components'] if c['name'].endswith('libpq-9d1a2b.so.5.17')]
    assert _props(lib)['ucm:license'] == ['unknown'] and 'version' not in lib
    (py,) = _by_name(doc, 'cpython')
    assert py['version'] == '3.13.9'


def test_the_psycopg_build_changes_the_inventory(tmp_path):
    frag = s.frontend(tmp_path)
    tar = s.rootfs(tmp_path, tmp_path / 'frontend' / 'dist', 'fips', 'amd64', psycopg='psycopg_c')
    proc = s.image_sbom(tmp_path, frag, 'fips', 'amd64', tar=tar)
    assert proc.returncode == 0, proc.stderr
    doc = _doc(tmp_path / 'ucm-3.0.rc1-image-fips-amd64.cdx.json')
    assert _by_name(doc, 'psycopg-c') and not _by_name(doc, 'psycopg-binary')


def test_the_fips_provider_is_listed_once_from_the_recipe(tmp_path):
    proc, out = _image(tmp_path, 'fips', 'amd64')
    assert proc.returncode == 0, proc.stderr
    doc = _doc(out)
    (prov,) = _by_name(doc, 'OpenSSL FIPS Provider')
    dockerfile = (s.ROOT / 'Dockerfile').read_text()
    assert prov['version'] == '3.5.9' and 'ARG FIPS_PROVIDER_VERSION=3.5.9' in dockerfile
    binary = prov['hashes'][0]['content']
    assert binary == hashlib.sha256(b'fips provider binary amd64').hexdigest()
    source = _props(prov)['ucm:source-sha256'][0]
    assert source != binary and f'ARG FIPS_PROVIDER_SHA256={source}' in dockerfile
    assert _props(prov)['ucm:path'] == ['usr/lib/x86_64-linux-gnu/ossl-modules/fips.so']
    # The system libcrypto stays its own component, with the version the scan read
    (ssl,) = _by_name(doc, 'libssl3t64')
    assert ssl['version'] == '3.5.4-1' and _props(ssl)['ucm:evidence'] == ['trivy (os packages)']


def test_a_fips_image_without_its_provider_is_refused(tmp_path):
    frag = s.frontend(tmp_path)
    tar = s.rootfs(tmp_path, tmp_path / 'frontend' / 'dist', 'fips', 'amd64', fips=False)
    proc = s.image_sbom(tmp_path, frag, 'fips', 'amd64', tar=tar)
    assert proc.returncode == 1 and '0 fips.so' in proc.stderr


def test_a_standard_image_holding_a_provider_is_refused(tmp_path):
    frag = s.frontend(tmp_path)
    tar = s.rootfs(tmp_path, tmp_path / 'frontend' / 'dist', 'standard', 'amd64',
                   extra=[('usr/lib/x86_64-linux-gnu/ossl-modules/fips.so', b'x')])
    proc = s.image_sbom(tmp_path, frag, 'standard', 'amd64', tar=tar)
    assert proc.returncode == 1 and 'standard image holds' in proc.stderr


def test_a_provider_already_listed_by_the_scan_is_refused(tmp_path):
    digest = s.DIGEST[('fips', 'amd64')]
    doc = s.trivy(tmp_path, digest, components=[{'type': 'library', 'bom-ref': 'x', 'name': 'fips.so'}])
    proc, _ = _image(tmp_path, 'fips', 'amd64', trivy_doc=doc)
    assert proc.returncode == 1 and 'already listed' in proc.stderr


def test_a_provider_hash_equal_to_its_source_is_refused(tmp_path):
    df = tmp_path / 'Dockerfile'
    text = (s.ROOT / 'Dockerfile').read_text()
    fake = hashlib.sha256(b'fips provider binary amd64').hexdigest()
    df.write_text(text.replace(s_re := text.split('ARG FIPS_PROVIDER_SHA256=')[1].split('\n')[0], fake))
    assert s_re != fake
    proc, _ = _image(tmp_path, 'fips', 'amd64', dockerfile=df)
    assert proc.returncode == 1 and 'equals its source' in proc.stderr


@pytest.mark.parametrize('case', ['tag-scanned', 'other-digest-exported', 'other-arch'])
def test_an_image_sbom_is_bound_to_the_digest_and_arch_it_names(tmp_path, case):
    digest = s.DIGEST[('standard', 'amd64')]
    kw = {}
    if case == 'tag-scanned':
        kw['trivy_doc'] = s.trivy(tmp_path, digest, scanned='e' * 64)
    elif case == 'other-digest-exported':
        kw['config'] = s.image_config(tmp_path, digest, repo_digests=[f"{s.REPO}@sha256:{'e' * 64}"])
    else:
        kw['config'] = s.image_config(tmp_path, digest, arch='arm64')
    proc, out = _image(tmp_path, **kw)
    assert proc.returncode == 1, proc.stdout
    assert not out.exists()


def test_an_image_whose_interface_is_another_build_is_refused(tmp_path):
    frag = s.frontend(tmp_path)
    other = tmp_path / 'other-dist'
    shutil.copytree(tmp_path / 'frontend' / 'dist', other)
    (other / 'assets' / 'index.js').write_text('/* not this build */')
    tar = s.rootfs(tmp_path, other)
    proc = s.image_sbom(tmp_path, frag, tar=tar)
    assert proc.returncode == 1 and 'differs from the recorded build' in proc.stderr


def test_nothing_private_of_the_image_reaches_the_sbom(tmp_path):
    proc, out = _image(tmp_path, 'fips', 'amd64')
    assert proc.returncode == 0, proc.stderr
    text = out.read_text()
    assert s.SECRET not in text and 'user:' not in text and 'opt/ucm/data' not in text
    assert 'UCM_SECRET' not in text and '/tmp' not in text and str(tmp_path) not in text


def test_nothing_private_of_the_build_reaches_the_package_sbom(deb):
    _, out, _ = deb
    assert str(out.parent) not in out.read_text()


# ---- the document contract --------------------------------------------------------------------------

def _check(tmp_path, doc, kind=None):
    p = tmp_path / 'x.cdx.json'
    _rewrite(p, doc)
    return s.run('check', p, '--version', s.VERSION, *(['--kind', kind] if kind else []))


def test_every_generated_document_passes_the_cyclonedx_schema(deb, tmp_path):
    doc, out, _ = deb
    assert doc['specVersion'] == '1.6'
    s.ok('check', out, '--version', s.VERSION, '--kind', 'package')


@pytest.mark.parametrize('breakage, message', [
    (lambda d: d['components'][0].__setitem__('type', 'banana'), 'schema'),
    (lambda d: d['metadata']['component'].__setitem__('hashes', [{'alg': 'SHA-256', 'content': 'xyz'}]), 'schema'),
    (lambda d: d.__setitem__('specVersion', '1.5'), 'CycloneDX 1.6'),
    (lambda d: d['metadata'].__setitem__('properties', [p for p in d['metadata']['properties']
                                                        if p['name'] != 'ucm:not-covered']), 'coverage limits'),
    (lambda d: d['compositions'][0].__setitem__('aggregate', 'complete'), 'completeness'),
    (lambda d: next(c for c in d['components'] if c['name'] == 'SQLAlchemy').__setitem__('version', '2.0.45'),
     'carries a version'),
    (lambda d: next(c for c in d['components'] if c['name'] == 'nolicense')['properties'].pop(), 'not marked unknown'),
    (lambda d: next(c for c in d['components'] if c['name'] == 'react')['properties'].pop(0), 'role'),
    (lambda d: d['metadata']['properties'].__setitem__(1, {'name': 'ucm:release-version', 'value': '3.0-rc2'}),
     'not 3.0-rc1'),
])
def test_a_document_breaking_the_contract_is_refused(deb, tmp_path, breakage, message):
    doc, _, _ = deb
    breakage(doc)
    proc = _check(tmp_path, doc)
    assert proc.returncode == 1 and message in proc.stderr, proc.stderr


def test_an_image_document_is_not_a_package_one(tmp_path):
    proc, out = _image(tmp_path)
    assert proc.returncode == 0
    proc = s.run('check', out, '--version', s.VERSION, '--kind', 'package')
    assert proc.returncode == 1 and 'not a package' in proc.stderr


def test_an_empty_document_is_refused(tmp_path):
    p = tmp_path / 'x.cdx.json'
    p.write_text('')
    p.with_name(p.name + '.sha256').write_text(f'{hashlib.sha256(b"").hexdigest()}  x.cdx.json\n')
    proc = s.run('check', p, '--version', s.VERSION)
    assert proc.returncode == 1 and 'unreadable' in proc.stderr


# ---- the release directory --------------------------------------------------------------------------

def _validate(art, digests):
    return s.run('validate', '--dir', art, '--digests', digests, '--version', s.VERSION)


@pytest.fixture(scope='module')
def _built_release(tmp_path_factory):
    base = tmp_path_factory.mktemp('release')
    art, digests = s.release_dir(base)
    s.ok('index', '--dir', art, '--digests', digests, '--version', s.VERSION)
    return art, digests


@pytest.fixture
def release(_built_release, tmp_path):
    # Built once per module, copied per test: each test breaks its own copy
    art, digests = (tmp_path / 'artifacts', tmp_path / 'digests')
    shutil.copytree(_built_release[0], art)
    shutil.copytree(_built_release[1], digests)
    return art, digests


def test_a_complete_release_passes(release):
    art, digests = release
    proc = _validate(art, digests)
    assert proc.returncode == 0, proc.stderr
    assert '8 deliverables' in proc.stdout
    index = json.loads((art / 'sbom-index.json').read_text())
    assert {(e['kind'], e['variant'], e['arch']) for e in index['documents']} == {
        ('package', None, None)} | {('image', v, a) for v, a in s.DIGEST}
    assert len(index['documents']) == 8


def _arm_copy(art):
    src = art / 'ucm-3.0.rc1-image-standard-amd64.cdx.json'
    dst = art / 'ucm-3.0.rc1-image-standard-arm64.cdx.json'
    shutil.copy(src, dst)
    shutil.copy(src.with_name(src.name + '.sha256'), dst.with_name(dst.name + '.sha256'))
    (dst.with_name(dst.name + '.sha256')).write_text(f'{hashlib.sha256(dst.read_bytes()).hexdigest()}  {dst.name}\n')


def _wrong_package(art):
    src = art / 'ucm-el9-3.0.rc1-1.el9.noarch.rpm.cdx.json'
    dst = art / 'ucm-3.0.rc1-1.fc43.noarch.rpm.cdx.json'
    doc = _doc(src)
    for p in doc['metadata']['component']['properties']:
        if p['name'] == 'ucm:asset':
            p['value'] = dst.name[:-len('.cdx.json')]
    _rewrite(dst, doc)


def _tilde_asset(art):
    p = art / 'ucm_3.0.rc1_all.deb.cdx.json'
    doc = _doc(p)
    for prop in doc['metadata']['component']['properties']:
        if prop['name'] == 'ucm:asset':
            prop['value'] = 'ucm_3.0~rc1_all.deb'
    _rewrite(p, doc)


def _tilde_file(art):
    p = art / 'ucm_3.0.rc1_all.deb.cdx.json'
    p.rename(art / 'ucm_3.0~rc1_all.deb.cdx.json')


def _other_version(art):
    p = art / 'ucm-3.0.rc1-image-fips-arm64.cdx.json'
    doc = _doc(p)
    for prop in doc['metadata']['properties']:
        if prop['name'] == 'ucm:release-version':
            prop['value'] = '3.0-rc0'
    _rewrite(p, doc)


def _invalid_schema(art):
    p = art / 'ucm-3.0.rc1-image-fips-amd64.cdx.json'
    doc = _doc(p)
    doc['components'][0]['type'] = 'banana'
    _rewrite(p, doc)


def _arch_property_lies(art):
    p = art / 'ucm-3.0.rc1-image-standard-arm64.cdx.json'
    doc = _doc(p)
    for prop in doc['metadata']['component']['properties']:
        if prop['name'] == 'ucm:arch':
            prop['value'] = 'amd64'
    _rewrite(p, doc)
    # Indexed again, as the release job does just before validating: only the arch check is left
    s.ok('index', '--dir', art, '--digests', art.parent / 'digests', '--version', s.VERSION)


def _altered_sum(art):
    p = art / 'ucm-3.0.rc1-image-fips-amd64.cdx.json.sha256'
    p.write_text('0' * 64 + '  ucm-3.0.rc1-image-fips-amd64.cdx.json\n')


def _index_drops_one(art):
    p = art / 'sbom-index.json'
    doc = _doc(p)
    doc['documents'].pop()
    _rewrite(p, doc)


def _index_wrong_hash(art):
    p = art / 'sbom-index.json'
    doc = _doc(p)
    doc['documents'][0]['sbom-sha256'] = '0' * 64
    _rewrite(p, doc)


def _empty(art):
    p = art / 'ucm-3.0.rc1-image-fips-amd64.cdx.json'
    p.write_text('')
    p.with_name(p.name + '.sha256').write_text(f'{hashlib.sha256(b"").hexdigest()}  {p.name}\n')


def _stray(art):
    shutil.copy(art / 'ucm_3.0.rc1_all.deb.cdx.json', art / 'ucm-noble_3.0.rc1_all.deb.cdx.json')


def _new_rpm(art):
    (art / 'ucm-sles-3.0~rc1-1.sles.noarch.rpm').write_bytes(b'unsmoked, undescribed')


@pytest.mark.parametrize('breakage', [
    lambda art, d: (art / 'ucm-3.0.rc1-image-fips-arm64.cdx.json').unlink(),
    lambda art, d: (art / 'ucm_3.0.rc1_all.deb.cdx.json').unlink(),
    lambda art, d: _arm_copy(art),
    lambda art, d: _wrong_package(art),
    lambda art, d: (art / 'ucm_3.0~rc1_all.deb').write_bytes(b'another package'),
    lambda art, d: _tilde_asset(art),
    lambda art, d: _tilde_file(art),
    lambda art, d: _other_version(art),
    lambda art, d: _invalid_schema(art),
    lambda art, d: _altered_sum(art),
    lambda art, d: _arch_property_lies(art),
    lambda art, d: _index_drops_one(art),
    lambda art, d: _index_wrong_hash(art),
    lambda art, d: (art / 'sbom-index.json').unlink(),
    lambda art, d: _empty(art),
    lambda art, d: _stray(art),
    lambda art, d: _new_rpm(art),
    lambda art, d: shutil.rmtree(d / 'fips-digest-arm64'),
    lambda art, d: (d / 'std-digest-amd64' / ('f' * 64)).touch(),
], ids=['no-image-sbom', 'no-package-sbom', 'amd64-as-arm64', 'other-package', 'package-replaced',
        'rc-asset-not-normalized', 'rc-file-not-normalized', 'other-version', 'invalid-schema', 'altered-sum', 'arch-property-lies',
        'index-incomplete', 'index-wrong-hash', 'no-index', 'empty', 'stray-sbom', 'rpm-without-sbom',
        'image-sbom-without-digest', 'two-digests'])
def test_a_broken_release_is_refused(release, breakage):
    art, digests = release
    breakage(art, digests)
    proc = _validate(art, digests)
    assert proc.returncode == 1, proc.stdout
    assert '::error::SBOM:' in proc.stderr


def test_the_validator_needs_its_schema_library(release, tmp_path):
    art, digests = release
    # An interpreter without jsonschema: the check is refused rather than skipped
    shadow = tmp_path / 'shadow'
    shadow.mkdir()
    (shadow / 'jsonschema.py').write_text('raise ImportError("hidden")\n')
    proc = s.run('validate', '--dir', art, '--digests', digests, '--version', s.VERSION,
                 env={'PYTHONPATH': str(shadow)})
    assert proc.returncode == 1 and 'jsonschema is not installed' in proc.stderr


# ---- before an image index is tagged ----------------------------------------------------------------

def _images(art, digests, variant):
    flat = art.parent / f'flat-{variant}'
    flat.mkdir(exist_ok=True)
    short = 'std' if variant == 'standard' else 'fips'
    for d in digests.glob(f'{short}-digest-*'):
        for f in d.iterdir():
            shutil.copy(f, flat / f.name)
    sboms = art.parent / f'sboms-{variant}'
    sboms.mkdir(exist_ok=True)
    for f in art.glob(f'ucm-*-image-{variant}-*.cdx.json*'):
        shutil.copy(f, sboms / f.name)
    return flat, sboms


@pytest.mark.parametrize('variant', ['standard', 'fips'])
def test_each_index_needs_one_sbom_per_arch_on_its_digests(release, variant):
    art, digests = release
    flat, sboms = _images(art, digests, variant)
    s.ok('images', '--variant', variant, '--digests', flat, '--sboms', sboms, '--version', s.VERSION, '--no-schema')
    next(sboms.glob('*-arm64.cdx.json')).unlink()
    proc = s.run('images', '--variant', variant, '--digests', flat, '--sboms', sboms, '--version', s.VERSION)
    assert proc.returncode == 1


def test_an_index_refuses_the_sbom_of_the_other_variant(release):
    art, digests = release
    flat, sboms = _images(art, digests, 'standard')
    _, fips_sboms = _images(art, digests, 'fips')
    proc = s.run('images', '--variant', 'standard', '--digests', flat, '--sboms', fips_sboms,
                 '--version', s.VERSION)
    assert proc.returncode == 1


def test_a_compressed_file_is_not_listed_as_a_legal_text(tmp_path):
    """dh_compress leaves the legal texts as they are (-X in packaging/debian/rules): a .gz is not one."""
    frag = s.frontend(tmp_path)
    tree = s.package_tree(tmp_path, tmp_path / 'frontend' / 'dist', name='gz-root')
    (tree / 'usr' / 'share' / 'doc' / 'ucm' / 'LICENSE.gz').write_bytes(b'gz')
    proc, out, _ = s.package_sbom(tmp_path, frag, 'ucm_3.0~rc1_all.deb', tree=tree)
    assert proc.returncode == 0, proc.stderr
    legal = {c['name'] for c in _doc(out)['components'] if c['name'].startswith('usr/share/doc/ucm/')}
    assert legal == {'usr/share/doc/ucm/LICENSE', 'usr/share/doc/ucm/NOTICE',
                     'usr/share/doc/ucm/COMMERCIAL-LICENSE.md'}
