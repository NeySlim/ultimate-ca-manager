#!/usr/bin/env python3
"""CycloneDX 1.6 SBOMs of the release deliverables: assembled from the built artefact, then checked.

Every component carries a role (ucm:role): content (in the deliverable), build-input (used to build
it, not shipped), install-requirement (resolved on the host at install time: constraint as written,
never a version) or excluded. A field the evidence does not give stays unknown (ucm:license=unknown).

  frontend  record of one frontend build: dist/ hashes, npm packages fused into it, fonts
  package   SBOM of a DEB or RPM, from its extracted tree
  image     SBOM of one image platform, from its exported filesystem and a Trivy OS-package scan
  check     contract and schema of SBOM documents
  index     writes sbom-index.json for a release directory
  validate  every deliverable of a release directory has exactly its SBOM, before anything is published
"""
import argparse
import email.parser
import functools
import hashlib
import json
import pathlib
import re
import sys
import tarfile
import uuid
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import release_version  # noqa: E402

SPEC_VERSION = '1.6'
# CycloneDX specification, tag 1.6.2 (commit e833d732337dd33aceb45ff1991f896796f1e5e7), schema/
SCHEMA_DIR = HERE / 'sbom-data' / 'cyclonedx'
FONTS = HERE / 'sbom-data' / 'fonts.json'
ROLES = ('content', 'build-input', 'install-requirement', 'excluded')
LEGAL = ('LICENSE', 'NOTICE', 'COMMERCIAL-LICENSE.md')
# Where each package format installs them: packaging/debian/rules, %license of the RPM spec
LEGAL_DIRS = {'deb': 'usr/share/doc/ucm', 'rpm': 'usr/share/licenses/ucm'}
FONT_SUFFIXES = ('.woff2', '.woff', '.ttf', '.otf')
VARIANTS = {'std': 'standard', 'fips': 'fips'}
ARCHES = ('amd64', 'arm64')
INDEX = 'sbom-index.json'
HEX64 = re.compile(r'[0-9a-f]{64}')


class SbomError(Exception):
    pass


def fail(msg):
    raise SbomError(msg)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def published(name):
    """Asset name on GitHub, which turns '~' into '.'."""
    return name.replace('~', '.')


def image_sbom_name(version, variant, arch):
    return f'ucm-{release_version.file_version(version)}-image-{variant}-{arch}.cdx.json'


def prop(name, value):
    return {'name': name, 'value': str(value)}


def props_of(obj):
    out = {}
    for p in obj.get('properties', []) or []:
        out.setdefault(p.get('name'), []).append(p.get('value'))
    return out


def one_prop(obj, name):
    values = props_of(obj).get(name, [])
    return values[0] if len(values) == 1 else None


_SPDX_IDS = None


def spdx_ids():
    global _SPDX_IDS
    if _SPDX_IDS is None:
        _SPDX_IDS = set(json.loads((SCHEMA_DIR / 'spdx.schema.json').read_text())['enum'])
    return _SPDX_IDS


def license_entries(values):
    """CycloneDX licenses of declared values: SPDX id, expression, or name as written. Nothing for none."""
    out = []
    for v in values:
        v = (v or '').strip()
        if not v or v.upper() == 'UNKNOWN':
            continue
        if v in spdx_ids():
            out.append({'license': {'id': v}})
        elif re.search(r'\s(AND|OR|WITH)\s', v) or v.startswith('('):
            out.append({'expression': v})
        else:
            out.append({'license': {'name': v}})
    # An expression must stand alone in a licenses array
    exprs = [e for e in out if 'expression' in e]
    return exprs[:1] if exprs else out


def with_license(component, values, source):
    entries = license_entries(values)
    props = component.setdefault('properties', [])
    if entries:
        component['licenses'] = entries
        props.append(prop('ucm:license-source', source))
    else:
        props.append(prop('ucm:license', 'unknown'))
    return component


def component(ctype, name, role, ref, version=None, **extra):
    c = {'type': ctype, 'bom-ref': ref, 'name': name}
    if version is not None:
        c['version'] = version
    c.update({k.replace('_', '-'): v for k, v in extra.items() if v is not None})
    c.setdefault('properties', []).insert(0, prop('ucm:role', role))
    return c


def file_component(path, digest, role, ref, kind):
    c = component('file', path, role, ref, hashes=[{'alg': 'SHA-256', 'content': digest}])
    c['properties'].append(prop('ucm:kind', kind))
    return c


def document(subject, components, metadata_props, dependencies=None):
    doc = {
        'bomFormat': 'CycloneDX',
        'specVersion': SPEC_VERSION,
        'serialNumber': uuid.uuid4().urn,
        'version': 1,
        'metadata': {
            'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'tools': {'components': [{'type': 'application', 'name': 'ucm-sbom', 'version': '1'}]},
            'component': subject,
            'properties': metadata_props,
        },
        'components': components,
        # What the evidence gives, never everything a host will hold: no document claims completeness
        'compositions': [{'aggregate': 'incomplete', 'assemblies': [subject['bom-ref']]}],
    }
    if dependencies:
        doc['dependencies'] = dependencies
    return doc


def write_json(path, data):
    pathlib.Path(path).write_text(json.dumps(data, indent=1, sort_keys=False) + '\n')


def write_checksum(path):
    path = pathlib.Path(path)
    out = path.with_name(path.name + '.sha256')
    out.write_text(f'{sha256_file(path)}  {path.name}\n')
    return out


# ---- frontend -------------------------------------------------------------------------------------

def _lock_key(module_id, keys):
    """Longest lock entry (node_modules/a/node_modules/b) holding a bundled module path."""
    best = None
    for k in keys:
        if module_id.startswith(k + '/') and (best is None or len(k) > len(best)):
            best = k
    return best


def _installed_license(frontend, key):
    pkg = frontend / key / 'package.json'
    if not pkg.is_file():
        return [], None
    data = json.loads(pkg.read_text())
    if isinstance(data.get('license'), str):
        return [data['license']], 'package.json license'
    old = data.get('licenses')
    if isinstance(old, list):
        types = [x.get('type') for x in old if isinstance(x, dict) and x.get('type')]
        if types:
            return types, 'package.json licenses'
    return [], None


def cmd_frontend(args):
    frontend = pathlib.Path(args.frontend_dir)
    dist = pathlib.Path(args.dist)
    lock = json.loads((frontend / 'package-lock.json').read_text())
    record = json.loads(pathlib.Path(args.modules).read_text())
    if record.get('format') != 'ucm-bundle-modules':
        fail(f'{args.modules}: not a bundle modules record')
    packages = {k: v for k, v in lock.get('packages', {}).items() if k}
    dist_files = {p.relative_to(dist).as_posix(): sha256_file(p) for p in sorted(dist.rglob('*')) if p.is_file()}
    if not dist_files:
        fail(f'{dist}: empty build')
    emitted, first_party, unattributed = {}, 0, []
    for m in record['modules']:
        if not m.get('emitted'):
            continue
        mid = m['id']
        if mid.startswith('node_modules/'):
            key = _lock_key(mid, packages)
            if key is None:
                fail(f'bundled module {mid} belongs to no package-lock.json entry')
            emitted.setdefault(key, set()).update(c for c in m.get('chunks', []))
        elif m.get('virtual'):
            unattributed.append(mid)
        else:
            first_party += 1
    for chunks in emitted.values():
        for c in chunks:
            if c not in dist_files:
                fail(f'bundle record names {c}, absent from {dist}')
    out_pkgs = []
    for key, meta in sorted(packages.items()):
        if key in emitted:
            role = 'content'
        elif meta.get('dev'):
            continue  # build tools: never shipped, not listed (see the coverage note)
        else:
            role = 'build-input'
        values, source = ([meta['license']], 'package-lock.json') if meta.get('license') else \
            _installed_license(frontend, key)
        out_pkgs.append({'key': key, 'name': key.rsplit('node_modules/', 1)[1], 'version': meta.get('version'),
                         'role': role, 'licenses': values, 'license_source': source,
                         'integrity': meta.get('integrity'), 'resolved': meta.get('resolved'),
                         'dev': bool(meta.get('dev')), 'chunks': sorted(emitted.get(key, ()))})
    registry = {f['sha256']: f for f in json.loads(pathlib.Path(args.fonts).read_text())['fonts']}
    fonts = []
    for path, digest in dist_files.items():
        if path.endswith(FONT_SUFFIXES):
            fonts.append({'path': path, 'sha256': digest, **{k: v for k, v in registry.get(digest, {}).items()
                                                            if k not in ('file', 'sha256')}})
    write_json(args.output, {'format': 'ucm-frontend-build', 'version': 1, 'dist': dist_files,
                             'packages': out_pkgs, 'fonts': fonts, 'first_party_modules': first_party,
                             'unattributed_modules': sorted(set(unattributed))})


def frontend_components(frag, prefix):
    comps = []
    for p in frag['packages']:
        purl = f"pkg:npm/{p['name'].replace('@', '%40')}@{p['version']}" if p.get('version') else None
        c = component('library', p['name'], p['role'], f"npm:{p['key']}", version=p.get('version'), purl=purl)
        if p.get('integrity'):
            c['properties'].append(prop('ucm:npm-integrity', p['integrity']))
        if p['role'] == 'content':
            c['properties'].append(prop('ucm:evidence', 'bundle module record'))
            for chunk in p['chunks']:
                c['properties'].append(prop('ucm:emitted-in', f'{prefix}/{chunk}'))
        if p.get('dev'):
            c['properties'].append(prop('ucm:npm-dev', 'true'))
        comps.append(with_license(c, p['licenses'], p['license_source'] or ''))
    for f in frag['fonts']:
        c = file_component(f"{prefix}/{f['path']}", f['sha256'], 'content', f"font:{f['path']}", 'font')
        if f.get('family'):
            c['name'] = f"{f['family']} ({prefix}/{f['path']})"
            c['version'] = f['version']
            c['copyright'] = f['copyright']
            c['externalReferences'] = [{'type': 'website', 'url': f['source']}]
            c['properties'].append(prop('ucm:license-text', f"{prefix}/{f['license_file']}"))
        comps.append(with_license(c, [f.get('license')], 'font name table (ID 13)'))
    return comps


def check_dist(tree_files, frag, prefix):
    """The interface in the deliverable is the one this build recorded, file for file."""
    shipped = {p[len(prefix) + 1:]: h for p, h in tree_files.items() if p.startswith(prefix + '/')}
    if shipped != frag['dist']:
        missing = sorted(set(frag['dist']) - set(shipped))
        extra = sorted(set(shipped) - set(frag['dist']))
        changed = sorted(k for k in set(shipped) & set(frag['dist']) if shipped[k] != frag['dist'][k])
        fail(f'{prefix} differs from the recorded build: missing {missing[:3]}, extra {extra[:3]}, '
             f'changed {changed[:3]}')


# ---- packages -------------------------------------------------------------------------------------

_REQ = re.compile(r'^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<extras>\[[^\]]*\])?\s*(?P<spec>[^;#]*)'
                  r'(?:;(?P<marker>[^#]*))?')


def parse_requirements(text):
    out = []
    for line in text.splitlines():
        line = line.split(' #', 1)[0].strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-'):
            fail(f'requirements option not understood: {line}')
        m = _REQ.match(line)
        if not m:
            fail(f'requirement not understood: {line}')
        out.append({'name': m['name'], 'extras': m['extras'] or '', 'spec': m['spec'].strip(),
                    'marker': (m['marker'] or '').strip(), 'raw': line})
    return out


def native_setup_rules(text):
    """--no-deps installs and the FIPS-build substitutions of native-setup.sh."""
    nodeps = sorted(set(re.findall(r'pip"? install (?:--quiet )?--no-deps (\S+)', text)))
    subs, el9 = [], False
    body = re.search(r'^fips_requirements\(\) \{\n(.*?)^\}', text, re.S | re.M)
    for line in (body.group(1).splitlines() if body else []):
        if re.search(r'\bif\b.*\bel9\b', line):
            el9 = True
        elif line.strip() == 'fi':
            el9 = False
        m = re.search(r"sed (?:-i )?'s/\^(.+?)/(.+?)/'", line)
        if m:
            subs.append((m.group(1), m.group(2), 'UCM_FIPS_BUILD=1, EL9' if el9 else 'UCM_FIPS_BUILD=1'))
    return nodeps, subs


def requirement_components(reqs, source, subs=(), option=None):
    comps = []
    for r in reqs:
        c = component('library', r['name'] + r['extras'], 'install-requirement', f"pypi:{source}:{r['raw']}",
                      purl=f"pkg:pypi/{re.sub(r'[-_.]+', '-', r['name']).lower()}")
        c['properties'] += [prop('ucm:requirement', r['raw']), prop('ucm:requirement-source', source),
                            prop('ucm:resolved', 'at install, on the host')]
        if option:
            c['properties'].append(prop('ucm:install-option', option))
        for pattern, repl, cond in subs:
            new = re.sub('^' + pattern, repl, r['raw'])
            if new != r['raw']:
                c['properties'].append(prop('ucm:fips-native-build', f'{new} ({cond})'))
        comps.append(c)
    return comps


def parse_host_depends(text, fmt):
    out, field = [], None
    lines = []
    for line in text.splitlines():
        if line[:1] in (' ', '\t') and lines:
            lines[-1] += ' ' + line.strip()
        elif line.strip():
            lines.append(line.strip())
    for line in lines:
        field, _, value = line.partition(':')
        items = value.split(',') if fmt == 'deb' else [value]
        for item in items:
            item = item.strip()
            if item:
                out.append((field.strip(), item))
    return out


def tree_files(root):
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(root.rglob('*'))
            if p.is_file() and not p.is_symlink()}


def cmd_package(args):
    root = pathlib.Path(args.root)
    pkg = pathlib.Path(args.file)
    frag = json.loads(pathlib.Path(args.frontend).read_text())
    files = tree_files(root)
    app = 'opt/ucm'
    # The packages ship no Python environment: one in the tree would make this SBOM wrong
    venv = [p for p in files if '/site-packages/' in p or '.dist-info/' in p or p.startswith(app + '/venv/')]
    if venv:
        fail(f'{pkg.name} carries a Python environment ({venv[0]}): its SBOM would not describe it')
    req_path = f'{app}/requirements.txt'
    if req_path not in files:
        fail(f'{pkg.name}: no {req_path}')
    check_dist(files, frag, f'{app}/frontend/dist')
    missing = [p for p in (f'{LEGAL_DIRS[args.format]}/{name}' for name in LEGAL) if p not in files]
    if missing:
        fail(f'{pkg.name}: no {missing[0]}, a legal text every {args.format} package ships')
    asset = published(pkg.name)
    subject = {'type': 'application', 'bom-ref': 'subject', 'name': 'ucm', 'version': args.version,
               'hashes': [{'alg': 'SHA-256', 'content': sha256_file(pkg)}],
               'properties': [prop('ucm:asset', asset), prop('ucm:package-format', args.format)]}
    comps = [with_license(component('application', 'ucm', 'content', 'ucm', version=args.version,
                                    properties=[prop('ucm:first-party', 'true'), prop('ucm:commit', args.commit)]),
                          ['AGPL-3.0-only'], 'NOTICE')]
    comps += frontend_components(frag, f'{app}/frontend/dist')
    for path, digest in files.items():
        if path.rsplit('/', 1)[-1] in LEGAL:
            comps.append(file_component(path, digest, 'content', f'legal:{path}', 'legal-text'))
    nodeps, subs = native_setup_rules(_read(root / app / 'scripts' / 'native-setup.sh'))
    comps += requirement_components(parse_requirements((root / req_path).read_text()), req_path, subs)
    comps += requirement_components(parse_requirements('\n'.join(nodeps)), f'{app}/scripts/native-setup.sh',
                                    option='--no-deps')
    for i, (field, item) in enumerate(parse_host_depends(pathlib.Path(args.depends).read_text(), args.format)):
        c = component('library', re.split(r'[\s(<>=]', item, maxsplit=1)[0], 'install-requirement', f'host:{i}')
        c['properties'] += [prop('ucm:requirement', item), prop('ucm:relation', field),
                            prop('ucm:ecosystem', 'host package manager')]
        comps.append(c)
    meta = [prop('ucm:subject-kind', 'package'), prop('ucm:release-version', args.version),
            prop('ucm:not-covered', 'Python distributions: resolved by pip on the host at install time'),
            prop('ucm:not-covered', 'the host system and its packages'),
            prop('ucm:not-covered', 'anything installed or changed after installation'),
            prop('ucm:not-covered', 'npm build tools (devDependencies), not shipped')]
    if frag.get('unattributed_modules'):
        meta.append(prop('ucm:unattributed-bundle-modules', ', '.join(frag['unattributed_modules'])))
    doc = document(subject, comps, meta)
    write_json(args.output, doc)
    check_document(doc, args.version, schema=not args.no_schema)


def _read(path):
    return path.read_text() if path.is_file() else ''


# ---- images ---------------------------------------------------------------------------------------

_DIST_INFO = re.compile(r'^(?P<loc>(?:.*/)?(?:site|dist)-packages)/(?P<dir>[^/]+\.(?:dist|egg)-info)/'
                        r'(?:METADATA|PKG-INFO)$')
_BUNDLED_LIB = re.compile(r'^(?P<loc>(?:.*/)?site-packages)/[^/]+\.libs/[^/]+\.so[.0-9]*$')
_FIPS_SO = re.compile(r'^usr/lib/[^/]+/ossl-modules/fips\.so$')


def dockerfile_arg(text, name):
    values = re.findall(rf'^ARG {name}=(\S+)$', text, re.M)
    if len(values) != 1:
        fail(f'Dockerfile: ARG {name} with a default must appear once, found {len(values)}')
    return values[0]


def scan_rootfs(fileobj, app):
    """Python distributions, wheel-bundled libraries, fips.so, the interface and legal texts of an
    exported image filesystem, read without running anything from it."""
    dists, libs, fips, files = [], [], [], {}
    with tarfile.open(fileobj=fileobj, mode='r|*') as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = member.name.lstrip('./')
            want = (_DIST_INFO.match(name) or _BUNDLED_LIB.match(name) or _FIPS_SO.match(name)
                    or name.startswith(app + '/frontend/dist/') or name in [f'{app}/{x}' for x in LEGAL])
            if not want:
                continue
            data = tar.extractfile(member).read()
            m = _DIST_INFO.match(name)
            if m:
                meta = email.parser.BytesParser().parsebytes(data, headersonly=True)
                dists.append({'loc': m['loc'], 'name': meta.get('Name'), 'version': meta.get('Version'),
                              'expression': meta.get('License-Expression'), 'license': meta.get('License'),
                              'classifiers': [c for c in meta.get_all('Classifier', []) if c.startswith('License ::')]})
            elif _BUNDLED_LIB.match(name):
                libs.append((name, sha256_bytes(data)))
            elif _FIPS_SO.match(name):
                fips.append((name, sha256_bytes(data)))
            else:
                files[name] = sha256_bytes(data)
    return dists, libs, fips, files


def _python_license(d):
    if d['expression']:
        return [d['expression']], 'METADATA License-Expression'
    lic = (d['license'] or '').strip()
    if lic and '\n' not in lic and len(lic) <= 80:
        return [lic], 'METADATA License'
    if d['classifiers']:
        return [c.split(' :: ')[-1] for c in d['classifiers']], 'METADATA classifier'
    return [], None


def cmd_image(args):
    variant, arch = args.variant, args.arch
    if variant not in VARIANTS.values() or arch not in ARCHES:
        fail(f'unknown image {variant}/{arch}')
    digest = args.digest
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        fail(f'not an image digest: {digest!r}')
    config = json.loads(pathlib.Path(args.image_config).read_text())
    config = config[0] if isinstance(config, list) else config
    if config.get('Architecture') != arch:
        fail(f'the scanned image is {config.get("Architecture")}, not {arch}')
    repo_digests = config.get('RepoDigests') or []
    if not any(r.endswith('@' + digest) for r in repo_digests):
        fail(f'the exported image is not {digest} (it is {repo_digests})')
    trivy = json.loads(pathlib.Path(args.trivy).read_text())
    if trivy.get('bomFormat') != 'CycloneDX' or trivy.get('specVersion') != SPEC_VERSION:
        fail('the scanner output is not CycloneDX ' + SPEC_VERSION)
    troot = trivy.get('metadata', {}).get('component') or {}
    if not any((v or '').endswith('@' + digest) for v in props_of(troot).get('aquasecurity:trivy:RepoDigest', [])):
        fail(f'the scanner did not scan {digest}')
    frag = json.loads(pathlib.Path(args.frontend).read_text())
    app = 'opt/ucm'
    stream = sys.stdin.buffer if args.rootfs_tar == '-' else open(args.rootfs_tar, 'rb')
    with stream:
        dists, libs, fips, files = scan_rootfs(stream, app)
    check_dist(files, frag, f'{app}/frontend/dist')
    ref = troot.get('bom-ref') or 'subject'
    subject = {'type': 'container', 'bom-ref': ref, 'name': args.repository, 'version': args.version,
               'hashes': [{'alg': 'SHA-256', 'content': digest.split(':', 1)[1]}],
               'purl': f"pkg:oci/{args.repository.rsplit('/', 1)[-1]}@{digest.replace(':', '%3A')}?arch={arch}",
               'properties': [prop('ucm:image-digest', digest), prop('ucm:variant', variant), prop('ucm:arch', arch)]}
    comps = []
    for c in trivy.get('components', []):
        c = json.loads(json.dumps(c))
        c.setdefault('properties', []).insert(0, prop('ucm:role', 'content'))
        c['properties'].append(prop('ucm:evidence', 'trivy (os packages)'))
        if not c.get('licenses'):
            c['properties'].append(prop('ucm:license', 'unknown'))
        comps.append(c)
    comps.append(with_license(component('application', 'ucm', 'content', 'ucm', version=args.version,
                                        properties=[prop('ucm:first-party', 'true'), prop('ucm:commit', args.commit)]),
                              ['AGPL-3.0-only'], 'NOTICE'))
    py = re.findall(r'^PYTHON_VERSION=(\S+)$', '\n'.join(config.get('Config', {}).get('Env') or []), re.M)
    if py:
        c = component('application', 'cpython', 'content', 'cpython', version=py[0])
        c['properties'].append(prop('ucm:evidence', 'image configuration PYTHON_VERSION of the base image'))
        comps.append(with_license(c, [], ''))
    seen = set()
    for d in sorted(dists, key=lambda d: (d['loc'], (d['name'] or '').lower())):
        if not d['name'] or not d['version']:
            fail(f"{d['loc']}: a distribution without a name or a version")
        key = (d['loc'], d['name'].lower())
        if key in seen:
            fail(f"{d['loc']}: {d['name']} installed twice")
        seen.add(key)
        c = component('library', d['name'], 'content', f"pypi:{d['loc']}:{d['name']}", version=d['version'],
                      purl=f"pkg:pypi/{re.sub(r'[-_.]+', '-', d['name']).lower()}@{d['version']}")
        c['properties'] += [prop('ucm:location', d['loc']), prop('ucm:evidence', 'installed METADATA')]
        comps.append(with_license(c, *_python_license(d)))
    for path, h in sorted(libs):
        c = file_component(path, h, 'content', f'lib:{path}', 'library bundled in a wheel')
        c['properties'].append(prop('ucm:license', 'unknown'))
        comps.append(c)
    dockerfile = pathlib.Path(args.dockerfile).read_text()
    if variant == 'fips':
        if len(fips) != 1:
            fail(f'the FIPS image holds {len(fips)} fips.so, not one')
        if any(c.get('name') in ('fips.so', 'OpenSSL FIPS Provider') for c in comps):
            fail('the FIPS provider is already listed')
        version = dockerfile_arg(dockerfile, 'FIPS_PROVIDER_VERSION')
        source = dockerfile_arg(dockerfile, 'FIPS_PROVIDER_SHA256')
        path, h = fips[0]
        if h == source:
            fail('the provider binary hash equals its source archive hash')
        c = component('library', 'OpenSSL FIPS Provider', 'content', 'fips-provider', version=version,
                      hashes=[{'alg': 'SHA-256', 'content': h}],
                      externalReferences=[{'type': 'distribution', 'url': 'https://github.com/openssl/openssl/'
                                           f'releases/download/openssl-{version}/openssl-{version}.tar.gz',
                                           'hashes': [{'alg': 'SHA-256', 'content': source}]}])
        c['properties'] += [prop('ucm:path', path), prop('ucm:evidence', 'built from source by the Dockerfile'),
                            prop('ucm:source-sha256', source)]
        comps.append(with_license(c, [], ''))
    elif fips:
        fail(f'the standard image holds {fips[0][0]}')
    comps += frontend_components(frag, f'{app}/frontend/dist')
    for path, h in sorted(files.items()):
        if path.rsplit('/', 1)[-1] in LEGAL and not path.startswith(f'{app}/frontend/'):
            comps.append(file_component(path, h, 'content', f'legal:{path}', 'legal-text'))
    meta = [prop('ucm:subject-kind', 'image'), prop('ucm:release-version', args.version),
            prop('ucm:not-covered', 'code statically linked into native extensions, unless listed'),
            prop('ucm:not-covered', 'binaries outside the OS package database, Python METADATA and fips.so'),
            prop('ucm:not-covered', 'the host, its kernel and container runtime, volumes and external services'),
            prop('ucm:not-covered', 'anything installed or changed after the image was built'),
            prop('ucm:not-covered', 'npm build tools (devDependencies), not shipped')]
    doc = document(subject, comps, meta, trivy.get('dependencies'))
    if pathlib.Path(args.output).is_dir():
        args.output = str(pathlib.Path(args.output) / image_sbom_name(args.version, variant, arch))
    write_json(args.output, doc)
    check_document(doc, args.version, schema=not args.no_schema)


# ---- checks ---------------------------------------------------------------------------------------

@functools.cache
def schema_validator():
    try:
        import jsonschema
        import referencing
    except ImportError:
        fail('jsonschema is not installed: scripts/ci/sbom-venv.sh installs the pinned validator')
    resources = []
    for f in SCHEMA_DIR.glob('*.schema.json'):
        contents = json.loads(f.read_text())
        resources.append((contents['$id'], referencing.Resource.from_contents(contents)))
    registry = referencing.Registry().with_resources(resources)
    bom = json.loads((SCHEMA_DIR / 'bom-1.6.schema.json').read_text())
    return jsonschema.Draft7Validator(bom, registry=registry)


def check_document(doc, version, schema=True, kind=None):
    if not isinstance(doc, dict) or doc.get('bomFormat') != 'CycloneDX' or doc.get('specVersion') != SPEC_VERSION:
        fail(f'not a CycloneDX {SPEC_VERSION} document')
    if schema:
        errors = sorted(schema_validator().iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            e = errors[0]
            fail(f"schema: {'/'.join(map(str, e.path))}: {e.message[:200]}")
    meta = doc.get('metadata', {})
    subject = meta.get('component')
    if not subject or not subject.get('bom-ref'):
        fail('no subject')
    mprops = props_of(meta)
    if mprops.get('ucm:release-version') != [version]:
        fail(f"the document is for {mprops.get('ucm:release-version')}, not {version}")
    if kind and mprops.get('ucm:subject-kind') != [kind]:
        fail(f"the document describes {mprops.get('ucm:subject-kind')}, not a {kind}")
    if not mprops.get('ucm:not-covered'):
        fail('the coverage limits are missing')
    if not any(c.get('aggregate') not in (None, 'complete') for c in doc.get('compositions', [])):
        fail('the document claims completeness')
    refs = [subject['bom-ref']] + [c.get('bom-ref') for c in doc.get('components', [])]
    if len(refs) != len(set(refs)):
        fail('duplicate bom-ref')
    for c in doc.get('components', []):
        p = props_of(c)
        role = p.get('ucm:role', [None])
        if len(role) != 1 or role[0] not in ROLES:
            fail(f"{c.get('name')}: role {role}")
        if role[0] == 'install-requirement' and 'version' in c:
            fail(f"{c.get('name')}: an install requirement carries a version")
        shipped_or_built = role[0] in ('content', 'build-input') and p.get('ucm:kind') != ['legal-text']
        if shipped_or_built and not c.get('licenses') and p.get('ucm:license') != ['unknown']:
            fail(f"{c.get('name')}: no license and not marked unknown")
    return doc


def _load(path):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError) as e:
        fail(f'{pathlib.Path(path).name}: unreadable ({e.__class__.__name__})')


def _check_sum_file(path):
    side = path.with_name(path.name + '.sha256')
    if not side.is_file():
        fail(f'{path.name}: no .sha256')
    if side.read_text().split() != [sha256_file(path), path.name]:
        fail(f'{side.name} does not match {path.name}')


def _subject(doc):
    return doc['metadata']['component']


def expected_documents(directory, digests, version):
    """(kind, subject, subject hash, variant, arch, SBOM file name) of every deliverable present."""
    d = pathlib.Path(directory)
    out = []
    for f in sorted(d.iterdir()):
        if f.is_file() and f.name.endswith(('.deb', '.rpm')):
            out.append(('package', published(f.name), sha256_file(f), None, None, published(f.name) + '.cdx.json'))
    for sub in sorted(pathlib.Path(digests).iterdir()) if digests else []:
        m = re.fullmatch(r'(std|fips)-digest-(amd64|arm64)', sub.name)
        if not m:
            fail(f'unexpected digest artifact {sub.name}')
        found = [p.name for p in sub.iterdir()]
        if len(found) != 1 or not HEX64.fullmatch(found[0]):
            fail(f'{sub.name}: not exactly one digest')
        variant = VARIANTS[m[1]]
        out.append(('image', f'sha256:{found[0]}', found[0], variant, m[2], image_sbom_name(version, variant, m[2])))
    return out


def cmd_index(args):
    entries = []
    for kind, subject, digest, variant, arch, sbom in expected_documents(args.dir, args.digests, args.version):
        path = pathlib.Path(args.dir) / sbom
        if not path.is_file():
            fail(f'{subject}: no SBOM {sbom}')
        entries.append({'kind': kind, 'subject': subject, 'subject-sha256': digest, 'variant': variant,
                        'arch': arch, 'sbom': sbom, 'sbom-sha256': sha256_file(path)})
    out = pathlib.Path(args.dir) / INDEX
    write_json(out, {'format': 'ucm-sbom-index', 'version': 1, 'release': args.version, 'documents': entries})
    write_checksum(out)


def cmd_validate(args):
    d = pathlib.Path(args.dir)
    expected = expected_documents(d, args.digests, args.version)
    kinds = {k for k, *_ in expected}
    if 'package' not in kinds:
        fail('no package in the release directory')
    if args.digests and 'image' not in kinds:
        fail('no image digest')
    validator_schema = not args.no_schema
    names = set()
    for kind, subject, digest, variant, arch, sbom in expected:
        path = d / sbom
        if not path.is_file():
            fail(f'{subject}: no SBOM {sbom}')
        doc = check_document(_load(path), args.version, schema=validator_schema, kind=kind)
        _check_sum_file(path)
        subj = _subject(doc)
        hashes = [h.get('content') for h in subj.get('hashes', []) if h.get('alg') == 'SHA-256']
        if hashes != [digest]:
            fail(f'{sbom} describes another file or image than {subject}')
        sp = props_of(subj)
        if kind == 'package' and sp.get('ucm:asset') != [subject]:
            fail(f"{sbom} names the asset {sp.get('ucm:asset')}, not {subject}")
        if kind == 'image' and (sp.get('ucm:variant') != [variant] or sp.get('ucm:arch') != [arch]
                                or sp.get('ucm:image-digest') != [subject]):
            fail(f'{sbom} is not the SBOM of the {variant} {arch} image {subject}')
        names.add(sbom)
    stray = sorted(f.name for f in d.glob('*.cdx.json') if f.name not in names)
    if stray:
        fail(f'SBOM without a deliverable: {stray}')
    index_path = d / INDEX
    index = _load(index_path)
    _check_sum_file(index_path)
    want = sorted((e[5], sha256_file(d / e[5]), e[1]) for e in expected)
    have = sorted((e.get('sbom'), e.get('sbom-sha256'), e.get('subject')) for e in index.get('documents', []))
    if index.get('release') != args.version or have != want:
        fail(f'{INDEX} does not list exactly the SBOMs of this release')
    print(f'{len(expected)} deliverables, each with its SBOM')


def cmd_images(args):
    """Before an image index is tagged: one SBOM per architecture, each naming one of its digests."""
    digests = {p.name for p in pathlib.Path(args.digests).iterdir() if p.is_file()}
    seen = {}
    for path in sorted(pathlib.Path(args.sboms).glob('*.cdx.json')):
        doc = check_document(_load(path), args.version, schema=not args.no_schema, kind='image')
        _check_sum_file(path)
        sp = props_of(_subject(doc))
        arch = (sp.get('ucm:arch') or [None])[0]
        if sp.get('ucm:variant') != [args.variant] or arch in seen:
            fail(f'{path.name}: not the one {args.variant} SBOM of {arch}')
        if path.name != image_sbom_name(args.version, args.variant, arch):
            fail(f'{path.name}: not named after its image')
        seen[arch] = (sp.get('ucm:image-digest') or [''])[0].removeprefix('sha256:')
    if sorted(seen) != sorted(ARCHES) or set(seen.values()) != digests:
        fail(f'the {args.variant} SBOMs cover {sorted(seen.items())}, not the digests {sorted(digests)}')
    print(f'{args.variant}: one SBOM per architecture, each on its digest')


def cmd_check(args):
    for path in args.files:
        check_document(_load(path), args.version, schema=not args.no_schema, kind=args.kind)
        _check_sum_file(pathlib.Path(path))
        print(f'{path}: ok')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('frontend')
    f.add_argument('--frontend-dir', required=True)
    f.add_argument('--dist', required=True)
    f.add_argument('--modules', required=True)
    f.add_argument('--fonts', default=str(FONTS))
    f.add_argument('-o', '--output', required=True)
    for name in ('package', 'image'):
        p = sub.add_parser(name)
        p.add_argument('--version', required=True)
        p.add_argument('--frontend', required=True)
        p.add_argument('--commit', required=True)
        p.add_argument('-o', '--output', required=True)
        p.add_argument('--no-schema', action='store_true')
        if name == 'package':
            p.add_argument('--root', required=True)
            p.add_argument('--file', required=True)
            p.add_argument('--format', choices=('deb', 'rpm'), required=True)
            p.add_argument('--depends', required=True)
        else:
            p.add_argument('--rootfs-tar', required=True)
            p.add_argument('--image-config', required=True)
            p.add_argument('--trivy', required=True)
            p.add_argument('--digest', required=True)
            p.add_argument('--repository', required=True)
            p.add_argument('--variant', required=True)
            p.add_argument('--arch', required=True)
            p.add_argument('--dockerfile', required=True)
    c = sub.add_parser('check')
    c.add_argument('files', nargs='+')
    c.add_argument('--version', required=True)
    c.add_argument('--kind', choices=('package', 'image'))
    c.add_argument('--no-schema', action='store_true')
    i = sub.add_parser('images')
    i.add_argument('--variant', choices=sorted(VARIANTS.values()), required=True)
    i.add_argument('--digests', required=True)
    i.add_argument('--sboms', required=True)
    i.add_argument('--version', required=True)
    i.add_argument('--no-schema', action='store_true')
    for name in ('index', 'validate'):
        p = sub.add_parser(name)
        p.add_argument('--dir', required=True)
        p.add_argument('--digests')
        p.add_argument('--version', required=True)
        if name == 'validate':
            p.add_argument('--no-schema', action='store_true')
    args = ap.parse_args(argv)
    try:
        if getattr(args, 'version', None):
            release_version.parse(args.version)
        {'frontend': cmd_frontend, 'package': cmd_package, 'image': cmd_image, 'images': cmd_images,
         'check': cmd_check, 'index': cmd_index, 'validate': cmd_validate}[args.cmd](args)
        if args.cmd in ('package', 'image'):
            write_checksum(args.output)
    except (SbomError, ValueError) as e:
        print(f'::error::SBOM: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
