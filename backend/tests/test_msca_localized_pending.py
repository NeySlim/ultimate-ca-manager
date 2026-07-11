"""
Locale-independent pending/denied classification for Microsoft AD CS (bug fix).

certsrv only recognizes the English "Certificate Pending" page, so against a
localized AD CS (e.g. French) it raised RequestDenied for a genuinely pending
submission — which UCM surfaced as a 400 — and a generic failure when polling a
still-pending request (500). The classifier keys off certsrv's
locale-independent HTML markers (element ids + numeric disposition codes).
"""
import pytest

from services.msca.requests import MicrosoftCARequestsMixin as R
from services.msca_service import MicrosoftCAService


# Minimal fragments mirroring the real French AD CS pages captured from the lab.
FR_SUBMIT_PENDING = (
    '<P ID=locPageTitle> <B> Certificat en attente </B>'
    '<P ID=locInfoReqID>\nL’identificateur de votre requête est 25.\n</P>'
)
FR_POLL_PENDING = (
    '<P ID=locPageTitle> <B> Erreur </B>'
    '<DT ID=locDispLabel><B>Disposition :</B></DT><DD>\n\t\t5 '
    '<LocID ID=locDispSpacer>-</LocID><LocID ID=locDispUnknown>(inconnu)</LocID>'
)
FR_POLL_DENIED = (
    '<P ID=locPageTitle> <B> Erreur </B>'
    '<DT ID=locDispLabel><B>Disposition :</B></DT><DD>\n\t\t2 '
    '<LocID ID=locDispSpacer>-</LocID>'
)


class _CertsrvErr(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class TestClassifier:

    def test_french_submit_pending(self):
        err = _CertsrvErr('An unknown error occured', FR_SUBMIT_PENDING)
        assert R._classify_certsrv_error(err) == ('pending', 25)

    def test_french_poll_pending_disposition5(self):
        err = _CertsrvErr('An unknown error occured', FR_POLL_PENDING)
        assert R._classify_certsrv_error(err) == ('pending', None)

    def test_french_poll_denied_disposition2(self):
        err = _CertsrvErr('An unknown error occured', FR_POLL_DENIED)
        assert R._classify_certsrv_error(err) == ('denied', None)

    def test_english_pending_message(self):
        err = _CertsrvErr('...you must wait... pending. Your Request Id is 42.')
        assert R._classify_certsrv_error(err) == ('pending', 42)

    def test_english_denied_message(self):
        assert R._classify_certsrv_error(_CertsrvErr('Request was denied')) == ('denied', None)

    def test_generic_error(self):
        assert R._classify_certsrv_error(_CertsrvErr('connection reset')) == ('error', None)

    def test_response_object_with_text_attr(self):
        class Resp:
            text = FR_SUBMIT_PENDING
        assert R._classify_certsrv_error(_CertsrvErr('x', Resp())) == ('pending', 25)


class _FakeClient:
    """Stands in for a certsrv.Certsrv client."""
    def __init__(self, on_get_cert=None, on_get_existing=None):
        self._on_get_cert = on_get_cert
        self._on_get_existing = on_get_existing
        self._temp_files = []

    def get_cert(self, csr, template, encoding='b64', attributes=None):
        raise self._on_get_cert

    def get_existing_cert(self, req_id, encoding='b64'):
        raise self._on_get_existing


_conn_counter = [0]


def _make_conn(app):
    with app.app_context():
        from models import db
        from models.msca import MicrosoftCA
        _conn_counter[0] += 1
        m = MicrosoftCA(name=f'FR ADCS {_conn_counter[0]}', server='dc.fr.local',
                        auth_method='basic', username='u', enabled=True)
        m.password = 'p'
        db.session.add(m)
        db.session.commit()
        return m.id


class TestSubmitAndPollLocalized:

    def test_submit_pending_on_french_ca(self, app, monkeypatch):
        """A French-CA pending submission must return status 'pending', not raise."""
        msca_id = _make_conn(app)
        from services.msca.connection import MicrosoftCAConnectionMixin
        err = _CertsrvErr('An unknown error occured', FR_SUBMIT_PENDING)
        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client',
                            staticmethod(lambda msca: _FakeClient(on_get_cert=err)))
        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client',
                            staticmethod(lambda c: None))

        with app.app_context():
            csr_pem = '-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----\n'
            result = MicrosoftCAService.submit_csr(msca_id, csr_pem, 'WebServer')
            assert result['status'] == 'pending'
            assert result['ms_request_id'] == 25

    def test_poll_still_pending_on_french_ca(self, app, monkeypatch):
        """Polling a still-pending request on a French CA must not raise (was 500)."""
        msca_id = _make_conn(app)
        from services.msca.connection import MicrosoftCAConnectionMixin
        from models import db
        from models.msca import MSCARequest
        from utils.datetime_utils import utc_now

        with app.app_context():
            req = MSCARequest(msca_id=msca_id, request_id=25, template='WebServer',
                              status='pending', submitted_at=utc_now())
            db.session.add(req)
            db.session.commit()
            req_pk = req.id

        err = _CertsrvErr('An unknown error occured', FR_POLL_PENDING)
        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client',
                            staticmethod(lambda msca: _FakeClient(on_get_existing=err)))
        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client',
                            staticmethod(lambda c: None))

        with app.app_context():
            result = MicrosoftCAService.check_request(msca_id, req_pk)
            assert result['status'] == 'pending'

    def test_poll_denied_on_french_ca(self, app, monkeypatch):
        msca_id = _make_conn(app)
        from services.msca.connection import MicrosoftCAConnectionMixin
        from models import db
        from models.msca import MSCARequest
        from utils.datetime_utils import utc_now

        with app.app_context():
            req = MSCARequest(msca_id=msca_id, request_id=26, template='WebServer',
                              status='pending', submitted_at=utc_now())
            db.session.add(req)
            db.session.commit()
            req_pk = req.id

        err = _CertsrvErr('An unknown error occured', FR_POLL_DENIED)
        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client',
                            staticmethod(lambda msca: _FakeClient(on_get_existing=err)))
        monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client',
                            staticmethod(lambda c: None))

        with app.app_context():
            result = MicrosoftCAService.check_request(msca_id, req_pk)
            assert result['status'] == 'denied'
