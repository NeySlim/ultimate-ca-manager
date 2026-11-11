"""An RFC 9763 refusal raised at commit is logged once, by the route that answers it."""
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding

from services.cert import related_pair
from tests import test_est_rfc7030 as est
from tests import test_wstep_issue as wstep
from tests.test_est_rfc7030 import est_config  # noqa: F401
from tests.test_wstep_issue import wstep_config  # noqa: F401

TEXT = 'already used with another key'


@pytest.fixture(autouse=True)
def _refused_at_commit(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise related_pair.RelatedCertificateRefused(TEXT)
    monkeypatch.setattr(related_pair, 'record_request_key', refuse)


def _one_line(caplog):
    lines = [(r.levelname, r.exc_info) for r in caplog.records
             if r.levelno >= 30 and TEXT in r.getMessage()]
    assert lines == [('WARNING', None)], caplog.text


def test_est_answers_400_with_one_log_line(client, est_config, caplog):  # noqa: F811
    from tests.test_final_review_followups import _csr
    csr, _key = _csr('refused-est.example.test')
    with caplog.at_level('INFO'):
        r = est._post_csr(client, 'simpleenroll', csr, headers=est._basic_auth())
    assert r.status_code == 400, r.data
    _one_line(caplog)


def test_wstep_answers_with_one_log_line(client, wstep_config, caplog):  # noqa: F811
    csr, _key = wstep._make_csr(common_name='refused-wstep.example.test')
    with caplog.at_level('INFO'):
        r = client.post(wstep.ISSUE_URL, data=wstep._build_rst(csr), headers=wstep._basic_auth())
    assert r.status_code != 200, r.data
    _one_line(caplog)
