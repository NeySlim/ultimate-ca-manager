"""Without UCM_SECRET_KEY the image keeps the key it generated at the first start (#457).

A new key at each start invalidated every session and token signed with it at each restart.
The helper is sourced in a sandbox: tmp_path stands for /etc/ucm, nothing of the host is touched.
"""
import os
import pathlib
import stat
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'docker' / 'secret-key.sh'


def _start(directory, **env):
    script = f'. {HELPER}; ucm_secret_key "$1" || exit 3; printf "KEY=%s\\n" "$UCM_SECRET_KEY"'
    r = subprocess.run(['bash', '-c', script, '_', str(directory)], env={'PATH': '/usr/bin:/bin', **env},
                       capture_output=True, text=True)
    keys = [line[4:] for line in r.stdout.splitlines() if line.startswith('KEY=')]
    return r, keys[0] if keys else None


def test_the_key_generated_at_the_first_start_is_kept_for_the_next(tmp_path):
    first, key = _start(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    assert len(key) == 64 and int(key, 16) >= 0
    held = tmp_path / 'secret.key'
    assert held.read_text().strip() == key
    assert stat.S_IMODE(held.stat().st_mode) == 0o600
    if os.geteuid() == 0:
        assert held.stat().st_uid == 1000
    again, same = _start(tmp_path)
    assert again.returncode == 0 and same == key
    assert sorted(p.name for p in tmp_path.iterdir()) == ['secret.key']


def test_an_explicit_key_wins_and_nothing_is_written(tmp_path):
    (tmp_path / 'secret.key').write_text('kept-from-before' * 4 + '\n')
    r, key = _start(tmp_path, UCM_SECRET_KEY='from-the-environment')
    assert r.returncode == 0 and key == 'from-the-environment'
    assert (tmp_path / 'secret.key').read_text() == 'kept-from-before' * 4 + '\n'
    empty = tmp_path / 'empty'
    empty.mkdir()
    _start(empty, UCM_SECRET_KEY='from-the-environment')
    assert list(empty.iterdir()) == []


def test_a_link_at_the_name_is_replaced_never_written_through(tmp_path):
    target = tmp_path / 'elsewhere'
    target.write_text('')
    conf = tmp_path / 'conf'
    conf.mkdir()
    (conf / 'secret.key').symlink_to(target)
    r, key = _start(conf)
    assert r.returncode == 0, r.stdout + r.stderr
    assert target.read_text() == ''
    assert not (conf / 'secret.key').is_symlink()
    assert (conf / 'secret.key').read_text().strip() == key


def test_a_blank_file_is_replaced_by_a_new_key(tmp_path):
    (tmp_path / 'secret.key').write_text('\n')
    r, key = _start(tmp_path)
    assert r.returncode == 0 and len(key) == 64
    assert (tmp_path / 'secret.key').read_text().strip() == key


def test_an_unwritable_directory_starts_with_a_key_for_this_start_only(tmp_path):
    missing = tmp_path / 'not-mounted' / 'etc'
    r, key = _start(missing)
    assert r.returncode == 0 and len(key) == 64
    assert 'UCM_SECRET_KEY' in r.stdout + r.stderr
    assert not missing.exists()


def test_the_entrypoint_takes_the_kept_key_after_the_ha_check():
    # ordre textuel seulement ; le comportement est prouvé par les tests de secret-key.sh ci-dessus
    text = (ROOT / 'docker' / 'entrypoint.sh').read_text()
    assert 'generate_secret)}' not in text
    assert text.index('check_ha_secret || exit 1') < text.index('ucm_secret_key /etc/ucm || exit 1')
    assert 'COPY --chown=ucm:ucm docker/secret-key.sh /secret-key.sh' in (ROOT / 'Dockerfile').read_text()
