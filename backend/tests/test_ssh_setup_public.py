"""Tests for public SSH CA setup script endpoint (/ssh/setup/<refid>)."""

import json

from tests.conftest import get_json


def _create_host_ca(auth_client):
    payload = {
        'descr': 'Public setup test CA',
        'ca_type': 'host',
        'key_type': 'ed25519',
    }
    r = auth_client.post(
        '/api/v2/ssh/cas',
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert r.status_code == 201, r.data
    return get_json(r).get('data', get_json(r))


class TestPublicSSHSetupScript:
  def test_rejects_shell_metacharacters_in_hostname(self, app, auth_client):
      ca = _create_host_ca(auth_client)
      refid = ca['refid']
      client = app.test_client()
      r = client.get(
          f'/ssh/setup/{refid}?type=host&hostname=$(id)'
      )
      assert r.status_code == 400
      assert b'Invalid hostname format' in r.data

  def test_rejects_quote_breakout_in_hostname(self, app, auth_client):
      ca = _create_host_ca(auth_client)
      refid = ca['refid']
      client = app.test_client()
      r = client.get(
          f'/ssh/setup/{refid}?type=host&hostname=x";id;"'
      )
      assert r.status_code == 400

  def test_valid_hostname_embedded_safely(self, app, auth_client):
      ca = _create_host_ca(auth_client)
      refid = ca['refid']
      hostname = 'web01.example.com'
      client = app.test_client()
      r = client.get(
          f'/ssh/setup/{refid}?type=host&hostname={hostname}'
      )
      assert r.status_code == 200
      body = r.data.decode('utf-8')
      assert f'HOSTNAME="{hostname}"' in body
      assert '$(id)' not in body
