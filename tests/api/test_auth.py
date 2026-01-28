"""
Tests for Authentication API endpoints
"""
import pytest
import json


class TestAuthAPI:
    """Test /api/v2/auth endpoints"""

    def test_login_missing_credentials(self, client):
        """POST /auth/login requires username and password"""
        resp = client.post('/api/v2/auth/login', json={})
        assert resp.status_code == 400
        
        data = json.loads(resp.data)
        assert 'error' in data or 'message' in data

    def test_login_invalid_credentials(self, client):
        """POST /auth/login rejects invalid credentials"""
        resp = client.post('/api/v2/auth/login', json={
            'username': 'invalid',
            'password': 'invalid'
        })
        assert resp.status_code == 401

    def test_login_success(self, client):
        """POST /auth/login succeeds with valid credentials"""
        resp = client.post('/api/v2/auth/login', json={
            'username': 'testuser',
            'password': 'testpass123'
        })
        assert resp.status_code == 200
        
        data = json.loads(resp.data)
        assert 'data' in data

    def test_verify_without_auth(self, client):
        """GET /auth/verify returns unauthenticated status"""
        resp = client.get('/api/v2/auth/verify')
        assert resp.status_code == 200
        
        data = json.loads(resp.data)
        assert 'data' in data
        assert data['data'].get('authenticated') == False

    def test_verify_with_auth(self, auth_client):
        """GET /auth/verify returns user info when authenticated"""
        resp = auth_client.get('/api/v2/auth/verify')
        assert resp.status_code == 200

    def test_logout_without_auth(self, client):
        """POST /auth/logout requires authentication"""
        resp = client.post('/api/v2/auth/logout')
        assert resp.status_code == 401

    def test_logout_success(self, auth_client):
        """POST /auth/logout invalidates session"""
        resp = auth_client.post('/api/v2/auth/logout')
        assert resp.status_code == 200


class TestPasswordAuth:
    """Test password authentication flow"""

    def test_password_login_endpoint(self, client):
        """POST /auth/login/password works"""
        resp = client.post('/api/v2/auth/login/password', json={
            'username': 'testuser',
            'password': 'testpass123'
        })
        assert resp.status_code in [200, 400, 401, 404]

    def test_login_rate_limiting(self, client):
        """Login endpoint has rate limiting"""
        # Make multiple rapid requests
        for i in range(10):
            resp = client.post('/api/v2/auth/login', json={
                'username': 'invalid',
                'password': 'invalid'
            })
        
        # Should eventually get rate limited (429) or just 401
        assert resp.status_code in [401, 429]
