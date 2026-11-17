"""
Issue #300 — TSA CA selection does not persist.

TSAPage.jsx loads GET /api/v2/tsa/config into state, the user picks a CA
(only ca_refid changes), then the WHOLE state object is PATCHed back —
including the stale ca_id echoed by the GET. The PATCH handler processes
ca_refid first, then lets ca_id override it, so the selection is wiped
(ca_id null → '') or reverted (ca_id stale → previous CA).
"""
import json


class TestTsaCaSelectRoundtrip:
    def _get_config(self, auth_client):
        r = auth_client.get('/api/v2/tsa/config')
        assert r.status_code == 200
        return json.loads(r.data)['data']

    def test_ui_roundtrip_persists_selected_ca(self, app, auth_client, create_ca):
        from models import db, CA

        ca_data = create_ca(cn='TSA Roundtrip CA')
        with app.app_context():
            refid = db.session.get(CA, ca_data['id']).refid

        config = self._get_config(auth_client)
        config['ca_refid'] = refid  # what the Select onChange does

        r = auth_client.patch(
            '/api/v2/tsa/config',
            data=json.dumps(config),  # UI sends the whole object back
            content_type='application/json',
        )
        assert r.status_code == 200

        assert self._get_config(auth_client)['ca_refid'] == refid

    def test_ui_roundtrip_switches_ca(self, app, auth_client, create_ca):
        from models import db, CA

        ca_a = create_ca(cn='TSA CA A')
        ca_b = create_ca(cn='TSA CA B')
        with app.app_context():
            refid_a = db.session.get(CA, ca_a['id']).refid
            refid_b = db.session.get(CA, ca_b['id']).refid

        auth_client.patch(
            '/api/v2/tsa/config',
            data=json.dumps({'ca_refid': refid_a}),
            content_type='application/json',
        )

        config = self._get_config(auth_client)
        assert config['ca_refid'] == refid_a
        config['ca_refid'] = refid_b  # user switches A → B in the UI

        r = auth_client.patch(
            '/api/v2/tsa/config',
            data=json.dumps(config),
            content_type='application/json',
        )
        assert r.status_code == 200

        assert self._get_config(auth_client)['ca_refid'] == refid_b
