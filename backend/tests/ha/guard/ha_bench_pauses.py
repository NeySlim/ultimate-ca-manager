"""HA bench only: pauses a node's background jobs at named points, from files the bench writes.

While ``<UCM_HA_PAUSE_DIR>/pause-<point>`` exists, a process of the node that reaches the
point waits, with ``paused-<point>`` written beside it; removing the file lets it go on.
Points: ``claim`` (before a job is taken), ``<kind>`` and ``<kind>-<phase>`` (after a progress
write of a running job), ``restore-finish`` (a committed restore, before its end steps).
Nothing in the product reads these files: the functions are wrapped as their modules load.
"""
import importlib.machinery
import os
import sys
import time

_DIR = os.environ.get('UCM_HA_PAUSE_DIR')
# A pause left behind never holds a node longer than this
MAX_SECONDS = 1200


def pause(*points):
    for point in points:
        if not point:
            continue
        hold = os.path.join(_DIR, f'pause-{point}')
        if not os.path.exists(hold):
            continue
        marker = os.path.join(_DIR, f'paused-{point}')
        with open(marker, 'w') as out:
            out.write(str(os.getpid()))
        deadline = time.monotonic() + MAX_SECONDS
        try:
            while os.path.exists(hold) and time.monotonic() < deadline:
                time.sleep(0.2)
        finally:
            try:
                os.unlink(marker)
            except OSError:
                pass


def _patch_store(module):
    claim = module.claim_job

    def claim_job(*args, **kwargs):
        pause('claim')
        return claim(*args, **kwargs)
    module.claim_job = claim_job


def _patch_runner(module):
    progress = module.JobContext.progress

    def wrapped(self, done=None, total=None, phase=None):
        progress(self, done=done, total=total, phase=phase)
        pause(self.kind, f'{self.kind}-{phase}' if phase else None)
    module.JobContext.progress = wrapped


def _patch_restore(module):
    steps = module._finish_steps

    def _finish_steps(job_id):
        pause('restore-finish')
        return steps(job_id)
    module._finish_steps = _finish_steps


_PATCHES = {
    'services.jobs.store': _patch_store,
    'services.jobs.runner': _patch_runner,
    'services.jobs.restore': _patch_restore,
}


class _AfterLoad:
    """A meta path finder that runs a patch once its module has executed."""

    def find_spec(self, fullname, path, target=None):
        patch = _PATCHES.get(fullname)
        if patch is None:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        execute = spec.loader.exec_module

        def exec_module(module):
            execute(module)
            patch(module)
        spec.loader.exec_module = exec_module
        return spec


if _DIR:
    sys.meta_path.insert(0, _AfterLoad())
