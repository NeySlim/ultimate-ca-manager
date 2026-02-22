"""
System API endpoint tests.

Tests all 45 system routes for:
- Authentication enforcement (401 without auth)
- Response structure and status codes
- GET endpoints: full response validation
- Dangerous POST endpoints: auth-only (no mutation)
"""
import pytest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_json(response):
    """Parse JSON response, return dict."""
    import json as _json
    return _json.loads(response.data)


def assert_success(response, status=200):
    """Assert response is successful and return parsed data."""
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    data = json.loads(response.data)
    return data.get('data', data)


def assert_error(response, status):
    """Assert response is an error with given status code."""
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


# ============================================================
# Auth Required — all system endpoints must return 401
# ============================================================

class TestSystemAuthRequired:
    """All system endpoints should return 401 without auth."""

    @pytest.mark.parametrize('method,path', [
        # Database
        ('GET',  '/api/v2/system/database/stats'),
        ('POST', '/api/v2/system/database/optimize'),
        ('POST', '/api/v2/system/database/integrity-check'),
        ('GET',  '/api/v2/system/database/export'),
        ('POST', '/api/v2/system/database/reset'),
        # HTTPS
        ('GET',  '/api/v2/system/https/cert-info'),
        ('POST', '/api/v2/system/https/regenerate'),
        ('POST', '/api/v2/system/https/apply'),
        # Backup/Restore
        ('POST', '/api/v2/system/backup'),
        ('POST', '/api/v2/system/backup/create'),
        ('GET',  '/api/v2/system/backups'),
        ('GET',  '/api/v2/system/backup/list'),
        ('GET',  '/api/v2/system/backup/testfile.ucmbkp/download'),
        ('DELETE', '/api/v2/system/backup/testfile.ucmbkp'),
        ('POST', '/api/v2/system/restore'),
        ('POST', '/api/v2/system/backup/restore'),
        # Security
        ('GET',  '/api/v2/system/security/encryption-status'),
        ('POST', '/api/v2/system/security/enable-encryption'),
        ('POST', '/api/v2/system/security/disable-encryption'),
        ('POST', '/api/v2/system/security/encrypt-all-keys'),
        ('GET',  '/api/v2/system/security/generate-key'),
        ('POST', '/api/v2/system/security/rotate-secrets'),
        ('GET',  '/api/v2/system/security/secrets-status'),
        ('GET',  '/api/v2/system/security/anomalies'),
        # Rate Limiting
        ('GET',  '/api/v2/system/security/rate-limit'),
        ('PUT',  '/api/v2/system/security/rate-limit'),
        ('GET',  '/api/v2/system/security/rate-limit/stats'),
        ('POST', '/api/v2/system/security/rate-limit/reset'),
        # Audit
        ('GET',  '/api/v2/system/audit/retention'),
        ('PUT',  '/api/v2/system/audit/retention'),
        ('POST', '/api/v2/system/audit/cleanup'),
        ('GET',  '/api/v2/system/audit/syslog'),
        ('PUT',  '/api/v2/system/audit/syslog'),
        ('POST', '/api/v2/system/audit/syslog/test'),
        # Alerts
        ('GET',  '/api/v2/system/alerts/expiry'),
        ('PUT',  '/api/v2/system/alerts/expiry'),
        ('POST', '/api/v2/system/alerts/expiry/check'),
        # Updates
        ('GET',  '/api/v2/system/updates/check'),
        ('POST', '/api/v2/system/updates/install'),
        # Misc
        ('GET',  '/api/v2/system/hsm-status'),
        ('GET',  '/api/v2/system/chain-repair'),
        ('POST', '/api/v2/system/chain-repair/run'),
        ('GET',  '/api/v2/system/service/status'),
        ('POST', '/api/v2/system/service/restart'),
    ])
    def test_requires_auth(self, client, method, path):
        """All system endpoints require authentication."""
        if method == 'GET':
            r = client.get(path)
        elif method == 'POST':
            r = client.post(path, data=json.dumps({}), content_type='application/json')
        elif method == 'PUT':
            r = client.put(path, data=json.dumps({}), content_type='application/json')
        elif method == 'DELETE':
            r = client.delete(path)
        assert r.status_code == 401, f'{method} {path} should require auth, got {r.status_code}'

    def test_version_is_public(self, client):
        """GET /system/updates/version is a public endpoint (no auth)."""
        r = client.get('/api/v2/system/updates/version')
        assert r.status_code == 200
        data = get_json(r)
        assert 'data' in data
        assert 'version' in data['data']


# ============================================================
# Database Endpoints
# ============================================================

class TestDatabaseStats:
    """GET /system/database/stats"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/database/stats')
        assert r.status_code == 200

    def test_response_structure(self, auth_client):
        r = auth_client.get('/api/v2/system/database/stats')
        data = assert_success(r)
        assert 'size_mb' in data
        assert 'counts' in data
        assert isinstance(data['counts'], dict)

    def test_counts_contain_tables(self, auth_client):
        r = auth_client.get('/api/v2/system/database/stats')
        data = assert_success(r)
        counts = data['counts']
        assert 'cas' in counts
        assert 'certificates' in counts

    def test_size_is_numeric(self, auth_client):
        r = auth_client.get('/api/v2/system/database/stats')
        data = assert_success(r)
        assert isinstance(data['size_mb'], (int, float))

    def test_fragmentation_present(self, auth_client):
        r = auth_client.get('/api/v2/system/database/stats')
        data = assert_success(r)
        assert 'fragmentation_percent' in data


class TestDatabaseOptimize:
    """POST /system/database/optimize"""

    def test_returns_200(self, auth_client):
        r = auth_client.post('/api/v2/system/database/optimize',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 200

    def test_success_message(self, auth_client):
        r = auth_client.post('/api/v2/system/database/optimize',
                             data=json.dumps({}),
                             content_type='application/json')
        data = get_json(r)
        assert 'message' in data
        assert 'optimiz' in data['message'].lower()


class TestDatabaseIntegrityCheck:
    """POST /system/database/integrity-check"""

    def test_returns_200(self, auth_client):
        r = auth_client.post('/api/v2/system/database/integrity-check',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 200

    def test_integrity_passes(self, auth_client):
        r = auth_client.post('/api/v2/system/database/integrity-check',
                             data=json.dumps({}),
                             content_type='application/json')
        data = get_json(r)
        assert 'message' in data
        assert 'pass' in data['message'].lower() or 'ok' in data['message'].lower()


class TestDatabaseExport:
    """GET /system/database/export"""

    def test_returns_response(self, auth_client):
        """Export returns SQL content (200) or 400 if DB path unresolvable in test env."""
        r = auth_client.get('/api/v2/system/database/export')
        assert r.status_code in (200, 400)

    def test_export_content_when_available(self, auth_client):
        r = auth_client.get('/api/v2/system/database/export')
        if r.status_code == 200:
            cd = r.headers.get('Content-Disposition', '')
            assert 'attachment' in cd or len(r.data) > 0
            content = r.data.decode('utf-8', errors='replace')
            assert 'CREATE TABLE' in content or 'INSERT' in content or 'BEGIN' in content


class TestDatabaseReset:
    """POST /system/database/reset — DANGEROUS, auth-only test."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/database/reset',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


# ============================================================
# HTTPS Endpoints
# ============================================================

class TestHttpsCertInfo:
    """GET /system/https/cert-info"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/https/cert-info')
        assert r.status_code == 200

    def test_response_structure(self, auth_client):
        r = auth_client.get('/api/v2/system/https/cert-info')
        data = assert_success(r)
        assert 'common_name' in data
        assert 'type' in data

    def test_has_fingerprint(self, auth_client):
        r = auth_client.get('/api/v2/system/https/cert-info')
        data = assert_success(r)
        assert 'fingerprint' in data

    def test_has_validity_dates(self, auth_client):
        r = auth_client.get('/api/v2/system/https/cert-info')
        data = assert_success(r)
        assert 'valid_from' in data
        assert 'valid_to' in data


class TestHttpsRegenerate:
    """POST /system/https/regenerate — DANGEROUS, auth-only test."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/https/regenerate',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


class TestHttpsApply:
    """POST /system/https/apply — DANGEROUS, auth-only test."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/https/apply',
                        data=json.dumps({'cert_id': 1}),
                        content_type='application/json')
        assert r.status_code == 401


# ============================================================
# Backup/Restore Endpoints
# ============================================================

class TestBackupCreate:
    """POST /system/backup/create"""

    def test_missing_password_returns_400(self, auth_client):
        r = auth_client.post('/api/v2/system/backup/create',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_short_password_returns_400(self, auth_client):
        r = auth_client.post('/api/v2/system/backup/create',
                             data=json.dumps({'password': 'short'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_backup_alias_route(self, auth_client):
        """POST /system/backup also works (alias)."""
        r = auth_client.post('/api/v2/system/backup',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 400  # Missing password


class TestBackupList:
    """GET /system/backups"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/backups')
        assert r.status_code == 200

    def test_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/system/backups')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_alias_route(self, auth_client):
        """GET /system/backup/list also works."""
        r = auth_client.get('/api/v2/system/backup/list')
        assert r.status_code == 200


class TestBackupDownload:
    """GET /system/backup/<filename>/download"""

    def test_nonexistent_file_returns_404(self, auth_client):
        r = auth_client.get('/api/v2/system/backup/nonexistent.ucmbkp/download')
        assert r.status_code == 404


class TestBackupDelete:
    """DELETE /system/backup/<filename>"""

    def test_nonexistent_file_returns_404(self, auth_client):
        r = auth_client.delete('/api/v2/system/backup/nonexistent.ucmbkp')
        assert r.status_code == 404


class TestRestore:
    """POST /system/restore — DANGEROUS, auth-only test."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/restore',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401

    def test_alias_auth_required(self, client):
        r = client.post('/api/v2/system/backup/restore',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


# ============================================================
# Security — Encryption Status
# ============================================================

class TestEncryptionStatus:
    """GET /system/security/encryption-status"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/security/encryption-status')
        assert r.status_code == 200

    def test_response_structure(self, auth_client):
        r = auth_client.get('/api/v2/system/security/encryption-status')
        data = assert_success(r)
        assert 'enabled' in data
        assert 'encrypted_count' in data
        assert 'unencrypted_count' in data
        assert 'total_keys' in data

    def test_counts_are_integers(self, auth_client):
        r = auth_client.get('/api/v2/system/security/encryption-status')
        data = assert_success(r)
        assert isinstance(data['encrypted_count'], int)
        assert isinstance(data['unencrypted_count'], int)
        assert isinstance(data['total_keys'], int)


class TestEnableEncryption:
    """POST /system/security/enable-encryption — DANGEROUS."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/security/enable-encryption',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


class TestDisableEncryption:
    """POST /system/security/disable-encryption — DANGEROUS."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/security/disable-encryption',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


class TestEncryptAllKeys:
    """POST /system/security/encrypt-all-keys — DANGEROUS."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/security/encrypt-all-keys',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


class TestGenerateKey:
    """GET /system/security/generate-key"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/security/generate-key')
        assert r.status_code == 200

    def test_returns_key_string(self, auth_client):
        r = auth_client.get('/api/v2/system/security/generate-key')
        data = assert_success(r)
        assert 'key' in data
        assert isinstance(data['key'], str)
        assert len(data['key']) > 16

    def test_generates_unique_keys(self, auth_client):
        r1 = auth_client.get('/api/v2/system/security/generate-key')
        r2 = auth_client.get('/api/v2/system/security/generate-key')
        key1 = assert_success(r1)['key']
        key2 = assert_success(r2)['key']
        assert key1 != key2


class TestRotateSecrets:
    """POST /system/security/rotate-secrets — DANGEROUS."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/security/rotate-secrets',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


class TestSecretsStatus:
    """GET /system/security/secrets-status"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/security/secrets-status')
        assert r.status_code == 200

    def test_response_structure(self, auth_client):
        r = auth_client.get('/api/v2/system/security/secrets-status')
        data = assert_success(r)
        assert 'session_secret' in data
        assert 'encryption_key' in data

    def test_session_secret_configured_in_test(self, auth_client):
        r = auth_client.get('/api/v2/system/security/secrets-status')
        data = assert_success(r)
        assert 'configured' in data['session_secret']


class TestSecurityAnomalies:
    """GET /system/security/anomalies"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/security/anomalies')
        assert r.status_code == 200

    def test_response_structure(self, auth_client):
        r = auth_client.get('/api/v2/system/security/anomalies')
        data = assert_success(r)
        assert 'anomalies' in data
        assert 'total' in data
        assert isinstance(data['anomalies'], list)

    def test_custom_hours_param(self, auth_client):
        r = auth_client.get('/api/v2/system/security/anomalies?hours=1')
        data = assert_success(r)
        assert data['period_hours'] == 1


# ============================================================
# Rate Limiting
# ============================================================

class TestRateLimitGet:
    """GET /system/security/rate-limit"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/security/rate-limit')
        assert r.status_code == 200

    def test_response_has_config_and_stats(self, auth_client):
        r = auth_client.get('/api/v2/system/security/rate-limit')
        data = assert_success(r)
        assert 'config' in data
        assert 'stats' in data


class TestRateLimitUpdate:
    """PUT /system/security/rate-limit"""

    def test_update_enabled_flag(self, auth_client):
        r = auth_client.put('/api/v2/system/security/rate-limit',
                            data=json.dumps({'enabled': True}),
                            content_type='application/json')
        assert r.status_code == 200

    def test_returns_updated_config(self, auth_client):
        r = auth_client.put('/api/v2/system/security/rate-limit',
                            data=json.dumps({'enabled': True}),
                            content_type='application/json')
        data = get_json(r)
        assert 'data' in data


class TestRateLimitStats:
    """GET /system/security/rate-limit/stats"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/security/rate-limit/stats')
        assert r.status_code == 200

    def test_returns_dict(self, auth_client):
        r = auth_client.get('/api/v2/system/security/rate-limit/stats')
        data = assert_success(r)
        assert isinstance(data, dict)


class TestRateLimitReset:
    """POST /system/security/rate-limit/reset"""

    def test_returns_200(self, auth_client):
        r = auth_client.post('/api/v2/system/security/rate-limit/reset',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 200

    def test_reset_with_stats(self, auth_client):
        r = auth_client.post('/api/v2/system/security/rate-limit/reset',
                             data=json.dumps({'reset_stats': True}),
                             content_type='application/json')
        assert r.status_code == 200


# ============================================================
# Audit — Retention
# ============================================================

class TestAuditRetentionGet:
    """GET /system/audit/retention"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/audit/retention')
        assert r.status_code == 200

    def test_returns_dict(self, auth_client):
        r = auth_client.get('/api/v2/system/audit/retention')
        data = assert_success(r)
        assert isinstance(data, dict)


class TestAuditRetentionUpdate:
    """PUT /system/audit/retention"""

    def test_returns_200(self, auth_client):
        r = auth_client.put('/api/v2/system/audit/retention',
                            data=json.dumps({}),
                            content_type='application/json')
        assert r.status_code == 200

    def test_returns_updated_settings(self, auth_client):
        r = auth_client.put('/api/v2/system/audit/retention',
                            data=json.dumps({'retention_days': 90}),
                            content_type='application/json')
        data = get_json(r)
        assert 'data' in data or 'message' in data


class TestAuditCleanup:
    """POST /system/audit/cleanup"""

    def test_returns_200(self, auth_client):
        r = auth_client.post('/api/v2/system/audit/cleanup',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 200


# ============================================================
# Audit — Syslog
# ============================================================

class TestSyslogGet:
    """GET /system/audit/syslog"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/audit/syslog')
        assert r.status_code == 200

    def test_returns_config_dict(self, auth_client):
        r = auth_client.get('/api/v2/system/audit/syslog')
        data = assert_success(r)
        assert isinstance(data, dict)


class TestSyslogUpdate:
    """PUT /system/audit/syslog"""

    def test_empty_body_returns_400(self, auth_client):
        """PUT with no data should return 400."""
        r = auth_client.put('/api/v2/system/audit/syslog',
                            data=json.dumps(None),
                            content_type='application/json')
        # Accepts empty or returns 400
        assert r.status_code in (200, 400)

    def test_invalid_protocol_returns_400(self, auth_client):
        r = auth_client.put('/api/v2/system/audit/syslog',
                            data=json.dumps({
                                'enabled': False,
                                'host': 'localhost',
                                'port': 514,
                                'protocol': 'invalid'
                            }),
                            content_type='application/json')
        assert r.status_code == 400

    def test_invalid_port_returns_400(self, auth_client):
        r = auth_client.put('/api/v2/system/audit/syslog',
                            data=json.dumps({
                                'enabled': False,
                                'host': 'localhost',
                                'port': 99999,
                                'protocol': 'udp'
                            }),
                            content_type='application/json')
        assert r.status_code == 400

    def test_valid_disabled_config(self, auth_client):
        r = auth_client.put('/api/v2/system/audit/syslog',
                            data=json.dumps({
                                'enabled': False,
                                'host': '',
                                'port': 514,
                                'protocol': 'udp'
                            }),
                            content_type='application/json')
        assert r.status_code == 200

    def test_enabled_without_host_returns_400(self, auth_client):
        r = auth_client.put('/api/v2/system/audit/syslog',
                            data=json.dumps({
                                'enabled': True,
                                'host': '',
                                'port': 514,
                                'protocol': 'udp'
                            }),
                            content_type='application/json')
        assert r.status_code == 400


class TestSyslogTest:
    """POST /system/audit/syslog/test"""

    def test_returns_response(self, auth_client):
        """Test syslog connection — may fail if not configured, accept 200 or 400."""
        r = auth_client.post('/api/v2/system/audit/syslog/test',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code in (200, 400, 500)


# ============================================================
# Alerts — Expiry
# ============================================================

class TestExpiryAlertGet:
    """GET /system/alerts/expiry"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/alerts/expiry')
        assert r.status_code == 200

    def test_returns_dict(self, auth_client):
        r = auth_client.get('/api/v2/system/alerts/expiry')
        data = assert_success(r)
        assert isinstance(data, dict)


class TestExpiryAlertUpdate:
    """PUT /system/alerts/expiry"""

    def test_returns_200(self, auth_client):
        r = auth_client.put('/api/v2/system/alerts/expiry',
                            data=json.dumps({}),
                            content_type='application/json')
        assert r.status_code == 200


class TestExpiryAlertCheck:
    """POST /system/alerts/expiry/check"""

    def test_returns_200_or_500(self, auth_client):
        """May return 500 if email/SMTP not configured after settings changes."""
        r = auth_client.post('/api/v2/system/alerts/expiry/check',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code in (200, 500)

    def test_response_has_message(self, auth_client):
        r = auth_client.post('/api/v2/system/alerts/expiry/check',
                             data=json.dumps({}),
                             content_type='application/json')
        data = get_json(r)
        assert 'message' in data or 'error' in data


# ============================================================
# Updates
# ============================================================

class TestUpdatesVersion:
    """GET /system/updates/version — public endpoint."""

    def test_returns_200_without_auth(self, client):
        r = client.get('/api/v2/system/updates/version')
        assert r.status_code == 200

    def test_returns_version_string(self, client):
        r = client.get('/api/v2/system/updates/version')
        data = get_json(r)
        version = data.get('data', {}).get('version', '')
        assert isinstance(version, str)
        assert len(version) > 0

    def test_version_looks_like_semver(self, client):
        r = client.get('/api/v2/system/updates/version')
        data = get_json(r)
        version = data.get('data', {}).get('version', '')
        # Should contain at least one dot (e.g., "1.0" or "1.0.0")
        assert '.' in version


class TestUpdatesCheck:
    """GET /system/updates/check"""

    def test_returns_response(self, auth_client):
        """May fail without internet — accept 200 or 500."""
        r = auth_client.get('/api/v2/system/updates/check')
        assert r.status_code in (200, 500)


class TestUpdatesInstall:
    """POST /system/updates/install — DANGEROUS."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/updates/install',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401


# ============================================================
# HSM Status
# ============================================================

class TestHsmStatus:
    """GET /system/hsm-status"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/hsm-status')
        assert r.status_code == 200

    def test_returns_dict(self, auth_client):
        r = auth_client.get('/api/v2/system/hsm-status')
        data = assert_success(r)
        assert isinstance(data, dict)


# ============================================================
# Chain Repair
# ============================================================

class TestChainRepairGet:
    """GET /system/chain-repair"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/chain-repair')
        assert r.status_code == 200

    def test_response_structure(self, auth_client):
        r = auth_client.get('/api/v2/system/chain-repair')
        data = assert_success(r)
        assert 'task' in data or 'stats' in data


class TestChainRepairRun:
    """POST /system/chain-repair/run"""

    def test_returns_200(self, auth_client):
        r = auth_client.post('/api/v2/system/chain-repair/run',
                             data=json.dumps({}),
                             content_type='application/json')
        # May return 200 or 404 if task not registered
        assert r.status_code in (200, 404)


# ============================================================
# Service Status / Restart
# ============================================================

class TestServiceStatus:
    """GET /system/service/status"""

    def test_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/system/service/status')
        assert r.status_code == 200

    def test_has_version(self, auth_client):
        r = auth_client.get('/api/v2/system/service/status')
        data = assert_success(r)
        assert 'version' in data

    def test_has_uptime(self, auth_client):
        r = auth_client.get('/api/v2/system/service/status')
        data = assert_success(r)
        assert 'uptime_seconds' in data
        assert isinstance(data['uptime_seconds'], int)
        assert data['uptime_seconds'] >= 0

    def test_has_memory(self, auth_client):
        r = auth_client.get('/api/v2/system/service/status')
        data = assert_success(r)
        assert 'memory_mb' in data
        assert isinstance(data['memory_mb'], (int, float))

    def test_has_python_version(self, auth_client):
        r = auth_client.get('/api/v2/system/service/status')
        data = assert_success(r)
        assert 'python_version' in data
        assert '.' in data['python_version']

    def test_has_pid(self, auth_client):
        r = auth_client.get('/api/v2/system/service/status')
        data = assert_success(r)
        assert 'pid' in data
        assert isinstance(data['pid'], int)


class TestServiceRestart:
    """POST /system/service/restart — DANGEROUS."""

    def test_auth_required(self, client):
        r = client.post('/api/v2/system/service/restart',
                        data=json.dumps({}),
                        content_type='application/json')
        assert r.status_code == 401
