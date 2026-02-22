"""
Templates API Tests — /api/v2/templates/*

Comprehensive tests for certificate template management endpoints:
- List, Create, Get, Update, Delete
- Bulk delete
- Duplicate
- Export (single + all)
- Import (JSON content)
- Auth/RBAC enforcement
- System template protection
- Full lifecycle
"""
import pytest
import os
import sys
import json
import io
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# Module-scoped fixtures (isolated DB per module)
# ============================================================

@pytest.fixture(scope='module')
def app():
    """Create app with test configuration."""
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-for-testing'
    os.environ['UCM_ENV'] = 'test'
    os.environ['HTTP_REDIRECT'] = 'false'
    os.environ['INITIAL_ADMIN_PASSWORD'] = 'changeme123'
    os.environ['CSRF_DISABLED'] = 'true'

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name

    from app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    yield app

    if os.path.exists(temp_db):
        os.unlink(temp_db)


@pytest.fixture(scope='module')
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture(scope='module')
def auth_client(app):
    """Authenticated test client (admin)."""
    c = app.test_client()
    r = c.post('/api/v2/auth/login',
               data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
               content_type='application/json')
    assert r.status_code == 200, f'Login failed: {r.data}'
    return c


# ============================================================
# Helpers
# ============================================================

def get_json(response):
    return json.loads(response.data)


def assert_success(response, status=200):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    return get_json(response)


def assert_error(response, status):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


VALID_TEMPLATE = {
    'name': 'Test Web Server TLS',
    'description': 'Template for web server certificates',
    'template_type': 'web_server',
    'key_type': 'RSA-2048',
    'validity_days': 365,
    'digest': 'sha256',
    'dn_template': {'CN': '{hostname}', 'O': 'Test Org'},
    'extensions_template': {
        'key_usage': ['digitalSignature', 'keyEncipherment'],
        'extended_key_usage': ['serverAuth'],
        'basic_constraints': {'ca': False},
    },
}


def _create_template(auth_client, name=None, **overrides):
    """Helper to create a template and return (response, data)."""
    data = {**VALID_TEMPLATE}
    if name:
        data['name'] = name
    data.update(overrides)
    r = auth_client.post('/api/v2/templates',
                         data=json.dumps(data),
                         content_type='application/json')
    return r, get_json(r)


# ============================================================
# 1. Authentication Required
# ============================================================

class TestTemplatesAuth:
    """All template endpoints require authentication."""

    def test_list_unauth(self, client):
        r = client.get('/api/v2/templates')
        assert r.status_code in (401, 403)

    def test_create_unauth(self, client):
        r = client.post('/api/v2/templates',
                        data=json.dumps(VALID_TEMPLATE),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_get_unauth(self, client):
        r = client.get('/api/v2/templates/1')
        assert r.status_code in (401, 403)

    def test_update_unauth(self, client):
        r = client.put('/api/v2/templates/1',
                       data=json.dumps({'name': 'x'}),
                       content_type='application/json')
        assert r.status_code in (401, 403)

    def test_delete_unauth(self, client):
        r = client.delete('/api/v2/templates/1')
        assert r.status_code in (401, 403)

    def test_bulk_delete_unauth(self, client):
        r = client.post('/api/v2/templates/bulk/delete',
                        data=json.dumps({'ids': [1]}),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_duplicate_unauth(self, client):
        r = client.post('/api/v2/templates/1/duplicate')
        assert r.status_code in (401, 403)

    def test_export_single_unauth(self, client):
        r = client.get('/api/v2/templates/1/export')
        assert r.status_code in (401, 403)

    def test_export_all_unauth(self, client):
        r = client.get('/api/v2/templates/export')
        assert r.status_code in (401, 403)

    def test_import_unauth(self, client):
        r = client.post('/api/v2/templates/import',
                        data={'json_content': '[]'},
                        content_type='multipart/form-data')
        assert r.status_code in (401, 403)


# ============================================================
# 2. List Templates
# ============================================================

class TestListTemplates:
    """GET /api/v2/templates"""

    def test_list_returns_200(self, auth_client):
        r = auth_client.get('/api/v2/templates')
        assert r.status_code == 200

    def test_list_returns_array(self, auth_client):
        data = assert_success(auth_client.get('/api/v2/templates'))
        assert isinstance(data.get('data'), list)

    def test_system_templates_exist(self, auth_client):
        """System templates should be seeded at startup."""
        data = assert_success(auth_client.get('/api/v2/templates'))
        templates = data['data']
        system = [t for t in templates if t.get('is_system')]
        assert len(system) >= 1, 'Expected at least one system template'

    def test_filter_by_type(self, auth_client):
        r = auth_client.get('/api/v2/templates?type=web_server')
        data = assert_success(r)
        for t in data['data']:
            assert t['template_type'] == 'web_server'

    def test_filter_by_active(self, auth_client):
        r = auth_client.get('/api/v2/templates?active=true')
        data = assert_success(r)
        for t in data['data']:
            assert t['is_active'] is True

    def test_search_by_name(self, auth_client):
        # Create a template with a unique name for search
        _create_template(auth_client, name='Searchable Unique XYZ')
        r = auth_client.get('/api/v2/templates?search=Searchable Unique')
        data = assert_success(r)
        names = [t['name'] for t in data['data']]
        assert any('Searchable Unique' in n for n in names)


# ============================================================
# 3. Create Template
# ============================================================

class TestCreateTemplate:
    """POST /api/v2/templates"""

    def test_create_valid(self, auth_client):
        r, data = _create_template(auth_client, name='Create Valid Test')
        assert r.status_code in (200, 201)
        assert data['data']['name'] == 'Create Valid Test'
        assert data['data']['is_system'] is False

    def test_create_returns_all_fields(self, auth_client):
        r, data = _create_template(auth_client, name='Field Check Tpl')
        tpl = data['data']
        for field in ('id', 'name', 'description', 'template_type', 'key_type',
                      'validity_days', 'digest', 'is_system', 'is_active'):
            assert field in tpl, f'Missing field: {field}'

    def test_create_missing_name(self, auth_client):
        payload = {**VALID_TEMPLATE}
        del payload['name']
        r = auth_client.post('/api/v2/templates',
                             data=json.dumps(payload),
                             content_type='application/json')
        assert_error(r, 400)

    def test_create_missing_type(self, auth_client):
        payload = {**VALID_TEMPLATE, 'name': 'No Type Tpl'}
        del payload['template_type']
        r = auth_client.post('/api/v2/templates',
                             data=json.dumps(payload),
                             content_type='application/json')
        assert_error(r, 400)

    def test_create_invalid_type(self, auth_client):
        r = auth_client.post('/api/v2/templates',
                             data=json.dumps({**VALID_TEMPLATE,
                                              'name': 'Bad Type',
                                              'template_type': 'invalid_type'}),
                             content_type='application/json')
        assert_error(r, 400)

    def test_create_duplicate_name(self, auth_client):
        name = 'Duplicate Name Check'
        _create_template(auth_client, name=name)
        r, _ = _create_template(auth_client, name=name)
        assert r.status_code == 409

    def test_create_default_values(self, auth_client):
        """Omitted optional fields get defaults."""
        payload = {
            'name': 'Defaults Test Tpl',
            'template_type': 'web_server',
        }
        r = auth_client.post('/api/v2/templates',
                             data=json.dumps(payload),
                             content_type='application/json')
        assert r.status_code in (200, 201)
        tpl = get_json(r)['data']
        assert tpl['key_type'] == 'RSA-2048'
        assert tpl['validity_days'] == 397
        assert tpl['digest'] == 'sha256'

    def test_create_all_valid_types(self, auth_client):
        """All documented template types should be accepted."""
        valid_types = ['web_server', 'email', 'vpn_server', 'vpn_client',
                       'code_signing', 'client_auth', 'piv', 'custom']
        for ttype in valid_types:
            r, data = _create_template(auth_client,
                                       name=f'Type Test {ttype}',
                                       template_type=ttype)
            assert r.status_code in (200, 201), \
                f'Type {ttype} rejected: {r.data[:200]}'


# ============================================================
# 4. Get Template
# ============================================================

class TestGetTemplate:
    """GET /api/v2/templates/<id>"""

    def test_get_existing(self, auth_client):
        r, created = _create_template(auth_client, name='Get Test Tpl')
        tid = created['data']['id']
        r = auth_client.get(f'/api/v2/templates/{tid}')
        data = assert_success(r)
        assert data['data']['id'] == tid
        assert data['data']['name'] == 'Get Test Tpl'

    def test_get_nonexistent(self, auth_client):
        r = auth_client.get('/api/v2/templates/999999')
        assert_error(r, 404)

    def test_get_returns_extensions(self, auth_client):
        r, created = _create_template(auth_client, name='Extensions Check Tpl')
        tid = created['data']['id']
        r = auth_client.get(f'/api/v2/templates/{tid}')
        tpl = get_json(r)['data']
        assert 'extensions_template' in tpl
        ext = tpl['extensions_template']
        assert 'key_usage' in ext
        assert 'digitalSignature' in ext['key_usage']


# ============================================================
# 5. Update Template
# ============================================================

class TestUpdateTemplate:
    """PUT /api/v2/templates/<id>"""

    def test_update_description(self, auth_client):
        r, created = _create_template(auth_client, name='Update Desc Tpl')
        tid = created['data']['id']
        r = auth_client.put(f'/api/v2/templates/{tid}',
                            data=json.dumps({'description': 'Updated!'}),
                            content_type='application/json')
        data = assert_success(r)
        assert data['data']['description'] == 'Updated!'

    def test_update_name(self, auth_client):
        r, created = _create_template(auth_client, name='Rename Me Tpl')
        tid = created['data']['id']
        r = auth_client.put(f'/api/v2/templates/{tid}',
                            data=json.dumps({'name': 'Renamed Tpl'}),
                            content_type='application/json')
        data = assert_success(r)
        assert data['data']['name'] == 'Renamed Tpl'

    def test_update_name_conflict(self, auth_client):
        """Renaming to an existing name should fail."""
        _create_template(auth_client, name='Existing Name Tpl')
        r, created = _create_template(auth_client, name='Will Conflict Tpl')
        tid = created['data']['id']
        r = auth_client.put(f'/api/v2/templates/{tid}',
                            data=json.dumps({'name': 'Existing Name Tpl'}),
                            content_type='application/json')
        assert r.status_code == 409

    def test_update_nonexistent(self, auth_client):
        r = auth_client.put('/api/v2/templates/999999',
                            data=json.dumps({'description': 'nope'}),
                            content_type='application/json')
        assert_error(r, 404)

    def test_update_system_template_forbidden(self, auth_client):
        """System templates cannot be modified."""
        data = assert_success(auth_client.get('/api/v2/templates'))
        system = [t for t in data['data'] if t.get('is_system')]
        if not system:
            pytest.skip('No system templates found')
        tid = system[0]['id']
        r = auth_client.put(f'/api/v2/templates/{tid}',
                            data=json.dumps({'description': 'hacked'}),
                            content_type='application/json')
        assert r.status_code == 403

    def test_update_validity_days(self, auth_client):
        r, created = _create_template(auth_client, name='Validity Update Tpl')
        tid = created['data']['id']
        r = auth_client.put(f'/api/v2/templates/{tid}',
                            data=json.dumps({'validity_days': 730}),
                            content_type='application/json')
        data = assert_success(r)
        assert data['data']['validity_days'] == 730

    def test_update_deactivate(self, auth_client):
        r, created = _create_template(auth_client, name='Deactivate Tpl')
        tid = created['data']['id']
        r = auth_client.put(f'/api/v2/templates/{tid}',
                            data=json.dumps({'is_active': False}),
                            content_type='application/json')
        data = assert_success(r)
        assert data['data']['is_active'] is False


# ============================================================
# 6. Delete Template
# ============================================================

class TestDeleteTemplate:
    """DELETE /api/v2/templates/<id>"""

    def test_delete_user_template(self, auth_client):
        r, created = _create_template(auth_client, name='Delete Me Tpl')
        tid = created['data']['id']
        r = auth_client.delete(f'/api/v2/templates/{tid}')
        assert r.status_code == 204
        # Confirm gone
        r = auth_client.get(f'/api/v2/templates/{tid}')
        assert_error(r, 404)

    def test_delete_nonexistent(self, auth_client):
        r = auth_client.delete('/api/v2/templates/999999')
        assert_error(r, 404)

    def test_delete_system_template_forbidden(self, auth_client):
        """System templates cannot be deleted."""
        data = assert_success(auth_client.get('/api/v2/templates'))
        system = [t for t in data['data'] if t.get('is_system')]
        if not system:
            pytest.skip('No system templates found')
        tid = system[0]['id']
        r = auth_client.delete(f'/api/v2/templates/{tid}')
        assert r.status_code == 403
        # Confirm still exists
        r = auth_client.get(f'/api/v2/templates/{tid}')
        assert r.status_code == 200


# ============================================================
# 7. Duplicate Template
# ============================================================

class TestDuplicateTemplate:
    """POST /api/v2/templates/<id>/duplicate"""

    def test_duplicate_creates_copy(self, auth_client):
        r, created = _create_template(auth_client, name='Original Tpl')
        tid = created['data']['id']
        r = auth_client.post(f'/api/v2/templates/{tid}/duplicate')
        assert r.status_code in (200, 201)
        clone = get_json(r)['data']
        assert clone['name'] == 'Original Tpl (Copy)'
        assert clone['id'] != tid
        assert clone['is_system'] is False

    def test_duplicate_preserves_fields(self, auth_client):
        r, created = _create_template(auth_client, name='Clone Fields Tpl',
                                      validity_days=999, digest='sha384')
        tid = created['data']['id']
        r = auth_client.post(f'/api/v2/templates/{tid}/duplicate')
        clone = get_json(r)['data']
        assert clone['validity_days'] == 999
        assert clone['digest'] == 'sha384'
        assert clone['template_type'] == created['data']['template_type']

    def test_duplicate_increments_name(self, auth_client):
        """Second duplicate should get ' (Copy) 2' suffix."""
        r, created = _create_template(auth_client, name='Multi Dup Tpl')
        tid = created['data']['id']
        # First duplicate
        auth_client.post(f'/api/v2/templates/{tid}/duplicate')
        # Second duplicate
        r = auth_client.post(f'/api/v2/templates/{tid}/duplicate')
        clone = get_json(r)['data']
        assert '(Copy)' in clone['name']
        assert clone['name'] != 'Multi Dup Tpl (Copy)'  # should be different

    def test_duplicate_nonexistent(self, auth_client):
        r = auth_client.post('/api/v2/templates/999999/duplicate')
        assert_error(r, 404)

    def test_duplicate_system_template(self, auth_client):
        """Duplicating a system template should work (clone is non-system)."""
        data = assert_success(auth_client.get('/api/v2/templates'))
        system = [t for t in data['data'] if t.get('is_system')]
        if not system:
            pytest.skip('No system templates found')
        tid = system[0]['id']
        r = auth_client.post(f'/api/v2/templates/{tid}/duplicate')
        assert r.status_code in (200, 201)
        clone = get_json(r)['data']
        assert clone['is_system'] is False


# ============================================================
# 8. Export Templates
# ============================================================

class TestExportTemplates:
    """GET /api/v2/templates/<id>/export and /api/v2/templates/export"""

    def test_export_single(self, auth_client):
        r, created = _create_template(auth_client, name='Export Single Tpl')
        tid = created['data']['id']
        r = auth_client.get(f'/api/v2/templates/{tid}/export')
        assert r.status_code == 200
        assert r.content_type == 'application/json'
        export = json.loads(r.data)
        assert export['name'] == 'Export Single Tpl'
        assert export['is_system'] is False

    def test_export_single_has_content_disposition(self, auth_client):
        r, created = _create_template(auth_client, name='Export Header Tpl')
        tid = created['data']['id']
        r = auth_client.get(f'/api/v2/templates/{tid}/export')
        assert 'Content-Disposition' in r.headers
        assert 'attachment' in r.headers['Content-Disposition']

    def test_export_single_nonexistent(self, auth_client):
        r = auth_client.get('/api/v2/templates/999999/export')
        assert_error(r, 404)

    def test_export_all(self, auth_client):
        r = auth_client.get('/api/v2/templates/export')
        assert r.status_code == 200
        export = json.loads(r.data)
        assert isinstance(export, list)

    def test_export_all_excludes_system(self, auth_client):
        """Export all should only include non-system templates."""
        r = auth_client.get('/api/v2/templates/export')
        export = json.loads(r.data)
        for tpl in export:
            assert tpl.get('is_system') is False

    def test_export_single_contains_required_fields(self, auth_client):
        r, created = _create_template(auth_client, name='Export Fields Tpl')
        tid = created['data']['id']
        r = auth_client.get(f'/api/v2/templates/{tid}/export')
        export = json.loads(r.data)
        for field in ('name', 'template_type', 'key_type', 'validity_days',
                      'digest', 'extensions_template'):
            assert field in export, f'Export missing field: {field}'


# ============================================================
# 9. Import Templates
# ============================================================

class TestImportTemplates:
    """POST /api/v2/templates/import"""

    def test_import_json_content(self, auth_client):
        tpl = {
            'name': 'Imported Via JSON',
            'template_type': 'custom',
            'key_type': 'RSA-4096',
            'validity_days': 365,
            'digest': 'sha256',
            'extensions_template': json.dumps({
                'key_usage': ['digitalSignature'],
                'extended_key_usage': ['serverAuth'],
            }),
        }
        r = auth_client.post('/api/v2/templates/import',
                             data={'json_content': json.dumps(tpl)},
                             content_type='multipart/form-data')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert result['imported'] == 1

    def test_import_array(self, auth_client):
        ext = json.dumps({'key_usage': ['digitalSignature']})
        tpls = [
            {'name': 'Import Array 1', 'template_type': 'custom', 'extensions_template': ext},
            {'name': 'Import Array 2', 'template_type': 'email', 'extensions_template': ext},
        ]
        r = auth_client.post('/api/v2/templates/import',
                             data={'json_content': json.dumps(tpls)},
                             content_type='multipart/form-data')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert result['imported'] == 2

    def test_import_skips_existing(self, auth_client):
        name = 'Import Skip Existing'
        _create_template(auth_client, name=name)
        tpl = {'name': name, 'template_type': 'custom'}
        r = auth_client.post('/api/v2/templates/import',
                             data={'json_content': json.dumps(tpl)},
                             content_type='multipart/form-data')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert result['skipped'] == 1
        assert result['imported'] == 0

    def test_import_update_existing(self, auth_client):
        name = 'Import Update Existing'
        _create_template(auth_client, name=name, description='original')
        tpl = {'name': name, 'template_type': 'custom', 'description': 'updated'}
        r = auth_client.post('/api/v2/templates/import',
                             data={
                                 'json_content': json.dumps(tpl),
                                 'update_existing': 'true',
                             },
                             content_type='multipart/form-data')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert result['updated'] == 1

    def test_import_no_data(self, auth_client):
        r = auth_client.post('/api/v2/templates/import',
                             content_type='multipart/form-data')
        assert_error(r, 400)

    def test_import_invalid_json(self, auth_client):
        r = auth_client.post('/api/v2/templates/import',
                             data={'json_content': '{bad json!!!'},
                             content_type='multipart/form-data')
        assert_error(r, 400)

    def test_import_skips_nameless(self, auth_client):
        """Templates without a name should be skipped."""
        tpl = {'template_type': 'custom', 'description': 'no name'}
        r = auth_client.post('/api/v2/templates/import',
                             data={'json_content': json.dumps(tpl)},
                             content_type='multipart/form-data')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert result['imported'] == 0
        assert result['skipped'] == 1


# ============================================================
# 10. Bulk Delete
# ============================================================

class TestBulkDelete:
    """POST /api/v2/templates/bulk/delete"""

    def test_bulk_delete(self, auth_client):
        r1, d1 = _create_template(auth_client, name='Bulk Del 1')
        r2, d2 = _create_template(auth_client, name='Bulk Del 2')
        ids = [d1['data']['id'], d2['data']['id']]
        r = auth_client.post('/api/v2/templates/bulk/delete',
                             data=json.dumps({'ids': ids}),
                             content_type='application/json')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert len(result['success']) == 2

    def test_bulk_delete_missing_ids(self, auth_client):
        r = auth_client.post('/api/v2/templates/bulk/delete',
                             data=json.dumps({}),
                             content_type='application/json')
        assert_error(r, 400)

    def test_bulk_delete_nonexistent(self, auth_client):
        r = auth_client.post('/api/v2/templates/bulk/delete',
                             data=json.dumps({'ids': [999998, 999999]}),
                             content_type='application/json')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert len(result['failed']) == 2

    def test_bulk_delete_skips_system(self, auth_client):
        """System templates should be reported as failed in bulk delete."""
        data = assert_success(auth_client.get('/api/v2/templates'))
        system = [t for t in data['data'] if t.get('is_system')]
        if not system:
            pytest.skip('No system templates found')
        sid = system[0]['id']
        r = auth_client.post('/api/v2/templates/bulk/delete',
                             data=json.dumps({'ids': [sid]}),
                             content_type='application/json')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert len(result['failed']) == 1
        assert len(result['success']) == 0

    def test_bulk_delete_mixed(self, auth_client):
        """Mix of valid, system, and nonexistent IDs."""
        r, created = _create_template(auth_client, name='Bulk Mixed Tpl')
        valid_id = created['data']['id']
        data = assert_success(auth_client.get('/api/v2/templates'))
        system = [t for t in data['data'] if t.get('is_system')]
        ids = [valid_id, 999997]
        if system:
            ids.append(system[0]['id'])
        r = auth_client.post('/api/v2/templates/bulk/delete',
                             data=json.dumps({'ids': ids}),
                             content_type='application/json')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert valid_id in result['success']
        assert len(result['failed']) >= 1


# ============================================================
# 11. Template Lifecycle
# ============================================================

class TestTemplateLifecycle:
    """End-to-end lifecycle: create → get → update → duplicate → export → delete"""

    def test_full_lifecycle(self, auth_client):
        # 1. Create
        r, data = _create_template(auth_client, name='Lifecycle Tpl',
                                   description='initial',
                                   validity_days=365)
        assert r.status_code in (200, 201)
        tid = data['data']['id']

        # 2. Get
        r = auth_client.get(f'/api/v2/templates/{tid}')
        tpl = assert_success(r)['data']
        assert tpl['name'] == 'Lifecycle Tpl'
        assert tpl['validity_days'] == 365

        # 3. Update
        r = auth_client.put(f'/api/v2/templates/{tid}',
                            data=json.dumps({
                                'description': 'updated desc',
                                'validity_days': 730,
                            }),
                            content_type='application/json')
        tpl = assert_success(r)['data']
        assert tpl['description'] == 'updated desc'
        assert tpl['validity_days'] == 730

        # 4. Duplicate
        r = auth_client.post(f'/api/v2/templates/{tid}/duplicate')
        clone = get_json(r)['data']
        clone_id = clone['id']
        assert clone['name'] == 'Lifecycle Tpl (Copy)'
        assert clone['validity_days'] == 730  # inherited updated value

        # 5. Export original
        r = auth_client.get(f'/api/v2/templates/{tid}/export')
        assert r.status_code == 200
        exported = json.loads(r.data)
        assert exported['name'] == 'Lifecycle Tpl'

        # 6. Delete both
        r = auth_client.delete(f'/api/v2/templates/{tid}')
        assert r.status_code == 204
        r = auth_client.delete(f'/api/v2/templates/{clone_id}')
        assert r.status_code == 204

        # 7. Confirm gone
        assert_error(auth_client.get(f'/api/v2/templates/{tid}'), 404)
        assert_error(auth_client.get(f'/api/v2/templates/{clone_id}'), 404)

    def test_create_export_import_roundtrip(self, auth_client):
        """Create → export → delete → import should restore the template."""
        # Create
        r, data = _create_template(auth_client, name='Roundtrip Tpl',
                                   validity_days=500)
        tid = data['data']['id']

        # Export
        r = auth_client.get(f'/api/v2/templates/{tid}/export')
        exported_json = r.data.decode('utf-8')

        # Delete
        r = auth_client.delete(f'/api/v2/templates/{tid}')
        assert r.status_code == 204

        # Import
        r = auth_client.post('/api/v2/templates/import',
                             data={'json_content': exported_json},
                             content_type='multipart/form-data')
        assert r.status_code == 200
        result = get_json(r)['data']
        assert result['imported'] == 1

        # Verify restored
        r = auth_client.get('/api/v2/templates?search=Roundtrip Tpl')
        templates = get_json(r)['data']
        restored = [t for t in templates if t['name'] == 'Roundtrip Tpl']
        assert len(restored) == 1
        assert restored[0]['validity_days'] == 500
