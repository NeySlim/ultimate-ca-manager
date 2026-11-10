"""Loaded by every process of an HA bench node (on its PYTHONPATH only).

A process that touches an installation path records it in UCM_HA_GUARD_FILE
and kills its whole node, so the bench fails instead of reading or writing the host.
"""
import os
import signal
import sys

_FORBIDDEN = ('/etc/ucm', '/opt/ucm', '/var/lib/softhsm', '/var/log/ucm')
_PATH_EVENTS = frozenset({
    'open', 'os.chmod', 'os.chown', 'os.mkdir', 'os.rename', 'os.remove', 'os.rmdir',
    'os.link', 'os.symlink', 'os.listdir', 'os.scandir', 'os.truncate', 'os.utime',
    'shutil.copyfile', 'shutil.rmtree', 'shutil.move',
})
_REPORT = os.environ.get('UCM_HA_GUARD_FILE')


def _path(value):
    if isinstance(value, (str, bytes, os.PathLike)):
        try:
            return os.path.abspath(os.fsdecode(os.fspath(value)))
        except (TypeError, ValueError):
            return None
    return None


def _guard(event, args):
    if event not in _PATH_EVENTS or not args:
        return
    path = _path(args[0])
    if path is None or not (path in _FORBIDDEN or path.startswith(tuple(p + '/' for p in _FORBIDDEN))):
        return
    line = f'{os.getpid()} {event} {path}\n'.encode()
    if _REPORT:
        fd = os.open(_REPORT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.write(fd, line)
        os.close(fd)
    os.write(2, b'HA bench guard: ' + line)
    os.killpg(os.getpgid(0), signal.SIGKILL)


if _REPORT:
    sys.addaudithook(_guard)
