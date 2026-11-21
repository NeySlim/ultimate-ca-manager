"""The session-scoped admin client signs back in and replays a request, an upload included."""
import io


def _sign_out(auth_client):
    # The inner client: the wrapper would sign back in at once
    r = auth_client._client.post('/api/v2/auth/logout')
    assert r.status_code in (200, 204), r.data
    assert auth_client._client.get('/api/v2/account/profile').status_code == 401


def test_a_request_after_the_session_went_is_replayed(auth_client):
    _sign_out(auth_client)
    assert auth_client.get('/api/v2/account/profile').status_code == 200


def test_an_upload_after_the_session_went_is_replayed(auth_client):
    """A restore in an earlier file revokes the session: the next upload must not answer 401."""
    _sign_out(auth_client)
    r = auth_client.post('/api/v2/certificates/import',
                         data={'file': (io.BytesIO(b'not a certificate'), 'x.pem')},
                         content_type='multipart/form-data')
    assert r.status_code != 401, r.data
