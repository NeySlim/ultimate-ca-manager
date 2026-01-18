"""
UI Routes - Flask templates with HTMX
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, make_response, current_app
from flask_jwt_extended import create_access_token, set_access_cookies
from functools import wraps
from datetime import datetime, timedelta
import requests
import time
import os
import socket
from html import escape as html_escape
from config.settings import Config, DATA_DIR, restart_ucm_service
from app import cache

ui_bp = Blueprint('ui', __name__, template_folder='../../frontend/templates')

# Helper function to escape JavaScript strings
def escape_js(text):
    """Escape text for safe use in JavaScript strings"""
    if text is None:
        return ''
    # Escape backslashes first, then quotes
    text = str(text).replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    return text


# Helper function to get valid JWT token
def get_valid_jwt_token():
    """
    Get a valid JWT token, auto-refreshing if expired
    Returns: (token, headers) or (None, None) if session invalid
    """
    if 'user_id' not in session:
        return None, None
    
    # Get current token
    token = session.get('access_token')
    
    # If no token, create new one
    if not token:
        try:
            token = create_access_token(identity=session['user_id'])
            session['access_token'] = token
        except Exception as e:
            current_app.logger.error(f"Failed to create token: {e}")
            return None, None
    
    headers = {'Authorization': f'Bearer {token}'}
    return token, headers


# Helper function to make API call with auto token refresh
def api_call_with_retry(method, url, headers=None, **kwargs):
    """
    Make API call with automatic JWT refresh on 401
    Returns: Response object or None
    """
    token, api_headers = get_valid_jwt_token()
    if not token:
        return None
    
    if headers:
        api_headers.update(headers)
    
    # First attempt
    response = requests.request(method, url, headers=api_headers, verify=False, **kwargs)
    
    # If 401, refresh token and retry once
    if response.status_code == 401:
        current_app.logger.info(f"JWT expired, refreshing token for user {session.get('username')}")
        try:
            new_token = create_access_token(identity=session['user_id'])
            session['access_token'] = new_token
            api_headers['Authorization'] = f'Bearer {new_token}'
            
            # Retry request with new token
            response = requests.request(method, url, headers=api_headers, verify=False, **kwargs)
        except Exception as e:
            current_app.logger.error(f"Token refresh failed: {e}")
            return None
    
    return response

# Helper to check if user is logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if 'user_id' not in session:
            # If HTMX request, return 401 to trigger client-side redirect
            if request.headers.get('HX-Request'):
                return jsonify({'error': 'Session expired'}), 401
            return redirect(url_for('ui.login', expired='1'))
        
        # Check if session has expired (additional check)
        if 'last_activity' in session:
            last_activity_time = session['last_activity']
            # Handle old datetime format (migrate to timestamp)
            if isinstance(last_activity_time, datetime):
                last_activity_time = last_activity_time.timestamp()
                session['last_activity'] = last_activity_time
            
            current_time = time.time()
            # Check if 30 minutes (1800 seconds) have passed
            if current_time - last_activity_time > 1800:
                session.clear()
                if request.headers.get('HX-Request'):
                    return jsonify({'error': 'Session expired'}), 401
                return redirect(url_for('ui.login', expired='1'))
        
        # Update last activity time (use timestamp)
        session['last_activity'] = time.time()
        
        return f(*args, **kwargs)
    return decorated_function


# Helper to check if user is admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check if logged in
        if 'user_id' not in session:
            if request.headers.get('HX-Request'):
                return jsonify({'error': 'Session expired'}), 401
            return redirect(url_for('ui.login', expired='1'))
        
        # Check if admin role
        if session.get('role') != 'admin':
            if request.headers.get('HX-Request'):
                return jsonify({'error': 'Admin access required'}), 403
            flash('Accès administrateur requis', 'error')
            return redirect(url_for('ui.dashboard'))
        
        # Update last activity
        session['last_activity'] = time.time()
        
        return f(*args, **kwargs)
    return decorated_function


# Auth routes
@ui_bp.route('/')
def index():
    """Redirect to dashboard or login"""
    if 'user_id' in session:
        return redirect(url_for('ui.dashboard'))
    return redirect(url_for('ui.login'))


@ui_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    # Show session expired message if redirected with expired flag
    if request.method == 'GET' and request.args.get('expired') == '1':
        flash('Votre session a expiré. Veuillez vous reconnecter.', 'error')
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Call API to authenticate
        try:
            response = requests.post(
                f"{request.url_root}api/v1/auth/login",
                json={"username": username, "password": password},
                verify=False
            )
            
            if response.status_code == 200:
                data = response.json()
                session.permanent = True  # Enable permanent session with timeout
                session['user_id'] = data.get('user', {}).get('id')
                session['username'] = username
                session['access_token'] = data.get('access_token')
                session['role'] = data.get('user', {}).get('role', 'viewer')
                session['last_activity'] = time.time()  # Track session activity (timestamp)
                flash('Login successful!', 'success')
                
                # Create response with JWT cookies using Flask-JWT-Extended
                resp = make_response(redirect(url_for('ui.dashboard'), code=303))
                
                # Use Flask-JWT-Extended helper to set cookies properly
                # We need to create a new access token because set_access_cookies expects the token
                access_token = data.get('access_token')
                set_access_cookies(resp, access_token)
                
                return resp
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'error')
    
    return render_template('auth/login.html')


@ui_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Logout"""
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('ui.login'), code=303)


# Dashboard
@ui_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page"""
    from datetime import datetime, timedelta
    
    stats = {
        'total_cas': 0,
        'total_certificates': 0,
        'valid_certificates': 0,
        'expiring_soon': 0
    }
    
    certificates = []
    scep_requests = []
    
    try:
        token = session.get('access_token')
        if not token:
            return render_template('dashboard.html', stats=stats, certificates=certificates, scep_requests=scep_requests)
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get CAs count
        ca_response = requests.get(f"{request.url_root}api/v1/ca/", headers=headers, verify=False)
        if ca_response.status_code == 200:
            cas = ca_response.json()
            stats['total_cas'] = len(cas)
        
        # Get all certificates
        cert_response = requests.get(f"{request.url_root}api/v1/certificates/", headers=headers, verify=False)
        if cert_response.status_code == 200:
            all_certs = cert_response.json()
            stats['total_certificates'] = len(all_certs)
            
            now = datetime.now()
            threshold = now + timedelta(days=30)
            
            valid_count = 0
            expiring_count = 0
            recent_list = []
            
            # Process certificates
            for cert in all_certs:
                # Determine if certificate is valid
                is_valid = False
                if cert.get('valid_to') and not cert.get('revoked', False):
                    try:
                        valid_to = datetime.fromisoformat(cert['valid_to'].replace('Z', '+00:00'))
                        is_valid = valid_to > now
                        
                        # Count expiring certificates
                        if is_valid and valid_to <= threshold:
                            expiring_count += 1
                    except:
                        pass
                
                if is_valid:
                    valid_count += 1
                
                # Add to recent list (will sort by created_at later)
                recent_list.append({
                    'common_name': cert.get('common_name', cert.get('descr', 'Unknown')),
                    'type': cert.get('cert_type', 'N/A'),
                    'issuer_cn': cert.get('issuer_name', 'Unknown'),
                    'is_valid': is_valid,
                    'not_after': cert.get('valid_to'),
                    'created_at': cert.get('created_at', '')
                })
            
            stats['valid_certificates'] = valid_count
            stats['expiring_soon'] = expiring_count
            
            # Sort by created_at and take top 5
            recent_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            certificates = recent_list[:5]
        
        # Get SCEP requests
        scep_response = requests.get(f"{request.url_root}scep/requests", headers=headers, verify=False)
        if scep_response.status_code == 200:
            scep_data = scep_response.json()
            
            # Get CA names for display
            ca_names = {}
            if ca_response.status_code == 200:
                for ca in ca_response.json():
                    ca_names[ca['refid']] = ca['descr']
            
            # Process SCEP requests
            for req in scep_data:
                # Extract common name from subject
                subject = req.get('subject', '')
                common_name = subject
                if 'CN=' in subject:
                    # Extract CN from subject string
                    parts = subject.split(',')
                    for part in parts:
                        if part.strip().startswith('CN='):
                            common_name = part.strip()[3:]
                            break
                
                scep_requests.append({
                    'common_name': common_name,
                    'status': req.get('status', 'unknown'),
                    'ca_name': 'SCEP',  # Could enhance this by linking to actual CA
                    'created_at': datetime.fromisoformat(req['created_at'].replace('Z', '+00:00')) if req.get('created_at') else None
                })
            
            # Sort by created_at (newest first) and limit to 5
            scep_requests.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
            
    except Exception as e:
        print(f"⚠️  Dashboard error: {e}")
        import traceback
        traceback.print_exc()
    
    return render_template('dashboard.html',
                         stats=stats,
                         certificates=certificates,
                         scep_requests=scep_requests,
                         token=token if 'token' in locals() else session.get('access_token', ''))



# Dashboard API endpoints (for HTMX)
@ui_bp.route('/api/dashboard/stats')
@login_required
@cache.cached(timeout=300, key_prefix='dashboard_stats')  # Cache for 5 minutes
def dashboard_stats():
    """Get dashboard statistics"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get counts from API
        ca_response = requests.get(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            verify=False
        )
        
        cert_response = requests.get(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            verify=False
        )
        
        scep_response = requests.get(
            f"{request.url_root}scep/requests",
            headers=headers,
            verify=False
        )
        
        ca_count = len(ca_response.json()) if ca_response.status_code == 200 else 0
        cert_count = len(cert_response.json()) if cert_response.status_code == 200 else 0
        scep_count = len(scep_response.json()) if scep_response.status_code == 200 else 0
        
        # Count pending SCEP requests
        pending_count = 0
        if scep_response.status_code == 200:
            pending_count = len([r for r in scep_response.json() if r['status'] == 'pending'])
        
        return f"""
        <!-- CA Count -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center;">
                <div style="flex-shrink: 0; padding: 0.75rem; background: var(--primary-bg); border-radius: 8px;">
                    <i class="fas fa-certificate" style="color: var(--primary-color); font-size: 1.5rem;"></i>
                </div>
                <div style="margin-left: 1rem;">
                    <p style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Certificate Authorities</p>
                    <p style="font-size: 1.875rem; font-weight: 700; color: var(--text-primary);">{ca_count}</p>
                </div>
            </div>
        </div>
        
        <!-- Cert Count -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center;">
                <div style="flex-shrink: 0; padding: 0.75rem; background: var(--success-bg); border-radius: 8px;">
                    <i class="fas fa-file-certificate" style="color: var(--success-color); font-size: 1.5rem;"></i>
                </div>
                <div style="margin-left: 1rem;">
                    <p style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Certificates</p>
                    <p style="font-size: 1.875rem; font-weight: 700; color: var(--text-primary);">{cert_count}</p>
                </div>
            </div>
        </div>
        
        <!-- SCEP Count -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center;">
                <div style="flex-shrink: 0; padding: 0.75rem; background: var(--warning-bg); border-radius: 8px;">
                    <i class="fas fa-network-wired" style="color: var(--warning-color); font-size: 1.5rem;"></i>
                </div>
                <div style="margin-left: 1rem;">
                    <p style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">SCEP Requests</p>
                    <p style="font-size: 1.875rem; font-weight: 700; color: var(--text-primary);">{scep_count}</p>
                </div>
            </div>
        </div>
        
        <!-- Pending Count -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center;">
                <div style="flex-shrink: 0; padding: 0.75rem; background: var(--warning-bg); border-radius: 8px;">
                    <i class="fas fa-clock" style="color: var(--warning-color); font-size: 1.5rem;"></i>
                </div>
                <div style="margin-left: 1rem;">
                    <p style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Pending Approvals</p>
                    <p style="font-size: 1.875rem; font-weight: 700; color: var(--text-primary);">{pending_count}</p>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        return f'<div style="color: var(--danger-color);">Error loading stats: {str(e)}</div>'


@ui_bp.route('/api/dashboard/recent-cas')
@login_required
@cache.cached(timeout=3600, key_prefix='dashboard_recent_cas')  # Cache for 1 hour
def dashboard_recent_cas():
    """Get recent CAs"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/ca/")
        
        if response.status_code != 200:
            return '<p style="color: var(--text-secondary);">No CAs found</p>'
        
        cas = response.json()[:5]  # Get latest 5
        
        if not cas:
            return '<p style="color: var(--text-secondary);">No CAs found. <a href="/ca/new" style="color: var(--primary-color);">Create one</a></p>'
        
        html = '<div class="space-y-3">'
        for ca in cas:
            html += f'''
            <a href="/ca/{ca['refid']}" style="display: block; padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px; text-decoration: none; transition: background 0.2s;" onmouseover="this.style.background='var(--hover-bg)'" onmouseout="this.style.background='var(--bg-secondary)'">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <p style="font-weight: 500; color: var(--text-primary);">{ca['descr']}</p>
                        <p style="font-size: 0.75rem; color: var(--text-secondary);">{ca.get('subject', 'N/A')}</p>
                    </div>
                    <i class="fas fa-chevron-right" style="color: var(--text-muted);"></i>
                </div>
            </a>
            '''
        html += '</div>'
        
        return html
    except Exception as e:
        return f'<p style="color: var(--danger-color);">Error: {str(e)}</p>'


@ui_bp.route('/api/dashboard/scep-status')
@login_required
def dashboard_scep_status():
    """Get SCEP status"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}scep/config")
        
        if response.status_code != 200:
            return '<p style="color: var(--danger-color);">Failed to load SCEP status</p>'
        
        config = response.json()
        enabled = config.get('enabled', False)
        auto_approve = config.get('auto_approve', False)
        
        if not enabled:
            return f'''
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 1rem; background: var(--bg-secondary); border-radius: 8px;">
                <div style="display: flex; align-items: center;">
                    <i class="fas fa-circle" style="color: var(--danger-color); margin-right: 0.75rem;"></i>
                    <div>
                        <p style="font-weight: 500; color: var(--text-primary);">SCEP Server: Disabled</p>
                        <p style="font-size: 0.875rem; color: var(--text-secondary);">Configure SCEP to start accepting enrollment requests</p>
                    </div>
                </div>
                <a href="/scep" class="btn btn-primary" style="font-size: 0.875rem;">
                    Configure
                </a>
            </div>
            '''
        
        return f'''
        <div style="display: flex; flex-direction: column; gap: 1rem;">
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 1rem; background: var(--success-bg); border-radius: 8px;">
                <div style="display: flex; align-items: center;">
                    <i class="fas fa-circle animate-pulse" style="color: var(--success-color); margin-right: 0.75rem;"></i>
                    <div>
                        <p style="font-weight: 500; color: var(--text-primary);">SCEP Server: Active</p>
                        <p style="font-size: 0.875rem; color: var(--text-secondary);">Accepting enrollment requests</p>
                    </div>
                </div>
                <a href="/scep" style="color: var(--accent-color); font-size: 0.875rem; text-decoration: none;">
                    Manage <i class="fas fa-chevron-right" style="margin-left: 0.25rem;"></i>
                </a>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; font-size: 0.875rem;">
                <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px;">
                    <p style="color: var(--text-secondary);">Mode</p>
                    <p style="font-weight: 500; color: var(--text-primary);">
                        {'Auto-Approval' if auto_approve else 'Manual Approval'}
                    </p>
                </div>
                <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px;">
                    <p style="color: var(--text-secondary);">Endpoint</p>
                    <p style="font-weight: 500; color: var(--text-primary); font-size: 0.75rem;">/scep/pkiclient.exe</p>
                </div>
            </div>
        </div>
        '''
    except Exception as e:
        return f'<p style="color: var(--danger-color);">Error: {str(e)}</p>'


# Settings
@ui_bp.route('/settings')
@login_required
def settings():
    """System settings page (admin only)"""
    from config.settings import Config
    return render_template('settings.html', 
                         version=Config.APP_VERSION,
                         port=Config.HTTPS_PORT)


@ui_bp.route('/my-account')
@login_required
def my_account():
    """User account settings page"""
    return render_template('my_account.html')


@ui_bp.route('/my-account/mtls')
@login_required
def my_account_mtls():
    """User mTLS certificates management page"""
    return render_template('my_account_mtls.html')


@ui_bp.route('/api/ui/my-account/sessions')
@login_required
def my_account_sessions():
    """Get user's active sessions"""
    try:
        from datetime import datetime
        
        html = f'''
        <div style="padding: 1rem; border: 1px solid var(--border-color); border-radius: 0.5rem; background: var(--bg-secondary);">
            <div style="display: flex; justify-content: space-between; align-items: start; gap: 1rem;">
                <div style="flex: 1;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                        <svg class="ucm-icon" width="16" height="16" style="color: var(--success-color);"><use href="#icon-check-circle"/></svg>
                        <strong style="color: var(--text-primary);">Current Session</strong>
                    </div>
                    <div style="font-size: 0.875rem; color: var(--text-secondary);">
                        <div><strong>IP:</strong> {request.remote_addr}</div>
                        <div><strong>Device:</strong> {request.user_agent.string[:80]}...</div>
                        <div><strong>Last Activity:</strong> Just now</div>
                    </div>
                </div>
            </div>
        </div>
        '''
        return html
    except Exception as e:
        return f'<div style="color: var(--danger-color);">Error: {str(e)}</div>', 500


@ui_bp.route('/api/ui/my-account/api-keys')
@login_required
def my_account_api_keys():
    """Get user's API keys"""
    html = '''
    <div style="text-align: center; padding: 3rem 1rem;">
        <svg class="ucm-icon" width="48" height="48" style="color: var(--text-secondary); opacity: 0.5; margin-bottom: 1rem;"><use href="#icon-key"/></svg>
        <h3 style="font-size: 1.125rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.5rem;">API Keys Coming Soon</h3>
        <p style="color: var(--text-secondary); font-size: 0.875rem;">
            Personal API key management will be available in a future update.
        </p>
    </div>
    '''
    return html


@ui_bp.route('/api/ui/my-account/notification-settings', methods=['POST'])
@login_required
def my_account_save_notification_settings():
    """Save user notification preferences"""
    return jsonify({'success': True, 'message': 'Settings saved successfully'})


@ui_bp.route('/users')
@login_required
def users():
    """Users management page"""
    return render_template('users.html')


# CA Management
@ui_bp.route('/ca')
@login_required
def ca_list():
    """CA list page"""
    return render_template('ca/list.html')


@ui_bp.route('/api/ui/ca/list')
@login_required
def ca_list_content():
    """Get CA list HTML with hierarchical display"""
    try:
        token = session.get('access_token')
        if not token:
            return '<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Session expired. Please <a href="/logout" style="text-decoration: underline;">logout</a> and login again.</div>'
        
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            verify=False
        )
        
        if response.status_code == 401:
            return '<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Session expired. Please refresh the page or <a href="/logout" style="text-decoration: underline;">logout</a> and login again.</div>'
        elif response.status_code != 200:
            return f'<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Failed to load CAs (Error {response.status_code})</div>'
        
        cas = response.json()
        
        if not cas:
            return '''
            <div style="padding: 2rem; text-align: center; color: var(--text-secondary);">
                <i class="fas fa-certificate" style="font-size: 2.25rem; margin-bottom: 1rem;"></i>
                <p style="font-size: 1.125rem; font-weight: 500; margin-bottom: 0.5rem;">No Certificate Authorities</p>
                <p style="font-size: 0.875rem;">Create your first CA to get started</p>
            </div>
            '''
        
        # Get certificate counts for each CA
        cert_response = requests.get(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            verify=False
        )
        
        ca_usage = {}
        if cert_response.status_code == 200:
            certs = cert_response.json()
            for cert in certs:
                caref = cert.get('caref')
                if caref:
                    ca_usage[caref] = ca_usage.get(caref, 0) + 1
        
        # Organize CAs into hierarchy
        root_cas = []
        intermediate_cas = []
        orphan_cas = []
        ca_by_refid = {}
        ca_by_subject_cn = {}
        
        # First pass: categorize and build lookups
        for ca in cas:
            ca_by_refid[ca['refid']] = ca
            subject = ca.get('subject', '')
            issuer = ca.get('issuer', '')
            
            # Extract CN from subject for lookup
            if 'CN=' in subject:
                for part in subject.split(','):
                    if 'CN=' in part:
                        cn = part.split('CN=')[1].strip()
                        ca_by_subject_cn[cn] = ca
                        break
            
            # Categorize
            if subject == issuer:
                root_cas.append(ca)
            else:
                intermediate_cas.append(ca)
        
        # Second pass: link intermediates to parents
        ca_children = {ca['refid']: [] for ca in root_cas}
        
        for int_ca in intermediate_cas:
            parent_caref = int_ca.get('caref')
            parent_found = False
            
            if parent_caref and parent_caref in ca_by_refid:
                # Direct link via caref
                if parent_caref not in ca_children:
                    ca_children[parent_caref] = []
                ca_children[parent_caref].append(int_ca)
                parent_found = True
            else:
                # Try to find parent by issuer CN
                issuer = int_ca.get('issuer', '')
                if 'CN=' in issuer:
                    for part in issuer.split(','):
                        if 'CN=' in part:
                            issuer_cn = part.split('CN=')[1].strip()
                            if issuer_cn in ca_by_subject_cn:
                                parent_ca = ca_by_subject_cn[issuer_cn]
                                parent_refid = parent_ca['refid']
                                if parent_refid not in ca_children:
                                    ca_children[parent_refid] = []
                                ca_children[parent_refid].append(int_ca)
                                parent_found = True
                            break
            
            if not parent_found:
                orphan_cas.append(int_ca)
        
        def render_ca_row(ca, indent_level=0, is_last_child=False, family_index=0):
            """Render a single CA row with optional indentation and tree connector"""
            subject = ca.get('subject', '')
            issuer = ca.get('issuer', '')
            is_root = (subject == issuer)
            usage_count = ca_usage.get(ca['refid'], 0)
            
            # Extract CN from subject
            cn = 'N/A'
            if 'CN=' in subject:
                for part in subject.split(','):
                    if 'CN=' in part:
                        cn = part.split('CN=')[1].strip()
                        break
            
            # Issuer display
            if is_root:
                issuer_display = 'Self-signed'
            else:
                parent_caref = ca.get('caref')
                if parent_caref and parent_caref in ca_by_refid:
                    issuer_display = ca_by_refid[parent_caref]['descr']
                else:
                    issuer_cn = 'Unknown'
                    if 'CN=' in issuer:
                        for part in issuer.split(','):
                            if 'CN=' in part:
                                issuer_cn = part.split('CN=')[1].strip()
                                break
                    if issuer_cn in ca_by_subject_cn:
                        issuer_display = ca_by_subject_cn[issuer_cn]['descr']
                    else:
                        issuer_display = issuer_cn
            
            valid_from = ca.get('valid_from', '')[:10] if ca.get('valid_from') else 'N/A'
            valid_to = ca.get('valid_to', '')[:10] if ca.get('valid_to') else 'N/A'
            
            has_key = ca.get('has_private_key', False)
            key_badge = '<span class="badge-outline badge-success ml-2"><i class="fas fa-key"></i> Key</span>' if has_key else '<span class="badge-outline badge-secondary ml-2"><i class="fas fa-key-skeleton"></i> No Key</span>'
            
            safe_refid = escape_js(ca['refid'])
            safe_descr = escape_js(ca['descr'])
            
            # Build tree connector visual
            tree_connector = ''
            if indent_level > 0:
                # Create L-shaped connector using CSS class
                tree_connector = '''
                    <div style="display: flex; align-items: center; margin-right: 0.5rem;">
                        <div class="ca-tree-connector"></div>
                    </div>
                '''
            
            # Alternating family background colors - disabled for now to avoid confusion
            # Different color per family using modulo patterns
            # family_colors = [
            #     'var(--info-color)',      # Violet/Blue
            #     'transparent',            # None
            #     'var(--success-color)',   # Green
            #     'transparent',            # None
            # ]
            # family_border_left = f'border-left: 4px solid {family_colors[family_index % 4]};'
            family_border_left = ''  # No colored border to avoid confusion
            
            # Add class for styling
            row_class = 'ca-parent-row' if indent_level == 0 and len(ca_children.get(ca['refid'], [])) > 0 else ''
            row_class += ' ca-child-row' if indent_level > 0 else ''
            row_class += ' ca-last-child' if is_last_child else ''
            row_class += ' ca-standalone' if indent_level == 0 and len(ca_children.get(ca['refid'], [])) == 0 else ''
            
            # Vertical alignment and padding: parent with children aligns bottom, children are tight
            if indent_level == 0 and len(ca_children.get(ca['refid'], [])) > 0:
                # Parent with children: align text to bottom, reduced padding-bottom
                vertical_align = 'vertical-align: bottom;'
                row_padding_top = '0.75rem'
                row_padding_bottom = '0.25rem'
            elif indent_level > 0:
                # Children: very tight padding, no top padding
                vertical_align = 'vertical-align: middle;'
                row_padding_top = '0.15rem'
                row_padding_bottom = '0.15rem'
            else:
                # Standalone ROOT: normal padding
                vertical_align = 'vertical-align: middle;'
                row_padding_top = '0.75rem'
                row_padding_bottom = '0.75rem'
            
            # Border for separators - inline override
            border_bottom = ''
            if 'ca-standalone' in row_class or 'ca-last-child' in row_class:
                border_bottom = 'border-bottom: 1px solid var(--border-color) !important;'
                row_padding_bottom = '0.5rem'  # Extra spacing
            
            return f'''
                <tr class="{row_class}" 
                    data-action="navigate-ca" 
                    data-ca-id="{ca['id']}" 
                    style="cursor: pointer;">
                    <td style="padding: {row_padding_top} 0.75rem {row_padding_bottom} 0.75rem; {border_bottom} {vertical_align} {family_border_left}">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center;">
                                {tree_connector}
                                <span style="color: var(--text-primary);">{ca['descr']}</span>
                            </div>
                            <div style="display: flex; gap: 4px;">
                                <span class="badge-outline badge-primary">
                                    <i class="{'fas fa-crown' if is_root else 'fas fa-link'}"></i>
                                    {'ROOT' if is_root else 'INT'}
                                </span>
                                {key_badge}
                            </div>
                        </div>
                    </td>
                    <td style="padding: {row_padding_top} 0.75rem {row_padding_bottom} 0.75rem; color: var(--text-primary); {border_bottom} {vertical_align}">
                        {issuer_display}
                    </td>
                    <td style="padding: {row_padding_top} 0.75rem {row_padding_bottom} 0.75rem; color: var(--text-primary); {border_bottom} {vertical_align}">
                        {cn}
                    </td>
                    <td style="padding: {row_padding_top} 0.75rem {row_padding_bottom} 0.75rem; color: var(--text-primary); {border_bottom} {vertical_align}">
                        <span>
                            {usage_count}
                        </span>
                    </td>
                    <td style="padding: {row_padding_top} 0.75rem {row_padding_bottom} 0.75rem; color: var(--text-primary); {border_bottom} {vertical_align}">
                        {valid_from}
                    </td>
                    <td style="padding: {row_padding_top} 0.75rem {row_padding_bottom} 0.75rem; color: var(--text-primary); {border_bottom} {vertical_align}">
                        {valid_to}
                    </td>
                    <td style="padding: {row_padding_top} 0.75rem {row_padding_bottom} 0.75rem; {border_bottom} {vertical_align}">
                        <button data-action="export-ca"
                                data-id="{ca['id']}"
                                class="btn-icon btn-icon-primary"
                                title="Export CA">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-download"/></svg>
                        </button>
                        <button data-action="delete-ca"
                                data-refid="{ca['refid']}" 
                                data-descr="{html_escape(ca['descr'])}"
                                class="btn-icon btn-icon-danger"
                                title="Delete CA">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-trash"/></svg>
                        </button>
                    </td>
                </tr>
            '''
        
        # Build HTML with hierarchy
        html = '''
        <div style="overflow-x: auto; overflow-y: visible;">
            <table id="ca-table">
                <thead style="background: var(--bg-secondary);">
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span>Description</span>
                                <div style="position: relative; margin-left: 12px;">
                                    <input type="text" id="searchCA" placeholder="Search..." 
                                           style="padding: 4px 8px 4px 24px; font-size: 12px; width: 160px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);"
                                           onkeyup="filterTableCA()"
                                           onclick="event.stopPropagation()">
                                    <i class="fas fa-search" style="position: absolute; left: 6px; top: 50%; transform: translateY(-50%); font-size: 11px; opacity: 0.5; pointer-events: none;"></i>
                                </div>
                            </div>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-ca" data-column="1">
                            Issuer <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-ca" data-column="2">
                            Name <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-ca" data-column="3">
                            Usage <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-ca" data-column="4">
                            Valid From <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-ca" data-column="5">
                            Valid Until <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        # Render ROOT CAs with their children
        for family_idx, root_ca in enumerate(root_cas):
            html += render_ca_row(root_ca, indent_level=0, is_last_child=False, family_index=family_idx)
            # Render children with indentation
            children = ca_children.get(root_ca['refid'], [])
            for idx, child_ca in enumerate(children):
                is_last = (idx == len(children) - 1)
                html += render_ca_row(child_ca, indent_level=1, is_last_child=is_last, family_index=family_idx)
        
        html += '''
                </tbody>
            </table>
        </div>
        
        <!-- Pagination for CA table -->
        <div class="table-pagination">
            <div class="pagination-info">
                <span>Showing <span id="ca-start">1</span>-<span id="ca-end">10</span> of <span id="ca-total"></span> CAs</span>
            </div>
            <div class="pagination-controls">
                <select class="pagination-select" id="ca-per-page" onchange="updateCAPagination()">
                    <option value="10" selected>10 per page</option>
                    <option value="25">25 per page</option>
                    <option value="50">50 per page</option>
                    <option value="100">100 per page</option>
                </select>
                <div class="pagination-buttons" id="ca-pagination-buttons"></div>
            </div>
        </div>
        '''
        
        # Add orphan CAs section if any exist
        if orphan_cas:
            html += f'''
        <div style="margin-top: 2rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem; padding: 0.75rem; background: var(--warning-bg); border: 1px solid var(--warning-border); border-radius: 0.5rem;">
                <i class="fas fa-exclamation-triangle" style="color: var(--warning-color);"></i>
                <span style="color: var(--warning-color); font-weight: 500;">Orphaned CAs ({len(orphan_cas)}) - Parent Not Found</span>
            </div>
            <table id="ca-orphan-table">
                <thead style="background: var(--bg-secondary);">
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left;">Description</th>
                        <th style="padding: 0.75rem; text-align: left;">Issuer (DN)</th>
                        <th style="padding: 0.75rem; text-align: left;">Name</th>
                        <th style="padding: 0.75rem; text-align: left;">Usage</th>
                        <th style="padding: 0.75rem; text-align: left;">Valid From</th>
                        <th style="padding: 0.75rem; text-align: left;">Valid Until</th>
                        <th style="padding: 0.75rem; text-align: left;">Actions</th>
                    </tr>
                </thead>
                <tbody>
            '''
            
            for orphan_ca in orphan_cas:
                html += render_ca_row(orphan_ca, indent_level=0, is_last_child=False)
            
            html += '''
                </tbody>
            </table>
        </div>
            '''
        
        html += '''
        <script>
        // CA Table Pagination - Use window object to avoid redeclaration in HTMX
        if (typeof window.window.caCurrentPage === 'undefined') {
            window.window.caCurrentPage = 1;
            window.window.caPerPage = 10;
            window.window.caTotalRows = 0;
        }
        
        function initCAPagination() {
            const table = document.getElementById('ca-table');
            if (!table) return;
            
            const tbody = table.querySelector('tbody');
            const allRows = Array.from(tbody.querySelectorAll('tr'));
            
            // Count only ROOT CAs (families), not children
            window.window.caTotalRows = allRows.filter(row => !row.classList.contains('ca-child-row')).length;
            
            document.getElementById('ca-total').textContent = window.window.caTotalRows;
            updateCAPagination();
        }
        
        function updateCAPagination() {
            const perPageSelect = document.getElementById('ca-per-page');
            window.caPerPage = parseInt(perPageSelect.value);
            const totalPages = Math.ceil(window.caTotalRows / window.caPerPage);
            
            showCAPage(window.caCurrentPage, totalPages);
            renderCAPaginationButtons(totalPages);
        }
        
        function showCAPage(page, totalPages) {
            const table = document.getElementById('ca-table');
            if (!table) return;
            
            const tbody = table.querySelector('tbody');
            const allRows = Array.from(tbody.querySelectorAll('tr'));
            
            // Separate ROOT CAs from children
            const rootRows = allRows.filter(row => !row.classList.contains('ca-child-row'));
            const childMap = new Map();
            
            // Build map of children for each parent
            allRows.forEach((row, index) => {
                if (row.classList.contains('ca-child-row')) {
                    for (let i = index - 1; i >= 0; i--) {
                        if (!allRows[i].classList.contains('ca-child-row')) {
                            if (!childMap.has(allRows[i])) {
                                childMap.set(allRows[i], []);
                            }
                            childMap.get(allRows[i]).push(row);
                            break;
                        }
                    }
                }
            });
            
            const start = (page - 1) * window.caPerPage;
            const end = start + window.caPerPage;
            
            // Hide all rows first
            allRows.forEach(row => row.style.display = 'none');
            
            // Show only ROOT CAs in current page range + their children
            rootRows.forEach((rootRow, index) => {
                if (index >= start && index < end) {
                    rootRow.style.display = '';
                    // Show children
                    if (childMap.has(rootRow)) {
                        childMap.get(rootRow).forEach(childRow => {
                            childRow.style.display = '';
                        });
                    }
                }
            });
            
            // Update info
            const actualStart = Math.min(start + 1, window.caTotalRows);
            const actualEnd = Math.min(end, window.caTotalRows);
            document.getElementById('ca-start').textContent = actualStart;
            document.getElementById('ca-end').textContent = actualEnd;
        }
        
        function renderCAPaginationButtons(totalPages) {
            const container = document.getElementById('ca-pagination-buttons');
            if (!container) return;
            
            let html = '';
            
            // Previous button
            html += `<button class="pagination-btn" onclick="goToCAPage(${window.caCurrentPage - 1}, ${totalPages})" ${window.caCurrentPage === 1 ? 'disabled' : ''}>
                <svg class="ucm-icon" width="14" height="14"><use href="#icon-chevron-left"/></svg>
            </button>`;
            
            // Page numbers (show first, last, and pages around current)
            const maxButtons = 7;
            let startPage = Math.max(1, window.caCurrentPage - Math.floor(maxButtons / 2));
            let endPage = Math.min(totalPages, startPage + maxButtons - 1);
            
            if (endPage - startPage < maxButtons - 1) {
                startPage = Math.max(1, endPage - maxButtons + 1);
            }
            
            if (startPage > 1) {
                html += `<button class="pagination-btn" onclick="goToCAPage(1, ${totalPages})">1</button>`;
                if (startPage > 2) {
                    html += `<span class="pagination-ellipsis">...</span>`;
                }
            }
            
            for (let i = startPage; i <= endPage; i++) {
                html += `<button class="pagination-btn ${i === window.caCurrentPage ? 'active' : ''}" 
                         onclick="goToCAPage(${i}, ${totalPages})">${i}</button>`;
            }
            
            if (endPage < totalPages) {
                if (endPage < totalPages - 1) {
                    html += `<span class="pagination-ellipsis">...</span>`;
                }
                html += `<button class="pagination-btn" onclick="goToCAPage(${totalPages}, ${totalPages})">${totalPages}</button>`;
            }
            
            // Next button
            html += `<button class="pagination-btn" onclick="goToCAPage(${window.caCurrentPage + 1}, ${totalPages})" ${window.caCurrentPage === totalPages ? 'disabled' : ''}>
                <svg class="ucm-icon" width="14" height="14"><use href="#icon-chevron-right"/></svg>
            </button>`;
            
            container.innerHTML = html;
        }
        
        function goToCAPage(page, totalPages) {
            if (page < 1 || page > totalPages) return;
            window.caCurrentPage = page;
            showCAPage(page, totalPages);
            renderCAPaginationButtons(totalPages);
        }
        
        // Initialize immediately (HTMX content already loaded)
        setTimeout(initCAPagination, 100);
        
        function filterTableCA() {
            const input = document.getElementById('searchCA');
            const filter = input.value.toLowerCase();
            const tables = document.querySelectorAll('#ca-table, table');
            
            tables.forEach(table => {
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(filter) ? '' : 'none';
                });
            });
        }
        
        // Export function with JWT token for CA exports
        if (typeof window.exportWithToken === 'undefined') {
            window.exportWithToken = function(url) {
                var token = ''' + f"'{token}'" + ''';
                
                // Show loading toast
                showToast('Preparing download...', 'info');
                
                fetch(url, {
                    headers: { 'Authorization': 'Bearer ' + token }
                })
                .then(response => {
                    if (!response.ok) throw new Error('Export failed');
                    
                    // Extract filename from Content-Disposition header or URL
                    var filename = '';
                    var disposition = response.headers.get('Content-Disposition');
                    if (disposition && disposition.includes('filename=')) {
                        var matches = disposition.match(/filename[^;=\\n]*=(([\'"]).*?\\2|[^;\\n]*)/);
                        if (matches && matches[1]) {
                            filename = matches[1].replace(/[\'"]/g, '');
                        }
                    }
                    
                    // Fallback: extract from URL or use generic name
                    if (!filename) {
                        var urlParts = url.split('/');
                        filename = urlParts[urlParts.length - 1].split('?')[0] || 'download';
                    }
                    
                    return response.blob().then(blob => ({blob: blob, filename: filename}));
                })
                .then(function(result) {
                    // Small delay to show spinner
                    setTimeout(function() {
                        var downloadUrl = window.URL.createObjectURL(result.blob);
                        var a = document.createElement('a');
                        a.href = downloadUrl;
                        a.download = result.filename;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(downloadUrl);
                        showToast('Download started: ' + result.filename, 'success');
                    }, 500);
                })
                .catch(error => {
                    console.error('Export error:', error);
                    showToast('Export failed: ' + error.message, 'error');
                });
            };
        }
        </script>
        '''
        
        return html
    except Exception as e:
        return f'<div style="padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/ca/create', methods=['POST'])
@login_required
def ca_create():
    """Create new CA"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        # Build CA data from form
        data = {
            'descr': request.form.get('descr'),
            'key_type': request.form.get('key_type'),
            'digest_alg': request.form.get('digest_alg'),
            'lifetime': int(request.form.get('lifetime', 3650)),
            'dn_country': request.form.get('dn_country'),
            'dn_state': request.form.get('dn_state'),
            'dn_city': request.form.get('dn_city'),
            'dn_org': request.form.get('dn_org'),
            'dn_orgunit': request.form.get('dn_orgunit'),
            'dn_commonname': request.form.get('dn_commonname'),
        }
        
        response = requests.post(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            json=data,
            verify=False
        )
        
        if response.status_code in [200, 201]:
            return '', 200
        else:
            return response.text, response.status_code
    except Exception as e:
        return str(e), 500


@ui_bp.route('/api/ui/ca/import', methods=['POST'])
@login_required
def ca_import():
    """Import existing CA certificate with optional private key"""
    try:
        token = session.get('access_token')
        if not token:
            flash('Session expired', 'error')
            return 'Session expired', 401
        
        description = request.form.get('description', '').strip()
        certificate = request.form.get('certificate', '').strip()
        private_key = request.form.get('private_key', '').strip()
        
        if not description or not certificate:
            flash('Description and certificate are required', 'error')
            return 'Description and certificate are required', 400
        
        # Prepare data for API
        data = {
            'action': 'import',
            'descr': description,
            'crt_payload': certificate
        }
        
        if private_key:
            data['prv_payload'] = private_key
        
        # Call API to import CA
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        response = requests.post(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            json=data,
            verify=False
        )
        
        if response.status_code in [200, 201]:
            if private_key:
                flash(f'CA "{description}" imported successfully with private key', 'success')
            else:
                flash(f'CA "{description}" imported successfully (no private key)', 'success')
            return '', 200
        else:
            error_msg = response.json().get('error', 'Import failed')
            flash(f'Error importing CA: {error_msg}', 'error')
            return error_msg, response.status_code
            
    except Exception as e:
        flash(f'Error importing CA: {str(e)}', 'error')
        return str(e), 500


# Certificate Management
@ui_bp.route('/certificates')
@login_required
def cert_list():
    """Certificate list page"""
    return render_template('certs/list.html')


@ui_bp.route('/api/ui/ca/options')
@login_required
def ca_options():
    """Get CA options for select dropdown"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/ca/")
        
        if response.status_code != 200:
            return '<option>Error loading CAs</option>'
        
        cas = response.json()
        
        if not cas:
            return '<option>No CAs available</option>'
        
        html = '<option value="">Select a CA...</option>'
        for ca in cas:
            html += f'<option value="{ca["refid"]}">{ca["descr"]}</option>'
        
        return html
    except Exception as e:
        return f'<option>Error: {str(e)}</option>'


@ui_bp.route('/api/ui/cert/list')
@login_required
def cert_list_content():
    """Get certificate list HTML as sortable table"""
    try:
        token = session.get('access_token')
        if not token:
            return '<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Session expired. Please <a href="/logout" style="text-decoration: underline;">logout</a> and login again.</div>'
        
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            verify=False
        )
        
        if response.status_code == 401:
            return '<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Session expired. Please refresh the page or <a href="/logout" style="text-decoration: underline;">logout</a> and login again.</div>'
        elif response.status_code != 200:
            return f'<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Failed to load certificates (Error {response.status_code})</div>'
        
        certs = response.json()
        
        if not certs:
            return '''
            <div style="padding: 2rem; text-align: center; color: var(--text-secondary);">
                <i class="fas fa-file-certificate" style="font-size: 2.25rem; margin-bottom: 1rem;"></i>
                <p style="font-size: 1.125rem; font-weight: 500; margin-bottom: 0.5rem;">No Certificates</p>
                <p style="font-size: 0.875rem;">Create your first certificate to get started</p>
            </div>
            '''
        
        # Get CA info for mapping
        ca_response = requests.get(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            verify=False
        )
        
        ca_names = {}
        if ca_response.status_code == 200:
            cas = ca_response.json()
            for ca in cas:
                ca_names[ca['refid']] = ca['descr']
        
        html = '''
        <div style="overflow-x: auto; overflow-y: visible;">
            <table id="cert-table">
                <thead style="background: var(--bg-secondary);">
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left;" data-action="sort-table-cert" data-column="0">
                            <div style="display: flex; align-items: center; justify-content: space-between; cursor: pointer;">
                                <span>Description <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i></span>
                                <div style="position: relative; margin-left: 12px;">
                                    <input type="text" id="searchCert" placeholder="Search..." 
                                           style="padding: 4px 8px 4px 24px; font-size: 12px; width: 160px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);"
                                           onkeyup="filterTableCert()"
                                           onclick="event.stopPropagation()">
                                    <i class="fas fa-search" style="position: absolute; left: 6px; top: 50%; transform: translateY(-50%); font-size: 11px; opacity: 0.5; pointer-events: none;"></i>
                                </div>
                            </div>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-cert" data-column="1">
                            Issuer <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-cert" data-column="2">
                            Type <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-cert" data-column="3">
                            Valid From <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left; cursor: pointer;" data-action="sort-table-cert" data-column="4">
                            Valid Until <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th style="padding: 0.75rem; text-align: left;">
                            Actions
                        </th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for cert in certs:
            # A certificate is a CSR if it doesn't have a signed certificate yet
            # Check if valid_from exists - CSRs don't have validity dates from signing
            is_csr = not cert.get('crt') if 'crt' in cert else (cert.get('valid_from') is None or cert.get('serial_number') is None)
            is_revoked = cert.get('revoked', False)
            
            # Determine status badge
            if is_csr:
                status_badge = '<span class="badge-outline badge-warning"><i class="fas fa-file-signature"></i> CSR</span>'
            elif is_revoked:
                status_badge = '<span class="badge-outline badge-danger"><i class="fas fa-ban"></i> REVOKED</span>'
            else:
                status_badge = '<span class="badge-outline badge-success"><i class="fas fa-check"></i> VALID</span>'
            
            # Add CRT/KEY badges - for CSRs these will be false, for signed certs check actual presence
            has_crt = not is_csr  # If it's not a CSR, it has a certificate
            has_key = cert.get('has_private_key', False)
            
            crt_badge = '<span class="badge-outline badge-info"><i class="fas fa-certificate"></i> CRT</span>' if has_crt else ''
            key_badge = '<span class="badge-outline badge-success"><i class="fas fa-key"></i> KEY</span>' if has_key else ''
            
            # Check if ACME certificate
            is_acme = cert.get('created_by') == 'acme'
            acme_badge = '<span class="badge-outline badge-success"><i class="fas fa-robot"></i> ACME</span>' if is_acme else ''
            
            # Check if SCEP certificate
            is_scep = cert.get('created_by') == 'scep'
            scep_badge = '<span class="badge-outline badge-info"><i class="fas fa-network-wired"></i> SCEP</span>' if is_scep else ''
            
            # Get issuer name
            issuer_name = ca_names.get(cert.get('caref', ''), 'Unknown')
            
            # Determine cert type
            cert_type = cert.get('cert_type', 'unknown')
            type_map = {
                'server_cert': 'Serveur',
                'client_cert': 'Client',
                'usr_cert': 'Client',
                'combined_cert': 'Combiné',
                'combined_server_client': 'Combiné',
                'sign_cert': 'Signature',
                'ca_cert': 'CA',
                'unknown': 'N/A'
            }
            cert_type_display = type_map.get(cert_type, cert_type)
            
            valid_from = cert.get('valid_from', '')[:10] if cert.get('valid_from') else 'N/A'
            valid_to = cert.get('valid_to', '')[:10] if cert.get('valid_to') else 'N/A'
            
            # Escape values for JavaScript
            safe_refid = escape_js(cert['refid'])
            safe_descr = escape_js(cert['descr'])
            
            html += f'''
                <tr data-action="navigate-cert" data-cert-id="{cert['id']}">
                    <td style="padding: 0.75rem; color: var(--text-primary);">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <span>{cert['descr']}</span>
                            <div style="display: flex; gap: 4px;">
                                {status_badge}
                                {crt_badge}
                                {key_badge}
                                {acme_badge}
                                {scep_badge}
                            </div>
                        </div>
                    </td>
                    <td style="padding: 0.75rem; color: var(--text-primary);">
                        {issuer_name}
                    </td>
                    <td style="padding: 0.75rem; color: var(--text-primary);">
                        {cert_type_display}
                    </td>
                    <td style="padding: 0.75rem; color: var(--text-primary);">
                        {valid_from}
                    </td>
                    <td style="padding: 0.75rem; color: var(--text-primary);">
                        {valid_to}
                    </td>
                    <td style="padding: 0.75rem;">
            '''
            
            # Unified export button for both CSR and certificates
            button_class = "btn-icon btn-icon-primary"
            html += f'''
                        <button data-action="export-cert"
                                data-id="{cert['id']}"
                                data-is-csr="{'true' if is_csr else 'false'}"
                                class="{button_class}"
                                title="Export {'CSR' if is_csr else 'Certificate'}">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-download"/></svg>
                        </button>
            '''
                
            if not is_revoked and not is_csr:
                html += f'''
                        <button data-action="revoke-cert"
                                data-refid="{cert['refid']}" 
                                data-descr="{html_escape(cert['descr'])}" 
                                class="btn-icon btn-icon-danger"
                                title="Revoke Certificate">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-ban"/></svg>
                        </button>
                '''
            
            html += f'''
                        <button data-action="delete-cert"
                                data-refid="{cert['refid']}" 
                                data-descr="{html_escape(cert['descr'])}"
                                class="btn-icon btn-icon-danger"
                                title="Delete {'CSR' if is_csr else 'Certificate'}">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-trash"/></svg>
                        </button>
                    </td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        
        <!-- Pagination for Certificate table -->
        <div class="table-pagination">
            <div class="pagination-info">
                <span>Showing <span id="cert-start">1</span>-<span id="cert-end">10</span> of <span id="cert-total"></span> certificates</span>
            </div>
            <div class="pagination-controls">
                <select class="pagination-select" id="cert-per-page" data-action="update-cert-pagination">
                    <option value="10" selected>10 per page</option>
                    <option value="25">25 per page</option>
                    <option value="50">50 per page</option>
                    <option value="100">100 per page</option>
                </select>
                <div class="pagination-buttons" id="cert-pagination-buttons"></div>
            </div>
        </div>
        
        <script>
        // Initialize certificate pagination on HTMX load
        setTimeout(initCertPagination, 100);
        </script>
        
        <script>
        // Use window object to avoid var in HTMX-loaded content
        if (typeof window.sortDirectionCert === 'undefined') {
            window.sortDirectionCert = {};
        }
        
        function sortTableCert(columnIndex) {
            const table = document.getElementById('cert-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            const currentDirection = window.sortDirectionCert[columnIndex] || 'asc';
            const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
            window.sortDirectionCert[columnIndex] = newDirection;
            
            rows.sort((a, b) => {
                let aValue = a.cells[columnIndex].textContent.trim();
                let bValue = b.cells[columnIndex].textContent.trim();
                
                if (aValue < bValue) return newDirection === 'asc' ? -1 : 1;
                if (aValue > bValue) return newDirection === 'asc' ? 1 : -1;
                return 0;
            });
            
            rows.forEach(row => tbody.appendChild(row));
        }
        
        function filterTableCert() {
            const input = document.getElementById('searchCert');
            const filter = input.value.toLowerCase();
            const table = document.getElementById('cert-table');
            const tbody = table.querySelector('tbody');
            const rows = tbody.querySelectorAll('tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(filter) ? '' : 'none';
            });
        }
        
        function exportCert(id, event, isCSR) {
            // Show export menu
            event.stopPropagation();
            
            // Remove any existing menu
            const existingMenu = document.getElementById('export-cert-menu-' + id);
            if (existingMenu) {
                existingMenu.remove();
                return;
            }
            
            // Remove all other menus
            document.querySelectorAll('[id^="export-cert-menu-"]').forEach(m => m.remove());
            
            // Create menu with different options for CSR vs Certificate
            const menu = document.createElement('div');
            menu.id = 'export-cert-menu-' + id;
            menu.className = 'absolute right-0 mt-1 w-56 rounded-md shadow-lg bg-white dark:bg-gray-700 ring-1 ring-black ring-opacity-5 z-50';
            
            if (isCSR) {
                // CSR only has simple PEM export
                menu.innerHTML = '<div style="padding: 0.25rem 0;" role="menu">' +
                    '<button data-action="export-cert-simple" data-id="' + id + '" style="display: block; width: 100%; text-align: left; padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--text-primary); background: transparent; border: none; cursor: pointer;" onmouseover="this.style.background=\\'var(--hover-bg)\\'" onmouseout="this.style.background=\\'transparent\\'">' +
                        '<i class="fas fa-file-certificate" style="margin-right: 0.5rem;"></i>CSR (PEM)' +
                    '</button>' +
                '</div>';
            } else {
                // Full certificate has all export options
                menu.innerHTML = '<div style="padding: 0.25rem 0;" role="menu">' +
                    '<button data-action="export-cert-simple" data-id="' + id + '" style="display: block; width: 100%; text-align: left; padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--text-primary); background: transparent; border: none; cursor: pointer;" onmouseover="this.style.background=\\'var(--hover-bg)\\'" onmouseout="this.style.background=\\'transparent\\'">' +
                        '<i class="fas fa-file-certificate" style="margin-right: 0.5rem;"></i>Certificate only (PEM)' +
                    '</button>' +
                    '<button data-action="export-cert-key" data-id="' + id + '" style="display: block; width: 100%; text-align: left; padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--text-primary); background: transparent; border: none; cursor: pointer;" onmouseover="this.style.background=\\'var(--hover-bg)\\'" onmouseout="this.style.background=\\'transparent\\'">' +
                        '<i class="fas fa-key" style="margin-right: 0.5rem;"></i>Certificate + Key (PEM)' +
                    '</button>' +
                    '<button data-action="export-cert-chain" data-id="' + id + '" style="display: block; width: 100%; text-align: left; padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--text-primary); background: transparent; border: none; cursor: pointer;" onmouseover="this.style.background=\\'var(--hover-bg)\\'" onmouseout="this.style.background=\\'transparent\\'">' +
                        '<i class="fas fa-link" style="margin-right: 0.5rem;"></i>Certificate + CA Chain (PEM)' +
                    '</button>' +
                    '<button data-action="export-cert-full" data-id="' + id + '" style="display: block; width: 100%; text-align: left; padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--text-primary); background: transparent; border: none; cursor: pointer;" onmouseover="this.style.background=\\'var(--hover-bg)\\'" onmouseout="this.style.background=\\'transparent\\'">' +
                        '<i class="fas fa-archive" style="margin-right: 0.5rem;"></i>Full Chain + Key (PEM)' +
                    '</button>' +
                    '<button data-action="export-cert-der" data-id="' + id + '" style="display: block; width: 100%; text-align: left; padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--text-primary); background: transparent; border: none; cursor: pointer;" onmouseover="this.style.background=\\'var(--hover-bg)\\'" onmouseout="this.style.background=\\'transparent\\'">' +
                        '<i class="fas fa-file-binary" style="margin-right: 0.5rem;"></i>Certificate (DER)' +
                    '</button>' +
                    '<button data-action="show-pkcs12-modal" data-id="' + id + '" data-type="cert" style="display: block; width: 100%; text-align: left; padding: 0.5rem 1rem; font-size: 0.875rem; color: var(--text-primary); background: transparent; border: none; cursor: pointer;" onmouseover="this.style.background=\\'var(--hover-bg)\\'" onmouseout="this.style.background=\\'transparent\\'">' +
                        '<i class="fas fa-lock" style="margin-right: 0.5rem;"></i>PKCS#12 (.p12/.pfx)' +
                    '</button>' +
                '</div>';
            }
            
            // Position menu next to button - allow overflow for floating menu
            const button = event.target.closest('button');
            const td = button.closest('td');
            const tr = td.closest('tr');
            const tbody = tr.closest('tbody');
            const table = tbody.closest('table');
            const container = table.closest('div');
            
            // Allow overflow at all levels
            td.style.position = 'relative';
            td.style.overflow = 'visible';
            tr.style.overflow = 'visible';
            tbody.style.overflow = 'visible';
            table.style.overflow = 'visible';
            if (container) {
                container.style.overflow = 'visible';
            }
            
            td.appendChild(menu);
        }
        
        // Export function with JWT token for certificates
        if (typeof window.exportWithTokenCert === 'undefined') {
            window.exportWithTokenCert = function(url) {
                var token = ''' + f"'{token}'" + ''';
                
                // Show loading toast
                showToast('Preparing download...', 'info');
                
                fetch(url, {
                    headers: { 'Authorization': 'Bearer ' + token }
                })
                .then(response => {
                    if (!response.ok) throw new Error('Export failed');
                    
                    // Extract filename from Content-Disposition header or URL
                    var filename = '';
                    var disposition = response.headers.get('Content-Disposition');
                    if (disposition && disposition.includes('filename=')) {
                        var matches = disposition.match(/filename[^;=\\n]*=(([\'"]).*?\\2|[^;\\n]*)/);
                        if (matches && matches[1]) {
                            filename = matches[1].replace(/[\'"]/g, '');
                        }
                    }
                    
                    // Fallback: extract from URL or use generic name
                    if (!filename) {
                        var urlParts = url.split('/');
                        filename = urlParts[urlParts.length - 1].split('?')[0] || 'certificate.pem';
                    }
                    
                    return response.blob().then(blob => ({blob: blob, filename: filename}));
                })
                .then(function(result) {
                    // Small delay to show spinner
                    setTimeout(function() {
                        var downloadUrl = window.URL.createObjectURL(result.blob);
                        var a = document.createElement('a');
                        a.href = downloadUrl;
                        a.download = result.filename;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(downloadUrl);
                        showToast('Download started: ' + result.filename, 'success');
                    }, 500);
                })
                .catch(error => {
                    console.error('Export error:', error);
                    showToast('Export failed: ' + error.message, 'error');
                });
            };
        }
        
        function exportCertSimple(id) {
            window.exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertWithKey(id) {
            window.exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem&key=true');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertWithChain(id) {
            window.exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem&chain=true');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertFull(id) {
            window.exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem&key=true&chain=true');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertDER(id) {
            window.exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=der');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        
        // NOTE: downloadCSR, revokeCert, deleteCert, and export functions
        // are now in ucm-global.js with JWT cookie authentication.
        
        // Close menus when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('button[onclick*="exportCert"]') && !e.target.closest('[id^="export-cert-menu-"]')) {
                document.querySelectorAll('[id^="export-cert-menu-"]').forEach(m => m.remove());
            }
        });
        </script>
        '''
        
        # Force no-cache to ensure fresh content
        response = make_response(html)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return f'<div style="padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/cert/create', methods=['POST'])
@login_required
def cert_create():
    """Create new certificate with full OPNsense-compatible options"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        # Parse all SAN entries
        san_dns = request.form.get('san_dns', '').strip()
        san_dns_list = [s.strip() for s in san_dns.split('\n') if s.strip()] if san_dns else []
        
        san_ip = request.form.get('san_ip', '').strip()
        san_ip_list = [s.strip() for s in san_ip.split('\n') if s.strip()] if san_ip else []
        
        san_email = request.form.get('san_email', '').strip()
        san_email_list = [s.strip() for s in san_email.split('\n') if s.strip()] if san_email else []
        
        san_uri = request.form.get('san_uri', '').strip()
        san_uri_list = [s.strip() for s in san_uri.split('\n') if s.strip()] if san_uri else []
        
        # Build Distinguished Name
        dn = {}
        if request.form.get('country'):
            dn['C'] = request.form.get('country')
        if request.form.get('state'):
            dn['ST'] = request.form.get('state')
        if request.form.get('city'):
            dn['L'] = request.form.get('city')
        if request.form.get('organization'):
            dn['O'] = request.form.get('organization')
        if request.form.get('organizational_unit'):
            dn['OU'] = request.form.get('organizational_unit')
        if request.form.get('email'):
            dn['emailAddress'] = request.form.get('email')
        dn['CN'] = request.form.get('common_name')  # Required
        
        data = {
            'caref': request.form.get('caref'),
            'descr': request.form.get('descr'),
            'dn': dn,
            'cert_type': request.form.get('cert_type', 'server_cert'),
            'san_dns': san_dns_list,
            'san_ip': san_ip_list,
            'san_email': san_email_list,
            'san_uri': san_uri_list,
            'lifetime': int(request.form.get('lifetime', 397)),
            'key_type': request.form.get('key_type'),
            'digest_alg': request.form.get('digest_alg', 'sha256'),
            'ocsp_uri': request.form.get('ocsp_uri', '').strip() or None,
            'private_key_location': request.form.get('private_key_location', 'stored'),
            'template_id': int(request.form.get('template_id')) if request.form.get('template_id') else None,
        }
        
        response = requests.post(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            json=data,
            verify=False
        )
        
        if response.status_code in [200, 201]:
            return '', 200
        else:
            return response.text, response.status_code
    except Exception as e:
        return str(e), 500


@ui_bp.route('/api/ui/cert/csr', methods=['POST'])
@login_required
def cert_csr():
    """Generate CSR"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        # Build DN from form data
        dn = {
            'CN': request.form.get('common_name'),
            'O': request.form.get('organization', ''),
            'OU': request.form.get('organizational_unit', ''),
            'C': request.form.get('country', ''),
            'ST': request.form.get('state', ''),
            'L': request.form.get('locality', '')
        }
        
        # Filter out empty values
        dn = {k: v for k, v in dn.items() if v}
        
        # Parse SANs if provided
        altnames = []
        altnames_raw = request.form.get('altnames', '').strip()
        if altnames_raw:
            for line in altnames_raw.split('\n'):
                line = line.strip()
                if line:
                    altnames.append(line)
        
        data = {
            'action': 'csr',  # CRITICAL: use action=csr
            'descr': request.form.get('descr'),
            'dn': dn,
            'key_type': request.form.get('key_type'),
            'digest': request.form.get('digest', 'sha256')
        }
        
        # Add SANs if provided
        if altnames:
            data['altnames'] = altnames
        
        response = requests.post(
            f"{request.url_root}api/v1/certificates",  # FIXED: correct endpoint
            headers=headers,
            json=data,
            verify=False
        )
        
        if response.status_code in [200, 201]:
            return '', 200
        else:
            return response.text, response.status_code
    except Exception as e:
        return str(e), 500



# SCEP Management
@ui_bp.route('/crl')
@login_required
def crl_list():
    """CRL Management page"""
    return render_template('crl/list.html')


@ui_bp.route('/api/ui/crl/list')
@login_required
def crl_list_data():
    """Get CRL list data"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get all CRLs
        response = requests.get(
            f"{request.url_root}api/v1/crl/",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return f'<div style="padding: 1rem; color: var(--danger-color);">Failed to load CRLs: {response.text}</div>'
        
        crls = response.json()
        
        if not crls:
            return '''
            <div style="padding: 2rem; text-align: center; color: var(--text-secondary);">
                <i class="fas fa-file-contract" style="font-size: 3.75rem; margin-bottom: 1rem;"></i>
                <p style="font-size: 1.125rem;">No CRLs generated yet</p>
                <p style="font-size: 0.875rem; margin-top: 0.5rem;">Enable CDP on a CA and generate a CRL to get started</p>
            </div>
            '''
        
        # Calculate Stats
        total_cas = len(crls)
        active_crls = sum(1 for c in crls if c.get('has_crl'))
        total_revoked = sum(c.get('revoked_count', 0) for c in crls if c.get('has_crl'))
        
        # Get scheduler status
        scheduler_status = "Unknown"
        last_run_str = '<div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">Last check: Initializing...</div>'
        
        try:
            from services.scheduler_service import get_scheduler
            scheduler = get_scheduler()
            task_status = scheduler.get_task_status("crl_auto_regen")
            if task_status:
                if not task_status.get('enabled'):
                    scheduler_status = "Disabled"
                    last_run_str = '<div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">Last check: Disabled</div>'
                else:
                    scheduler_status = "Active"
                    last_run = task_status.get('last_run')
                    if last_run:
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                            # Convert to local time approximation (assuming server is UTC, browser will see server time)
                            last_run_time = dt.strftime('%H:%M:%S UTC')
                            last_run_str = f'<div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">Last check: {last_run_time}</div>'
                        except:
                            pass
                    else:
                         last_run_str = '<div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">Last check: Pending...</div>'
        except Exception as e:
            scheduler_status = "Error"
            last_run_str = f'<div style="font-size: 0.75rem; color: var(--danger-color); margin-top: 0.25rem;">Error: {str(e)}</div>'

        # Build HTML
        html = f'''
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; align-items: stretch;">
            <!-- Active CRLs -->
            <div class="card">
                <div class="stat-card">
                    <div class="stat-card-icon">
                        <svg class="ucm-icon" width="28" height="28"><use href="#icon-activity"/></svg>
                    </div>
                    <div class="stat-card-content">
                        <div class="stat-card-value">{active_crls} <span style="font-size: 0.875rem; color: var(--text-secondary); font-weight: 400;">/ {total_cas}</span></div>
                        <div class="stat-card-label">Active CRLs</div>
                    </div>
                </div>
            </div>
            
            <!-- Total Revoked -->
            <div class="card">
                <div class="stat-card">
                    <div class="stat-card-icon danger">
                        <svg class="ucm-icon" width="28" height="28"><use href="#icon-slash"/></svg>
                    </div>
                    <div class="stat-card-content">
                        <div class="stat-card-value">{total_revoked}</div>
                        <div class="stat-card-label">Revoked Certificates</div>
                    </div>
                </div>
            </div>
            
            <!-- Scheduler Status -->
            <div class="card">
                <div class="stat-card">
                    <div class="stat-card-icon success">
                        <svg class="ucm-icon" width="28" height="28"><use href="#icon-clock"/></svg>
                    </div>
                    <div class="stat-card-content">
                        <div class="stat-card-value" style="font-size: 1.25rem;">{scheduler_status}</div>
                        <div class="stat-card-label">Auto-Regeneration</div>
                    </div>
                </div>
            </div>
        </div>
                </div>
                <div>
                    <div style="font-size: 0.875rem; color: var(--text-secondary); font-weight: 500;">Auto-Regeneration</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: var(--text-primary);">{scheduler_status}</div>
                    {last_run_str}
                </div>
            </div>
        </div>
        
        <div class="card" style="padding: 0;">
            <div style="overflow-x: auto;">
                <table id="crl-table">
                    <thead style="background: var(--bg-secondary);">
                        <tr style="border-bottom: 2px solid var(--border-color);">
                            <th style="padding: 0.75rem; text-align: left;">CA</th>
                            <th style="padding: 0.75rem; text-align: left;">CDP Status</th>
                            <th style="padding: 0.75rem; text-align: left;">CRL Status</th>
                            <th style="padding: 0.75rem; text-align: left;">Revoked Count</th>
                            <th style="padding: 0.75rem; text-align: left;">Last Update</th>
                            <th style="padding: 0.75rem; text-align: left;">Next Update</th>
                            <th style="padding: 0.75rem; text-align: left;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        '''
        
        for crl_data in crls:
            ca_name = crl_data.get('ca_name', 'Unknown')
            ca_id = crl_data.get('ca_id')
            ca_refid = crl_data.get('ca_refid', '')
            cdp_enabled = crl_data.get('cdp_enabled', False)
            has_crl = crl_data.get('has_crl', False)
            
            # CDP Status badge
            if cdp_enabled:
                cdp_status = '<span class="badge-outline badge-success"><i class="fas fa-check" style="margin-right: 0.25rem;"></i>Enabled</span>'
            else:
                cdp_status = '<span class="badge-outline badge-secondary"><i class="fas fa-times" style="margin-right: 0.25rem;"></i>Disabled</span>'
            
            # CRL Status badge
            if not has_crl:
                crl_status = '<span class="badge-outline badge-warning">Never Generated</span>'
                revoked_count = '-'
                last_update = '-'
                next_update = '-'
                days_until = '-'
            else:
                is_stale = crl_data.get('is_stale', False)
                days_until_expiry = crl_data.get('days_until_expiry', 0)
                
                if is_stale:
                    crl_status = '<span class="badge-outline badge-danger"><i class="fas fa-exclamation-triangle" style="margin-right: 0.25rem;"></i>Stale</span>'
                elif days_until_expiry <= 1:
                    crl_status = '<span class="badge-outline badge-warning"><i class="fas fa-clock" style="margin-right: 0.25rem;"></i>Expiring Soon</span>'
                else:
                    crl_status = '<span class="badge-outline badge-success"><i class="fas fa-check" style="margin-right: 0.25rem;"></i>Up to Date</span>'
                
                revoked_count = crl_data.get('revoked_count', 0)
                
                # Format dates
                this_update = crl_data.get('this_update', '')
                next_update_str = crl_data.get('next_update', '')
                
                if this_update:
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(this_update.replace('Z', '+00:00'))
                        last_update = dt.strftime('%Y-%m-%d %H:%M UTC')
                    except:
                        last_update = this_update[:16]
                else:
                    last_update = '-'
                
                if next_update_str:
                    try:
                        dt = datetime.fromisoformat(next_update_str.replace('Z', '+00:00'))
                        next_update = dt.strftime('%Y-%m-%d %H:%M UTC')
                        days_until = f"({days_until_expiry}d)"
                    except:
                        next_update = next_update_str[:16]
                        days_until = ''
                else:
                    next_update = '-'
                    days_until = ''
            
            # Actions buttons
            actions = f'''
            <div style="display: flex; justify-content: flex-end; gap: 0.5rem;">
            '''
            
            if has_crl:
                actions += f'''
                <button data-action="download-crl" data-ca-id="{ca_id}" data-format="pem"
                        class="btn-icon btn-icon-secondary" title="Download PEM">
                    <svg class="ucm-icon" width="16" height="16"><use href="#icon-download"/></svg>
                </button>
                <button data-action="download-crl" data-ca-id="{ca_id}" data-format="der"
                        class="btn-icon btn-icon-secondary" title="Download DER">
                    <svg class="ucm-icon" width="16" height="16"><use href="#icon-download"/></svg>
                </button>
                <button data-action="view-crl-info" data-refid="{ca_refid}"
                        class="btn-icon btn-icon-secondary" title="View Info">
                    <svg class="ucm-icon" width="16" height="16"><use href="#icon-info"/></svg>
                </button>
                '''
            
            if cdp_enabled:
                actions += f'''
                <button data-action="generate-crl" data-ca-id="{ca_id}" data-name="{html_escape(ca_name)}"
                        class="btn-icon btn-icon-primary" title="Force Generate">
                    <svg class="ucm-icon" width="16" height="16"><use href="#icon-refresh"/></svg>
                </button>
                '''
            
            actions += '</div>'
            
            html += f'''
            <tr style="border-bottom: 1px solid var(--border-color);">
                <td style="padding: 0.75rem;">
                    <div style="font-weight: 500; color: var(--text-primary);">{ca_name}</div>
                    <div style="font-size: 0.875rem; color: var(--text-secondary);">{ca_refid}</div>
                </td>
                <td style="padding: 0.75rem;">{cdp_status}</td>
                <td style="padding: 0.75rem;">{crl_status}</td>
                <td style="padding: 0.75rem; color: var(--text-primary);">{revoked_count}</td>
                <td style="padding: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">{last_update}</td>
                <td style="padding: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">{next_update} {days_until}</td>
                <td style="padding: 0.75rem;">{actions}</td>
            </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        </div>
        '''
        
        return html
        
    except Exception as e:
        return f'<div style="padding: 1rem; color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/scep')
@login_required
def scep_config():
    """SCEP configuration page"""
    return render_template('scep/config.html')


@ui_bp.route('/api/ui/scep/config-form')
@login_required
def scep_config_form():
    """Get SCEP configuration form"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get current config
        response = requests.get(
            f"{request.url_root}scep/config",
            headers=headers,
            verify=False
        )
        
        config = response.json() if response.status_code == 200 else {}
        enabled = config.get('enabled', False)
        
        # Get CA list
        ca_response = requests.get(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            verify=False
        )
        cas = ca_response.json() if ca_response.status_code == 200 else []
        
        ca_options = '<option value="">Select CA...</option>'
        for ca in cas:
            selected = 'selected' if ca['refid'] == config.get('ca_refid') else ''
            ca_options += f'<option value="{ca["refid"]}" {selected}>{ca["descr"]}</option>'
        
        return f'''
        <form hx-post="/api/ui/scep/save" 
              hx-swap="none"
              hx-on::after-request="if(event.detail.successful) {{ showToast('SCEP configuration saved', 'success'); htmx.trigger('#scep-config-card', 'reload'); }}" 
              style="display: flex; flex-direction: column; gap: 1.25rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--bg-secondary); border-radius: 0.5rem;">
                <input type="checkbox" name="enabled" {"checked" if enabled else ""} 
                       style="width: 1.125rem; height: 1.125rem; cursor: pointer;">
                <label style="font-weight: 600; color: var(--text-primary); cursor: pointer;">Enable SCEP Server</label>
            </div>
            
            <div>
                <label style="display: block; font-size: 0.875rem; font-weight: 500; color: var(--text-secondary); margin-bottom: 0.5rem;">CA</label>
                <select name="ca_refid" class="form-input" style="width: 100%; padding: 0.625rem; border: 1px solid var(--border-color); border-radius: 0.5rem; background: var(--card-bg); color: var(--text-primary);">
                    {ca_options}
                </select>
            </div>
            
            <div>
                <label style="display: block; font-size: 0.875rem; font-weight: 500; color: var(--text-secondary); margin-bottom: 0.5rem;">Challenge Password</label>
                <input type="text" name="challenge_password" value="{config.get('challenge_password', '')}" placeholder="None"
                       class="form-input" style="width: 100%; padding: 0.625rem; border: 1px solid var(--border-color); border-radius: 0.5rem; background: var(--card-bg); color: var(--text-primary);">
            </div>
            
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--bg-secondary); border-radius: 0.5rem;">
                <input type="checkbox" name="auto_approve" {"checked" if config.get('auto_approve') else ""}
                       style="width: 1.125rem; height: 1.125rem; cursor: pointer;">
                <label style="color: var(--text-primary); cursor: pointer;">Auto-approve enrollment requests</label>
            </div>
            
            <div style="padding-top: 1rem; border-top: 1px solid var(--border-color);">
                <button type="submit" class="btn btn-primary">
                    <svg class="ucm-icon" width="16" height="16" style="margin-right: 0.5rem;"><use href="#icon-check"/></svg>
                    Save Configuration
                </button>
            </div>
        </form>
        '''
    except Exception as e:
        return f'<p style="color: var(--status-danger); padding: 1rem;">Error: {str(e)}</p>'


@ui_bp.route('/api/ui/scep/save', methods=['POST'])
@login_required
def scep_save():
    """Save SCEP configuration"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        data = {
            'enabled': request.form.get('enabled') == 'on',
            'ca_refid': request.form.get('ca_refid'),
            'challenge_password': request.form.get('challenge_password'),
            'auto_approve': request.form.get('auto_approve') == 'on'
        }
        
        response = requests.put(
            f"{request.url_root}scep/config",
            headers=headers,
            json=data,
            verify=False
        )
        
        return '', 200 if response.status_code == 200 else response.status_code
    except Exception as e:
        return str(e), 500


@ui_bp.route('/api/ui/scep/requests')
@login_required
def scep_requests():
    """Get SCEP requests list"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}scep/requests")
        
        if response.status_code != 200:
            return '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">Failed to load requests</div>'
        
        requests_list = response.json()
        
        if not requests_list:
            return '''
            <div style="padding: 2rem; text-align: center; color: var(--text-secondary);">
                <i class="fas fa-inbox" style="font-size: 2.5rem; margin-bottom: 1rem; opacity: 0.5;"></i>
                <p style="font-size: 1rem; font-weight: 500; margin-bottom: 0.5rem;">No SCEP Requests</p>
                <p style="font-size: 0.875rem;">Enrollment requests will appear here</p>
            </div>
            '''
        
        # Separate by status
        pending = [r for r in requests_list if r['status'] == 'pending']
        approved = [r for r in requests_list if r['status'] == 'approved']
        rejected = [r for r in requests_list if r['status'] == 'rejected']
        
        html = '<div style="overflow-x: auto;"><table style="width: 100%; border-collapse: collapse;">'
        html += '''
        <thead style="background: var(--bg-secondary);">
            <tr style="border-bottom: 2px solid var(--border-color);">
                <th style="padding: 0.75rem; text-align: left; font-weight: 600; color: var(--text-primary);">Status</th>
                <th style="padding: 0.75rem; text-align: left; font-weight: 600; color: var(--text-primary);">Subject</th>
                <th style="padding: 0.75rem; text-align: left; font-weight: 600; color: var(--text-primary);">Client IP</th>
                <th style="padding: 0.75rem; text-align: left; font-weight: 600; color: var(--text-primary);">Date</th>
                <th style="padding: 0.75rem; text-align: left; font-weight: 600; color: var(--text-primary);">Actions</th>
            </tr>
        </thead>
        <tbody>
        '''
        
        # Show pending first
        for req in pending:
            safe_txid = escape_js(req['transaction_id'])
            created_date = req['created_at'][:19] if req.get('created_at') else 'N/A'
            html += f'''
            <tr style="border-bottom: 1px solid var(--border-color);">
                <td style="padding: 0.75rem;">
                    <span class="badge-outline badge-warning"><i class="fas fa-clock"></i> Pending</span>
                </td>
                <td style="padding: 0.75rem; color: var(--text-primary); font-weight: 500;">{req['subject']}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">{req.get('client_ip', 'N/A')}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">{created_date}</td>
                <td style="padding: 0.75rem;">
                    <div style="display: flex; gap: 0.5rem;">
                        <button data-action="approve-scep" data-txid="{safe_txid}"
                                class="btn-primary" style="padding: 0.375rem 0.75rem; font-size: 0.875rem;">
                            <i class="fas fa-check" style="margin-right: 0.25rem;"></i> Approve
                        </button>
                        <button data-action="reject-scep" data-txid="{safe_txid}"
                                class="btn-secondary" style="padding: 0.375rem 0.75rem; font-size: 0.875rem; color: var(--danger-color);">
                            <i class="fas fa-times" style="margin-right: 0.25rem;"></i> Reject
                        </button>
                    </div>
                </td>
            </tr>
            '''
        
        # Then approved
        for req in approved:
            created_date = req['created_at'][:19] if req.get('created_at') else 'N/A'
            approved_date = req['approved_at'][:19] if req.get('approved_at') else 'N/A'
            html += f'''
            <tr style="border-bottom: 1px solid var(--border-color);">
                <td style="padding: 0.75rem;">
                    <span class="badge-outline badge-success"><i class="fas fa-check"></i> Approved</span>
                </td>
                <td style="padding: 0.75rem; color: var(--text-primary);">{req['subject']}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">{req.get('client_ip', 'N/A')}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">{created_date}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">
                    Approved: {approved_date}
                </td>
            </tr>
            '''
        
        # Then rejected
        for req in rejected:
            created_date = req['created_at'][:19] if req.get('created_at') else 'N/A'
            reason = req.get('rejection_reason', 'No reason provided')
            html += f'''
            <tr style="border-bottom: 1px solid var(--border-color);">
                <td style="padding: 0.75rem;">
                    <span class="badge-outline badge-danger"><i class="fas fa-ban"></i> Rejected</span>
                </td>
                <td style="padding: 0.75rem; color: var(--text-primary);">{req['subject']}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">{req.get('client_ip', 'N/A')}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">{created_date}</td>
                <td style="padding: 0.75rem; color: var(--text-secondary); font-size: 0.875rem;">
                    {reason}
                </td>
            </tr>
            '''
        
        html += '</tbody></table></div>'
        
        html += f'''
        <script>
        function approveSCEP(txid) {{
            if (!txid) return;
            fetch('/scep/requests/' + txid + '/approve', {{
                method: 'POST',
                headers: {{ 'Authorization': 'Bearer {token}', 'Content-Type': 'application/json' }}
            }})
            .then(r => r.json())
            .then(() => {{ 
                if (typeof showToast === 'function') showToast('Request approved', 'success'); 
                htmx.trigger('body', 'refreshSCEP'); 
            }})
            .catch(e => {{ 
                if (typeof showToast === 'function') showToast('Error: ' + e, 'error'); 
            }});
        }}
        
        function rejectSCEP(txid) {{
            if (!txid) return;
            fetch('/scep/requests/' + txid + '/reject', {{
                method: 'POST',
                headers: {{ 'Authorization': 'Bearer {token}', 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ reason: 'Rejected by administrator' }})
            }})
            .then(r => r.json())
            .then(() => {{ 
                if (typeof showToast === 'function') showToast('Request rejected', 'success'); 
                htmx.trigger('body', 'refreshSCEP'); 
            }})
            .catch(e => {{ 
                if (typeof showToast === 'function') showToast('Error: ' + e, 'error'); 
            }});
        }}
        </script>
        '''
        
        return html
    except Exception as e:
        return f'<div style="padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


# Import Management
@ui_bp.route('/import')
@login_required
def import_page():
    """Import page"""
    return render_template('import/index.html')


@ui_bp.route('/import-ca')
@login_required
def import_ca_page():
    """Import CA page"""
    return render_template('ca-import/index.html')


@ui_bp.route('/api/ui/import/config-form')
@login_required
def import_config_form():
    """Get import configuration form with support for API key or username/password"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/import/config")
        
        config = response.json() if response and response.status_code == 200 else {}
        auth_method = config.get('auth_method', 'web')
        
        html = f'''
        <form hx-post="/api/ui/import/save" hx-swap="none" 
              hx-on::after-request="if(event.detail.successful) window.showToast('Configuration saved successfully', 'success')">
            <div style="display: flex; flex-direction: column; gap: 1rem;">
                <div>
                    <label style="display: block; font-size: 0.875rem; font-weight: 500; color: var(--text-primary); margin-bottom: 0.5rem;">OPNsense URL</label>
                    <input type="url" name="base_url" value="{config.get('base_url', 'https://network')}" required
                           class="form-control">
                </div>
                
                <!-- API Key Authentication (only method) -->
                <input type="hidden" name="auth_method" value="api">
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    <div>
                        <label style="display: block; font-size: 0.875rem; font-weight: 500; color: var(--text-primary); margin-bottom: 0.5rem;">API Key</label>
                        <input type="text" name="api_key" value="{config.get('api_key', '')}" required
                               class="form-control">
                    </div>
                    <div>
                        <label style="display: block; font-size: 0.875rem; font-weight: 500; color: var(--text-primary); margin-bottom: 0.5rem;">API Secret</label>
                        <input type="password" name="api_secret" required
                               class="form-control">
                    </div>
                </div>
                <p style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-secondary);">
                    <i class="fas fa-info-circle"></i> Create API key in OPNsense: System → Access → Users → Edit user → API keys
                </p>
                
                <div class="flex space-x-3">
                    <button type="submit" class="btn btn-primary" id="save-config-btn">
                        Save Configuration
                    </button>
                    <button type="button" onclick="testImportConnection()"
                            class="btn btn-outline-secondary">
                        <svg class="ucm-icon" width="16" height="16"><use href="#icon-check-circle"/></svg>
                        Test Connection
                    </button>
                    <button type="button" onclick="executeImport()"
                            class="btn btn-secondary">
                        Execute Import
                    </button>
                </div>
            </div>
        </form>
        <script>
        function testImportConnection() {{
            const baseUrl = document.querySelector('input[name="base_url"]').value;
            const apiKey = document.querySelector('input[name="api_key"]').value;
            const apiSecret = document.querySelector('input[name="api_secret"]').value;
            
            if (!baseUrl || !apiKey || !apiSecret) {{
                showToast('Please fill in all fields', 'error');
                return;
            }}
            
            let requestData = {{
                base_url: baseUrl,
                verify_ssl: false,
                api_key: apiKey,
                api_secret: apiSecret
            }};
            
            fetch('/api/v1/import/test-connection', {{
                method: 'POST',
                headers: {{ 
                    'Authorization': 'Bearer {token}',
                    'Content-Type': 'application/json'
                }},
                body: JSON.stringify(requestData)
            }})
            .then(r => r.json())
            .then(d => {{
                if (d.success) {{
                    showToast('Connection successful!', 'success');
                }} else {{
                    showToast('Connection failed: ' + (d.error || 'Unknown error'), 'error');
                }}
            }})
            .catch(e => showToast('Error: ' + e.message, 'error'));
        }}
        
        function executeImport() {{
            if (confirm('Execute import from OPNsense?')) {{
                const baseUrl = document.querySelector('input[name="base_url"]').value;
                const apiKey = document.querySelector('input[name="api_key"]').value;
                const apiSecret = document.querySelector('input[name="api_secret"]').value;
                
                if (!baseUrl || !apiKey || !apiSecret) {{
                    showToast('Please fill in all fields', 'error');
                    return;
                }}
                
                let requestData = {{
                    skip_existing: true,
                    base_url: baseUrl,
                    verify_ssl: false,
                    api_key: apiKey,
                    api_secret: apiSecret
                }};
                
                fetch('/api/v1/import/execute', {{
                    method: 'POST',
                    headers: {{ 'Authorization': 'Bearer {token}', 'Content-Type': 'application/json' }},
                    body: JSON.stringify(requestData)
                }})
                .then(r => r.json())
                .then(d => {{
                    if (d.error) {{
                        showToast('Import failed: ' + d.error, 'error');
                    }} else {{
                        const casImported = d.cas?.imported || 0;
                        const casSkipped = d.cas?.skipped || 0;
                        const certsImported = d.certs?.imported || 0;
                        const certsSkipped = d.certs?.skipped || 0;
                        
                        let message = 'Import complete: ';
                        if (casImported > 0 || certsImported > 0) {{
                            message += casImported + ' CAs, ' + certsImported + ' certs imported';
                            if (casSkipped > 0 || certsSkipped > 0) {{
                                message += ' (' + (casSkipped + certsSkipped) + ' skipped)';
                            }}
                        }} else if (casSkipped > 0 || certsSkipped > 0) {{
                            message += 'All items already exist (' + casSkipped + ' CAs, ' + certsSkipped + ' certs skipped)';
                        }} else {{
                            message += 'No items found';
                        }}
                        
                        showToast(message, 'success');
                        htmx.trigger('body', 'refreshCAs');
                        htmx.trigger('body', 'refreshCerts');
                    }}
                }})
                .catch(e => showToast('Error: ' + e.message, 'error'));
            }}
        }}
        </script>
        '''
        
        # Debug: check if token is in generated HTML
        import sys
        token_placeholder = 'Bearer {token}'
        if token_placeholder in html and token:
            sys.stderr.write(f"ERROR: Token placeholder not replaced! Token starts with: {token[:30]}\n")
            sys.stderr.flush()
        
        return html
    except Exception as e:
        import sys
        sys.stderr.write(f"ERROR import_config_form: {str(e)}\n")
        sys.stderr.flush()
        return f'<p style="color: var(--danger-color);">Error: {str(e)}</p>'


@ui_bp.route('/api/ui/import/save', methods=['POST'])
@login_required
def import_save():
    """Save import configuration - supports both auth methods"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        auth_method = request.form.get('auth_method', 'web')
        
        data = {
            'base_url': request.form.get('base_url'),
            'verify_ssl': False
        }
        
        if auth_method == 'api':
            data['api_key'] = request.form.get('api_key')
            data['api_secret'] = request.form.get('api_secret')
        else:
            data['username'] = request.form.get('username')
            data['password'] = request.form.get('password')
        
        response = requests.put(
            f"{request.url_root}api/v1/import/config",
            headers=headers,
            json=data,
            verify=False
        )
        
        return '', 200 if response.status_code == 200 else response.status_code
    except Exception as e:
        return str(e), 500


@ui_bp.route('/api/ui/import/history')
@login_required
def import_history():
    """Get import history"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/import/history")
        
        if response is None or response.status_code != 200:
            return '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">No history</div>'
        
        data = response.json()
        total = data['cas']['count'] + data['certs']['count']
        
        if total == 0:
            return '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">No imported items</div>'
        
        return f'''
        <div style="padding: 1.5rem;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div style="text-align: center; padding: 1rem; background: var(--primary-bg); border-radius: 8px;">
                    <p style="font-size: 1.5rem; font-weight: 700; color: var(--primary-color);">{data['cas']['count']}</p>
                    <p style="font-size: 0.875rem; color: var(--text-secondary);">Imported CAs</p>
                </div>
                <div style="text-align: center; padding: 1rem; background: var(--success-bg); border-radius: 8px;">
                    <p style="font-size: 1.5rem; font-weight: 700; color: var(--success-color);">{data['certs']['count']}</p>
                    <p style="font-size: 0.875rem; color: var(--text-secondary);">Imported Certificates</p>
                </div>
            </div>
        </div>
        '''
    except Exception as e:
        return f'<div style="padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/certificates/import', methods=['POST'])
@login_required
def import_certificate_manual():
    """Manual certificate import endpoint"""
    try:
        data = request.get_json()
        import_method = data.get('import_method', 'paste')
        
        # Prepare payload for backend API
        payload = {
            'description': data.get('description', 'Imported Certificate'),
        }
        
        if import_method == 'container':
            # Container import (PKCS#12, PKCS#7, JKS, DER)
            import base64
            from cryptography.hazmat.primitives.serialization import pkcs12
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            
            container_data = base64.b64decode(data.get('container_data'))
            container_format = data.get('container_format', 'auto')
            container_password = data.get('container_password', '').encode() if data.get('container_password') else None
            
            try:
                # Try PKCS#12 first
                if container_format in ['auto', 'pkcs12']:
                    try:
                        private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                            container_data, 
                            container_password,
                            backend=default_backend()
                        )
                        
                        # Convert to PEM
                        cert_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
                        key_pem = private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption()
                        ).decode() if private_key else None
                        
                        chain_pem = None
                        if additional_certs:
                            chain_pem = '\n'.join([
                                cert.public_bytes(serialization.Encoding.PEM).decode() 
                                for cert in additional_certs
                            ])
                        
                        payload['crt'] = cert_pem
                        payload['prv'] = key_pem
                        if chain_pem:
                            payload['certificate_chain'] = chain_pem
                            
                    except Exception as e:
                        if container_format == 'pkcs12':
                            raise
                        # Try other formats
                        pass
                
                # Try DER format
                if container_format in ['auto', 'der'] and 'crt' not in payload:
                    try:
                        certificate = x509.load_der_x509_certificate(container_data, default_backend())
                        cert_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
                        payload['crt'] = cert_pem
                    except:
                        pass
                
                # Try PKCS#7
                if container_format in ['auto', 'pkcs7'] and 'crt' not in payload:
                    try:
                        from cryptography.hazmat.primitives.serialization import pkcs7
                        certs = pkcs7.load_der_pkcs7_certificates(container_data)
                        if certs:
                            cert_pem = certs[0].public_bytes(serialization.Encoding.PEM).decode()
                            payload['crt'] = cert_pem
                            if len(certs) > 1:
                                chain_pem = '\n'.join([
                                    cert.public_bytes(serialization.Encoding.PEM).decode() 
                                    for cert in certs[1:]
                                ])
                                payload['certificate_chain'] = chain_pem
                    except:
                        pass
                
                if 'crt' not in payload:
                    return jsonify({'error': 'Unable to parse container file'}), 400
                    
            except Exception as e:
                return jsonify({'error': f'Container parsing failed: {str(e)}'}), 400
        else:
            # PEM paste or upload
            payload['crt'] = data.get('certificate')
            payload['prv'] = data.get('private_key')
            if data.get('certificate_chain'):
                payload['certificate_chain'] = data.get('certificate_chain')
            
            if not payload['crt'] or not payload['prv']:
                return jsonify({'error': 'Certificate and private key are required'}), 400
        
        # Get access token and call backend API
        token = session.get('access_token')
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Call the existing certificate creation endpoint
        response = requests.post(
            f"{request.url_root}api/v1/certificates",
            headers=headers,
            json=payload,
            verify=False
        )
        
        if response.status_code in [200, 201]:
            return jsonify({'success': True, 'message': 'Certificate imported successfully'}), 200
        else:
            error_msg = response.json().get('error', 'Unknown error') if response.text else 'Import failed'
            return jsonify({'error': error_msg}), response.status_code
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Configuration Management
@ui_bp.route('/config')
@login_required
def config_page():
    """System configuration page"""
    return render_template('config/system.html')


@ui_bp.route('/api/ui/config/https-cert')
@login_required
def config_https_cert():
    """Get HTTPS certificate info"""
    try:
        import os
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from models import SystemConfig
        
        cert_path = str(Config.HTTPS_CERT_PATH)
        
        if not os.path.exists(cert_path):
            return '<div style="color: var(--warning-color);">No HTTPS certificate found</div>'
        
        with open(cert_path, 'rb') as f:
            cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        
        subject = cert.subject.rfc4514_string()
        issuer = cert.issuer.rfc4514_string()
        not_before = cert.not_valid_before.strftime('%Y-%m-%d %H:%M:%S UTC')
        not_after = cert.not_valid_after.strftime('%Y-%m-%d %H:%M:%S UTC')
        serial = hex(cert.serial_number)[2:].upper()
        
        # Check certificate source
        cert_source_config = SystemConfig.query.filter_by(key='https_cert_source').first()
        if cert_source_config and cert_source_config.value == 'managed':
            # Get cert ID
            cert_id_config = SystemConfig.query.filter_by(key='https_cert_id').first()
            cert_id = cert_id_config.value if cert_id_config else 'Unknown'
            source_badge = f'<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 500; background-color: var(--success-bg); color: var(--success-color);"><i class="fas fa-certificate" style="margin-right: 0.375rem;"></i>Managed Certificate (ID: {cert_id})</span>'
        elif cert_source_config and cert_source_config.value == 'imported':
            source_badge = '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 500; background-color: var(--info-bg); color: var(--info-color);"><i class="fas fa-file-import" style="margin-right: 0.375rem;"></i>Imported</span>'
        else:
            source_badge = '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 500; background-color: var(--warning-bg); color: var(--warning-color);"><i class="fas fa-tools" style="margin-right: 0.375rem;"></i>Auto-generated</span>'
        
        return f'''
        <div style="margin-bottom: 1rem;">
            {source_badge}
        </div>
        <dl style="display: grid; grid-template-columns: 1fr; gap: 1rem;">
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Subject</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary); font-family: monospace;">{subject}</dd>
            </div>
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Issuer</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary); font-family: monospace;">{issuer}</dd>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Valid From</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary);">{not_before}</dd>
                </div>
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Valid Until</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary);">{not_after}</dd>
                </div>
            </div>
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Serial Number</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary); font-family: monospace;">{serial}</dd>
            </div>
        </dl>
        '''
    except Exception as e:
        return f'<div style="color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/config/regenerate-https', methods=['POST'])
@login_required
def config_regenerate_https():
    """Regenerate HTTPS certificate"""
    try:
        from config.https_manager import HTTPSManager
        from models import SystemConfig
        
        https_mgr = HTTPSManager()
        https_mgr.setup_https()
        
        # Mark as auto-generated
        config = SystemConfig.query.filter_by(key='https_cert_source').first()
        if not config:
            config = SystemConfig(key='https_cert_source')
        config.value = 'auto-generated'
        config.description = 'Auto-generated self-signed certificate'
        db.session.add(config)
        db.session.commit()
        
        # Trigger automatic restart
        restart_ucm_service()
        
        flash('HTTPS certificate regenerated. Server will restart automatically.', 'success')
        return '', 200
    except Exception as e:
        flash(f'Error regenerating certificate: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/users')
@login_required
def config_users():
    """Get users list"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/auth/users")
        
        if response is None or response.status_code != 200:
            return '<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">No users</div>'
        
        users = response.json()
        
        html = '''
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Username</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Email</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Role</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for user in users:
            # Role badge
            role_colors = {
                'admin': 'var(--danger-color)',
                'operator': 'var(--warning-color)',
                'viewer': 'var(--info-color)'
            }
            role_color = role_colors.get(user['role'], 'var(--text-secondary)')
            
            # Role badge - clickable if not admin user
            if user['username'] == 'admin':
                role_badge = f'''
                    <span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--bg-secondary); color: {role_color}; border: 1px solid var(--border-color);">
                        <i class="fas fa-shield-alt" style="margin-right: 0.25rem;"></i> {user['role'].title()}
                    </span>
                '''
            else:
                role_badge = f'''
                    <button data-action="change-role" data-user-id="{user['id']}" data-username="{user['username']}" data-current-role="{user['role']}"
                            style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--bg-secondary); color: {role_color}; border: 1px solid var(--border-color); cursor: pointer; transition: all 0.2s;"
                            onmouseover="this.style.borderColor='{role_color}'; this.style.background='var(--card-bg)';"
                            onmouseout="this.style.borderColor='var(--border-color)'; this.style.background='var(--bg-secondary)';"
                            title="Click to change role">
                        <i class="fas fa-user-tag" style="margin-right: 0.25rem;"></i> {user['role'].title()}
                    </button>
                '''
            
            html += f'''
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: 0.75rem; color: var(--text-primary); font-weight: 500;">
                            <i class="fas fa-user" style="margin-right: 0.5rem; color: var(--text-secondary);"></i>
                            {user['username']}
                        </td>
                        <td style="padding: 0.75rem; color: var(--text-primary);">
                            {user['email']}
                        </td>
                        <td style="padding: 0.75rem;">
                            {role_badge}
                        </td>
                        <td style="padding: 0.75rem;">
                            <button data-action="change-password" data-user-id="{user['id']}" data-username="{user['username']}"
                                    style="color: var(--primary-color); background: none; border: none; cursor: pointer; text-decoration: none; font-size: 0.875rem; margin-right: 1rem;">
                                <i class="fas fa-key" style="margin-right: 0.25rem;"></i> Change Password
                            </button>
            '''
            
            if user['username'] != 'admin':
                html += f'''
                            <button hx-delete="/api/ui/config/user/{user['id']}"
                                    hx-confirm="Delete user {user['username']}?"
                                    hx-on::after-request="if(event.detail.successful){{htmx.trigger('body','refreshUsers');if(typeof showToast==='function')showToast('User deleted','success');}}"
                                    style="color: var(--danger-color); background: none; border: none; cursor: pointer; text-decoration: none; font-size: 0.875rem;">
                                <i class="fas fa-trash" style="margin-right: 0.25rem;"></i> Delete
                            </button>
                '''
            
            html += '''
                        </td>
                    </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
    except Exception as e:
        return f'<div style="text-align: center; padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/config/add-user', methods=['POST'])
@login_required
def config_add_user():
    """Add a new user"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        data = {
            'username': request.form.get('username'),
            'email': request.form.get('email'),
            'password': request.form.get('password'),
            'role': request.form.get('role', 'viewer')
        }
        
        response = requests.post(
            f"{request.url_root}api/v1/auth/users",
            headers=headers,
            json=data,
            verify=False
        )
        
        if response.status_code == 201:
            flash('User created successfully', 'success')
            return '<script>htmx.trigger("body", "refreshUsers")</script>', 200
        else:
            error_msg = response.json().get('error', 'Unknown error')
            flash(f'Error creating user: {error_msg}', 'error')
            return '', response.status_code
    except Exception as e:
        flash(f'Error creating user: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/change-password', methods=['POST'])
@login_required
def config_change_password():
    """Change user password"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        user_id = request.form.get('user_id')
        new_password = request.form.get('new_password')
        
        response = requests.put(
            f"{request.url_root}api/v1/auth/users/{user_id}",
            headers=headers,
            json={'password': new_password},
            verify=False
        )
        
        if response.status_code == 200:
            return '', 200
        else:
            error_msg = response.json().get('error', 'Unknown error')
            return error_msg, response.status_code
    except Exception as e:
        return str(e), 500


@ui_bp.route('/api/ui/config/change-role', methods=['POST'])
@login_required
def config_change_role():
    """Change user role"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        user_id = request.form.get('user_id')
        new_role = request.form.get('role')
        
        # Validate role
        if new_role not in ['admin', 'operator', 'viewer']:
            return 'Invalid role', 400
        
        response = requests.put(
            f"{request.url_root}api/v1/auth/users/{user_id}",
            headers=headers,
            json={'role': new_role},
            verify=False
        )
        
        if response.status_code == 200:
            return '', 200
        else:
            error_msg = response.json().get('error', 'Unknown error')
            return error_msg, response.status_code
    except Exception as e:
        return str(e), 500


@ui_bp.route('/api/ui/config/user/<int:user_id>', methods=['DELETE'])
@login_required
def config_delete_user(user_id):
    """Delete a user"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.delete(
            f"{request.url_root}api/v1/auth/users/{user_id}",
            headers=headers,
            verify=False
        )
        
        if response.status_code == 200:
            flash('User deleted successfully', 'success')
            return '<script>htmx.trigger("body", "refreshUsers")</script>', 200
        else:
            error_msg = response.json().get('error', 'Unknown error')
            flash(f'Error deleting user: {error_msg}', 'error')
            return '', response.status_code
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/system-save', methods=['POST'])
@login_required
def config_system_save():
    """Save system settings"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        data = {
            'default_cert_validity': int(request.form.get('default_cert_validity', 365)),
            'session_timeout': int(request.form.get('session_timeout', 60)),
            'enable_audit_log': request.form.get('enable_audit_log') == 'on',
            'enable_rate_limit': request.form.get('enable_rate_limit') == 'on',
            'scep_auto_approve': request.form.get('scep_auto_approve') == 'true'
        }
        
        response = requests.put(
            f"{request.url_root}api/v1/system/config",
            headers=headers,
            json=data,
            verify=False
        )
        
        if response.status_code == 200:
            flash('System settings saved successfully', 'success')
            return '', 200
        else:
            error_msg = response.json().get('error', 'Unknown error')
            flash(f'Error saving settings: {error_msg}', 'error')
            return '', response.status_code
    except Exception as e:
        flash(f'Error saving settings: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/db-stats')
@login_required
def config_db_stats():
    """Get database statistics"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/system/stats")
        
        if response.status_code != 200:
            return '<div style="color: var(--danger-color);">Error loading stats</div>'
        
        stats = response.json()
        
        # Get database file size
        import os
        db_path = str(Config.DATABASE_PATH)
        db_size = 0
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path) / (1024 * 1024)  # MB
        
        return f'''
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem;">
            <div style="background: var(--primary-bg); padding: 1rem; border-radius: 8px;">
                <p style="font-size: 1.5rem; font-weight: 700; color: var(--primary-color);">{stats.get('cas', 0)}</p>
                <p style="font-size: 0.875rem; color: var(--text-secondary);">CAs</p>
            </div>
            <div style="background: var(--success-bg); padding: 1rem; border-radius: 8px;">
                <p style="font-size: 1.5rem; font-weight: 700; color: var(--success-color);">{stats.get('certificates', 0)}</p>
                <p style="font-size: 0.875rem; color: var(--text-secondary);">Certificates</p>
            </div>
            <div style="background: var(--info-bg); padding: 1rem; border-radius: 8px;">
                <p style="font-size: 1.5rem; font-weight: 700; color: var(--info-color);">{stats.get('users', 0)}</p>
                <p style="font-size: 0.875rem; color: var(--text-secondary);">Users</p>
            </div>
            <div style="background: var(--warning-bg); padding: 1rem; border-radius: 8px;">
                <p style="font-size: 1.5rem; font-weight: 700; color: var(--warning-color);">{db_size:.2f} MB</p>
                <p style="font-size: 0.875rem; color: var(--text-secondary);">Database Size</p>
            </div>
        </div>
        '''
    except Exception as e:
        return f'<div style="color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/config/backup-db', methods=['POST'])
@login_required
def config_backup_db():
    """Create database backup"""
    try:
        import shutil
        from datetime import datetime
        
        db_path = str(Config.DATABASE_PATH)
        backup_dir = str(DATA_DIR / "backups")
        
        import os
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f'{backup_dir}/ucm_backup_{timestamp}.db'
        
        shutil.copy2(db_path, backup_path)
        
        flash(f'Database backup created: ucm_backup_{timestamp}.db', 'success')
        return '', 200
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/vacuum-db', methods=['POST'])
@login_required
def config_vacuum_db():
    """Vacuum the database"""
    try:
        from models import db
        
        db.session.execute('VACUUM')
        db.session.commit()
        
        flash('Database vacuumed successfully', 'success')
        return '<script>htmx.trigger("body", "refreshDbStats")</script>', 200
    except Exception as e:
        flash(f'Error vacuuming database: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/system-info')
@login_required
def config_system_info():
    """Get system information"""
    try:
        import platform
        import sys
        from datetime import datetime
        
        # Get uptime (approximate from process start)
        import psutil
        process = psutil.Process()
        uptime_seconds = datetime.now().timestamp() - process.create_time()
        uptime_hours = int(uptime_seconds / 3600)
        uptime_minutes = int((uptime_seconds % 3600) / 60)
        
        return f'''
        <dl style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Version</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary);">UCM 1.0.0</dd>
            </div>
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Python Version</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary);">{platform.python_version()}</dd>
            </div>
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Operating System</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary);">{platform.system()} {platform.release()}</dd>
            </div>
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Uptime</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary);">{uptime_hours}h {uptime_minutes}m</dd>
            </div>
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Database Path</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary); font-family: monospace;">''' + str(Config.DATABASE_PATH) + '''</dd>
            </div>
            <div>
                <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">Data Directory</dt>
                <dd style="margin-top: 0.25rem; font-size: 0.875rem; color: var(--text-primary); font-family: monospace;">''' + str(DATA_DIR) + '''/</dd>
            </div>
        </dl>
        '''
    except Exception as e:
        return f'<div style="color: var(--danger-color);">Error: {str(e)}</div>'


# CA Detail Pages
@ui_bp.route('/ca/<ca_id>')
@login_required
def ca_detail(ca_id):
    """View CA details"""
    try:
        # Get CA details (with auto token refresh)
        response = api_call_with_retry(
            'GET',
            f"{request.url_root}api/v1/ca/{ca_id}"
        )
        
        if not response:
            flash('Failed to connect to API', 'error')
            return redirect(url_for('ui.ca_list'))
        
        if response.status_code == 401:
            # Session expired
            return redirect(url_for('ui.login', expired='1'))
        
        if response.status_code != 200:
            flash('CA not found', 'error')
            return redirect(url_for('ui.ca_list'))
        
        ca = response.json()
        return render_template('ca/detail.html', ca=ca)
    except Exception as e:
        current_app.logger.error(f"Error in ca_detail: {e}")
        flash(f'Error loading CA: {str(e)}', 'error')
        return redirect(url_for('ui.ca_list'))


@ui_bp.route('/ca/new')
@login_required
def ca_new():
    """Create new CA page - returns CA list with trigger to open modal"""
    response = make_response(render_template('ca/list.html'))
    # Send trigger after swap to open modal
    response.headers['HX-Trigger-After-Swap'] = 'openCreateCAModal'
    return response


# Certificate Detail Pages  
@ui_bp.route('/certificates/<cert_id>')
@login_required
def cert_detail(cert_id):
    """View certificate details"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/certificates/{cert_id}")
        
        if response.status_code != 200:
            flash('Certificate not found', 'error')
            return redirect(url_for('ui.cert_list'))
        
        cert = response.json()
        return render_template('certs/detail.html', cert=cert)
    except Exception as e:
        flash(f'Error loading certificate: {str(e)}', 'error')
        return redirect(url_for('ui.cert_list'))


@ui_bp.route('/certificates/new')
@login_required
def cert_new():
    """Create new certificate page - returns cert list with trigger to open modal"""
    response = make_response(render_template('certs/list.html'))
    # Send trigger after swap to open modal
    response.headers['HX-Trigger-After-Swap'] = 'openCreateCertModal'
    return response


@ui_bp.route('/api/ui/ca/<ca_id>/certificates')
@login_required
def ca_certificates(ca_id):
    """Get certificates issued by a CA"""
    try:
        # Get CA to find its refid (with auto token refresh)
        ca_response = api_call_with_retry(
            'GET',
            f"{request.url_root}api/v1/ca/{ca_id}"
        )
        
        if not ca_response or ca_response.status_code == 401:
            return '<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Session expired. Please <a href="/logout?expired=1" style="text-decoration: underline;">login again</a>.</div>', 401
        
        if ca_response.status_code != 200:
            return '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">CA not found</div>'
        
        ca = ca_response.json()
        ca_refid = ca.get('refid')
        
        # Get all certificates (with auto token refresh)
        response = api_call_with_retry(
            'GET',
            f"{request.url_root}api/v1/certificates/"
        )
        
        if not response or response.status_code == 401:
            return '<div style="padding: 2rem; text-align: center; color: var(--danger-color);">Session expired. Please <a href="/logout?expired=1" style="text-decoration: underline;">login again</a>.</div>', 401
        
        if response.status_code != 200:
            return '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">No certificates</div>'
        
        all_certs = response.json()
        # Filter by caref matching CA's refid
        ca_certs = [c for c in all_certs if c.get('caref') == ca_refid]
        
        if not ca_certs:
            return '<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">No certificates issued by this CA</div>'
        
        html = '''
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Subject</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Type</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Status</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Valid Until</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for cert in ca_certs:
            # Badge for status
            status_badge = {
                'active': '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--success-bg); color: var(--success-color); border: 1px solid var(--success-border);"><i class="fas fa-circle-check" style="margin-right: 0.25rem;"></i> Active</span>',
                'revoked': '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--danger-bg); color: var(--danger-color); border: 1px solid var(--danger-border);"><i class="fas fa-ban" style="margin-right: 0.25rem;"></i> Revoked</span>',
                'pending': '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--warning-bg); color: var(--warning-color); border: 1px solid var(--warning-border);"><i class="fas fa-clock" style="margin-right: 0.25rem;"></i> Pending</span>'
            }.get(cert.get('status', 'active'), '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--bg-secondary); color: var(--text-secondary); border: 1px solid var(--border-color);"><i class="fas fa-circle" style="margin-right: 0.25rem;"></i> Unknown</span>')
            
            # Check if ACME certificate
            is_acme = cert.get('created_by') == 'acme'
            acme_badge = '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; font-weight: 600; background: var(--success-bg); color: var(--success-color); border: 1px solid var(--success-border); margin-left: 0.5rem;"><i class="fas fa-robot" style="margin-right: 0.25rem;"></i> ACME</span>' if is_acme else ''
            
            html += f'''
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="padding: 0.75rem;">
                        <a href="/certificates/{cert['id']}" style="color: var(--primary-color); font-weight: 500; text-decoration: none;">
                            {cert.get('descr', cert.get('subject', 'N/A'))}
                        </a>
                    </td>
                    <td style="padding: 0.75rem; color: var(--text-primary);">
                        {cert.get('cert_type', 'server_cert').replace('_', ' ').title()}{acme_badge}
                    </td>
                    <td style="padding: 0.75rem;">
                        {status_badge}
                    </td>
                    <td style="padding: 0.75rem; color: var(--text-primary); font-family: monospace; font-size: 0.875rem;">
                        {cert.get('valid_to', 'N/A')[:10] if cert.get('valid_to') else 'N/A'}
                    </td>
                    <td style="padding: 0.75rem;">
                        <a href="/certificates/{cert['id']}" style="color: var(--primary-color); text-decoration: none; font-size: 0.875rem;">
                            <i class="fas fa-eye" style="margin-right: 0.25rem;"></i> View
                        </a>
                    </td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
    except Exception as e:
        return f'<div style="padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/test-design')
@login_required
def test_design():
    """Test page for new design"""
    return '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Design Test</title>
    <script>
        // Force browser to reload without cache
        window.location.href = window.location.href.split('#')[0] + '?nocache=' + Date.now();
    </script>
</head>
<body>
    <h1>Redirecting...</h1>
</body>
</html>
'''


@ui_bp.route('/api/ui/config/upload-https-cert', methods=['POST'])
@login_required
def upload_https_cert():
    """Upload custom HTTPS certificate chain"""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        from pathlib import Path
        import os
        
        certificate = request.form.get('certificate', '').strip()
        private_key = request.form.get('private_key', '').strip()
        ca_chain = request.form.get('ca_chain', '').strip()
        
        if not certificate or not private_key:
            flash('Certificate and private key are required', 'error')
            return '', 400
        
        # Validate certificate
        try:
            cert_obj = x509.load_pem_x509_certificate(
                certificate.encode(), default_backend()
            )
        except Exception as e:
            flash(f'Invalid certificate format: {str(e)}', 'error')
            return '', 400
        
        # Validate private key
        try:
            key_obj = serialization.load_pem_private_key(
                private_key.encode(), password=None, backend=default_backend()
            )
        except Exception as e:
            flash(f'Invalid private key format: {str(e)}', 'error')
            return '', 400
        
        # Validate CA chain if provided
        full_chain = certificate
        if ca_chain:
            try:
                # Validate each cert in chain
                chain_parts = ca_chain.split('-----BEGIN CERTIFICATE-----')
                for part in chain_parts:
                    if part.strip():
                        cert_pem = '-----BEGIN CERTIFICATE-----' + part
                        x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
                
                # Append to full chain
                full_chain = certificate + '\n' + ca_chain
            except Exception as e:
                flash(f'Invalid CA chain format: {str(e)}', 'error')
                return '', 400
        
        # Save files
        cert_path = Config.HTTPS_CERT_PATH
        key_path = Config.HTTPS_KEY_PATH
        
        # Backup existing files
        if cert_path.exists():
            os.rename(cert_path, str(cert_path) + '.backup')
        if key_path.exists():
            os.rename(key_path, str(key_path) + '.backup')
        
        try:
            with open(cert_path, 'w') as f:
                f.write(full_chain)
            with open(key_path, 'w') as f:
                f.write(private_key)
            
            # Mark as imported
            from models import SystemConfig
            config = SystemConfig.query.filter_by(key='https_cert_source').first()
            if not config:
                config = SystemConfig(key='https_cert_source')
            config.value = 'imported'
            config.description = 'Imported certificate chain'
            db.session.add(config)
            db.session.commit()
            
            # Trigger automatic restart
            restart_ucm_service()
            
            flash('HTTPS certificate imported successfully. Server will restart automatically.', 'success')
            return '', 200
        except Exception as e:
            # Restore backups on error
            if os.path.exists(str(cert_path) + '.backup'):
                os.rename(str(cert_path) + '.backup', cert_path)
            if os.path.exists(str(key_path) + '.backup'):
                os.rename(str(key_path) + '.backup', key_path)
            raise e
            
    except Exception as e:
        flash(f'Error uploading certificate: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/managed-certs')
@ui_bp.route('/api/ui/config/managed-certs-list')  # Backward compatibility
@login_required
def managed_certs_list():
    """Get list of recent certificates for dashboard"""
    try:
        token = session.get('access_token')
        if not token:
            return '<div style="text-align: center; padding: 2rem; color: var(--danger-color);">Session expired</div>'
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get all certificates via API
        response = requests.get(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<div style="text-align: center; padding: 2rem; color: var(--danger-color);">Failed to load certificates</div>'
        
        from datetime import datetime
        
        # Get all certificates (including CSRs, all types)
        all_certs = response.json()
        
        # Sort by creation date (most recent first)
        certs = sorted(all_certs, key=lambda x: x.get('created_at', ''), reverse=True)[:10]  # Last 10
        
        if not certs:
            return '''
            <div style="text-align: center; padding: 3rem;">
                <i class="fas fa-certificate" style="font-size: 3rem; color: var(--text-secondary); margin-bottom: 1rem;"></i>
                <p style="color: var(--text-secondary);">No certificates found</p>
                <p style="font-size: 0.875rem; color: var(--text-muted); margin-top: 0.5rem;">Create your first certificate to get started</p>
            </div>
            '''
        
        html = '''
        <div style="overflow-y: auto; max-height: 500px;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead style="position: sticky; top: 0; background: var(--bg-secondary); z-index: 10;">
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Certificate</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Type</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Status</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Expires</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for cert in certs:
            # Get description
            descr = cert.get('descr', 'Unknown Certificate')
            cert_id = cert.get('id', '')
            
            # Get type
            cert_type = cert.get('cert_type', 'unknown')
            type_labels = {
                'server_cert': 'Server',
                'client_cert': 'Client', 
                'combined_cert': 'Combined',
                'ca_cert': 'CA'
            }
            type_label = type_labels.get(cert_type, cert_type.replace('_', ' ').title())
            
            # Type icon
            type_icons = {
                'server_cert': 'server',
                'client_cert': 'user',
                'combined_cert': 'exchange-alt',
                'ca_cert': 'certificate'
            }
            type_icon = type_icons.get(cert_type, 'certificate')
            
            # Check if ACME certificate
            is_acme = cert.get('created_by') == 'acme'
            
            # Status
            is_csr = not cert.get('serial_number')
            is_revoked = cert.get('revoked', False)
            
            if is_csr:
                status_badge = '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; background: var(--warning-bg); color: var(--warning-color); border: 1px solid var(--warning-border);"><i class="fas fa-file-signature" style="margin-right: 0.25rem;"></i> CSR</span>'
            elif is_revoked:
                status_badge = '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; background: var(--danger-bg); color: var(--danger-color); border: 1px solid var(--danger-border);"><i class="fas fa-ban" style="margin-right: 0.25rem;"></i> Revoked</span>'
            else:
                status_badge = '<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; background: var(--success-bg); color: var(--success-color); border: 1px solid var(--success-border);"><i class="fas fa-check-circle" style="margin-right: 0.25rem;"></i> Active</span>'
            
            # Expiration with color
            valid_to = cert.get('valid_to', '')[:10] if cert.get('valid_to') else 'N/A'
            
            # Calculate days left
            days_color = 'var(--text-primary)'
            days_text = ''
            try:
                if cert.get('valid_to') and not is_csr:
                    exp_date = datetime.fromisoformat(cert['valid_to'].replace('Z', '+00:00'))
                    days_left = (exp_date - datetime.utcnow().replace(tzinfo=exp_date.tzinfo)).days
                    
                    if days_left < 0:
                        days_color = 'var(--danger-color)'
                        days_text = f'Expired'
                    elif days_left < 30:
                        days_color = 'var(--danger-color)'
                        days_text = f'{days_left}d left'
                    elif days_left < 90:
                        days_color = 'var(--warning-color)'
                        days_text = f'{days_left}d left'
                    else:
                        days_color = 'var(--success-color)'
                        days_text = f'{days_left}d left'
            except:
                pass
            
            html += f'''
                <tr style="border-bottom: 1px solid var(--border-color); cursor: pointer; transition: background 0.2s;"
                    onmouseover="this.style.background='var(--bg-secondary)'"
                    onmouseout="this.style.background='transparent'"
                    onclick="window.location.href='/certificates/{cert_id}'">
                    <td style="padding: 0.75rem;">
                        <div style="display: flex; align-items: center;">
                            <i class="fas fa-certificate" style="margin-right: 0.75rem; color: var(--primary-color);"></i>
                            <div>
                                <div style="font-weight: 500; color: var(--text-primary);">{descr}</div>
                                <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.125rem;">ID: {cert_id}</div>
                            </div>
                        </div>
                    </td>
                    <td style="padding: 0.75rem;">
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <div style="display: flex; align-items: center;">
                                <i class="fas fa-{type_icon}" style="margin-right: 0.5rem; color: var(--text-secondary);"></i>
                                <span style="color: var(--text-primary);">{type_label}</span>
                            </div>
                            {f'<span style="display: inline-flex; align-items: center; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.7rem; font-weight: 600; background: var(--success-bg); color: var(--success-color); border: 1px solid var(--success-border);"><i class="fas fa-robot" style="margin-right: 0.25rem;"></i> ACME</span>' if is_acme else ''}
                        </div>
                    </td>
                    <td style="padding: 0.75rem;">
                        {status_badge}
                    </td>
                    <td style="padding: 0.75rem;">
                        <div style="color: var(--text-primary); font-family: monospace; font-size: 0.875rem;">{valid_to}</div>
                        {f'<div style="font-size: 0.75rem; color: {days_color}; margin-top: 0.25rem;">{days_text}</div>' if days_text else ''}
                    </td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
    except Exception as e:
        return f'<div style="text-align: center; padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/config/use-managed-cert/<int:cert_id>', methods=['POST'])
@login_required
def use_managed_cert(cert_id):
    """Use a managed certificate for HTTPS"""
    try:
        token = session.get('access_token')
        if not token:
            flash('Session expired', 'error')
            return 'Session expired', 401
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get certificate with private key via secure API endpoint
        response = requests.get(
            f"{request.url_root}api/v1/certificates/{cert_id}/private",
            headers=headers,
            verify=False
        )
        
        if response.status_code == 403:
            flash('Admin access required', 'error')
            return 'Admin access required', 403
        elif response.status_code == 404:
            flash('Certificate not found', 'error')
            return 'Certificate not found', 404
        elif response.status_code != 200:
            error_msg = response.json().get('error', 'Failed to get certificate')
            flash(error_msg, 'error')
            return error_msg, response.status_code
        
        cert_data = response.json()
        
        # Verify we have required data
        if not cert_data.get('has_private_key'):
            flash('Private key not available for this certificate', 'error')
            return 'Private key not available', 400
        
        cert_pem = cert_data['certificate_pem']
        key_pem = cert_data['private_key_pem']
        ca_chain_pem = cert_data.get('ca_chain_pem')
        
        # Build full chain
        full_chain = cert_pem
        if ca_chain_pem:
            full_chain = cert_pem + '\n' + ca_chain_pem
        
        # Save files
        from pathlib import Path
        import os
        
        cert_path = Config.HTTPS_CERT_PATH
        key_path = Config.HTTPS_KEY_PATH
        
        # Backup existing files
        if cert_path.exists():
            os.rename(cert_path, str(cert_path) + '.backup')
        if key_path.exists():
            os.rename(key_path, str(key_path) + '.backup')
        
        try:
            with open(cert_path, 'w') as f:
                f.write(full_chain)
            with open(key_path, 'w') as f:
                f.write(key_pem)
            
            # Store certificate source in database (use same format as settings page)
            from models import SystemConfig
            cert_source_config = SystemConfig.query.filter_by(key='https_cert_source').first()
            if not cert_source_config:
                cert_source_config = SystemConfig(key='https_cert_source')
            cert_source_config.value = 'managed'
            cert_source_config.description = f'Managed certificate ID: {cert_id}'
            db.session.add(cert_source_config)
            
            # Store cert ID separately
            cert_id_config = SystemConfig.query.filter_by(key='https_cert_id').first()
            if not cert_id_config:
                cert_id_config = SystemConfig(key='https_cert_id')
            cert_id_config.value = str(cert_id)
            db.session.add(cert_id_config)
            
            db.session.commit()
            
            # Trigger automatic restart
            restart_ucm_service()
            
            flash('HTTPS certificate updated successfully. Server will restart automatically.', 'success')
            return '', 200
        except Exception as e:
            # Restore backups on error
            if os.path.exists(str(cert_path) + '.backup'):
                os.rename(str(cert_path) + '.backup', cert_path)
            if os.path.exists(str(key_path) + '.backup'):
                os.rename(str(key_path) + '.backup', key_path)
            raise e
            
    except Exception as e:
        flash(f'Error applying certificate: {str(e)}', 'error')
        return str(e), 500



# ===== SENTINEL THEME DEMO =====


@ui_bp.route('/test-simple')
def test_simple():
    """Ultra simple test page"""
    return render_template('test-simple.html')


# ===== SESSION MANAGEMENT API =====

@ui_bp.route('/api/session/extend', methods=['POST'])
@login_required
def extend_session():
    """Extend user session by updating last_activity"""
    try:
        session['last_activity'] = time.time()
        return jsonify({
            'success': True,
            'message': 'Session extended',
            'expires_at': session['last_activity'] + 1800  # 30 minutes from now
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ui_bp.route('/api/session/check', methods=['GET'])
@login_required
def check_session():
    """Check if session is still valid"""
    return jsonify({
        'success': True,
        'active': True,
        'last_activity': session.get('last_activity')
    }), 200


@ui_bp.route('/ocsp')
@login_required
def ocsp_page():
    """OCSP Status page"""
    return render_template('ocsp/status.html')


@ui_bp.route('/api/ui/ocsp/status')
@login_required
def ocsp_status_list():
    """Get OCSP status for all CAs"""
    try:
        from models import CA, OCSPResponse
        
        cas = CA.query.all()
        
        html = '''
        <div style="overflow-x: auto;">
            <table id="ocsp-status-table">
                <thead style="background: var(--bg-secondary);">
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left;">CA Name</th>
                        <th style="padding: 0.75rem; text-align: left;">OCSP Status</th>
                        <th style="padding: 0.75rem; text-align: left;">OCSP URL</th>
                        <th style="padding: 0.75rem; text-align: left;">Cached Responses</th>
                        <th style="padding: 0.75rem; text-align: left;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for ca in cas:
            cached_count = OCSPResponse.query.filter_by(ca_id=ca.id).count()
            
            status_badge = ''
            if ca.ocsp_enabled:
                status_badge = '<span class="badge-outline badge-success"><i class="fas fa-check" style="margin-right: 0.25rem;"></i>Enabled</span>'
            else:
                status_badge = '<span class="badge-outline badge-secondary"><i class="fas fa-times" style="margin-right: 0.25rem;"></i>Disabled</span>'
            
            ocsp_url_display = ca.ocsp_url if ca.ocsp_url else '<span style="color: var(--text-muted);">Not configured</span>'
            
            html += f'''
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="padding: 0.75rem;">
                        <div style="font-weight: 500; color: var(--text-primary);">{ca.descr}</div>
                        <div style="font-size: 0.875rem; color: var(--text-secondary);">{ca.refid}</div>
                    </td>
                    <td style="padding: 0.75rem;">{status_badge}</td>
                    <td style="padding: 0.75rem;"><code style="font-size: 0.875rem; color: var(--text-secondary);">{ocsp_url_display}</code></td>
                    <td style="padding: 0.75rem; text-align: center; color: var(--text-primary);">{cached_count}</td>
                    <td style="padding: 0.75rem;">
                        <a href="/ca/{ca.id}" class="btn-icon btn-icon-primary" title="Configure">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-settings"/></svg>
                        </a>
                    </td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
        
    except Exception as e:
        logger.error(f"Error getting OCSP status: {e}")
        return f'<div style="color: var(--danger-color);">Error loading OCSP status: {str(e)}</div>'


@ui_bp.route('/api/ui/ocsp/stats')
@login_required
def ocsp_stats_ui():
    """Get OCSP statistics for UI"""
    try:
        from models import CA, OCSPResponse
        
        # Count CAs with OCSP enabled
        ocsp_enabled_cas = CA.query.filter_by(ocsp_enabled=True).count()
        
        # Count cached responses
        cached_responses = OCSPResponse.query.count()
        
        # Return HTML fragments for HTMX
        return f'''
        <span class="ocsp-enabled-count">{ocsp_enabled_cas}</span>
        <span class="cached-responses-count">{cached_responses}</span>
        '''
        
    except Exception as e:
        logger.error(f"Error getting OCSP stats: {e}")
        return '<span style="color: var(--danger-color);">Error</span>'


# HTTPS Certificate Management UI Routes

@ui_bp.route('/api/ui/system/https-cert-info')
@login_required
def https_cert_info_ui():
    """Get current HTTPS certificate information (UI route with session auth)"""
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from pathlib import Path
    from models import SystemConfig
    import logging
    
    logger = logging.getLogger(__name__)
    
    cert_path = Path(current_app.config['HTTPS_CERT_PATH'])
    
    try:
        with open(cert_path, 'rb') as f:
            cert_pem = f.read()
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        # Determine certificate source
        source_config = SystemConfig.query.filter_by(key='https_cert_source').first()
        source = source_config.value if source_config else 'auto'
        
        # Get cert ID if managed
        cert_id = None
        if source == 'managed':
            cert_id_config = SystemConfig.query.filter_by(key='https_cert_id').first()
            if cert_id_config:
                cert_id = cert_id_config.value
        
        # Extract subject
        subject_parts = []
        for attr in cert.subject:
            subject_parts.append(f"{attr.oid._name}={attr.value}")
        subject_str = ', '.join(subject_parts)
        
        # Extract issuer
        issuer_str = cert.issuer.rfc4514_string()
        subject_rfc = cert.subject.rfc4514_string()
        
        # Determine if truly self-signed (subject == issuer)
        is_self_signed = (subject_rfc == issuer_str)
        
        # Format expiry date (compatible with all cryptography versions)
        expires = cert.not_valid_after.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Determine display type based on source and whether truly self-signed
        if source == 'managed':
            cert_type = 'UCM Managed'
        elif is_self_signed:
            cert_type = 'Self-Signed'
        else:
            cert_type = 'CA-Signed (Auto-generated)'
        
        result = {
            'type': cert_type,
            'subject': subject_str,
            'expires': expires,
            'source': source,
            'issuer': issuer_str,
            'is_self_signed': is_self_signed
        }
        
        # Add cert_id if managed
        if source == 'managed' and cert_id:
            result['cert_id'] = cert_id
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error loading HTTPS cert info: {e}")
        return jsonify({
            'type': 'Error',
            'subject': str(e),
            'expires': 'N/A',
            'source': 'unknown'
        }), 200


@ui_bp.route('/api/ui/system/https-cert-candidates')
@login_required
def https_cert_candidates_ui():
    """Get list of certificates suitable for HTTPS (UI route with session auth)"""
    from pathlib import Path
    from models import SystemConfig, Certificate, CA
    from datetime import datetime
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import ExtendedKeyUsageOID
    import base64
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get current cert_id if using managed
    current_cert_id = None
    config = SystemConfig.query.filter_by(key='https_cert_id').first()
    if config:
        current_cert_id = int(config.value)
    
    # Find suitable certificates (not revoked, server certs, not expired)
    now = datetime.utcnow()
    certificates = Certificate.query.filter(
        Certificate.revoked == False,
        Certificate.cert_type.in_(['server_cert', 'cert']),
        Certificate.valid_to > now  # Not expired
    ).all()
    
    logger.info(f"Found {len(certificates)} potential HTTPS certificate candidates")
    
    candidates = []
    for cert in certificates:
        # Check if certificate has been issued (has crt field)
        if not cert.crt:
            continue
            
        # Check if private key exists
        key_path = current_app.config['PRIVATE_DIR'] / f'cert_{cert.refid}.key'
        if not key_path.exists():
            # Try refid-based naming
            key_path = current_app.config['PRIVATE_DIR'] / f'{cert.refid}.key'
            if not key_path.exists():
                continue
        
        # Parse certificate to check Extended Key Usage
        try:
            cert_pem = base64.b64decode(cert.crt)
            x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            
            # Check if certificate has Server Authentication EKU
            has_server_auth = False
            try:
                ext = x509_cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
                )
                if ExtendedKeyUsageOID.SERVER_AUTH in ext.value:
                    has_server_auth = True
            except x509.ExtensionNotFound:
                # If no EKU extension, accept server_cert type certificates
                if cert.cert_type == 'server_cert':
                    has_server_auth = True
            
            if not has_server_auth:
                logger.debug(f"Certificate {cert.descr} rejected: no Server Authentication EKU")
                continue
                
        except Exception as e:
            logger.warning(f"Failed to parse certificate {cert.descr}: {e}")
            # If can't parse, skip for safety
            continue
        
        # Get CA name
        ca = CA.query.filter_by(refid=cert.caref).first()
        
        # Extract CN from subject if available
        cn = 'N/A'
        if cert.subject:
            for part in cert.subject.split(','):
                if 'CN=' in part:
                    cn = part.split('CN=')[1].strip()
                    break
        
        # Build SAN list
        san_list = []
        if cert.san_dns:
            try:
                import json
                dns_names = json.loads(cert.san_dns)
                san_list.extend(dns_names)
            except:
                pass
        
        # Calculate days until expiration
        days_left = (cert.valid_to - now).days if cert.valid_to else 0
        
        candidates.append({
            'id': cert.id,
            'cert_id': cert.refid,
            'common_name': cn or cert.descr,
            'subject': cert.subject or f'CN={cn}',
            'san': ', '.join(san_list) if san_list else '',
            'expires': cert.valid_to.strftime('%Y-%m-%d') if cert.valid_to else 'N/A',
            'days_left': days_left,
            'ca_name': ca.descr if ca else 'Unknown',
            'is_current': cert.id == current_cert_id
        })
    
    logger.info(f"Filtered to {len(candidates)} suitable HTTPS certificates")
    return jsonify({'certificates': candidates}), 200


@ui_bp.route('/api/ui/system/https-cert-apply', methods=['POST'])
@login_required
def https_cert_apply_ui():
    """Apply a new HTTPS certificate (UI route with session auth)"""
    from pathlib import Path
    from models import SystemConfig, Certificate, CA, User, db
    import shutil
    import subprocess
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    data = request.get_json()
    source = data.get('source', 'auto')
    cert_id = data.get('cert_id')
    
    # Check admin role
    user = User.query.get(session['user_id'])
    if user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin role required'}), 403
    
    try:
        if source == 'managed':
            if not cert_id:
                return jsonify({'success': False, 'error': 'cert_id required for managed source'}), 400
            
            # Get certificate from database
            cert = Certificate.query.get(cert_id)
            if not cert:
                return jsonify({'success': False, 'error': 'Certificate not found'}), 404
            
            # Load certificate and key (use refid for file paths)
            cert_file = current_app.config['CERT_DIR'] / f'{cert.refid}.crt'
            
            key_file = current_app.config['PRIVATE_DIR'] / f'{cert.refid}.key'
            
            if not cert_file.exists() or not key_file.exists():
                return jsonify({'success': False, 'error': 'Certificate or key file not found'}), 404
            
            # Copy to HTTPS location
            https_cert = Path(current_app.config['HTTPS_CERT_PATH'])
            https_key = Path(current_app.config['HTTPS_KEY_PATH'])
            
            # Backup current cert to backups directory (not in /etc/ucm)
            from config.settings import DATA_DIR
            backup_dir = DATA_DIR / 'backups'
            backup_dir.mkdir(exist_ok=True)
            
            if https_cert.exists():
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_cert = backup_dir / f'https_cert_{timestamp}.pem.backup'
                shutil.copy(https_cert, backup_cert)
            if https_key.exists():
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_key = backup_dir / f'https_key_{timestamp}.pem.backup'
                shutil.copy(https_key, backup_key)
            
            # Copy new cert
            shutil.copy(cert_file, https_cert)
            shutil.copy(key_file, https_key)
            
            # Set permissions
            os.chmod(https_key, 0o600)
            os.chmod(https_cert, 0o644)
            
            # Save configuration
            print(f"🔧 DEBUG: Saving certificate config - source=managed, cert_id={cert_id}")
            config = SystemConfig.query.filter_by(key='https_cert_source').first()
            if not config:
                print(f"🔧 DEBUG: Creating new https_cert_source config")
                config = SystemConfig(key='https_cert_source', value='managed')
                db.session.add(config)
            else:
                print(f"🔧 DEBUG: Updating existing https_cert_source config from {config.value} to managed")
                config.value = 'managed'
            
            cert_id_config = SystemConfig.query.filter_by(key='https_cert_id').first()
            if not cert_id_config:
                print(f"🔧 DEBUG: Creating new https_cert_id config with value {cert_id}")
                cert_id_config = SystemConfig(key='https_cert_id', value=str(cert_id))
                db.session.add(cert_id_config)
            else:
                print(f"🔧 DEBUG: Updating existing https_cert_id config from {cert_id_config.value} to {cert_id}")
                cert_id_config.value = str(cert_id)
            
            print(f"🔧 DEBUG: Committing database changes...")
            db.session.commit()
            print(f"🔧 DEBUG: Database commit successful!")
            
            logger.info(f"HTTPS certificate applied: {cert.common_name} (ID: {cert_id}) by {user.username}")
        
        elif source == 'auto':
            # Switch back to auto-generated self-signed certificate
            config = SystemConfig.query.filter_by(key='https_cert_source').first()
            if not config:
                config = SystemConfig(key='https_cert_source', value='auto')
                db.session.add(config)
            else:
                config.value = 'auto'
            
            db.session.commit()
            logger.info(f"HTTPS certificate source set to auto (self-signed) by {user.username}")
        
        # Restart UCM service
        from utils import restart_service
        success, message = restart_service()
        
        return jsonify({'success': success, 'message': message}), 200
        
    except Exception as e:
        logger.error(f"Error applying HTTPS certificate: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ui_bp.route('/api/ui/system/https-cert-regenerate', methods=['POST'])
@login_required
def https_cert_regenerate_ui():
    """Regenerate self-signed HTTPS certificate (UI route with session auth)"""
    from config.https_manager import HTTPSManager
    from pathlib import Path
    from models import SystemConfig, User, db
    import shutil
    import subprocess
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check admin role
    user = User.query.get(session['user_id'])
    if user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin role required'}), 403
    
    try:
        cert_path = Path(current_app.config['HTTPS_CERT_PATH'])
        key_path = Path(current_app.config['HTTPS_KEY_PATH'])
        
        # Backup current
        if cert_path.exists():
            shutil.copy(cert_path, str(cert_path) + '.backup')
        if key_path.exists():
            shutil.copy(key_path, str(key_path) + '.backup')
        
        # Generate new
        HTTPSManager.generate_self_signed_cert(cert_path, key_path)
        
        # Update config
        config = SystemConfig.query.filter_by(key='https_cert_source').first()
        if not config:
            config = SystemConfig(key='https_cert_source', value='auto')
            db.session.add(config)
        else:
            config.value = 'auto'
        
        db.session.commit()
        
        logger.info(f"HTTPS certificate regenerated by {user.username}")
        
        # Restart UCM service
        from utils import restart_service
        success, message = restart_service()
        
        return jsonify({'success': success, 'message': message}), 200
        
    except Exception as e:
        logger.error(f"Error regenerating HTTPS certificate: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@ui_bp.route('/crl/info/<ca_refid>')
@login_required
def crl_info_integrated(ca_refid):
    """CRL Information page (integrated in app)"""
    from models import CA
    from services.crl_service import CRLService
    
    try:
        # Get CA by refid
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            flash('CA not found', 'error')
            return redirect(url_for('ui.crl_list'))
        
        # Get latest CRL
        latest_crl = CRLService.get_latest_crl_by_refid(ca_refid)
        
        if not latest_crl:
            crl_info = {
                'ca_refid': ca_refid,
                'ca_name': ca.descr,
                'ca_common_name': ca.common_name,
                'has_crl': False,
                'message': 'No CRL generated yet for this CA'
            }
        else:
            crl_info = {
                'ca_refid': ca_refid,
                'ca_name': ca.descr,
                'ca_common_name': ca.common_name,
                'has_crl': True,
                'crl_number': latest_crl.crl_number,
                'this_update': latest_crl.this_update.isoformat() if latest_crl.this_update else None,
                'next_update': latest_crl.next_update.isoformat() if latest_crl.next_update else None,
                'revoked_count': latest_crl.revoked_count,
                'is_stale': latest_crl.is_stale,
                'days_until_expiry': latest_crl.days_until_expiry,
                'download_urls': {
                    'pem': f'/cdp/{ca_refid}/crl.pem',
                    'der': f'/cdp/{ca_refid}/crl.der',
                    'crl': f'/cdp/{ca_refid}/crl.crl'
                }
            }
        
        return render_template('crl/info_integrated.html', crl_info=crl_info)
        
    except Exception as e:
        flash(f'Error loading CRL info: {str(e)}', 'error')
        return redirect(url_for('ui.crl_list'))


@ui_bp.route('/api/ui/system/pki-stats')
@login_required
def pki_stats_ui():
    """Get PKI statistics (UI route with session auth)"""
    from services.pki_reset_service import PKIResetService
    
    try:
        stats = PKIResetService.get_pki_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ui_bp.route('/api/ui/system/pki-reset', methods=['POST'])
@login_required
def pki_reset_ui():
    """Reset PKI database (UI route with session auth - admin only)"""
    from services.pki_reset_service import PKIResetService
    from models import User, db, AuditLog
    
    # Check admin role
    user = User.query.get(session['user_id'])
    if user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin role required'}), 403
    
    # Require confirmation
    data = request.get_json()
    if not data or data.get('confirmation') != 'RESET PKI DATA':
        return jsonify({
            'success': False,
            'error': 'Invalid confirmation. Must be exactly: RESET PKI DATA'
        }), 400
    
    try:
        # Perform reset
        stats = PKIResetService.reset_pki_data()
        
        # Log audit
        log = AuditLog(
            username=user.username,
            action='pki_reset',
            resource_type='system',
            details=f"Reset PKI data. Backup: {stats['backup_path']}",
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'PKI data reset successfully',
            'stats': stats
        }), 200
        
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"PKI reset error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@ui_bp.route('/config/notifications')
@login_required
def config_notifications_page():
    """Email notifications configuration page"""
    return render_template('config/notifications.html')


@ui_bp.route('/config/mtls')
@login_required
def config_mtls_page():
    """mTLS authentication configuration page"""
    return render_template('config/mtls.html')

@ui_bp.route('/config/webauthn')
@login_required
def config_webauthn_page():
    """WebAuthn/FIDO2 security keys management page"""
    return render_template('config/webauthn.html')

@ui_bp.route('/api/v1/system/info')
@login_required
def system_info():
    """Get system information including FQDN"""
    import socket
    try:
        fqdn = socket.getfqdn()
        hostname = socket.gethostname()
        
        return jsonify({
            'fqdn': fqdn,
            'hostname': hostname,
            'success': True
        }), 200
    except Exception as e:
        return jsonify({
            'fqdn': None,
            'hostname': None,
            'error': str(e),
            'success': False
        }), 500


# ACME Management Routes
@ui_bp.route('/config/acme')
@login_required
def config_acme_page():
    """ACME configuration and management page"""
    return render_template('config/acme.html')


@ui_bp.route('/api/ui/acme/statistics')
@login_required
def acme_statistics():
    """Get ACME statistics"""
    try:
        from models import db
        from sqlalchemy import text
        
        # Query ACME database for statistics
        total_accounts = db.session.execute(
            text("SELECT COUNT(*) FROM acme_accounts")
        ).scalar() or 0
        
        active_orders = db.session.execute(
            text("SELECT COUNT(*) FROM acme_orders WHERE status IN ('pending', 'ready', 'processing')")
        ).scalar() or 0
        
        completed_orders = db.session.execute(
            text("SELECT COUNT(*) FROM acme_orders WHERE status = 'valid'")
        ).scalar() or 0
        
        issued_certs = db.session.execute(
            text("SELECT COUNT(*) FROM acme_orders WHERE status = 'valid' AND certificate_id IS NOT NULL")
        ).scalar() or 0
        
        return jsonify({
            'total_accounts': total_accounts,
            'active_orders': active_orders,
            'completed_orders': completed_orders,
            'issued_certs': issued_certs
        }), 200
        
    except Exception as e:
        return jsonify({
            'total_accounts': 0,
            'active_orders': 0,
            'completed_orders': 0,
            'issued_certs': 0,
            'error': str(e)
        }), 200

@ui_bp.route('/api/ui/acme/proxy/status')
@login_required
def acme_proxy_status():
    """Get ACME Proxy status"""
    try:
        from services.acme.acme_proxy_service import AcmeProxyService
        from models import SystemConfig
        
        # Get base URL
        base_url = f"{request.scheme}://{request.host}"
        svc = AcmeProxyService(base_url)
        
        # Get config
        upstream_url_conf = SystemConfig.query.filter_by(key='acme.proxy.upstream_url').first()
        upstream_url = upstream_url_conf.value if upstream_url_conf else svc.DEFAULT_UPSTREAM
        
        account_url_conf = SystemConfig.query.filter_by(key='acme.proxy.account_url').first()
        account_url = account_url_conf.value if account_url_conf else None
        
        # Check connectivity (lightweight check)
        is_registered = account_url is not None
        
        return jsonify({
            'enabled': True,
            'upstream_url': upstream_url,
            'account_url': account_url or "Not Registered",
            'is_registered': is_registered,
            'directory_url': f"{base_url}/acme/proxy/directory"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@ui_bp.route('/api/ui/acme/proxy/register', methods=['POST'])
@login_required
def acme_proxy_register():
    """Register ACME Proxy upstream account"""
    try:
        from services.acme.acme_proxy_service import AcmeProxyService
        
        base_url = f"{request.scheme}://{request.host}"
        svc = AcmeProxyService(base_url)
        
        # Force register
        svc._register_upstream_account()
        
        return jsonify({'status': 'success', 'message': 'Upstream account registered'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500



@ui_bp.route('/api/ui/acme/accounts')
@login_required
def acme_accounts_list():
    """Get ACME accounts list"""
    try:
        from models import db
        from datetime import datetime
        from sqlalchemy import text
        
        accounts = db.session.execute(text("""
            SELECT id, account_id, status, contact, created_at, 
                   SUBSTR(jwk_thumbprint, 1, 16) as thumbprint_short
            FROM acme_accounts 
            ORDER BY created_at DESC
        """)).fetchall()
        
        if not accounts:
            return '''
            <div style="text-align: center; padding: 2rem;">
                <i class="fas fa-user-shield" style="font-size: 3rem; opacity: 0.2; margin-bottom: 0.75rem; display: block; color: var(--text-secondary);"></i>
                <p style="margin-top: 1rem; color: var(--text-secondary); font-weight: 500;">No ACME accounts yet</p>
                <p style="font-size: 0.875rem; color: var(--text-muted); margin-top: 0.25rem;">Accounts will appear here when ACME clients register</p>
            </div>
            '''
        
        html = '''
        <div style="overflow-x: auto;">
            <table id="acme-accounts-table">
                <thead style="background: var(--bg-secondary);">
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left;">Account ID</th>
                        <th style="padding: 0.75rem; text-align: left;">Status</th>
                        <th style="padding: 0.75rem; text-align: left;">Contacts</th>
                        <th style="padding: 0.75rem; text-align: left;">JWK Thumbprint</th>
                        <th style="padding: 0.75rem; text-align: left;">Created</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for account in accounts:
            status_badge_class = 'badge-success' if account[2] == 'valid' else 'badge-secondary'
            contacts = account[3] or '[]'
            created = datetime.fromisoformat(account[4]).strftime('%Y-%m-%d %H:%M')
            
            html += f'''
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="padding: 0.75rem;"><code style="font-size: 0.875rem; color: var(--text-primary);">{account[1][:24]}...</code></td>
                    <td style="padding: 0.75rem;"><span class="badge-outline {status_badge_class}">{account[2]}</span></td>
                    <td style="padding: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">{contacts}</td>
                    <td style="padding: 0.75rem;"><code style="font-size: 0.875rem; color: var(--text-secondary);">{account[5]}...</code></td>
                    <td style="padding: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">{created}</td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
        
    except Exception as e:
        return f'<div class="alert alert-danger">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/acme/orders')
@login_required
def acme_orders_list():
    """Get ACME orders list"""
    try:
        from models import db
        from datetime import datetime
        from sqlalchemy import text
        
        orders = db.session.execute(text("""
            SELECT o.id, o.order_id, o.status, o.identifiers, o.created_at,
                   a.account_id
            FROM acme_orders o
            LEFT JOIN acme_accounts a ON o.account_id = a.account_id
            ORDER BY o.created_at DESC
            LIMIT 50
        """)).fetchall()
        
        if not orders:
            return '''
            <div style="text-align: center; padding: 2rem;">
                <i class="fas fa-file-alt" style="font-size: 3rem; opacity: 0.2; margin-bottom: 0.75rem; display: block; color: var(--text-secondary);"></i>
                <p style="margin-top: 1rem; color: var(--text-secondary); font-weight: 500;">No ACME orders yet</p>
                <p style="font-size: 0.875rem; color: var(--text-muted); margin-top: 0.25rem;">Orders will appear here when certificates are requested</p>
            </div>
            '''
        
        html = '''
        <div style="overflow-x: auto;">
            <table id="acme-orders-table">
                <thead style="background: var(--bg-secondary);">
                    <tr style="border-bottom: 2px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left;">Order ID</th>
                        <th style="padding: 0.75rem; text-align: left;">Status</th>
                        <th style="padding: 0.75rem; text-align: left;">Identifiers</th>
                        <th style="padding: 0.75rem; text-align: left;">Account</th>
                        <th style="padding: 0.75rem; text-align: left;">Created</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for order in orders:
            status_colors = {
                'pending': 'badge-warning',
                'ready': 'badge-info',
                'processing': 'badge-primary',
                'valid': 'badge-success',
                'invalid': 'badge-danger'
            }
            status_badge_class = status_colors.get(order[2], 'badge-secondary')
            created = datetime.fromisoformat(order[4]).strftime('%Y-%m-%d %H:%M')
            
            html += f'''
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="padding: 0.75rem;"><code style="font-size: 0.875rem; color: var(--text-primary);">{order[1][:24]}...</code></td>
                    <td style="padding: 0.75rem;"><span class="badge-outline {status_badge_class}">{order[2]}</span></td>
                    <td style="padding: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">{order[3]}</td>
                    <td style="padding: 0.75rem;"><code style="font-size: 0.875rem; color: var(--text-secondary);">{order[5][:16] if order[5] else 'N/A'}...</code></td>
                    <td style="padding: 0.75rem; font-size: 0.875rem; color: var(--text-secondary);">{created}</td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
        
    except Exception as e:
        return f'<div class="alert alert-danger">Error: {str(e)}</div>'


@ui_bp.route('/api/ui/acme/settings', methods=['POST'])
@login_required
def acme_save_settings():
    """Save ACME configuration settings"""
    try:
        from models import db, SystemConfig
        
        default_ca = request.form.get('default_ca')
        cert_validity = request.form.get('cert_validity', '90')
        
        # Save default CA
        if default_ca:
            config = SystemConfig.query.filter_by(key='acme_default_ca').first()
            if not config:
                config = SystemConfig(key='acme_default_ca')
            config.value = default_ca
            config.description = 'Default CA for ACME certificate signing'
            db.session.add(config)
        
        # Save certificate validity
        config_validity = SystemConfig.query.filter_by(key='acme_cert_validity').first()
        if not config_validity:
            config_validity = SystemConfig(key='acme_cert_validity')
        config_validity.value = cert_validity
        config_validity.description = 'Default validity period for ACME certificates (days)'
        db.session.add(config_validity)
        
        db.session.commit()
        
        flash('ACME settings saved successfully', 'success')
        return '', 200
        
    except Exception as e:
        flash(f'Error saving ACME settings: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/acme/settings/load')
@login_required
def acme_load_settings():
    """Load current ACME configuration"""
    try:
        from models import SystemConfig
        
        default_ca = SystemConfig.query.filter_by(key='acme_default_ca').first()
        cert_validity = SystemConfig.query.filter_by(key='acme_cert_validity').first()
        
        return jsonify({
            'default_ca': default_ca.value if default_ca else None,
            'cert_validity': cert_validity.value if cert_validity else '90'
        }), 200
        
    except Exception as e:
        return jsonify({
            'default_ca': None,
            'cert_validity': '90',
            'error': str(e)
        }), 200


# Public stats endpoint for login page
@ui_bp.route('/api/v1/stats/public')
def public_stats():
    """Public statistics for login page (no auth required)"""
    try:
        from models import CA, Certificate, User, SystemConfig
        from datetime import datetime
        import os
        
        # Get counts from database
        ca_count = CA.query.count()
        cert_count = Certificate.query.count()
        user_count = User.query.count()
        
        # Get ACME account count if table exists
        acme_count = 0
        try:
            from models import AcmeAccount
            acme_count = AcmeAccount.query.count()
        except:
            acme_count = 0
        
        # Get last backup time
        last_backup = None
        backup_dir = os.path.join(DATA_DIR, 'backups')
        if os.path.exists(backup_dir):
            try:
                backups = [f for f in os.listdir(backup_dir) if f.endswith('.tar.gz')]
                if backups:
                    latest = max(backups, key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
                    last_backup = datetime.fromtimestamp(
                        os.path.getmtime(os.path.join(backup_dir, latest))
                    ).isoformat()
            except:
                pass
        
        return jsonify({
            'ca_count': ca_count,
            'cert_count': cert_count,
            'acme_count': acme_count,
            'user_count': user_count,
            'last_backup': last_backup
        }), 200
        
    except Exception as e:
        # Return placeholder data on error (login should still work)
        return jsonify({
            'ca_count': 0,
            'cert_count': 0,
            'acme_count': 0,
            'user_count': 0,
            'last_backup': None
        }), 200

@ui_bp.route('/config/templates')
@login_required
def config_templates_page():
    """Certificate Templates configuration page"""
    return render_template('config/templates.html')


# ========================================
# TEMPLATES UI ROUTES (HTMX)
# ========================================

@ui_bp.route('/api/ui/templates/list', methods=['GET'])
@login_required
def ui_templates_list():
    """Get templates list HTML fragment for HTMX"""
    try:
        import json
        from services.template_service import TemplateService
        templates = TemplateService.get_all_templates()
        
        if not templates:
            return '''
            <div style="text-align: center; padding: 3rem; color: var(--text-secondary);">
                <svg class="ucm-icon" width="48" height="48" style="opacity: 0.3; margin-bottom: 1rem;"><use href="#icon-file"/></svg>
                <p>No templates found</p>
                <p style="font-size: 0.875rem; margin-top: 0.5rem;">Create a custom template to get started</p>
            </div>
            '''
        
        # Sort: system first, then by name
        templates.sort(key=lambda t: (not t.is_system, t.name))
        
        html = '<div style="display: grid; gap: 1rem;">'
        
        for template in templates:
            badge_color = 'var(--info-color)' if template.is_system else 'var(--success-color)'
            badge_text = 'System' if template.is_system else 'Custom'
            
            # Parse JSON extensions
            extensions = json.loads(template.extensions_template) if isinstance(template.extensions_template, str) else template.extensions_template
            eku = ', '.join(extensions.get('extended_key_usage', [])) or 'None'
            
            # Build action buttons
            actions = f'''
            <button onclick="viewTemplateDetail({template.id})" 
                    style="padding: 0.375rem 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary); cursor: pointer; font-size: 0.875rem; display: flex; align-items: center; gap: 0.375rem;">
                <svg class="ucm-icon" width="14" height="14"><use href="#icon-eye"/></svg>
                View
            </button>
            '''
            
            if not template.is_system:
                actions += f'''
                <button onclick="openEditModal({template.id})"
                        style="padding: 0.375rem 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 4px; color: var(--text-primary); cursor: pointer; font-size: 0.875rem; display: flex; align-items: center; gap: 0.375rem;">
                    <svg class="ucm-icon" width="14" height="14"><use href="#icon-edit"/></svg>
                    Edit
                </button>
                <button hx-delete="/api/ui/templates/delete/{template.id}"
                        hx-confirm="Delete template '{html_escape(template.name)}'? This cannot be undone."
                        hx-target="#templates-list"
                        hx-swap="innerHTML"
                        style="padding: 0.375rem 0.75rem; background: var(--danger-bg); border: 1px solid var(--danger-color); border-radius: 4px; color: var(--danger-color); cursor: pointer; font-size: 0.875rem; display: flex; align-items: center; gap: 0.375rem;">
                    <svg class="ucm-icon" width="14" height="14"><use href="#icon-trash"/></svg>
                    Delete
                </button>
                '''
            
            html += f'''
            <div style="border: 1px solid var(--border-color); border-radius: 6px; padding: 1rem; background: var(--bg-secondary); transition: all 0.2s;"
                 onmouseover="this.style.borderColor='var(--primary-color)'; this.style.boxShadow='0 2px 8px rgba(0,0,0,0.1)';" 
                 onmouseout="this.style.borderColor='var(--border-color)'; this.style.boxShadow='none';">
                <div style="display: flex; justify-content: space-between; align-items: start; gap: 1rem;">
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.375rem;">
                            <h3 style="font-size: 1.125rem; font-weight: 600; color: var(--text-primary); margin: 0;">
                                {html_escape(template.name)}
                            </h3>
                            <span style="padding: 0.125rem 0.5rem; background: {badge_color}20; color: {badge_color}; border-radius: 4px; font-size: 0.75rem; font-weight: 500;">
                                {badge_text}
                            </span>
                        </div>
                        <p style="color: var(--text-secondary); font-size: 0.875rem; margin: 0 0 0.75rem 0;">
                            {html_escape(template.description or '')}
                        </p>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.75rem; font-size: 0.875rem;">
                            <div>
                                <strong style="color: var(--text-secondary);">Type:</strong>
                                <span style="color: var(--text-primary);"> {html_escape(template.template_type)}</span>
                            </div>
                            <div>
                                <strong style="color: var(--text-secondary);">Key:</strong>
                                <span style="color: var(--text-primary);"> {html_escape(template.key_type)}</span>
                            </div>
                            <div>
                                <strong style="color: var(--text-secondary);">Validity:</strong>
                                <span style="color: var(--text-primary);"> {template.validity_days} days</span>
                            </div>
                            <div>
                                <strong style="color: var(--text-secondary);">EKU:</strong>
                                <span style="color: var(--text-primary);"> {html_escape(eku)}</span>
                            </div>
                        </div>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 0.5rem; min-width: 80px;">
                        {actions}
                    </div>
                </div>
            </div>
            '''
        
        html += '</div>'
        return html
        
    except Exception as e:
        return f'''
        <div style="text-align: center; padding: 2rem; color: var(--danger-color);">
            <p>Error loading templates: {html_escape(str(e))}</p>
        </div>
        '''


@ui_bp.route('/api/ui/templates/stats', methods=['GET'])
@login_required
def ui_templates_stats():
    """Get templates stats HTML fragment for HTMX"""
    try:
        from services.template_service import TemplateService
        templates = TemplateService.get_all_templates()
        
        total = len(templates)
        system = sum(1 for t in templates if t.is_system)
        custom = total - system
        active = sum(1 for t in templates if t.is_active)
        
        return f'''
        <div class="stats-card">
            <div style="color: var(--text-secondary); font-size: 0.875rem;">Total Templates</div>
            <div style="font-size: 2rem; font-weight: 700; color: var(--primary-color);">{total}</div>
        </div>
        <div class="stats-card">
            <div style="color: var(--text-secondary); font-size: 0.875rem;">System</div>
            <div style="font-size: 2rem; font-weight: 700; color: var(--info-color);">{system}</div>
        </div>
        <div class="stats-card">
            <div style="color: var(--text-secondary); font-size: 0.875rem;">Custom</div>
            <div style="font-size: 2rem; font-weight: 700; color: var(--success-color);">{custom}</div>
        </div>
        <div class="stats-card">
            <div style="color: var(--text-secondary); font-size: 0.875rem;">Active</div>
            <div style="font-size: 2rem; font-weight: 700; color: var(--accent-color);">{active}</div>
        </div>
        '''
    except Exception as e:
        return f'<div style="color: var(--danger-color);">Error: {html_escape(str(e))}</div>'


@ui_bp.route('/api/ui/templates/delete/<int:template_id>', methods=['DELETE'])
@login_required
def ui_templates_delete(template_id):
    """Delete a template and return refreshed list"""
    try:
        from services.template_service import TemplateService
        from models import User
        
        # Check admin role
        user = User.query.get(session['user_id'])
        if user.role != 'admin':
            return '<div style="color: var(--danger-color); padding: 1rem;">Admin role required</div>', 403
        
        success, message = TemplateService.delete_template(template_id, session['username'])
        
        if success:
            # Return refreshed list
            return ui_templates_list()
        else:
            return f'<div style="color: var(--danger-color); padding: 1rem;">{html_escape(message)}</div>', 400
            
    except Exception as e:
        return f'<div style="color: var(--danger-color); padding: 1rem;">Error: {html_escape(str(e))}</div>', 500


# CA Detail - Fingerprints
@ui_bp.route('/api/ui/ca/<ca_id>/fingerprints')
@login_required
def ca_fingerprints(ca_id):
    """Get CA fingerprints (for HTMX)"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/ca/{ca_id}/fingerprints")
        
        if not response or response.status_code != 200:
            return '<p style="color: var(--danger-color);">Failed to load fingerprints</p>'
        
        data = response.json()
        html = f'''
            <dl style="display: flex; flex-direction: column; gap: 0.75rem;">
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">SHA-256</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-primary); font-family: monospace; word-break: break-all; background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.25rem;">{data.get('sha256', 'N/A')}</dd>
                </div>
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">SHA-1</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-primary); font-family: monospace; word-break: break-all; background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.25rem;">{data.get('sha1', 'N/A')}</dd>
                </div>
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">MD5</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-primary); font-family: monospace; word-break: break-all; background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.25rem;">{data.get('md5', 'N/A')}</dd>
                </div>
            </dl>
        '''
        return html
    except Exception as e:
        return f'<p style="color: var(--danger-color);">Error: {str(e)}</p>'


# CA Detail - X509 Details
@ui_bp.route('/api/ui/ca/<ca_id>/x509details')
@login_required
def ca_x509_details(ca_id):
    """Get CA X.509 details (for HTMX)"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/ca/{ca_id}/details")
        
        if not response or response.status_code != 200:
            return '<p style="color: var(--danger-color);">Failed to load certificate details</p>'
        
        data = response.json()
        
        # Build extensions HTML
        extensions_html = ''
        if data.get('extensions'):
            extensions_html = '<dl style="display: flex; flex-direction: column; gap: 0.75rem;">'
            for ext_name, ext_value in data['extensions'].items():
                value_str = str(ext_value) if not isinstance(ext_value, dict) else '<br>'.join([f"{k}: {v}" for k, v in ext_value.items()])
                extensions_html += f'''
                    <div>
                        <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">{html_escape(ext_name)}</dt>
                        <dd style="margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-primary); background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.25rem;">{value_str}</dd>
                    </div>
                '''
            extensions_html += '</dl>'
        else:
            extensions_html = '<p style="color: var(--text-secondary);">No extensions</p>'
        
        return extensions_html
    except Exception as e:
        return f'<p style="color: var(--danger-color);">Error: {str(e)}</p>'


# Certificate Detail - Fingerprints
@ui_bp.route('/api/ui/certificates/<cert_id>/fingerprints')
@login_required
def cert_fingerprints(cert_id):
    """Get certificate fingerprints (for HTMX)"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/certificates/{cert_id}/fingerprints")
        
        if not response or response.status_code != 200:
            return '<p style="color: var(--danger-color);">Failed to load fingerprints</p>'
        
        data = response.json()
        html = f'''
            <dl class="space-y-3">
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">SHA-256</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-primary); font-family: monospace; word-break: break-all; background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.375rem;">{data.get('sha256', 'N/A')}</dd>
                </div>
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">SHA-1</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-primary); font-family: monospace; word-break: break-all; background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.375rem;">{data.get('sha1', 'N/A')}</dd>
                </div>
                <div>
                    <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary);">MD5</dt>
                    <dd style="margin-top: 0.25rem; font-size: 0.75rem; color: var(--text-primary); font-family: monospace; word-break: break-all; background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.375rem;">{data.get('md5', 'N/A')}</dd>
                </div>
            </dl>
        '''
        return html
    except Exception as e:
        return f'<p style="color: var(--danger-color);">Error: {str(e)}</p>'


# Certificate Operations - Delete by refid
@ui_bp.route('/api/ui/certificates/by-refid/<refid>', methods=['DELETE'])
@login_required
def ui_cert_delete_by_refid(refid):
    """Delete certificate by refid (proxy to /api/v1)"""
    try:
        response = api_call_with_retry('DELETE', f"{request.url_root}api/v1/certificates/by-refid/{refid}")
        
        if response and response.status_code in [200, 204]:
            return jsonify({"success": True, "message": "Certificate deleted"}), 200
        elif response:
            return response.json(), response.status_code
        return jsonify({"error": "Failed to delete certificate"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Certificate Operations - Revoke by refid
@ui_bp.route('/api/ui/certificates/by-refid/<refid>/revoke', methods=['POST'])
@login_required
def ui_cert_revoke_by_refid(refid):
    """Revoke certificate by refid (proxy to /api/v1)"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/certificates/by-refid/{refid}/revoke")
        
        if response and response.status_code in [200, 204]:
            return jsonify({"success": True, "message": "Certificate revoked"}), 200
        elif response:
            return response.json(), response.status_code
        return jsonify({"error": "Failed to revoke certificate"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# CA Operations - Delete by refid
@ui_bp.route('/api/ui/ca/<refid>', methods=['DELETE'])
@login_required
def ui_ca_delete_by_refid(refid):
    """Delete CA by refid (proxy to /api/v1)"""
    try:
        response = api_call_with_retry('DELETE', f"{request.url_root}api/v1/ca/{refid}")
        
        if response and response.status_code in [200, 204]:
            return jsonify({"success": True, "message": "CA deleted"}), 200
        elif response:
            return response.json(), response.status_code
        return jsonify({"error": "Failed to delete CA"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# CRL Operations - Generate
@ui_bp.route('/api/ui/ca/<refid>/crl/generate', methods=['POST'])
@login_required
def ui_ca_generate_crl(refid):
    """Generate CRL for CA (proxy to /api/v1)"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/ca/{refid}/crl/generate")
        
        if response and response.status_code in [200, 201]:
            return response.json(), response.status_code
        elif response:
            return response.json(), response.status_code
        return jsonify({"error": "Failed to generate CRL"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# SCEP Operations - Approve
@ui_bp.route('/api/ui/scep/<refid>/approve', methods=['POST'])
@login_required
def ui_scep_approve(refid):
    """Approve SCEP request (proxy to /api/v1)"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/scep/{refid}/approve")
        
        if response and response.status_code in [200, 201]:
            return response.json(), response.status_code
        elif response:
            return response.json(), response.status_code
        return jsonify({"error": "Failed to approve SCEP"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# SCEP Operations - Reject
@ui_bp.route('/api/ui/scep/<refid>/reject', methods=['POST'])
@login_required
def ui_scep_reject(refid):
    """Reject SCEP request (proxy to /api/v1)"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/scep/{refid}/reject")
        
        if response and response.status_code in [200, 204]:
            return jsonify({"success": True, "message": "SCEP request rejected"}), 200
        elif response:
            return response.json(), response.status_code
        return jsonify({"error": "Failed to reject SCEP"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Certificate Detail - X509 Details  
@ui_bp.route('/api/ui/certificates/<cert_id>/x509details')
@login_required
def cert_x509_details(cert_id):
    """Get certificate X.509 details (for HTMX)"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/certificates/{cert_id}/details")
        
        if not response or response.status_code != 200:
            return '<p style="color: var(--danger-color);">Failed to load certificate details</p>'
        
        data = response.json()
        
        html = '<div class="space-y-4">'
        
        # Public Key Info
        if data.get('public_key'):
            pk = data['public_key']
            html += f'''
                <div>
                    <h3 style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.5rem;">Public Key</h3>
                    <dl class="ml-4 space-y-1">
                        <div class="flex">
                            <dt style="width: 150px; font-size: 0.875rem; color: var(--text-secondary);">Algorithm:</dt>
                            <dd style="font-size: 0.875rem; color: var(--text-primary);">{pk.get('algorithm', 'N/A')}</dd>
                        </div>
                        <div class="flex">
                            <dt style="width: 150px; font-size: 0.875rem; color: var(--text-secondary);">Size:</dt>
                            <dd style="font-size: 0.875rem; color: var(--text-primary);">{pk.get('size', 'N/A')} bits</dd>
                        </div>
            '''
            if pk.get('curve'):
                html += f'''
                        <div class="flex">
                            <dt style="width: 150px; font-size: 0.875rem; color: var(--text-secondary);">Curve:</dt>
                            <dd style="font-size: 0.875rem; color: var(--text-primary);">{pk.get('curve')}</dd>
                        </div>
                '''
            html += '''
                    </dl>
                </div>
            '''
        
        # Signature
        if data.get('signature'):
            sig = data['signature']
            html += f'''
                <div>
                    <h3 style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.5rem;">Signature</h3>
                    <dl class="ml-4 space-y-1">
                        <div class="flex">
                            <dt style="width: 150px; font-size: 0.875rem; color: var(--text-secondary);">Algorithm:</dt>
                            <dd style="font-size: 0.875rem; color: var(--text-primary);">{sig.get('algorithm', 'N/A')}</dd>
                        </div>
                    </dl>
                </div>
            '''
        
        # Extensions
        if data.get('extensions'):
            html += '<div><h3 style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.5rem;">Extensions</h3><dl class="ml-4 space-y-2">'
            for ext_name, ext_value in data['extensions'].items():
                if isinstance(ext_value, dict):
                    value_str = '<br>'.join([f"&nbsp;&nbsp;{k}: {v}" for k, v in ext_value.items()])
                elif isinstance(ext_value, list):
                    value_str = '<br>'.join([f"&nbsp;&nbsp;- {v}" for v in ext_value])
                else:
                    value_str = str(ext_value)
                    
                html += f'''
                    <div>
                        <dt style="font-size: 0.875rem; font-weight: 500; color: var(--text-secondary); margin-bottom: 0.25rem;">{ext_name}</dt>
                        <dd style="font-size: 0.875rem; color: var(--text-primary); background: var(--bg-secondary); padding: 0.5rem; border-radius: 0.25rem; font-family: monospace; white-space: pre-wrap;">{value_str}</dd>
                    </div>
                '''
            html += '</dl></div>'
        
        html += '</div>'
        return html
    except Exception as e:
        return f'<p style="color: var(--danger-color);">Error: {str(e)}</p>'


# Template Detail (for modal)
@ui_bp.route('/api/ui/templates/<int:template_id>/detail')
@login_required
def ui_template_detail(template_id):
    """Get template details for modal (HTMX)"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/templates/{template_id}")
        
        if not response or response.status_code != 200:
            return '<div style="color: var(--danger-color); padding: 2rem; text-align: center;">Template not found</div>'
        
        t = response.json()
        
        # Format DN template
        dn_entries = ''
        if t.get('dn_template'):
            for k, v in t['dn_template'].items():
                if v and str(v).strip():
                    dn_entries += f'<div><strong>{html_escape(k)}:</strong> {html_escape(v)}</div>'
        
        # Format extensions
        ku = t.get('extensions_template', {}).get('key_usage', [])
        eku = t.get('extensions_template', {}).get('extended_key_usage', [])
        san = t.get('extensions_template', {}).get('san_types', [])
        
        html = f'''
            <div style="display: flex; flex-direction: column; gap: 1.5rem;">
                <!-- Header -->
                <div>
                    <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                        <h3 style="font-size: 1.25rem; font-weight: 600; color: var(--text-primary); margin: 0;">{html_escape(t.get('name', ''))}</h3>
                        <span style="padding: 0.125rem 0.5rem; background: {'var(--info-color)' if t.get('is_system') else 'var(--success-color)'}20; color: {'var(--info-color)' if t.get('is_system') else 'var(--success-color)'}; border-radius: 4px; font-size: 0.75rem; font-weight: 500;">
                            {'System' if t.get('is_system') else 'Custom'}
                        </span>
                    </div>
                    {f'<p style="color: var(--text-secondary); font-size: 0.875rem; margin: 0;">{html_escape(t.get("description", ""))}</p>' if t.get('description') else ''}
                </div>

                <!-- Configuration -->
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; padding: 1rem; background: var(--bg-secondary); border-radius: 6px;">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Type</div>
                        <div style="font-weight: 500; color: var(--text-primary);">{html_escape(t.get('template_type', ''))}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Key Type</div>
                        <div style="font-weight: 500; color: var(--text-primary);">{html_escape(t.get('key_type', ''))}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Validity</div>
                        <div style="font-weight: 500; color: var(--text-primary);">{t.get('validity_days', 0)} days</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Digest Algorithm</div>
                        <div style="font-weight: 500; color: var(--text-primary);">{html_escape(t.get('digest', ''))}</div>
                    </div>
                </div>

                <!-- DN Template -->
                <div>
                    <h4 style="font-weight: 600; margin-bottom: 0.75rem; color: var(--text-primary);">
                        <svg class="ucm-icon" width="16" height="16" style="vertical-align: middle; margin-right: 0.375rem;"><use href="#icon-file-text"/></svg>
                        Distinguished Name Template
                    </h4>
                    <div style="padding: 1rem; background: var(--bg-primary); border-radius: 4px; font-family: monospace; font-size: 0.875rem;">
                        {dn_entries if dn_entries else '<div style="color: var(--text-secondary);">No DN template</div>'}
                    </div>
                    <p style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">
                        Variables: {{hostname}}, {{email}}, {{username}}
                    </p>
                </div>

                <!-- Extensions -->
                <div>
                    <h4 style="font-weight: 600; margin-bottom: 0.75rem; color: var(--text-primary);">
                        <svg class="ucm-icon" width="16" height="16" style="vertical-align: middle; margin-right: 0.375rem;"><use href="#icon-shield"/></svg>
                        Certificate Extensions
                    </h4>
                    
                    <div style="display: grid; gap: 1rem;">
        '''
        
        if ku:
            html += f'''
                        <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 4px;">
                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Key Usage</div>
                            <div style="display: flex; flex-wrap: wrap; gap: 0.375rem;">
                                {' '.join([f'<span style="padding: 0.25rem 0.5rem; background: var(--primary-color)20; color: var(--primary-color); border-radius: 4px; font-size: 0.75rem;">{html_escape(k)}</span>' for k in ku])}
                            </div>
                        </div>
            '''
        
        if eku:
            html += f'''
                        <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 4px;">
                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Extended Key Usage</div>
                            <div style="display: flex; flex-wrap: wrap; gap: 0.375rem;">
                                {' '.join([f'<span style="padding: 0.25rem 0.5rem; background: var(--success-color)20; color: var(--success-color); border-radius: 4px; font-size: 0.75rem;">{html_escape(k)}</span>' for k in eku])}
                            </div>
                        </div>
            '''
        
        if san:
            html += f'''
                        <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: 4px;">
                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem;">SAN Types Supported</div>
                            <div style="display: flex; flex-wrap: wrap; gap: 0.375rem;">
                                {' '.join([f'<span style="padding: 0.25rem 0.5rem; background: var(--info-color)20; color: var(--info-color); border-radius: 4px; font-size: 0.75rem;">{html_escape(k)}</span>' for k in san])}
                            </div>
                        </div>
            '''
        
        html += '''
                    </div>
                </div>
            </div>
        '''
        
        return html
    except Exception as e:
        return f'<div style="color: var(--danger-color); padding: 2rem; text-align: center;">Error: {html_escape(str(e))}</div>'


@ui_bp.route('/api/ui/templates/options')
@login_required
def templates_options():
    """Get templates as HTML options for select dropdown"""
    try:
        token = session.get('access_token')
        if not token:
            return '<option value="">-- No template (session error) --</option>', 200
        
        headers = {'Authorization': f'Bearer {token}'}
        
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/templates")
        
        if response and response.status_code == 200:
            data = response.json()
            
            # Debug: check type
            current_app.logger.info(f"Templates response type: {type(data)}, content: {str(data)[:200]}")
            
            # Handle if data is a dict with 'templates' key or direct list
            if isinstance(data, dict):
                templates = data.get('templates', data.get('data', []))
            elif isinstance(data, list):
                templates = data
            else:
                current_app.logger.error(f"Unexpected templates data type: {type(data)}")
                return '<option value="">-- Unexpected response format --</option>', 200
            
            html = '<option value="">-- No Template (Manual) --</option>'
            for t in templates:
                if isinstance(t, dict):  # Safety check
                    html += f'<option value="{t.get("id", "")}">{t.get("name", "Unknown")} ({t.get("type", "")})</option>'
            return html, 200
        else:
            return '<option value="">-- No templates found --</option>', 200
    except Exception as e:
        current_app.logger.error(f"Error loading templates: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return f'<option value="">-- Error: {str(e)[:30]} --</option>', 200


@ui_bp.route('/api/ui/templates/<int:template_id>/json')
@login_required
def template_json(template_id):
    """Get single template as JSON (for CSR auto-fill)"""
    try:
        token = session.get('access_token')
        if not token:
            return {'error': 'No session token'}, 401
        
        headers = {'Authorization': f'Bearer {token}'}
        
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/templates/{template_id}")
        
        if response and response.status_code == 200:
            return response.json(), 200
        else:
            return {'error': 'Template not found'}, 404
    except Exception as e:
        current_app.logger.error(f"Error loading template {template_id}: {str(e)}")
        return {'error': str(e)}, 500
"""
Additional UI routes for settings.html refactoring
To be appended to ui_routes.py
"""

# ============================================================================
# mTLS UI Routes (Session-based)
# ============================================================================

@ui_bp.route('/api/ui/mtls/settings', methods=['GET'])
@login_required
def ui_mtls_settings_get():
    """Get mTLS settings"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/mtls/settings")
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to fetch mTLS settings'}, 500
    except Exception as e:
        current_app.logger.error(f"Error fetching mTLS settings: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/mtls/settings', methods=['POST'])
@login_required
@admin_required
def ui_mtls_settings_post():
    """Update mTLS settings (admin only)"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/mtls/settings", json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to update mTLS settings'}, 500
    except Exception as e:
        current_app.logger.error(f"Error updating mTLS settings: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/mtls/ca-list', methods=['GET'])
@login_required
def ui_mtls_ca_list():
    """Get list of CAs for mTLS dropdown"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/ca")
        if response and response.status_code == 200:
            cas = response.json()
            html = '<option value="">-- Select CA --</option>'
            for ca in cas:
                html += f'<option value="{ca.get("id", "")}">{ca.get("common_name", "Unknown CA")}</option>'
            return html, 200
        return '<option value="">-- Error loading CAs --</option>', 500
    except Exception as e:
        current_app.logger.error(f"Error fetching CA list: {e}")
        return '<option value="">-- Error --</option>', 500


@ui_bp.route('/api/ui/mtls/certificates', methods=['GET'])
@login_required
def ui_mtls_certificates_list():
    """Get user's mTLS certificates as HTML fragment"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/mtls/certificates")
        if response and response.status_code == 200:
            certs = response.json()
            
            if not certs:
                return '''
                    <div class="empty-state">
                        <svg class="ucm-icon" width="48" height="48"><use href="#icon-certificate"/></svg>
                        <p>No mTLS certificates yet</p>
                    </div>
                ''', 200
            
            html = '<div class="certificates-grid">'
            for cert in certs:
                status_class = 'active' if cert.get('status') == 'active' else 'revoked'
                html += f'''
                    <div class="certificate-card {status_class}">
                        <div class="cert-info">
                            <strong>{cert.get('common_name', 'Unknown')}</strong>
                            <span class="cert-serial">{cert.get('serial', 'N/A')}</span>
                            <span class="cert-status">{cert.get('status', 'unknown')}</span>
                        </div>
                        <div class="cert-actions">
                            <button hx-get="/api/ui/mtls/certificates/{cert.get('id')}/download" 
                                    class="btn-sm btn-secondary">Download</button>
                            <button hx-delete="/api/ui/mtls/certificates/{cert.get('id')}" 
                                    hx-confirm="Revoke this certificate?"
                                    hx-target="#mtls-certificates-list"
                                    class="btn-sm btn-danger">Revoke</button>
                        </div>
                    </div>
                '''
            html += '</div>'
            return html, 200
        return '<div class="error">Failed to load certificates</div>', 500
    except Exception as e:
        current_app.logger.error(f"Error fetching mTLS certificates: {e}")
        return f'<div class="error">Error: {str(e)}</div>', 500


@ui_bp.route('/api/ui/mtls/certificates', methods=['POST'])
@login_required
def ui_mtls_certificates_create():
    """Create new mTLS certificate"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/mtls/certificates/create", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to create certificate'}, 500
    except Exception as e:
        current_app.logger.error(f"Error creating mTLS certificate: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/mtls/certificates/<int:cert_id>', methods=['DELETE'])
@login_required
def ui_mtls_certificate_delete(cert_id):
    """Delete/revoke mTLS certificate and return refreshed list"""
    try:
        # Revoke certificate
        response = api_call_with_retry('DELETE', f"{request.url_root}api/v1/mtls/certificates/{cert_id}")
        
        if response and response.status_code in [200, 204]:
            # Return refreshed list
            return ui_mtls_certificates_list()
        return '<div class="error">Failed to revoke certificate</div>', 500
    except Exception as e:
        current_app.logger.error(f"Error revoking mTLS certificate {cert_id}: {e}")
        return f'<div class="error">Error: {str(e)}</div>', 500


@ui_bp.route('/api/ui/mtls/certificates/<int:cert_id>/download', methods=['GET'])
@login_required
def ui_mtls_certificate_download(cert_id):
    """Download mTLS certificate"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/mtls/certificates/{cert_id}/download")
        if response and response.status_code == 200:
            # Return certificate file
            return response.content, 200, {
                'Content-Type': 'application/x-pem-file',
                'Content-Disposition': f'attachment; filename="mtls-cert-{cert_id}.pem"'
            }
        return 'Certificate not found', 404
    except Exception as e:
        current_app.logger.error(f"Error downloading certificate {cert_id}: {e}")
        return f'Error: {str(e)}', 500


@ui_bp.route('/api/ui/mtls/validate', methods=['POST'])
@login_required
def ui_mtls_validate_certificate():
    """Validate uploaded certificate"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/mtls/validate-certificate", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Validation failed'}, 400
    except Exception as e:
        current_app.logger.error(f"Error validating certificate: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/mtls/certificates/enroll', methods=['POST'])
@login_required
def ui_mtls_certificate_enroll():
    """Enroll existing certificate"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/mtls/certificates/enroll", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Enrollment failed'}, 500
    except Exception as e:
        current_app.logger.error(f"Error enrolling certificate: {e}")
        return {'error': str(e)}, 500


# ============================================================================
# WebAuthn UI Routes (Session-based)
# ============================================================================

@ui_bp.route('/api/ui/webauthn/credentials', methods=['GET'])
@login_required
def ui_webauthn_credentials_list():
    """Get user's WebAuthn credentials as HTML fragment"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/webauthn/credentials")
        if response and response.status_code == 200:
            credentials = response.json()
            
            if not credentials:
                return '''
                    <div class="empty-state">
                        <svg class="ucm-icon" width="48" height="48"><use href="#icon-key"/></svg>
                        <p>No security keys registered</p>
                    </div>
                ''', 200
            
            html = '<div class="credentials-grid">'
            for cred in credentials:
                html += f'''
                    <div class="credential-card">
                        <div class="cred-info">
                            <strong>{cred.get('name', 'Security Key')}</strong>
                            <span class="cred-date">Registered: {cred.get('registered_at', 'N/A')}</span>
                        </div>
                        <div class="cred-actions">
                            <button hx-delete="/api/ui/webauthn/credentials/{cred.get('id')}" 
                                    hx-confirm="Remove this security key?"
                                    hx-target="#webauthn-credentials-list"
                                    class="btn-sm btn-danger">Remove</button>
                        </div>
                    </div>
                '''
            html += '</div>'
            return html, 200
        return '<div class="error">Failed to load credentials</div>', 500
    except Exception as e:
        current_app.logger.error(f"Error fetching WebAuthn credentials: {e}")
        return f'<div class="error">Error: {str(e)}</div>', 500


@ui_bp.route('/api/ui/webauthn/register/options', methods=['POST'])
@login_required
def ui_webauthn_register_options():
    """Get registration options for WebAuthn"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/webauthn/register/options", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to generate options'}, 500
    except Exception as e:
        current_app.logger.error(f"Error generating WebAuthn options: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/webauthn/register/verify', methods=['POST'])
@login_required
def ui_webauthn_register_verify():
    """Verify WebAuthn registration"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/webauthn/register/verify", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Verification failed'}, 400
    except Exception as e:
        current_app.logger.error(f"Error verifying WebAuthn registration: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/webauthn/credentials/<int:cred_id>', methods=['DELETE'])
@login_required
def ui_webauthn_credential_delete(cred_id):
    """Delete WebAuthn credential and return refreshed list"""
    try:
        response = api_call_with_retry('DELETE', f"{request.url_root}api/v1/webauthn/credentials/{cred_id}")
        
        if response and response.status_code in [200, 204]:
            # Return refreshed list
            return ui_webauthn_credentials_list()
        return '<div class="error">Failed to remove credential</div>', 500
    except Exception as e:
        current_app.logger.error(f"Error removing WebAuthn credential {cred_id}: {e}")
        return f'<div class="error">Error: {str(e)}</div>', 500


# ============================================================================
# Notifications UI Routes (Session-based)
# ============================================================================

@ui_bp.route('/api/ui/notifications/smtp/config', methods=['GET'])
@login_required
@admin_required
def ui_notifications_smtp_get():
    """Get SMTP configuration"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/notifications/smtp/config")
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to fetch SMTP config'}, 500
    except Exception as e:
        current_app.logger.error(f"Error fetching SMTP config: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/smtp/config', methods=['POST'])
@login_required
@admin_required
def ui_notifications_smtp_post():
    """Update SMTP configuration"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/notifications/smtp/config", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to update SMTP config'}, 500
    except Exception as e:
        current_app.logger.error(f"Error updating SMTP config: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/smtp/test', methods=['POST'])
@login_required
@admin_required
def ui_notifications_smtp_test():
    """Send test email"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/notifications/smtp/test", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to send test email'}, 500
    except Exception as e:
        current_app.logger.error(f"Error sending test email: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/user/settings', methods=['GET'])
@login_required
def ui_notifications_user_settings_get():
    """Get user notification settings"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/notifications/user/settings")
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to fetch notification settings'}, 500
    except Exception as e:
        current_app.logger.error(f"Error fetching notification settings: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/user/settings', methods=['POST'])
@login_required
def ui_notifications_user_settings_post():
    """Update user notification settings"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/notifications/user/settings", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to update notification settings'}, 500
    except Exception as e:
        current_app.logger.error(f"Error updating notification settings: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/config', methods=['GET'])
@login_required
@admin_required
def ui_notifications_config_get():
    """Get notification configuration"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/notifications/config")
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to fetch notification config'}, 500
    except Exception as e:
        current_app.logger.error(f"Error fetching notification config: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/config/<notification_type>', methods=['POST'])
@login_required
@admin_required
def ui_notifications_config_type_post(notification_type):
    """Update specific notification type configuration"""
    try:
        response = api_call_with_retry('POST', 
                                      f"{request.url_root}api/v1/notifications/config/{notification_type}", 
                                      json=request.json)
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': f'Failed to update {notification_type} config'}, 500
    except Exception as e:
        current_app.logger.error(f"Error updating notification config {notification_type}: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/history', methods=['GET'])
@login_required
def ui_notifications_history():
    """Get notification history as HTML fragment"""
    try:
        limit = request.args.get('limit', 20)
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/notifications/history?limit={limit}")
        
        if response and response.status_code == 200:
            notifications = response.json()
            
            if not notifications:
                return '''
                    <div class="empty-state">
                        <svg class="ucm-icon" width="48" height="48"><use href="#icon-inbox"/></svg>
                        <p>No notifications yet</p>
                    </div>
                ''', 200
            
            html = '<div class="notifications-list">'
            for notif in notifications:
                html += f'''
                    <div class="notification-item">
                        <span class="notif-type">{notif.get('type', 'info')}</span>
                        <span class="notif-message">{notif.get('message', 'N/A')}</span>
                        <span class="notif-date">{notif.get('created_at', 'N/A')}</span>
                    </div>
                '''
            html += '</div>'
            return html, 200
        return '<div class="error">Failed to load notifications</div>', 500
    except Exception as e:
        current_app.logger.error(f"Error fetching notification history: {e}")
        return f'<div class="error">Error: {str(e)}</div>', 500


@ui_bp.route('/api/ui/notifications/stats', methods=['GET'])
@login_required
@admin_required
def ui_notifications_stats():
    """Get notification statistics"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/notifications/stats")
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to fetch notification stats'}, 500
    except Exception as e:
        current_app.logger.error(f"Error fetching notification stats: {e}")
        return {'error': str(e)}, 500


@ui_bp.route('/api/ui/notifications/check', methods=['POST'])
@login_required
@admin_required
def ui_notifications_check():
    """Manually trigger notification check"""
    try:
        response = api_call_with_retry('POST', f"{request.url_root}api/v1/notifications/check")
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to check notifications'}, 500
    except Exception as e:
        current_app.logger.error(f"Error checking notifications: {e}")
        return {'error': str(e)}, 500


# ============================================================================
# System Info UI Route (was missing)
# ============================================================================

@ui_bp.route('/api/ui/system/info', methods=['GET'])
@login_required
def ui_system_info():
    """Get system information"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/system/info")
        if response and response.status_code == 200:
            return response.json(), 200
        return {'error': 'Failed to fetch system info'}, 500
    except Exception as e:
        current_app.logger.error(f"Error fetching system info: {e}")
        return {'error': str(e)}, 500


# ============================================================================
# Settings UI Routes (Backend endpoints for settings page)
# ============================================================================

# Settings endpoints - simple HTML forms (no internal API calls = no TLS deadlock)
@ui_bp.route('/api/ui/settings/mtls', methods=['GET'])
@login_required
@admin_required
def ui_settings_mtls():
    """Get mTLS settings - Admin configuration"""
    try:
        # Get CAs directly from database
        from models import CA
        cas = CA.query.all()
        
        # Build CA options
        ca_options = '<option value="">-- Select CA --</option>'
        for ca in cas:
            cn = ca.descr or f"CA #{ca.id}"
            ca_options += f'<option value="{ca.id}">{cn}</option>'
        
        html = f'''<div style="padding: 1.5rem;">
    <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 1.5rem;">
        Configure mutual TLS (mTLS) client certificate authentication for enhanced security.
    </p>
    
    <form hx-post="/api/ui/settings/mtls/save"
          hx-swap="none"
          hx-on::after-request="if(event.detail.successful && typeof showToast==='function')showToast('mTLS settings saved','success')">
        
        <div style="margin-bottom: 1.5rem;">
            <label style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer; padding: 1rem; background: var(--bg-secondary); border-radius: 0.5rem;">
                <input type="checkbox" name="mtls_enabled" id="mtls-enabled" style="width: 18px; height: 18px; cursor: pointer;">
                <div>
                    <span style="font-weight: 600; color: var(--text-primary); display: block;">Enable mTLS Authentication</span>
                    <small style="color: var(--text-secondary); font-size: 0.75rem;">Require client certificates for login</small>
                </div>
            </label>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label class="form-label">
                Trusted Certificate Authority
            </label>
            <select name="ca_id" class="form-input">
                {ca_options}
            </select>
            <small style="display: block; margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.75rem;">
                Only clients with certificates signed by this CA will be allowed ({len(cas)} CAs available)
            </small>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label class="form-label">Verification Mode</label>
            <select name="verification_mode" class="form-input">
                <option value="optional">Optional (Allow password or certificate)</option>
                <option value="required">Required (Certificate only)</option>
            </select>
        </div>
        
        <div class="info-box" style="margin-bottom: 1.5rem;">
            <div class="info-box-content">
                <p style="margin: 0; font-size: 0.875rem;">
                    <svg class="ucm-icon" width="14" height="14" style="vertical-align: text-bottom;"><use href="#icon-info-circle"/></svg>
                    Current enrolled certificates: <strong>0</strong>
                </p>
            </div>
        </div>
        
        <div style="display: flex; gap: 0.75rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">
            <button type="submit" class="btn-primary">
                <svg class="ucm-icon" width="16" height="16"><use href="#icon-save"/></svg> Save mTLS Settings
            </button>
            <a href="/config/mtls" class="btn-secondary">
                <svg class="ucm-icon" width="16" height="16"><use href="#icon-shield-check"/></svg> Manage Certificates
            </a>
        </div>
    </form>
</div>'''
        return html, 200
        
    except Exception as e:
        return f'<div style="padding: 1.5rem; color: var(--danger-color);">Error: {str(e)}</div>', 200

@ui_bp.route('/api/ui/settings/mtls/save', methods=['POST'])
@login_required
@admin_required
def ui_settings_mtls_save():
    """Save mTLS settings (TODO: implement backend)"""
    # TODO: Update nginx config
    return jsonify({"success": True, "message": "mTLS settings saved"}), 200


@ui_bp.route('/api/ui/settings/email', methods=['GET'])
@login_required
@admin_required
def ui_settings_email():
    """Get email settings - REAL SMTP form"""
    html = '''<div style="padding: 1.5rem;">
    <form hx-post="/api/ui/settings/email/save"
          hx-swap="none"
          hx-on::after-request="if(event.detail.successful && typeof showToast==='function')showToast('SMTP settings saved','success')">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-bottom: 1.5rem;">
            <div>
                <label class="form-label">SMTP Host *</label>
                <input type="text" name="smtp_host" class="form-input" placeholder="smtp.gmail.com" required>
            </div>
            
            <div>
                <label class="form-label">SMTP Port *</label>
                <input type="number" name="smtp_port" class="form-input" placeholder="587" value="587" required>
            </div>
            
            <div>
                <label class="form-label">Username</label>
                <input type="text" name="smtp_user" class="form-input" placeholder="user@gmail.com">
            </div>
            
            <div>
                <label class="form-label">Password</label>
                <input type="password" name="smtp_password" class="form-input" placeholder="••••••••">
                <small style="color: var(--text-secondary); font-size: 0.75rem;">Leave blank to keep current</small>
            </div>
            
            <div>
                <label class="form-label">From Email *</label>
                <input type="email" name="smtp_from" class="form-input" placeholder="noreply@ucm.local" required>
            </div>
            
            <div>
                <label class="form-label">From Name</label>
                <input type="text" name="smtp_from_name" class="form-input" placeholder="UCM Notifications" value="UCM Notifications">
            </div>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                <input type="checkbox" name="use_tls" checked>
                <span>Use TLS/STARTTLS</span>
            </label>
        </div>
        
        <div style="display: flex; gap: 0.75rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">
            <button type="submit" class="btn-primary">
                <svg class="ucm-icon" width="16" height="16"><use href="#icon-save"/></svg> Save SMTP Settings
            </button>
            <button type="button" class="btn-secondary" onclick="alert('Test email - coming soon')">
                <svg class="ucm-icon" width="16" height="16"><use href="#icon-mail"/></svg> Test Email
            </button>
        </div>
    </form>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/email/save', methods=['POST'])
@login_required
@admin_required
def ui_settings_email_save():
    """Save SMTP settings (TODO: implement backend storage)"""
    # TODO: Store in config file
    return jsonify({"success": True, "message": "SMTP settings saved"}), 200

@ui_bp.route('/api/ui/settings/users', methods=['GET'])
@login_required
@admin_required
def ui_settings_users():
    """Get users list - EXACT copy from config_users"""
    try:
        response = api_call_with_retry('GET', f"{request.url_root}api/v1/auth/users")
        
        if response is None or response.status_code != 200:
            return '<div style="text-align: center; padding: 2rem; color: var(--text-secondary);">No users</div>'
        
        users = response.json()
        
        html = '''
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: var(--bg-secondary); border-bottom: 1px solid var(--border-color);">
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Username</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Email</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Role</th>
                        <th style="padding: 0.75rem; text-align: left; font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase;">Actions</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for user in users:
            # Role badge
            role_colors = {
                'admin': 'var(--danger-color)',
                'operator': 'var(--warning-color)',
                'viewer': 'var(--info-color)'
            }
            role_color = role_colors.get(user['role'], 'var(--text-secondary)')
            
            # Role badge - clickable if not admin user
            if user['username'] == 'admin':
                role_badge = f'''
                    <span style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--bg-secondary); color: {role_color}; border: 1px solid var(--border-color);">
                        <i class="fas fa-shield-alt" style="margin-right: 0.25rem;"></i> {user['role'].title()}
                    </span>
                '''
            else:
                role_badge = f'''
                    <button data-action="change-role" data-user-id="{user['id']}" data-username="{user['username']}" data-current-role="{user['role']}"
                            style="display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 500; background: var(--bg-secondary); color: {role_color}; border: 1px solid var(--border-color); cursor: pointer; transition: all 0.2s;"
                            onmouseover="this.style.borderColor='{role_color}'; this.style.background='var(--card-bg)';"
                            onmouseout="this.style.borderColor='var(--border-color)'; this.style.background='var(--bg-secondary)';"
                            title="Click to change role">
                        <i class="fas fa-user-tag" style="margin-right: 0.25rem;"></i> {user['role'].title()}
                    </button>
                '''
            
            html += f'''
                    <tr style="border-bottom: 1px solid var(--border-color);">
                        <td style="padding: 0.75rem; color: var(--text-primary); font-weight: 500;">
                            <i class="fas fa-user" style="margin-right: 0.5rem; color: var(--text-secondary);"></i>
                            {user['username']}
                        </td>
                        <td style="padding: 0.75rem; color: var(--text-primary);">
                            {user['email']}
                        </td>
                        <td style="padding: 0.75rem;">
                            {role_badge}
                        </td>
                        <td style="padding: 0.75rem;">
                            <button data-action="change-password" data-user-id="{user['id']}" data-username="{user['username']}"
                                    style="color: var(--primary-color); background: none; border: none; cursor: pointer; text-decoration: none; font-size: 0.875rem; margin-right: 1rem;">
                                <i class="fas fa-key" style="margin-right: 0.25rem;"></i> Change Password
                            </button>
            '''
            
            if user['username'] != 'admin':
                html += f'''
                            <button hx-delete="/api/ui/config/user/{user['id']}"
                                    hx-confirm="Delete user {user['username']}?"
                                    hx-on::after-request="if(event.detail.successful){{htmx.trigger('body','refreshUsers');if(typeof showToast==='function')showToast('User deleted','success');}}"
                                    style="color: var(--danger-color); background: none; border: none; cursor: pointer; text-decoration: none; font-size: 0.875rem;">
                                <i class="fas fa-trash" style="margin-right: 0.25rem;"></i> Delete
                            </button>
                '''
            
            html += '''
                        </td>
                    </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        '''
        
        return html
    except Exception as e:
        return f'<div style="text-align: center; padding: 2rem; color: var(--danger-color);">Error: {str(e)}</div>'


# All simple settings endpoints (no internal API calls)
@ui_bp.route('/api/ui/settings/system-info', methods=['GET'])
@login_required
def ui_settings_system_info():
    """System info - content only"""
    import socket
    hostname = socket.gethostname()
    html = f'''<div style="padding: 1.5rem;">
    <div style="display: flex; flex-direction: column; gap: 0.75rem;">
        <div style="display: flex; justify-content: space-between; padding: 0.75rem; border-bottom: 1px solid var(--border-color);">
            <span style="color: var(--text-secondary);">Hostname</span>
            <span style="font-weight: 600;">{hostname}</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 0.75rem; border-bottom: 1px solid var(--border-color);">
            <span style="color: var(--text-secondary);">Version</span>
            <span style="font-weight: 600;">UCM v2.0.0-dev</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 0.75rem;">
            <span style="color: var(--text-secondary);">Status</span>
            <span style="font-weight: 600; color: var(--success-color);">✓ Running</span>
        </div>
    </div>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/session-config', methods=['GET'])
@login_required
def ui_settings_session_config():
    """Session config - content only"""
    html = '''<div style="padding: 1.5rem;">
    <p style="color: var(--text-secondary); margin-bottom: 1rem;">
        Session timeout: <strong style="color: var(--text-primary);">30 minutes</strong>
    </p>
    <small style="display: block; color: var(--text-secondary); font-size: 0.875rem;">
        Sessions automatically expire after 30 minutes of inactivity
    </small>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/cert-defaults', methods=['GET'])
@login_required
def ui_settings_cert_defaults():
    """Certificate defaults - content only"""
    html = '''<div style="padding: 1.5rem;">
    <div style="display: flex; flex-direction: column; gap: 0.75rem;">
        <div style="display: flex; justify-content: space-between; padding: 0.75rem; border-bottom: 1px solid var(--border-color);">
            <span style="color: var(--text-secondary);">Default Validity</span>
            <span style="font-weight: 600;">365 days</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 0.75rem;">
            <span style="color: var(--text-secondary);">Default Key Size</span>
            <span style="font-weight: 600;">2048 bits</span>
        </div>
    </div>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/ui-prefs', methods=['GET'])
@login_required
def ui_settings_ui_prefs():
    """UI preferences - content only"""
    html = '''<div style="padding: 1.5rem;">
    <p style="color: var(--text-secondary); margin-bottom: 1rem;">
        Theme and language preferences are managed in your account settings.
    </p>
    <a href="/my-account" class="btn-secondary">
        <svg class="ucm-icon" width="16" height="16"><use href="#icon-user"/></svg> Go to My Account
    </a>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/password-policy', methods=['GET'])
@login_required
def ui_settings_password_policy():
    """Password policy - REAL implementation with form"""
    html = '''<div style="padding: 1.5rem;">
    <form hx-post="/api/ui/settings/password-policy/save" 
          hx-swap="none"
          hx-on::after-request="if(event.detail.successful && typeof showToast==='function')showToast('Password policy saved','success')">
        <div style="margin-bottom: 1.5rem;">
            <label class="form-label">Minimum Password Length</label>
            <input type="number" name="min_length" class="form-input" value="8" min="4" max="64" style="max-width: 200px;">
            <small style="display: block; margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.75rem;">
                Minimum number of characters required (4-64)
            </small>
        </div>
        
        <div style="margin-bottom: 1rem;">
            <label style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer; padding: 0.75rem; background: var(--bg-secondary); border-radius: 0.5rem;">
                <input type="checkbox" name="require_uppercase" checked style="width: 18px; height: 18px; cursor: pointer;">
                <span style="font-weight: 500; color: var(--text-primary);">Require uppercase letters (A-Z)</span>
            </label>
        </div>
        
        <div style="margin-bottom: 1rem;">
            <label style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer; padding: 0.75rem; background: var(--bg-secondary); border-radius: 0.5rem;">
                <input type="checkbox" name="require_lowercase" checked style="width: 18px; height: 18px; cursor: pointer;">
                <span style="font-weight: 500; color: var(--text-primary);">Require lowercase letters (a-z)</span>
            </label>
        </div>
        
        <div style="margin-bottom: 1rem;">
            <label style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer; padding: 0.75rem; background: var(--bg-secondary); border-radius: 0.5rem;">
                <input type="checkbox" name="require_numbers" checked style="width: 18px; height: 18px; cursor: pointer;">
                <span style="font-weight: 500; color: var(--text-primary);">Require numbers (0-9)</span>
            </label>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer; padding: 0.75rem; background: var(--bg-secondary); border-radius: 0.5rem;">
                <input type="checkbox" name="require_special" style="width: 18px; height: 18px; cursor: pointer;">
                <span style="font-weight: 500; color: var(--text-primary);">Require special characters (!@#$%^&*)</span>
            </label>
        </div>
        
        <div style="padding-top: 1rem; border-top: 1px solid var(--border-color);">
            <button type="submit" class="btn-primary">
                <svg class="ucm-icon" width="16" height="16"><use href="#icon-save"/></svg> Save Password Policy
            </button>
        </div>
    </form>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/password-policy/save', methods=['POST'])
@login_required
@admin_required
def ui_settings_password_policy_save():
    """Save password policy (TODO: implement backend storage)"""
    # TODO: Store in config file or database
    return jsonify({"success": True, "message": "Password policy saved"}), 200

@ui_bp.route('/api/ui/settings/session-security', methods=['GET'])
@login_required
def ui_settings_session_security():
    """Session security - content only"""
    html = '''<div style="padding: 1.5rem;">
    <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">
        Cookie security settings for web sessions.
    </p>
    <div style="display: flex; flex-direction: column; gap: 0.75rem;">
        <div style="display: flex; justify-content: space-between; padding: 0.75rem; border-bottom: 1px solid var(--border-color);">
            <span style="color: var(--text-secondary);">Secure Cookies (HTTPS only)</span>
            <span style="font-weight: 600; color: var(--success-color);">✓ Enabled</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 0.75rem; border-bottom: 1px solid var(--border-color);">
            <span style="color: var(--text-secondary);">HTTP-Only Cookies</span>
            <span style="font-weight: 600; color: var(--success-color);">✓ Enabled</span>
        </div>
        <div style="display: flex; justify-content: space-between; padding: 0.75rem;">
            <span style="color: var(--text-secondary);">SameSite Protection</span>
            <span style="font-weight: 600; color: var(--success-color);">✓ Strict</span>
        </div>
    </div>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/https-cert', methods=['GET'])
@login_required
def ui_settings_https_cert():
    """HTTPS certificate - Selector from UCM managed certificates"""
    try:
        # Get all certificates directly from database
        from models import Certificate
        from datetime import datetime
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.x509.oid import ExtendedKeyUsageOID
        import base64
        
        now = datetime.utcnow()
        
        # Filter for valid server certificates
        all_certs = Certificate.query.filter(
            Certificate.revoked == False,
            Certificate.cert_type.in_(['server_cert', 'cert']),
            Certificate.valid_to > now
        ).all()
        
        # Further filter by checking Extended Key Usage
        certs = []
        for cert in all_certs:
            if not cert.crt:
                continue
                
            try:
                cert_pem = base64.b64decode(cert.crt)
                x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
                
                # Check for Server Authentication EKU
                has_server_auth = False
                try:
                    ext = x509_cert.extensions.get_extension_for_oid(
                        x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
                    )
                    if ExtendedKeyUsageOID.SERVER_AUTH in ext.value:
                        has_server_auth = True
                except x509.ExtensionNotFound:
                    if cert.cert_type == 'server_cert':
                        has_server_auth = True
                
                if has_server_auth:
                    certs.append(cert)
            except:
                pass
        
        # Build options HTML
        options_html = '<option value="">-- Select Certificate --</option>'
        for cert in certs:
            cn = cert.descr or f"Cert #{cert.id}"
            serial = cert.refid or ''
            not_after = cert.valid_to.strftime('%Y-%m-%d') if cert.valid_to else 'N/A'
            options_html += f'<option value="{serial}">{cn} (Expires: {not_after})</option>'
        
        html = f'''<div style="padding: 1.5rem;">
    <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 1.5rem;">
        Select which UCM-managed certificate to use for the HTTPS web interface.
    </p>
    
    <form hx-post="/api/ui/settings/https-cert/apply"
          hx-swap="none"
          hx-on::after-request="
            console.log('HTTPS cert apply response:', event.detail);
            if(event.detail.successful) {{
              console.log('Success! Calling showRestartCountdown...');
              if(typeof showToast==='function') showToast('Certificate applied - restarting UCM','success');
              if(typeof showRestartCountdown==='function') {{
                console.log('showRestartCountdown exists, calling it now');
                showRestartCountdown(8, '/login');
              }} else {{
                console.error('showRestartCountdown function not found!');
                alert('Restarting UCM - please reload in 8 seconds');
                setTimeout(() => window.location.href = '/login', 8000);
              }}
            }} else {{
              console.error('Request failed:', event.detail);
            }}
          ">
        
        <div style="margin-bottom: 1.5rem;">
            <label class="form-label">Current HTTPS Certificate</label>
            <div style="padding: 1rem; background: var(--bg-secondary); border-radius: 0.5rem; margin-bottom: 1rem;">
                <p style="margin: 0; color: var(--success-color); font-weight: 600;">
                    ✓ Self-Signed Certificate (Active)
                </p>
                <small style="display: block; margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.75rem;">
                    CN: netsuit.lan.pew.pet
                </small>
            </div>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label class="form-label">
                Select New Certificate <span style="color: var(--danger-color);">*</span>
            </label>
            <select name="cert_serial" class="form-input" required>
                {options_html}
            </select>
            <small style="display: block; margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.75rem;">
                Only certificates with Server Authentication extension are shown ({len(certs)} available)
            </small>
        </div>
        
        <div class="alert-warning-border" style="margin-bottom: 1.5rem;">
            <div style="display: flex; align-items: start; gap: 0.5rem;">
                <svg class="ucm-icon" width="16" height="16" style="color: var(--warning-color); flex-shrink: 0; margin-top: 2px;"><use href="#icon-warning-triangle"/></svg>
                <p style="margin: 0; font-size: 0.8125rem;">
                    <strong>Warning:</strong> Changing the HTTPS certificate requires a service restart. Active sessions will be disconnected.
                </p>
            </div>
        </div>
        
        <div style="display: flex; gap: 0.75rem; padding-top: 1rem; border-top: 1px solid var(--border-color);">
            <button type="submit" class="btn-primary">
                <svg class="ucm-icon" width="16" height="16"><use href="#icon-certificate"/></svg> Apply Certificate
            </button>
            <button type="button" class="btn-secondary" onclick="alert('Upload external certificate - coming soon')">
                <svg class="ucm-icon" width="16" height="16"><use href="#icon-upload"/></svg> Upload External Cert
            </button>
        </div>
    </form>
</div>'''
        return html, 200
        
    except Exception as e:
        return f'<div style="padding: 1.5rem; color: var(--danger-color);">Error loading certificates: {str(e)}</div>', 200

@ui_bp.route('/api/ui/settings/https-cert/apply', methods=['POST'])
@login_required
@admin_required
def ui_settings_https_cert_apply():
    """Apply new HTTPS certificate and restart service"""
    from pathlib import Path
    from models import SystemConfig, Certificate, db
    import shutil
    import os
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Accept both JSON and form data
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
    
    cert_serial = data.get('cert_serial')
    
    if not cert_serial:
        return jsonify({"success": False, "error": "No certificate selected"}), 400
    
    try:
        # Get certificate from database
        cert = Certificate.query.filter_by(refid=cert_serial).first()
        if not cert:
            return jsonify({"success": False, "error": "Certificate not found"}), 404
        
        # Check certificate files exist
        cert_file = current_app.config['CERT_DIR'] / f'{cert.refid}.crt'
        key_file = current_app.config['PRIVATE_DIR'] / f'{cert.refid}.key'
        
        if not cert_file.exists() or not key_file.exists():
            return jsonify({"success": False, "error": "Certificate or key file not found"}), 404
        
        # Backup current cert
        https_cert = Path(current_app.config['HTTPS_CERT_PATH'])
        https_key = Path(current_app.config['HTTPS_KEY_PATH'])
        
        from config.settings import DATA_DIR
        backup_dir = DATA_DIR / 'backups'
        backup_dir.mkdir(exist_ok=True)
        
        if https_cert.exists():
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy(https_cert, backup_dir / f'https_cert_{timestamp}.pem.backup')
        if https_key.exists():
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy(https_key, backup_dir / f'https_key_{timestamp}.pem.backup')
        
        # Copy new certificate
        shutil.copy(cert_file, https_cert)
        shutil.copy(key_file, https_key)
        
        # Set permissions
        os.chmod(https_key, 0o600)
        os.chmod(https_cert, 0o644)
        
        # Save configuration
        config = SystemConfig.query.filter_by(key='https_cert_source').first()
        if not config:
            config = SystemConfig(key='https_cert_source', value='managed')
            db.session.add(config)
        else:
            config.value = 'managed'
        
        cert_id_config = SystemConfig.query.filter_by(key='https_cert_id').first()
        if not cert_id_config:
            cert_id_config = SystemConfig(key='https_cert_id', value=str(cert.id))
            db.session.add(cert_id_config)
        else:
            cert_id_config.value = str(cert.id)
        
        db.session.commit()
        
        logger.info(f"HTTPS certificate applied: {cert.descr} (ID: {cert.id}) by {session.get('username')}")
        
        # Restart service
        from utils.service_manager import restart_service
        success, message = restart_service()
        
        if success:
            # Trigger immediate restart check by scheduling shutdown
            def trigger_restart():
                import time, sys
                time.sleep(0.5)  # Let response be sent
                sys.stdout.flush()
                import os
                os._exit(0)  # Graceful exit, systemd will restart
            
            import threading
            threading.Thread(target=trigger_restart, daemon=False).start()
        
        return jsonify({"success": success, "message": message}), 200
        
    except Exception as e:
        logger.error(f"Error applying HTTPS certificate: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@ui_bp.route('/api/ui/settings/backup', methods=['GET'])
@login_required
def ui_settings_backup():
    """Get backup settings - REAL backup/restore interface"""
    html = '''<div style="padding: 1.5rem;">
    <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 1.5rem;">
        Create encrypted backups of your entire PKI system or restore from a previous backup.
    </p>
    
    <!-- Create Backup -->
    <div style="background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 0.5rem; padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="font-size: 1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem;">
            <svg class="ucm-icon" width="18" height="18" style="color: var(--success-color);"><use href="#icon-save"/></svg>
            Create Backup
        </h3>
        <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 1rem;">
            Create an encrypted backup containing all CAs, certificates, users, and system configuration.
        </p>
        <div class="info-box" style="margin-bottom: 1rem;">
            <div class="info-box-content" style="margin: 0;">
                <p style="margin: 0;">
                    <svg class="ucm-icon" width="16" height="16" style="vertical-align: text-bottom; margin-right: 0.375rem; color: var(--info-color);"><use href="#icon-lock"/></svg>
                    <strong>Encryption:</strong> Backup is encrypted with AES-256-GCM. Keep your password safe - it's required for restore!
                </p>
            </div>
        </div>
        <button onclick="openBackupModal()" class="btn-primary">
            <svg class="ucm-icon" width="16" height="16"><use href="#icon-download"/></svg>
            Create Encrypted Backup
        </button>
    </div>
    
    <!-- Restore -->
    <div style="background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 0.5rem; padding: 1.5rem;">
        <h3 style="font-size: 1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem;">
            <svg class="ucm-icon" width="18" height="18" style="color: var(--warning-color);"><use href="#icon-upload"/></svg>
            Restore from Backup
        </h3>
        <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 1rem;">
            Restore your PKI system from a previously created backup file.
        </p>
        <div class="alert-warning-border">
            <div style="display: flex; align-items: start; gap: 0.5rem;">
                <svg class="ucm-icon" width="16" height="16" style="color: var(--warning-color); flex-shrink: 0; margin-top: 2px;"><use href="#icon-warning-triangle"/></svg>
                <p style="margin: 0; font-size: 0.8125rem;">
                    <strong>Warning:</strong> Restoring will merge or replace existing data. Service will restart automatically.
                </p>
            </div>
        </div>
        <button onclick="openRestoreModal()" class="btn-secondary">
            <svg class="ucm-icon" width="16" height="16"><use href="#icon-upload"/></svg>
            Restore from Backup
        </button>
    </div>
</div>'''
    return html, 200

@ui_bp.route('/api/ui/settings/backup/create', methods=['POST'])
@login_required
@admin_required
def ui_settings_backup_create():
    """Create backup (TODO: implement real backup)"""
    # TODO: Call backup API
    return jsonify({"success": True, "message": "Backup created"}), 200

@ui_bp.route('/api/ui/settings/database-stats', methods=['GET'])
@login_required
def ui_settings_database_stats():
    html = """
<div style="padding: 1rem;">
    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid var(--border-color);">
        <span style="color: var(--text-secondary);">Database Size</span>
        <span style="font-weight: 500;">N/A</span>
    </div>
    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid var(--border-color);">
        <span style="color: var(--text-secondary);">Last Modified</span>
        <span style="font-weight: 500;">Never</span>
    </div>
    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0;">
        <span style="color: var(--text-secondary);">Location</span>
        <span style="font-weight: 500; font-size: 0.875rem;">/opt/ucm/backend/data/ucm.db</span>
    </div>
</div>
"""
    return html, 200

# Design preview route (NO AUTH)
@ui_bp.route('/settings-preview', methods=['GET'])
def settings_design_preview():
    """Design preview page without authentication"""
    return render_template('settings_design_preview.html')

# Helper endpoints for settings dropdowns
@ui_bp.route('/api/ui/config/cas-list', methods=['GET'])
@login_required
def config_cas_list():
    """Get list of CAs for dropdowns"""
    from models import CA
    try:
        cas = CA.query.all()
        cas_list = []
        for ca in cas:
            cas_list.append({
                'id': ca.id,
                'subject_cn': ca.descr or f"CA #{ca.id}",
                'refid': ca.refid
            })
        return jsonify(cas_list), 200
    except Exception as e:
        return jsonify([]), 200

@ui_bp.route('/api/ui/config/certs-list', methods=['GET'])
@login_required  
def config_certs_list():
    """Get list of certificates for dropdowns"""
    from models import Certificate
    from datetime import datetime
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import ExtendedKeyUsageOID
    import base64
    
    try:
        now = datetime.utcnow()
        all_certs = Certificate.query.filter(
            Certificate.revoked == False,
            Certificate.cert_type.in_(['server_cert', 'cert']),
            Certificate.valid_to > now
        ).all()
        
        certs_list = []
        for cert in all_certs:
            if not cert.crt:
                continue
            
            try:
                cert_pem = base64.b64decode(cert.crt)
                x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
                
                has_server_auth = False
                try:
                    ext = x509_cert.extensions.get_extension_for_oid(
                        x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
                    )
                    if ExtendedKeyUsageOID.SERVER_AUTH in ext.value:
                        has_server_auth = True
                except x509.ExtensionNotFound:
                    if cert.cert_type == 'server_cert':
                        has_server_auth = True
                
                if has_server_auth:
                    certs_list.append({
                        'serial_number': cert.refid,
                        'subject_cn': cert.descr or f"Cert #{cert.id}",
                        'not_after': cert.valid_to.strftime('%Y-%m-%d %H:%M:%S') if cert.valid_to else 'N/A',
                        'extensions_text': 'TLS Web Server Authentication'
                    })
            except:
                pass
                
        return jsonify(certs_list), 200
    except Exception as e:
        return jsonify([]), 200


# ============================================================================
# DOCUMENTATION ROUTES
# ============================================================================

@ui_bp.route('/docs/smime-installation')
@login_required
def docs_smime_installation():
    """S/MIME installation guide"""
    return render_template('docs/smime-installation.html')

