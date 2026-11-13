#!/usr/bin/env python3
"""Release version grammar, conversions, notes and `latest` rule, shared by the workflows.

Accepted: X.Y, X.Y-rcN, X.Y.Z, X.Y.Z-rcN (Z >= 1). Usage: release_version.py <command> <version> [args].
"""
import re
import sys

VERSION_RE = re.compile(
    r'(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)'
    r'(?:\.(?P<patch>[1-9][0-9]*))?(?:-(?P<rc>rc[0-9]+))?'
)


def parse(version):
    m = VERSION_RE.fullmatch(version or '')
    if not m:
        raise ValueError(f'Invalid version: {version}')
    return m


def is_stable(version):
    return parse(version).group('rc') is None


def numeric(version):
    m = parse(version)
    return (int(m.group('major')), int(m.group('minor')), int(m.group('patch') or 0))


def deb_version(version):
    return parse(version).string.replace('-', '~')


def rpm_version(version):
    return deb_version(version)


def tar_version(version):
    return parse(version).string.replace('-', '_')


def file_version(version):
    """Release asset names carry dots where the package version has '~' or '-'."""
    return parse(version).string.replace('-', '.')


def npm_version(version):
    """Valid semver: X.Y gets a .0 patch, X.Y.Z is kept."""
    m = parse(version)
    base = f"{m.group('major')}.{m.group('minor')}.{m.group('patch') or 0}"
    return base + (f"-{m.group('rc')}" if m.group('rc') else '')


def asset_names(version):
    fv = file_version(version)
    return {
        'deb': f'ucm_{fv}_all.deb',
        'rpm': f'ucm-{fv}-1.fc43.noarch.rpm',
        'rpm_el9': f'ucm-el9-{fv}-1.el9.noarch.rpm',
    }


def changelog_section(version, text):
    """Body of `## [version]` up to the next `## [` heading, blank lines dropped, led by one blank line."""
    parse(version)
    lines = text.splitlines()
    heads = [(re.compile(r'^## \[' + re.escape(version) + r'\]'), '## ['),
             (re.compile(r'^## ' + re.escape(version) + r'(\s|$)'), '## ')]
    for head, stop in heads:
        for i, line in enumerate(lines):
            if head.match(line):
                body = []
                for nxt in lines[i + 1:]:
                    if nxt.startswith(stop):
                        break
                    body.append(nxt)
                return '\n'.join([''] + [b for b in body if b.strip()]) + '\n'
    return ''


def is_latest(version, published):
    """True when a stable `version` is not lower than any stable published tag."""
    if not is_stable(version):
        return False
    top = numeric(version)
    for tag in published:
        tag = tag.strip().removeprefix('refs/tags/').removeprefix('v')
        if VERSION_RE.fullmatch(tag) and is_stable(tag) and numeric(tag) > top:
            return False
    return True


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, version = argv[1], argv[2]
    try:
        if cmd == 'validate':
            parse(version)
        elif cmd == 'deb':
            print(deb_version(version))
        elif cmd == 'rpm':
            print(rpm_version(version))
        elif cmd == 'tar':
            print(tar_version(version))
        elif cmd == 'file':
            print(file_version(version))
        elif cmd == 'npm':
            print(npm_version(version))
        elif cmd == 'assets':
            print('\n'.join(asset_names(version).values()))
        elif cmd == 'notes':
            path = argv[3] if len(argv) > 3 else 'CHANGELOG.md'
            with open(path, encoding='utf-8') as fh:
                sys.stdout.write(changelog_section(version, fh.read()))
        elif cmd == 'latest':
            tags = sys.stdin.read().splitlines()
            print('true' if is_latest(version, tags) else 'false')
        else:
            print(f'Unknown command: {cmd}', file=sys.stderr)
            return 2
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
