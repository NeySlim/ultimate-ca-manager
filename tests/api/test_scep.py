"""
Tests for SCEP API endpoints
"""
import pytest
import json


class TestSCEPAPI:
    """Test /api/v2/scep endpoints"""

    def test_get_config_requires_auth(self, client):
        """GET /scep/config requires authentication"""
        resp = client.get('/api/v2/scep/config')
        assert resp.status_code == 401

    def test_get_config_success(self, auth_client):
        """GET /scep/config returns SCEP configuration"""
        resp = auth_client.get('/api/v2/scep/config')
        assert resp.status_code == 200
        
        data = json.loads(resp.data)
        assert 'data' in data
        assert 'enabled' in data['data']
        assert 'url' in data['data']

    def test_update_config_requires_auth(self, client):
        """PATCH /scep/config requires authentication"""
        resp = client.patch('/api/v2/scep/config', json={})
        assert resp.status_code == 401

    def test_update_config_success(self, auth_client):
        """PATCH /scep/config updates configuration"""
        resp = auth_client.patch('/api/v2/scep/config', json={
            'enabled': True,
            'auto_approve': False
        })
        assert resp.status_code == 200

    def test_get_stats(self, auth_client):
        """GET /scep/stats returns statistics"""
        resp = auth_client.get('/api/v2/scep/stats')
        assert resp.status_code == 200
        
        data = json.loads(resp.data)
        assert 'data' in data
        assert 'total' in data['data']
        assert 'pending' in data['data']

    def test_list_requests(self, auth_client):
        """GET /scep/requests returns request list"""
        resp = auth_client.get('/api/v2/scep/requests')
        assert resp.status_code == 200
        
        data = json.loads(resp.data)
        assert 'data' in data
        assert isinstance(data['data'], list)

    def test_list_requests_filter_status(self, auth_client):
        """GET /scep/requests?status=pending filters by status"""
        resp = auth_client.get('/api/v2/scep/requests?status=pending')
        assert resp.status_code == 200

    def test_approve_request_not_found(self, auth_client):
        """POST /scep/:id/approve returns 404 for non-existent request"""
        resp = auth_client.post('/api/v2/scep/99999/approve')
        assert resp.status_code == 404

    def test_reject_request_not_found(self, auth_client):
        """POST /scep/:id/reject returns 404 for non-existent request"""
        resp = auth_client.post('/api/v2/scep/99999/reject', json={
            'reason': 'Test rejection'
        })
        assert resp.status_code == 404

    def test_regenerate_challenge_requires_ca(self, auth_client):
        """POST /scep/challenge/:ca_id/regenerate requires valid CA"""
        resp = auth_client.post('/api/v2/scep/challenge/99999/regenerate')
        assert resp.status_code == 404

    def test_regenerate_challenge_success(self, auth_client, sample_ca):
        """POST /scep/challenge/:ca_id/regenerate creates new challenge"""
        resp = auth_client.post(f'/api/v2/scep/challenge/{sample_ca.id}/regenerate')
        assert resp.status_code == 200
        
        data = json.loads(resp.data)
        assert 'data' in data
        assert 'challenge' in data['data']
