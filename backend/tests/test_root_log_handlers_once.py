"""create_app gives the root logger one set of its handlers per process, however many
applications the process builds: a test worker builds hundreds, and each line it logged
was written once per application built before (gigabytes of captured output)."""
import logging
import uuid


def test_a_line_is_written_once_after_several_applications_were_built(capfd):
    from app import create_app
    for _ in range(3):
        create_app('testing')
    capfd.readouterr()
    marker = f'once-{uuid.uuid4().hex}'
    logging.getLogger('ucm.handlers.probe').warning(marker)
    assert capfd.readouterr().err.count(marker) == 1


def test_a_handler_the_application_did_not_install_is_kept(capfd):
    from app import create_app
    root = logging.getLogger()
    own = logging.NullHandler()
    root.addHandler(own)
    try:
        create_app('testing')
        create_app('testing')
        assert own in root.handlers
    finally:
        root.removeHandler(own)
