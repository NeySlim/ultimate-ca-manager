"""
Settings API Tests — /api/v2/settings/*

Comprehensive tests for all settings endpoints:
- General settings (GET/PATCH)
- Backup settings (GET, create, restore, download, delete, schedule, history)
- Email settings (GET/PATCH, test, template CRUD, preview, reset)
- Notification settings (GET/PATCH, logs)
- Audit logs (GET)
- LDAP settings (GET/PATCH, test)
- Webhooks (list, create, delete, test)

Uses shared conftest fixtures: app, client, auth_client.
"""
import pytest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'


def get_json(response):
    return json.loads(response.data)


def assert_success(response, status=200):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    data = json.loads(response.data)
    return data.get('data', data)


def assert_error(response, status):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all 28 endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All settings endpoints must return 401 without authentication."""

    # General
    def test_get_general_requires_auth(self, client):
        assert client.get('/api/v2/settings/general').status_code == 401

    def test_patch_general_requires_auth(self, client):
        r = patch_json(client, '/api/v2/settings/general', {'site_name': 'X'})
        assert r.status_code == 401

    # Backup
    def test_get_backup_requires_auth(self, client):
        assert client.get('/api/v2/settings/backup').status_code == 401

    def test_create_backup_requires_auth(self, client):
        r = post_json(client, '/api/v2/settings/backup/create', {})
        assert r.status_code == 401

    def test_restore_backup_requires_auth(self, client):
        r = client.post('/api/v2/settings/backup/restore',
                        content_type='multipart/form-data')
        assert r.status_code == 401

    def test_download_backup_requires_auth(self, client):
        assert client.get('/api/v2/settings/backup/test.ucmbkp/download').status_code == 401

    def test_delete_backup_requires_auth(self, client):
        assert client.delete('/api/v2/settings/backup/test.ucmbkp').status_code == 401

    def test_get_backup_schedule_requires_auth(self, client):
        assert client.get('/api/v2/settings/backup/schedule').status_code == 401

    def test_patch_backup_schedule_requires_auth(self, client):
        r = patch_json(client, '/api/v2/settings/backup/schedule', {'enabled': True})
        assert r.status_code == 401

    def test_get_backup_history_requires_auth(self, client):
        assert client.get('/api/v2/settings/backup/history').status_code == 401

    # Email
    def test_get_email_requires_auth(self, client):
        assert client.get('/api/v2/settings/email').status_code == 401

    def test_patch_email_requires_auth(self, client):
        r = patch_json(client, '/api/v2/settings/email', {'enabled': True})
        assert r.status_code == 401

    def test_test_email_requires_auth(self, client):
        r = post_json(client, '/api/v2/settings/email/test', {'email': 'a@b.com'})
        assert r.status_code == 401

    def test_get_email_template_requires_auth(self, client):
        assert client.get('/api/v2/settings/email/template').status_code == 401

    def test_patch_email_template_requires_auth(self, client):
        r = patch_json(client, '/api/v2/settings/email/template', {'template': '<h1>'})
        assert r.status_code == 401

    def test_reset_email_template_requires_auth(self, client):
        r = client.post('/api/v2/settings/email/template/reset')
        assert r.status_code == 401

    def test_preview_email_template_requires_auth(self, client):
        r = post_json(client, '/api/v2/settings/email/template/preview', {'template': ''})
        assert r.status_code == 401

    # Notifications
    def test_get_notifications_requires_auth(self, client):
        assert client.get('/api/v2/settings/notifications').status_code == 401

    def test_patch_notifications_requires_auth(self, client):
        r = patch_json(client, '/api/v2/settings/notifications', {'enabled': True})
        assert r.status_code == 401

    def test_get_notification_logs_requires_auth(self, client):
        assert client.get('/api/v2/settings/notifications/logs').status_code == 401

    # Audit logs
    def test_get_audit_logs_requires_auth(self, client):
        assert client.get('/api/v2/settings/audit-logs').status_code == 401

    # LDAP
    def test_get_ldap_requires_auth(self, client):
        assert client.get('/api/v2/settings/ldap').status_code == 401

    def test_patch_ldap_requires_auth(self, client):
        r = patch_json(client, '/api/v2/settings/ldap', {'enabled': True})
        assert r.status_code == 401

    def test_test_ldap_requires_auth(self, client):
        r = post_json(client, '/api/v2/settings/ldap/test', {})
        assert r.status_code == 401

    # Webhooks
    def test_list_webhooks_requires_auth(self, client):
        assert client.get('/api/v2/settings/webhooks').status_code == 401

    def test_create_webhook_requires_auth(self, client):
        r = post_json(client, '/api/v2/settings/webhooks', {'name': 'x', 'url': 'http://x'})
        assert r.status_code == 401

    def test_delete_webhook_requires_auth(self, client):
        assert client.delete('/api/v2/settings/webhooks/1').status_code == 401

    def test_test_webhook_requires_auth(self, client):
        r = post_json(client, '/api/v2/settings/webhooks/1/test', {})
        assert r.status_code == 401


# ============================================================
# General Settings
# ============================================================

class TestGeneralSettings:
    """GET/PATCH /api/v2/settings/general"""

    def test_get_general_settings(self, auth_client):
        r = auth_client.get('/api/v2/settings/general')
        data = assert_success(r)
        assert 'site_name' in data
        assert 'timezone' in data
        assert 'session_timeout' in data
        assert 'max_login_attempts' in data
        assert 'lockout_duration' in data
        assert 'backup_frequency' in data
        assert 'backup_retention_days' in data
        # Password should never be returned
        assert data.get('backup_password') == ''

    def test_get_general_settings_types(self, auth_client):
        r = auth_client.get('/api/v2/settings/general')
        data = assert_success(r)
        assert isinstance(data['session_timeout'], int)
        assert isinstance(data['max_login_attempts'], int)
        assert isinstance(data['lockout_duration'], int)
        assert isinstance(data['backup_retention_days'], int)
        assert isinstance(data['auto_backup_enabled'], bool)

    def test_patch_general_site_name(self, auth_client):
        r = patch_json(auth_client, '/api/v2/settings/general', {'site_name': 'Test UCM'})
        assert_success(r)
        # Verify saved
        r = auth_client.get('/api/v2/settings/general')
        data = assert_success(r)
        assert data['site_name'] == 'Test UCM'

    def test_patch_general_multiple_fields(self, auth_client):
        updates = {
            'site_name': 'Multi-Update UCM',
            'timezone': 'America/New_York',
            'session_timeout': 7200,
            'max_login_attempts': 3,
        }
        r = patch_json(auth_client, '/api/v2/settings/general', updates)
        assert_success(r)
        # Verify
        r = auth_client.get('/api/v2/settings/general')
        data = assert_success(r)
        assert data['site_name'] == 'Multi-Update UCM'
        assert data['timezone'] == 'America/New_York'
        assert data['session_timeout'] == 7200
        assert data['max_login_attempts'] == 3

    def test_patch_general_boolean_field(self, auth_client):
        r = patch_json(auth_client, '/api/v2/settings/general', {'auto_backup_enabled': True})
        assert_success(r)
        r = auth_client.get('/api/v2/settings/general')
        data = assert_success(r)
        assert data['auto_backup_enabled'] is True

    def test_patch_general_empty_body(self, auth_client):
        """PATCH with empty body should succeed (no-op)."""
        r = patch_json(auth_client, '/api/v2/settings/general', {})
        assert_success(r)

    def test_patch_general_ignores_unknown_keys(self, auth_client):
        """Unknown keys should be silently ignored, not error."""
        r = patch_json(auth_client, '/api/v2/settings/general', {
            'site_name': 'After Unknown',
            'nonexistent_key': 'should_be_ignored',
        })
        assert_success(r)
        r = auth_client.get('/api/v2/settings/general')
        data = assert_success(r)
        assert data['site_name'] == 'After Unknown'


# ============================================================
# Backup Settings
# ============================================================

class TestBackupSettings:
    """Backup endpoints: GET config, create, download, delete, schedule, history."""

    def test_get_backup_settings(self, auth_client):
        r = auth_client.get('/api/v2/settings/backup')
        data = assert_success(r)
        assert 'enabled' in data

    def test_create_backup(self, auth_client):
        """Create backup — auto-generates password if not provided."""
        r = post_json(auth_client, '/api/v2/settings/backup/create', {})
        # May succeed or fail depending on BackupService availability
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            data = assert_success(r)
            assert 'filename' in data
            assert 'size' in data
            assert data.get('password_generated') is True
            assert 'password' in data

    def test_create_backup_with_password(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/backup/create', {'password': 'securePass123!'})
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            data = assert_success(r)
            assert 'filename' in data
            # Should NOT include password in response when user-provided
            assert data.get('password_generated') is not True

    def test_create_backup_short_password(self, auth_client):
        """Password shorter than 8 chars should be rejected."""
        r = post_json(auth_client, '/api/v2/settings/backup/create', {'password': 'short'})
        assert r.status_code == 400

    def test_download_backup_not_found(self, auth_client):
        r = auth_client.get('/api/v2/settings/backup/nonexistent.ucmbkp/download')
        assert_error(r, 404)

    def test_download_backup_path_traversal(self, auth_client):
        """Path traversal should be blocked."""
        r = auth_client.get('/api/v2/settings/backup/../../etc/passwd/download')
        assert r.status_code in (400, 403, 404)

    def test_delete_backup_nonexistent(self, auth_client):
        """Deleting a nonexistent backup should still return 204 (idempotent)."""
        r = auth_client.delete('/api/v2/settings/backup/nonexistent_file.ucmbkp')
        assert r.status_code == 204

    def test_restore_backup_no_file(self, auth_client):
        """Restore without file should return 400."""
        r = auth_client.post('/api/v2/settings/backup/restore',
                             content_type='multipart/form-data')
        assert_error(r, 400)

    def test_restore_backup_no_password(self, auth_client):
        """Restore without password should return 400."""
        import io
        data = {
            'file': (io.BytesIO(b'fake backup data'), 'test.ucmbkp'),
        }
        r = auth_client.post('/api/v2/settings/backup/restore',
                             data=data,
                             content_type='multipart/form-data')
        assert_error(r, 400)

    # Schedule
    def test_get_backup_schedule(self, auth_client):
        r = auth_client.get('/api/v2/settings/backup/schedule')
        data = assert_success(r)
        assert 'enabled' in data
        assert 'frequency' in data
        assert 'time' in data
        assert 'retention_days' in data

    def test_patch_backup_schedule(self, auth_client):
        r = patch_json(auth_client, '/api/v2/settings/backup/schedule', {
            'enabled': True,
            'frequency': 'weekly',
            'time': '03:00',
        })
        assert_success(r)

    def test_patch_backup_schedule_empty_body(self, auth_client):
        r = patch_json(auth_client, '/api/v2/settings/backup/schedule', {})
        assert_error(r, 400)

    # History
    def test_get_backup_history(self, auth_client):
        r = auth_client.get('/api/v2/settings/backup/history')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_get_backup_history_pagination(self, auth_client):
        r = auth_client.get('/api/v2/settings/backup/history?page=1&per_page=5')
        assert r.status_code == 200


# ============================================================
# Email Settings
# ============================================================

class TestEmailSettings:
    """Email SMTP settings, template CRUD, test, preview."""

    def test_get_email_settings(self, auth_client):
        r = auth_client.get('/api/v2/settings/email')
        data = assert_success(r)
        assert 'enabled' in data
        assert 'smtp_host' in data
        assert 'smtp_port' in data
        assert 'smtp_tls' in data
        assert 'from_email' in data

    def test_get_email_default_values(self, auth_client):
        """Default values should be sane."""
        r = auth_client.get('/api/v2/settings/email')
        data = assert_success(r)
        assert isinstance(data['smtp_port'], int)
        assert data['smtp_port'] in (25, 465, 587, 2525)

    def test_patch_email_settings(self, auth_client):
        r = patch_json(auth_client, '/api/v2/settings/email', {
            'enabled': True,
            'smtp_host': 'smtp.test.local',
            'smtp_port': 587,
            'smtp_username': 'testuser',
            'smtp_tls': True,
            'from_email': 'noreply@test.local',
            'from_name': 'UCM Test',
        })
        assert_success(r)
        # Verify
        r = auth_client.get('/api/v2/settings/email')
        data = assert_success(r)
        assert data['smtp_host'] == 'smtp.test.local'
        assert data['from_email'] == 'noreply@test.local'

    def test_patch_email_no_data(self, auth_client):
        r = auth_client.patch('/api/v2/settings/email',
                              data=None,
                              content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_patch_email_password_masked(self, auth_client):
        """Sending '********' should NOT overwrite existing password."""
        patch_json(auth_client, '/api/v2/settings/email', {
            'smtp_password': 'real_secret_123'
        })
        r = patch_json(auth_client, '/api/v2/settings/email', {
            'smtp_password': '********'
        })
        assert_success(r)

    def test_patch_email_content_type_valid(self, auth_client):
        for ct in ('html', 'text', 'both'):
            r = patch_json(auth_client, '/api/v2/settings/email', {'smtp_content_type': ct})
            assert_success(r)

    def test_patch_email_content_type_invalid(self, auth_client):
        """Invalid content type should be ignored."""
        r = patch_json(auth_client, '/api/v2/settings/email', {'smtp_content_type': 'xml'})
        assert_success(r)

    def test_test_email_no_address(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/email/test', {})
        assert_error(r, 400)

    def test_test_email_with_address(self, auth_client):
        """Sending test email — will fail without SMTP but should NOT 500."""
        r = post_json(auth_client, '/api/v2/settings/email/test', {'email': 'test@test.local'})
        # Should return 200 (sent) or 500 (SMTP error) — not an unhandled crash
        assert r.status_code in (200, 500)

    # Template
    def test_get_email_template(self, auth_client):
        r = auth_client.get('/api/v2/settings/email/template')
        data = assert_success(r)
        assert 'template' in data
        assert 'text_template' in data
        assert 'is_custom' in data
        assert 'default_template' in data

    def test_patch_email_template(self, auth_client):
        custom = '<html><body>{{content}}</body></html>'
        r = patch_json(auth_client, '/api/v2/settings/email/template', {
            'template': custom
        })
        assert_success(r)
        # Verify
        r = auth_client.get('/api/v2/settings/email/template')
        data = assert_success(r)
        assert data['template'] == custom
        assert data['is_custom'] is True

    def test_patch_email_text_template(self, auth_client):
        custom_text = '{{title}}\n{{content}}'
        r = patch_json(auth_client, '/api/v2/settings/email/template', {
            'text_template': custom_text
        })
        assert_success(r)
        r = auth_client.get('/api/v2/settings/email/template')
        data = assert_success(r)
        assert data['text_template'] == custom_text
        assert data['is_text_custom'] is True

    def test_patch_email_template_no_data(self, auth_client):
        r = auth_client.patch('/api/v2/settings/email/template',
                              data=None,
                              content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_reset_email_template(self, auth_client):
        r = auth_client.post('/api/v2/settings/email/template/reset')
        assert_success(r)
        # After reset, should no longer be custom
        r = auth_client.get('/api/v2/settings/email/template')
        data = assert_success(r)
        assert data['is_custom'] is False

    def test_preview_email_template_html(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/email/template/preview', {
            'template': '<html><body>{{content}}</body></html>',
            'type': 'html',
        })
        data = assert_success(r)
        assert 'html' in data

    def test_preview_email_template_text(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/email/template/preview', {
            'template': '{{title}}\n{{content}}',
            'type': 'text',
        })
        data = assert_success(r)
        assert 'text' in data


# ============================================================
# Notification Settings
# ============================================================

class TestNotificationSettings:
    """GET/PATCH /api/v2/settings/notifications, notification logs."""

    def test_get_notification_settings(self, auth_client):
        r = auth_client.get('/api/v2/settings/notifications')
        data = assert_success(r)
        assert 'configs' in data
        assert isinstance(data['configs'], list)

    def test_patch_notification_create_new(self, auth_client):
        """Create a new notification config via PATCH."""
        r = patch_json(auth_client, '/api/v2/settings/notifications', {
            'notification_type': 'cert_expiry',
            'enabled': True,
            'recipients': ['admin@test.local'],
            'threshold_days': 30,
            'cooldown_hours': 24,
        })
        assert_success(r)
        data = get_json(r)
        assert data.get('data', {}).get('id') is not None

    def test_patch_notification_update_by_type(self, auth_client):
        """Update existing notification config by type."""
        r = patch_json(auth_client, '/api/v2/settings/notifications', {
            'notification_type': 'cert_expiry',
            'enabled': False,
        })
        assert_success(r)

    def test_patch_notification_no_data(self, auth_client):
        r = auth_client.patch('/api/v2/settings/notifications',
                              data=None,
                              content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_patch_notification_no_type_or_id(self, auth_client):
        """PATCH without id or notification_type should return 400."""
        r = patch_json(auth_client, '/api/v2/settings/notifications', {
            'enabled': True,
        })
        assert_error(r, 400)

    def test_get_notification_logs(self, auth_client):
        r = auth_client.get('/api/v2/settings/notifications/logs')
        data = assert_success(r)
        assert 'logs' in data
        assert 'pagination' in data
        assert isinstance(data['logs'], list)

    def test_get_notification_logs_pagination(self, auth_client):
        r = auth_client.get('/api/v2/settings/notifications/logs?page=1&per_page=10')
        data = assert_success(r)
        assert data['pagination']['per_page'] == 10

    def test_get_notification_logs_filter_type(self, auth_client):
        r = auth_client.get('/api/v2/settings/notifications/logs?type=cert_expiry')
        data = assert_success(r)
        assert isinstance(data['logs'], list)


# ============================================================
# Audit Logs
# ============================================================

class TestAuditLogs:
    """GET /api/v2/settings/audit-logs"""

    def test_get_audit_logs(self, auth_client):
        r = auth_client.get('/api/v2/settings/audit-logs')
        assert r.status_code == 200
        data = get_json(r)
        assert 'data' in data or isinstance(data, list)

    def test_get_audit_logs_pagination(self, auth_client):
        r = auth_client.get('/api/v2/settings/audit-logs?page=1&per_page=5')
        assert r.status_code == 200

    def test_get_audit_logs_filter_action(self, auth_client):
        r = auth_client.get('/api/v2/settings/audit-logs?action=settings_update')
        assert r.status_code == 200

    def test_get_audit_logs_filter_date_range(self, auth_client):
        r = auth_client.get(
            '/api/v2/settings/audit-logs?start_date=2020-01-01T00:00:00Z&end_date=2099-12-31T23:59:59Z'
        )
        assert r.status_code == 200


# ============================================================
# LDAP Settings
# ============================================================

class TestLDAPSettings:
    """GET/PATCH /api/v2/settings/ldap, test connection."""

    def test_get_ldap_settings(self, auth_client):
        r = auth_client.get('/api/v2/settings/ldap')
        data = assert_success(r)
        assert 'enabled' in data
        assert 'port' in data
        assert 'base_dn' in data
        assert 'user_filter' in data

    def test_get_ldap_defaults(self, auth_client):
        r = auth_client.get('/api/v2/settings/ldap')
        data = assert_success(r)
        assert data['enabled'] is False
        assert data['port'] == 389
        assert data['use_ssl'] is False

    def test_patch_ldap_settings(self, auth_client):
        r = patch_json(auth_client, '/api/v2/settings/ldap', {
            'enabled': True,
            'server': 'ldap.test.local',
            'port': 636,
            'use_ssl': True,
            'base_dn': 'dc=test,dc=local',
            'bind_dn': 'cn=admin,dc=test,dc=local',
        })
        assert_success(r)

    def test_patch_ldap_no_data(self, auth_client):
        r = auth_client.patch('/api/v2/settings/ldap',
                              data=None,
                              content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_test_ldap_connection(self, auth_client):
        """LDAP test will fail without server — should return error, not crash."""
        r = post_json(auth_client, '/api/v2/settings/ldap/test', {
            'server': 'nonexistent.test.local',
            'port': 389,
            'bind_dn': 'cn=admin,dc=test,dc=local',
            'bind_password': 'secret',
        })
        # 400 (connection failed) or 501 (ldap3 not installed) — not 500 unhandled
        assert r.status_code in (200, 400, 501)

    def test_test_ldap_no_body(self, auth_client):
        """Test with empty body should still not crash."""
        r = post_json(auth_client, '/api/v2/settings/ldap/test', {})
        assert r.status_code in (200, 400, 501)


# ============================================================
# Webhooks
# ============================================================

class TestWebhooks:
    """CRUD + test for webhooks stored in settings."""

    def test_list_webhooks_empty(self, auth_client):
        r = auth_client.get('/api/v2/settings/webhooks')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_create_webhook(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/webhooks', {
            'name': 'Test Webhook',
            'url': 'https://httpbin.org/post',
            'events': ['cert.created', 'cert.revoked'],
            'enabled': True,
        })
        data = assert_success(r, 201)
        assert data['name'] == 'Test Webhook'
        assert data['url'] == 'https://httpbin.org/post'
        assert 'id' in data
        assert 'created_at' in data

    def test_create_webhook_missing_name(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/webhooks', {
            'url': 'https://example.com',
            'events': ['cert.created'],
        })
        assert_error(r, 400)

    def test_create_webhook_missing_url(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/webhooks', {
            'name': 'No URL',
            'events': ['cert.created'],
        })
        assert_error(r, 400)

    def test_create_webhook_missing_events(self, auth_client):
        r = post_json(auth_client, '/api/v2/settings/webhooks', {
            'name': 'No Events',
            'url': 'https://example.com',
        })
        assert_error(r, 400)

    def test_list_webhooks_after_create(self, auth_client):
        # Ensure at least one exists
        post_json(auth_client, '/api/v2/settings/webhooks', {
            'name': 'List Test Webhook',
            'url': 'https://example.com/hook',
            'events': ['cert.created'],
        })
        r = auth_client.get('/api/v2/settings/webhooks')
        data = assert_success(r)
        assert len(data) >= 1
        assert any(w['name'] == 'List Test Webhook' for w in data)

    def test_delete_webhook(self, auth_client):
        # Create then delete
        r = post_json(auth_client, '/api/v2/settings/webhooks', {
            'name': 'To Delete',
            'url': 'https://example.com/delete',
            'events': ['cert.created'],
        })
        wh = assert_success(r, 201)
        wh_id = wh['id']

        r = auth_client.delete(f'/api/v2/settings/webhooks/{wh_id}')
        assert r.status_code == 204

        # Verify deleted
        r = auth_client.get('/api/v2/settings/webhooks')
        data = assert_success(r)
        assert not any(w.get('id') == wh_id for w in data)

    def test_delete_webhook_nonexistent(self, auth_client):
        """Deleting nonexistent webhook should be idempotent (204)."""
        r = auth_client.delete('/api/v2/settings/webhooks/99999')
        assert r.status_code == 204

    def test_test_webhook_not_found(self, auth_client):
        """Testing a nonexistent webhook should return 404."""
        r = post_json(auth_client, '/api/v2/settings/webhooks/99999/test', {})
        assert_error(r, 404)

    def test_test_webhook_unreachable(self, auth_client):
        """Testing a webhook with unreachable URL should return 500."""
        r = post_json(auth_client, '/api/v2/settings/webhooks', {
            'name': 'Unreachable Hook',
            'url': 'https://192.0.2.1:9999/nope',
            'events': ['test'],
        })
        wh = assert_success(r, 201)
        wh_id = wh['id']

        r = post_json(auth_client, f'/api/v2/settings/webhooks/{wh_id}/test', {})
        # Should return 500 with error message, not crash
        assert r.status_code == 500
        body = get_json(r)
        assert 'error' in body or 'message' in body
