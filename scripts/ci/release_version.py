#!/usr/bin/env python3
"""Release version grammar, conversions, release notes, `latest` and line rules, shared by the workflows and scripts.

Tags: X.Y, X.Y-rcN (this line), X.Y.Z, X.Y.Z-rcN with Z >= 1 (maintenance of the previous line).
A development version (X.Y-dev, X.Y.Z-dev) has an npm form but is never a tag.
Usage: release_version.py <validate|deb|rpm|tar|file|npm|chart|prerelease|assets|notes|latest|line> <version> [CHANGELOG] [--rehearsal]
`notes` stops the changes on a whole entry past NOTES_CHANGES_BUDGET characters, then links
`--changelog-url URL` (default CHANGELOG.md) for the rest.
`matches <version> <file>` exits 1, naming both values, when the file (whitespace stripped) is not that version.
`latest` reads the published tags (refs/tags/vX or vX, one per line) on stdin and prints true or false.
`line` reads them the same way and prints the line tag (the major) to apply, or an empty line.
"""
import re
import sys

# GitHub refuses a release body over 125 000 characters (HTTP 422): the changes stop under this
# budget, which leaves the page's heading and Installation part room under the limit.
NOTES_CHANGES_BUDGET = 110_000
_ENTRY_START = re.compile(r'#|[-*+] |[0-9]+[.)] ')
_FENCE = re.compile(r'\s*(```|~~~)')

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
    """Valid semver: X.Y gets a .0 patch, X.Y.Z is kept, a -dev suffix is kept."""
    if (version or '').endswith('-dev'):
        base = version[:-4]
        if not is_stable(base):
            raise ValueError(f'Invalid version: {version}')
        return npm_version(base) + '-dev'
    m = parse(version)
    base = f"{m.group('major')}.{m.group('minor')}.{m.group('patch') or 0}"
    return base + (f"-{m.group('rc')}" if m.group('rc') else '')


def chart_version(version):
    """Helm chart version of a tag: the semver form, the chart being versioned with its application."""
    parse(version)
    return npm_version(version)


def asset_names(version):
    fv = file_version(version)
    return {
        'deb': f'ucm_{fv}_all.deb',
        'rpm': f'ucm-{fv}-1.fc43.noarch.rpm',
        'rpm_el9': f'ucm-el9-{fv}-1.el9.noarch.rpm',
        'rpm_el10': f'ucm-el10-{fv}-1.el10.noarch.rpm',
    }


def _section(heading, text, stop):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if heading.match(line):
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith(stop):
                    break
                body.append(nxt)
            kept = [b for b in body if b.strip()]
            # Sub-headings alone are not entries.
            if not any(not b.startswith('#') for b in kept):
                return ''
            return '\n'.join([''] + kept) + '\n'
    return ''


def changelog_section(version, text):
    """Body of `## [version]` up to the next `## [` heading, blank lines dropped, led by one blank
    line; empty when it holds no entry (sub-headings alone are none)."""
    parse(version)
    return (_section(re.compile(r'^## \[' + re.escape(version) + r'\]'), text, '## [')
            or _section(re.compile(r'^## ' + re.escape(version) + r'(\s|$)'), text, '## '))


def _blocks(lines):
    """Lines grouped by entry: a heading or a list item at the margin opens one, never inside
    fenced code; indented lines and code blocks stay with their entry."""
    blocks, fence = [], None
    for line in lines:
        if not blocks or (fence is None and _ENTRY_START.match(line)):
            blocks.append([])
        blocks[-1].append(line)
        m = _FENCE.match(line)
        if m and fence is None:
            fence = m.group(1)
        elif m and m.group(1) == fence:
            fence = None
    return blocks


def cut_changes(body, budget=NOTES_CHANGES_BUDGET, changelog_url='CHANGELOG.md'):
    """`body` itself within `budget` characters; else its first whole entries and a closing
    sentence that links the CHANGELOG for the rest, all within `budget`."""
    if len(body) <= budget:
        return body
    blocks = _blocks(body.splitlines()[1:])
    total = sum(1 for b in blocks if not b[0].startswith('#'))

    def note(kept_entries):
        return (f'The list stops after {kept_entries} of {total} entries to fit the release page: '
                f'the rest is in [CHANGELOG.md]({changelog_url}).\n')

    room, kept = budget - len('\n' + '\n') - len(note(total)), []
    for block in blocks:
        room -= sum(len(line) + 1 for line in block)
        if room < 0:
            break
        kept.append(block)
    while kept and kept[-1][0].startswith('#'):
        kept.pop()  # a sub-heading whose entries all fell past the cut
    entries = sum(1 for b in kept if not b[0].startswith('#'))
    return '\n' + ''.join(line + '\n' for b in kept for line in b) + '\n' + note(entries)


def release_notes(version, text, rehearsal=False, changelog_url='CHANGELOG.md'):
    """Its own section when it has entries; a RC without one ships `[Unreleased]`, a stable fails.

    A rehearsal of a stable runs before its bump commit: it borrows `[Unreleased]` and warns instead.
    """
    body = changelog_section(version, text)
    if body.strip():
        return cut_changes(body, changelog_url=changelog_url)
    if is_stable(version):
        missing = f'CHANGELOG.md has no [{version}] section with entries for {version}'
        if not rehearsal:
            raise ValueError(missing)
        print(f'::warning::{missing}: the rehearsal takes [Unreleased]', file=sys.stderr)
    body = _section(re.compile(r'^## \[Unreleased\]'), text, '## [')
    if not body.strip():
        raise ValueError(f'CHANGELOG.md has no [{version}] or [Unreleased] section with entries for {version}')
    return cut_changes(body, changelog_url=changelog_url)


def _stable_tags(published):
    for tag in published:
        tag = tag.strip().removeprefix('refs/tags/').removeprefix('v')
        if VERSION_RE.fullmatch(tag) and is_stable(tag):
            yield numeric(tag)


def is_latest(version, published):
    """True for a stable `version` that no stable published tag exceeds: never a RC, never an older line."""
    if not is_stable(version):
        return False
    top = numeric(version)
    return not any(tag > top for tag in _stable_tags(published))


def line_tag(version, published):
    """The major of a stable `version` that no stable published tag of the same major exceeds, else ''.

    Unlike `latest`, a higher major does not count: a 2.254.N released after 3.0 still takes `2`."""
    if not is_stable(version):
        return ''
    top = numeric(version)
    if any(tag[0] == top[0] and tag > top for tag in _stable_tags(published)):
        return ''
    return str(top[0])


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
        elif cmd == 'chart':
            print(chart_version(version))
        elif cmd == 'prerelease':
            print('false' if is_stable(version) else 'true')
        elif cmd == 'assets':
            print('\n'.join(asset_names(version).values()))
        elif cmd == 'latest':
            print('true' if is_latest(version, sys.stdin.read().splitlines()) else 'false')
        elif cmd == 'line':
            print(line_tag(version, sys.stdin.read().splitlines()))
        elif cmd == 'matches':
            if len(argv) < 4:
                print(__doc__, file=sys.stderr)
                return 2
            try:
                with open(argv[3], encoding='utf-8') as fh:
                    found = fh.read().strip()
            except (OSError, ValueError) as exc:
                print(f'::error::{argv[3]} cannot be read: {exc}', file=sys.stderr)
                return 1
            if found != version:
                print(f'::error::{argv[3]} says {found!r} but the tag is {version!r}', file=sys.stderr)
                return 1
        elif cmd == 'notes':
            rehearsal, url, rest, args = False, 'CHANGELOG.md', [], iter(argv[3:])
            for arg in args:
                if arg == '--rehearsal':
                    rehearsal = True
                elif arg == '--changelog-url':
                    url = next(args, None)
                    if not url:
                        print('--changelog-url needs a URL', file=sys.stderr)
                        return 2
                else:
                    rest.append(arg)
            path = rest[0] if rest else 'CHANGELOG.md'
            try:
                with open(path, encoding='utf-8') as fh:
                    text = fh.read()
            except (OSError, ValueError) as exc:
                print(f'::error::{path} cannot be read: {exc}', file=sys.stderr)
                return 1
            sys.stdout.write(release_notes(version, text, rehearsal, url))
        else:
            print(f'Unknown command: {cmd}', file=sys.stderr)
            return 2
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
