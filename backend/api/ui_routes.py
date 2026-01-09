"""
UI Routes - Flask templates with HTMX
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from functools import wraps
from datetime import datetime, timedelta
import requests
import time
import html
from config.settings import Config, DATA_DIR

ui_bp = Blueprint('ui', __name__, template_folder='../../frontend/templates')

# Helper function to escape JavaScript strings
def escape_js(text):
    """Escape text for safe use in JavaScript strings"""
    if text is None:
        return ''
    return html.escape(str(text)).replace("'", "&#39;").replace('"', '&quot;')

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
                return redirect(url_for('ui.dashboard'), code=303)  # 303 forces GET
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
            
    except Exception as e:
        print(f"⚠️  Dashboard error: {e}")
        import traceback
        traceback.print_exc()
    
    return render_template('dashboard.html',
                         stats=stats,
                         certificates=certificates,
                         scep_requests=scep_requests)



# Dashboard API endpoints (for HTMX)
@ui_bp.route('/api/dashboard/stats')
@login_required
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
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div class="flex items-center">
                <div class="flex-shrink-0 p-3 bg-primary-100 dark:bg-primary-900 rounded-lg">
                    <i class="fas fa-certificate text-primary-600 dark:text-primary-400 text-2xl"></i>
                </div>
                <div class="ml-4">
                    <p class="text-sm font-medium text-gray-500 dark:text-gray-400">Certificate Authorities</p>
                    <p class="text-3xl font-bold text-gray-900 dark:text-white">{ca_count}</p>
                </div>
            </div>
        </div>
        
        <!-- Cert Count -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div class="flex items-center">
                <div class="flex-shrink-0 p-3 bg-green-100 dark:bg-green-900 rounded-lg">
                    <i class="fas fa-file-certificate text-green-600 dark:text-green-400 text-2xl"></i>
                </div>
                <div class="ml-4">
                    <p class="text-sm font-medium text-gray-500 dark:text-gray-400">Certificates</p>
                    <p class="text-3xl font-bold text-gray-900 dark:text-white">{cert_count}</p>
                </div>
            </div>
        </div>
        
        <!-- SCEP Count -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div class="flex items-center">
                <div class="flex-shrink-0 p-3 bg-orange-100 dark:bg-orange-900 rounded-lg">
                    <i class="fas fa-network-wired text-orange-600 dark:text-orange-400 text-2xl"></i>
                </div>
                <div class="ml-4">
                    <p class="text-sm font-medium text-gray-500 dark:text-gray-400">SCEP Requests</p>
                    <p class="text-3xl font-bold text-gray-900 dark:text-white">{scep_count}</p>
                </div>
            </div>
        </div>
        
        <!-- Pending Count -->
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div class="flex items-center">
                <div class="flex-shrink-0 p-3 bg-yellow-100 dark:bg-yellow-900 rounded-lg">
                    <i class="fas fa-clock text-yellow-600 dark:text-yellow-400 text-2xl"></i>
                </div>
                <div class="ml-4">
                    <p class="text-sm font-medium text-gray-500 dark:text-gray-400">Pending Approvals</p>
                    <p class="text-3xl font-bold text-gray-900 dark:text-white">{pending_count}</p>
                </div>
            </div>
        </div>
        """
    except Exception as e:
        return f'<div class="text-red-600">Error loading stats: {str(e)}</div>'


@ui_bp.route('/api/dashboard/recent-cas')
@login_required
def dashboard_recent_cas():
    """Get recent CAs"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<p class="text-gray-500 dark:text-gray-400">No CAs found</p>'
        
        cas = response.json()[:5]  # Get latest 5
        
        if not cas:
            return '<p class="text-gray-500 dark:text-gray-400">No CAs found. <a href="/ca/new" class="text-primary-600 hover:text-primary-700">Create one</a></p>'
        
        html = '<div class="space-y-3">'
        for ca in cas:
            html += f'''
            <a href="/ca/{ca['refid']}" class="block p-3 bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 rounded-lg transition-colors">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="font-medium text-gray-900 dark:text-white">{ca['descr']}</p>
                        <p class="text-xs text-gray-500 dark:text-gray-400">{ca.get('subject', 'N/A')}</p>
                    </div>
                    <i class="fas fa-chevron-right text-gray-400"></i>
                </div>
            </a>
            '''
        html += '</div>'
        
        return html
    except Exception as e:
        return f'<p class="text-red-600">Error: {str(e)}</p>'


@ui_bp.route('/api/dashboard/scep-status')
@login_required
def dashboard_scep_status():
    """Get SCEP status"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}scep/config",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<p class="text-red-600">Failed to load SCEP status</p>'
        
        config = response.json()
        enabled = config.get('enabled', False)
        auto_approve = config.get('auto_approve', False)
        
        if not enabled:
            return f'''
            <div class="flex items-center justify-between p-4 bg-gray-100 dark:bg-gray-700 rounded-lg">
                <div class="flex items-center">
                    <i class="fas fa-circle text-red-500 mr-3"></i>
                    <div>
                        <p class="font-medium text-gray-900 dark:text-white">SCEP Server: Disabled</p>
                        <p class="text-sm text-gray-500 dark:text-gray-400">Configure SCEP to start accepting enrollment requests</p>
                    </div>
                </div>
                <a href="/scep" class="btn btn-primary text-sm">
                    Configure
                </a>
            </div>
            '''
        
        return f'''
        <div class="space-y-4">
            <div class="flex items-center justify-between p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                <div class="flex items-center">
                    <i class="fas fa-circle text-green-500 mr-3 animate-pulse"></i>
                    <div>
                        <p class="font-medium text-gray-900 dark:text-white">SCEP Server: Active</p>
                        <p class="text-sm text-gray-500 dark:text-gray-400">Accepting enrollment requests</p>
                    </div>
                </div>
                <a href="/scep" class="text-accent hover:text-accent-hover text-sm">
                    Manage <i class="fas fa-chevron-right ml-1"></i>
                </a>
            </div>
            <div class="grid grid-cols-2 gap-4 text-sm">
                <div class="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <p class="text-gray-500 dark:text-gray-400">Mode</p>
                    <p class="font-medium text-gray-900 dark:text-white">
                        {'Auto-Approval' if auto_approve else 'Manual Approval'}
                    </p>
                </div>
                <div class="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <p class="text-gray-500 dark:text-gray-400">Endpoint</p>
                    <p class="font-medium text-gray-900 dark:text-white text-xs">/scep/pkiclient.exe</p>
                </div>
            </div>
        </div>
        '''
    except Exception as e:
        return f'<p class="text-red-600">Error: {str(e)}</p>'


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
    """Get CA list HTML as sortable table"""
    try:
        token = session.get('access_token')
        if not token:
            return '<div class="p-8 text-center text-red-600">Session expired. Please <a href="/logout" class="underline">logout</a> and login again.</div>'
        
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            verify=False
        )
        
        if response.status_code == 401:
            return '<div class="p-8 text-center text-red-600">Session expired. Please refresh the page or <a href="/logout" class="underline">logout</a> and login again.</div>'
        elif response.status_code != 200:
            return f'<div class="p-8 text-center text-red-600">Failed to load CAs (Error {response.status_code})</div>'
        
        cas = response.json()
        
        if not cas:
            return '''
            <div class="p-8 text-center text-gray-500 dark:text-gray-400">
                <i class="fas fa-certificate text-4xl mb-4"></i>
                <p class="text-lg font-medium mb-2">No Certificate Authorities</p>
                <p class="text-sm">Create your first CA to get started</p>
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
        
        html = '''
        <div style="overflow-x: auto; overflow-y: visible;">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700" id="ca-table">
                <thead class="bg-gray-50 dark:bg-gray-700">
                    <tr>
                        <th onclick="sortTable(0)" style="position: relative;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span>Description <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i></span>
                                <div style="position: relative; margin-left: 12px;">
                                    <input type="text" id="searchCA" placeholder="Recherche..." 
                                           class="form-control"
                                           style="padding: 4px 8px 4px 24px; font-size: 12px; width: 160px;"
                                           onkeyup="filterTableCA()"
                                           onclick="event.stopPropagation()">
                                    <i class="fas fa-search" style="position: absolute; left: 6px; top: 50%; transform: translateY(-50%); font-size: 11px; opacity: 0.5; pointer-events: none;"></i>
                                </div>
                            </div>
                        </th>
                        <th onclick="sortTable(1)">
                            Émetteur <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th onclick="sortTable(2)">
                            Nom <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th onclick="sortTable(3)">
                            Utilisations <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th onclick="sortTable(4)">
                            Début validité <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th onclick="sortTable(5)">
                            Fin validité <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th>
                            Commandes
                        </th>
                    </tr>
                </thead>
                <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
        '''
        
        for ca in cas:
            is_root = not ca.get('caref')
            usage_count = ca_usage.get(ca['refid'], 0)
            
            # Extract CN from subject
            subject = ca.get('subject', '')
            cn = 'N/A'
            if 'CN=' in subject:
                for part in subject.split(','):
                    if 'CN=' in part:
                        cn = part.split('CN=')[1].strip()
                        break
            
            # Issuer info
            issuer = ca.get('issuer', '')
            issuer_cn = 'Self-signed' if is_root else 'N/A'
            if 'CN=' in issuer and not is_root:
                for part in issuer.split(','):
                    if 'CN=' in part:
                        issuer_cn = part.split('CN=')[1].strip()
                        break
            
            valid_from = ca.get('valid_from', '')[:10] if ca.get('valid_from') else 'N/A'
            valid_to = ca.get('valid_to', '')[:10] if ca.get('valid_to') else 'N/A'
            
            # Check if CA has private key
            has_key = ca.get('has_private_key', False)
            key_badge = '<span class="badge-outline badge-success ml-2"><i class="fas fa-key"></i> Key</span>' if has_key else '<span class="badge-outline badge-secondary ml-2"><i class="fas fa-key-skeleton"></i> No Key</span>'
            
            # Escape values for JavaScript
            safe_refid = escape_js(ca['refid'])
            safe_descr = escape_js(ca['descr'])
            
            html += f'''
                <tr class="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer" onclick="window.location.href='/ca/{ca['id']}'">
                    <td>
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <span>{ca['descr']}</span>
                            <div style="display: flex; gap: 4px;">
                                <span class="badge-outline badge-primary">
                                    <i class="{'fas fa-crown' if is_root else 'fas fa-link'}"></i>
                                    {'ROOT' if is_root else 'INT'}
                                </span>
                                {key_badge}
                            </div>
                        </div>
                    </td>
                    <td>
                        {issuer_cn}
                    </td>
                    <td>
                        {cn}
                    </td>
                    <td>
                        <span>
                            {usage_count}
                        </span>
                    </td>
                    <td>
                        {valid_from}
                    </td>
                    <td>
                        {valid_to}
                    </td>
                    <td onclick="event.stopPropagation()">
                        <button onclick="exportCA({ca['id']}, event)" 
                                class="btn-icon btn-icon-primary"
                                title="Export CA">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-download"/></svg>
                        </button>
                        <button onclick="deleteCA('{safe_refid}', '{safe_descr}')" 
                                class="btn-icon btn-icon-danger"
                                title="Delete CA">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-trash"/></svg>
                        </button>
                    </td>
                </tr>
            '''
        
        html += '''
                </tbody>
            </table>
        </div>
        
        <script>
        (function() {
            // Isolated scope for CA list
            var sortDirection = {};
            
            window.sortTable = function(columnIndex) {
                const table = document.getElementById('ca-table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                
                const currentDirection = sortDirection[columnIndex] || 'asc';
                const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
                sortDirection[columnIndex] = newDirection;
                
                rows.sort((a, b) => {
                    let aValue = a.cells[columnIndex].textContent.trim();
                    let bValue = b.cells[columnIndex].textContent.trim();
                    
                    // Handle numeric values for usage column
                    if (columnIndex === 3) {
                        aValue = parseInt(aValue) || 0;
                        bValue = parseInt(bValue) || 0;
                    }
                    
                    if (aValue < bValue) return newDirection === 'asc' ? -1 : 1;
                    if (aValue > bValue) return newDirection === 'asc' ? 1 : -1;
                    return 0;
                });
                
                rows.forEach(row => tbody.appendChild(row));
            };
            
            window.filterTableCA = function() {
                const input = document.getElementById('searchCA');
                const filter = input.value.toLowerCase();
                const table = document.getElementById('ca-table');
                const tbody = table.querySelector('tbody');
                const rows = tbody.querySelectorAll('tr');
                
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(filter) ? '' : 'none';
                });
            };
        })();
        
        function exportCASimple(id) {
            exportWithToken('/api/v1/ca/' + id + '/export/advanced?format=pem');
            document.getElementById('export-menu-' + id).remove();
        }
        
        function exportCAWithKey(id) {
            exportWithToken('/api/v1/ca/' + id + '/export/advanced?format=pem&key=true');
            document.getElementById('export-menu-' + id).remove();
        }
        
        function exportCAWithChain(id) {
            exportWithToken('/api/v1/ca/' + id + '/export/advanced?format=pem&chain=true');
            document.getElementById('export-menu-' + id).remove();
        }
        
        function exportCAFull(id) {
            exportWithToken('/api/v1/ca/' + id + '/export/advanced?format=pem&key=true&chain=true');
            document.getElementById('export-menu-' + id).remove();
        }
        
        function exportCADER(id) {
            exportWithToken('/api/v1/ca/' + id + '/export/advanced?format=der');
            document.getElementById('export-menu-' + id).remove();
        }
        
        function deleteCA(refid, name) {
            ucmConfirm(
                'Delete CA "' + name + '"?\n\nThis cannot be undone! All certificates signed by this CA will be affected.',
                'Delete CA',
                { danger: true, confirmText: 'Delete', icon: 'trash' }
            ).then(confirmed => {
                if (!confirmed) return;
                
                fetch('/api/v1/ca/' + refid, {
                    method: 'DELETE',
                    headers: { 'Authorization': 'Bearer ' + ''' + f"'{token}'" + ''' }
                })
                .then(response => {
                    if (response.ok) {
                        showToast('CA deleted successfully', 'success');
                        htmx.trigger('body', 'refreshCAs');
                    } else {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Delete failed');
                        });
                    }
                })
                .catch(e => {
                    showToast('Error: ' + e.message, 'error');
                });
            });
        }
        
        function exportWithToken(url) {
            const token = ''' + f"'{token}'" + ''';
            fetch(url, {
                headers: { 'Authorization': 'Bearer ' + token }
            })
            .then(response => {
                if (!response.ok) throw new Error('Export failed');
                return response.blob();
            })
            .then(blob => {
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = '';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);
            })
            .catch(error => {
                showToast('Export failed: ' + error.message, 'error');
            });
        }
        
        // Close menus when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('button[onclick*="exportCA"]') && !e.target.closest('[id^="export-menu-"]')) {
                document.querySelectorAll('[id^="export-menu-"]').forEach(m => m.remove());
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
        return f'<div class="p-8 text-red-600">Error: {str(e)}</div>'


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
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/ca/",
            headers=headers,
            verify=False
        )
        
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
            return '<div class="p-8 text-center text-red-600">Session expired. Please <a href="/logout" class="underline">logout</a> and login again.</div>'
        
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            verify=False
        )
        
        if response.status_code == 401:
            return '<div class="p-8 text-center text-red-600">Session expired. Please refresh the page or <a href="/logout" class="underline">logout</a> and login again.</div>'
        elif response.status_code != 200:
            return f'<div class="p-8 text-center text-red-600">Failed to load certificates (Error {response.status_code})</div>'
        
        certs = response.json()
        
        if not certs:
            return '''
            <div class="p-8 text-center text-gray-500 dark:text-gray-400">
                <i class="fas fa-file-certificate text-4xl mb-4"></i>
                <p class="text-lg font-medium mb-2">No Certificates</p>
                <p class="text-sm">Create your first certificate to get started</p>
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
        <!-- Cert list v2.0 with CRT/KEY badges -->
        <div class="overflow-x-auto" style="overflow-y: visible;">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700" id="cert-table">
                <thead class="bg-gray-50 dark:bg-gray-700">
                    <tr>
                        <th onclick="sortTableCert(0)" style="position: relative;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span>Description <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i></span>
                                <div style="position: relative; margin-left: 12px;">
                                    <input type="text" id="searchCert" placeholder="Recherche..." 
                                           class="form-control"
                                           style="padding: 4px 8px 4px 24px; font-size: 12px; width: 160px;"
                                           onkeyup="filterTableCert()"
                                           onclick="event.stopPropagation()">
                                    <i class="fas fa-search" style="position: absolute; left: 6px; top: 50%; transform: translateY(-50%); font-size: 11px; opacity: 0.5; pointer-events: none;"></i>
                                </div>
                            </div>
                        </th>
                        <th onclick="sortTableCert(1)">
                            Émetteur <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th onclick="sortTableCert(2)">
                            Type <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th onclick="sortTableCert(3)">
                            Début validité <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th onclick="sortTableCert(4)">
                            Fin validité <i class="fas fa-chevron-down" style="font-size: 10px; opacity: 0.5;"></i>
                        </th>
                        <th>
                            Commandes
                        </th>
                    </tr>
                </thead>
                <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
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
                <tr class="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer" onclick="window.location.href='/certificates/{cert['id']}'">
                    <td>
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <span>{cert['descr']}</span>
                            <div style="display: flex; gap: 4px;">
                                {status_badge}
                                {crt_badge}
                                {key_badge}
                            </div>
                        </div>
                    </td>
                    <td>
                        {issuer_name}
                    </td>
                    <td>
                        {cert_type_display}
                    </td>
                    <td>
                        {valid_from}
                    </td>
                    <td>
                        {valid_to}
                    </td>
                    <td onclick="event.stopPropagation()">
            '''
            
            # Unified export button for both CSR and certificates
            button_class = "btn-icon btn-icon-primary"
            html += f'''
                        <button onclick="exportCert({cert['id']}, event, {'true' if is_csr else 'false'})" 
                                class="{button_class}"
                                title="Export {'CSR' if is_csr else 'Certificate'}">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-download"/></svg>
                        </button>
            '''
                
            if not is_revoked and not is_csr:
                html += f'''
                        <button onclick="revokeCert('{safe_refid}', '{safe_descr}')" 
                                class="btn-icon btn-icon-danger"
                                title="Revoke Certificate">
                            <svg class="ucm-icon" width="16" height="16"><use href="#icon-ban"/></svg>
                        </button>
                '''
            
            html += f'''
                        <button onclick="deleteCert('{safe_refid}', '{safe_descr}')" 
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
        
        <script>
        if (typeof sortDirectionCert === 'undefined') {
            var sortDirectionCert = {};
        }
        
        function sortTableCert(columnIndex) {
            const table = document.getElementById('cert-table');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            const currentDirection = sortDirectionCert[columnIndex] || 'asc';
            const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
            sortDirectionCert[columnIndex] = newDirection;
            
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
                menu.innerHTML = '<div class="py-1" role="menu">' +
                    '<button onclick="exportCertSimple(' + id + ')" class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">' +
                        '<i class="fas fa-file-certificate mr-2"></i>CSR (PEM)' +
                    '</button>' +
                '</div>';
            } else {
                // Full certificate has all export options
                menu.innerHTML = '<div class="py-1" role="menu">' +
                    '<button onclick="exportCertSimple(' + id + ')" class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">' +
                        '<i class="fas fa-file-certificate mr-2"></i>Certificate only (PEM)' +
                    '</button>' +
                    '<button onclick="exportCertWithKey(' + id + ')" class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">' +
                        '<i class="fas fa-key mr-2"></i>Certificate + Key (PEM)' +
                    '</button>' +
                    '<button onclick="exportCertWithChain(' + id + ')" class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">' +
                        '<i class="fas fa-link mr-2"></i>Certificate + CA Chain (PEM)' +
                    '</button>' +
                    '<button onclick="exportCertFull(' + id + ')" class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">' +
                        '<i class="fas fa-archive mr-2"></i>Full Chain + Key (PEM)' +
                    '</button>' +
                    '<button onclick="exportCertDER(' + id + ')" class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">' +
                        '<i class="fas fa-file-binary mr-2"></i>Certificate (DER)' +
                    '</button>' +
                    '<button onclick="showPKCS12ModalTable(' + id + ', &quot;cert&quot;)" class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">' +
                        '<i class="fas fa-lock mr-2"></i>PKCS#12 (.p12/.pfx)' +
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
        
        function exportCertSimple(id) {
            exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertWithKey(id) {
            exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem&key=true');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertWithChain(id) {
            exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem&chain=true');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertFull(id) {
            exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=pem&key=true&chain=true');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportCertDER(id) {
            exportWithTokenCert('/api/v1/certificates/' + id + '/export/advanced?format=der');
            document.getElementById('export-cert-menu-' + id).remove();
        }
        
        function exportWithTokenCert(url) {
            const token = ''' + f"'{token}'" + ''';
            fetch(url, {
                headers: { 'Authorization': 'Bearer ' + token }
            })
            .then(response => {
                if (!response.ok) throw new Error('Export failed');
                return response.blob();
            })
            .then(blob => {
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = '';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);
            })
            .catch(error => {
                showToast('Export failed: ' + error.message, 'error');
            });
        }
        
        function downloadCSR(id) {
            // Download via fetch with auth token
            fetch('/api/v1/certificates/' + id + '/export?format=pem', {
                headers: { 'Authorization': 'Bearer ' + ''' + f"'{token}'" + ''' }
            })
            .then(response => {
                if (!response.ok) throw new Error('Download failed');
                return response.blob();
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'csr_' + id + '.pem';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(e => alert('Error downloading CSR: ' + e));
        }
        
        function revokeCert(refid, name) {
            ucmConfirm(
                'Revoke certificate "' + name + '"?\\n\\nThis cannot be undone. The certificate will be marked as revoked.',
                'Revoke Certificate',
                { danger: true, confirmText: 'Revoke', icon: 'warning-triangle' }
            ).then(confirmed => {
                if (!confirmed) return;
                
                fetch('/api/v1/certificates/by-refid/' + refid + '/revoke', {
                    method: 'POST',
                    headers: { 
                        'Authorization': 'Bearer ' + ''' + f"'{token}'" + ''',
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ reason: 'unspecified' })
                })
                .then(response => {
                    if (response.ok) {
                        showToast('Certificate revoked successfully', 'success');
                        htmx.trigger('body', 'refreshCerts');
                    } else {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Revoke failed');
                        });
                    }
                })
                .catch(e => showToast('Error: ' + e.message, 'error'));
            });
        }
        
        function deleteCert(refid, name) {
            ucmConfirm(
                'Delete certificate "' + name + '"?\n\nThis action cannot be undone.',
                'Delete Certificate',
                { danger: true, confirmText: 'Delete', icon: 'trash' }
            ).then(confirmed => {
                if (!confirmed) return;
                
                fetch('/api/v1/certificates/by-refid/' + refid, {
                    method: 'DELETE',
                    headers: { 'Authorization': 'Bearer ' + ''' + f"'{token}'" + ''' }
                })
                .then(response => {
                    if (response.ok) {
                        showToast('Certificate deleted successfully', 'success');
                        htmx.trigger('body', 'refreshCerts');
                    } else {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Delete failed');
                        });
                    }
                })
                .catch(e => {
                    showToast('Error: ' + e.message, 'error');
                });
            });
        }
        
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
        return f'<div class="p-8 text-red-600">Error: {str(e)}</div>'


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
        
        data = {
            'descr': request.form.get('descr'),
            'common_name': request.form.get('common_name'),
            'key_type': request.form.get('key_type'),
        }
        
        response = requests.post(
            f"{request.url_root}api/v1/certificates/csr",
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
            return f'<div class="p-4 text-red-600">Failed to load CRLs: {response.text}</div>'
        
        crls = response.json()
        
        if not crls:
            return '''
            <div class="p-8 text-center text-gray-500">
                <i class="fas fa-file-contract text-6xl mb-4"></i>
                <p class="text-lg">No CRLs generated yet</p>
                <p class="text-sm mt-2">Enable CDP on a CA and generate a CRL to get started</p>
            </div>
            '''
        
        # Build table HTML
        html = '''
        <table class="w-full">
            <thead class="bg-gray-50 border-b border-gray-200">
                <tr>
                    <th>CA</th>
                    <th>CDP Status</th>
                    <th>CRL Status</th>
                    <th>Revoked Count</th>
                    <th>Last Update</th>
                    <th>Next Update</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
        '''
        
        for crl_data in crls:
            ca_name = crl_data.get('ca_name', 'Unknown')
            ca_id = crl_data.get('ca_id')
            ca_refid = crl_data.get('ca_refid', '')
            cdp_enabled = crl_data.get('cdp_enabled', False)
            has_crl = crl_data.get('has_crl', False)
            
            # CDP Status badge
            if cdp_enabled:
                cdp_status = '<span class="badge badge-success"><i class="fas fa-check mr-1"></i>Enabled</span>'
            else:
                cdp_status = '<span class="badge badge-secondary"><i class="fas fa-times mr-1"></i>Disabled</span>'
            
            # CRL Status badge
            if not has_crl:
                crl_status = '<span class="badge badge-warning">Never Generated</span>'
                revoked_count = '-'
                last_update = '-'
                next_update = '-'
                days_until = '-'
            else:
                is_stale = crl_data.get('is_stale', False)
                days_until_expiry = crl_data.get('days_until_expiry', 0)
                
                if is_stale:
                    crl_status = '<span class="badge badge-danger"><i class="fas fa-exclamation-triangle mr-1"></i>Stale</span>'
                elif days_until_expiry <= 1:
                    crl_status = '<span class="badge badge-warning"><i class="fas fa-clock mr-1"></i>Expiring Soon</span>'
                else:
                    crl_status = '<span class="badge badge-success"><i class="fas fa-check mr-1"></i>Up to Date</span>'
                
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
            <div class="flex justify-end space-x-2">
            '''
            
            if has_crl:
                actions += f'''
                <button onclick="downloadCRL({ca_id}, 'pem')" 
                        class="btn-sm btn-secondary" title="Download PEM">
                    <i class="fas fa-download"></i> PEM
                </button>
                <button onclick="downloadCRL({ca_id}, 'der')" 
                        class="btn-sm btn-secondary" title="Download DER">
                    <i class="fas fa-download"></i> DER
                </button>
                <button onclick="viewCRLInfo('{ca_refid}')" 
                        class="btn-sm btn-secondary" title="View Info">
                    <i class="fas fa-info-circle"></i>
                </button>
                '''
            
            if cdp_enabled:
                actions += f'''
                <button onclick="generateCRL({ca_id}, '{ca_name}')" 
                        class="btn-sm btn-primary" title="Force Generate">
                    <i class="fas fa-refresh"></i>
                </button>
                '''
            
            actions += '</div>'
            
            html += f'''
            <tr class="hover:bg-gray-50">
                <td>
                    <div class="font-medium text-gray-900">{ca_name}</div>
                    <div class="text-sm text-gray-500">{ca_refid}</div>
                </td>
                <td>{cdp_status}</td>
                <td>{crl_status}</td>
                <td>{revoked_count}</td>
                <td>{last_update}</td>
                <td>{next_update} {days_until}</td>
                <td>{actions}</td>
            </tr>
            '''
        
        html += '''
            </tbody>
        </table>
        '''
        
        return html
        
    except Exception as e:
        return f'<div class="p-4 text-red-600">Error: {str(e)}</div>'


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
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}scep/requests",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<div class="p-8 text-center text-gray-500">No requests</div>'
        
        requests_list = response.json()
        pending = [r for r in requests_list if r['status'] == 'pending']
        
        if not pending:
            return '<div class="p-8 text-center text-gray-500 dark:text-gray-400">No pending requests</div>'
        
        html = '<div class="divide-y divide-gray-200 dark:divide-gray-700">'
        for req in pending:
            safe_txid = escape_js(req['transaction_id'])
            html += f'''
            <div class="p-4">
                <div class="flex justify-between items-start">
                    <div>
                        <p class="font-medium text-gray-900 dark:text-white">{req['subject']}</p>
                        <p class="text-sm text-gray-500">From: {req['client_ip']}</p>
                        <p class="text-xs text-gray-400">{req['created_at']}</p>
                    </div>
                    <div class="flex space-x-2">
                        <button onclick="approveSCEP('{safe_txid}')"
                                class="btn btn-success text-sm">
                            Approve
                        </button>
                        <button onclick="rejectSCEP('{safe_txid}')"
                                class="btn btn-danger text-sm">
                            Reject
                        </button>
                    </div>
                </div>
            </div>
            '''
        html += '</div>'
        
        html += f'''
        <script>
        function approveSCEP(txid) {{
            fetch('/scep/requests/' + txid + '/approve', {{
                method: 'POST',
                headers: {{ 'Authorization': 'Bearer {token}', 'Content-Type': 'application/json' }}
            }})
            .then(r => r.json())
            .then(() => {{ showToast('Request approved', 'success'); htmx.trigger('body', 'refreshSCEP'); }})
            .catch(e => showToast('Error: ' + e, 'error'));
        }}
        
        function rejectSCEP(txid) {{
            fetch('/scep/requests/' + txid + '/reject', {{
                method: 'POST',
                headers: {{ 'Authorization': 'Bearer {token}', 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ reason: 'Rejected by administrator' }})
            }})
            .then(r => r.json())
            .then(() => {{ showToast('Request rejected', 'success'); htmx.trigger('body', 'refreshSCEP'); }})
            .catch(e => showToast('Error: ' + e, 'error'));
        }}
        </script>
        '''
        
        return html
    except Exception as e:
        return f'<div class="p-8 text-red-600">Error: {str(e)}</div>'


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
        token = session.get('access_token')
        import sys
        sys.stderr.write(f"DEBUG import_config_form: Token={token[:30] if token else 'None'}...\n")
        sys.stderr.flush()
        
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/import/config",
            headers=headers,
            verify=False
        )
        
        config = response.json() if response.status_code == 200 else {}
        auth_method = config.get('auth_method', 'web')
        
        html = f'''
        <form hx-post="/api/ui/import/save" hx-swap="none" 
              hx-on::after-request="if(event.detail.successful) window.showToast('Configuration saved successfully', 'success')">
            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">OPNsense URL</label>
                    <input type="url" name="base_url" value="{config.get('base_url', 'https://network')}" required
                           class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
                </div>
                
                <!-- API Key Authentication (only method) -->
                <input type="hidden" name="auth_method" value="api">
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">API Key</label>
                        <input type="text" name="api_key" value="{config.get('api_key', '')}" required
                               class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">API Secret</label>
                        <input type="password" name="api_secret" required
                               class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white">
                    </div>
                </div>
                <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    <i class="fas fa-info-circle"></i> Create API key in OPNsense: System → Access → Users → Edit user → API keys
                </p>
                
                <div class="flex space-x-3">
                    <button type="submit" class="btn btn-primary" id="save-config-btn">
                        Save Configuration
                    </button>
                    <button type="button" onclick="testImportConnection()"
                            class="btn btn-success">
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
        return f'<p class="text-red-600">Error: {str(e)}</p>'


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
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/import/history",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<div class="p-8 text-center text-gray-500">No history</div>'
        
        data = response.json()
        total = data['cas']['count'] + data['certs']['count']
        
        if total == 0:
            return '<div class="p-8 text-center text-gray-500 dark:text-gray-400">No imported items</div>'
        
        return f'''
        <div class="p-6">
            <div class="grid grid-cols-2 gap-4">
                <div class="text-center p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                    <p class="text-2xl font-bold text-blue-600 dark:text-blue-400">{data['cas']['count']}</p>
                    <p class="text-sm text-gray-600 dark:text-gray-400">Imported CAs</p>
                </div>
                <div class="text-center p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
                    <p class="text-2xl font-bold text-green-600 dark:text-green-400">{data['certs']['count']}</p>
                    <p class="text-sm text-gray-600 dark:text-gray-400">Imported Certificates</p>
                </div>
            </div>
        </div>
        '''
    except Exception as e:
        return f'<div class="p-8 text-red-600">Error: {str(e)}</div>'


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


@ui_bp.route('/api/ui/ca/import', methods=['POST'])
@login_required
def import_ca_manual():
    """Manual CA import endpoint"""
    try:
        data = request.get_json()
        import_method = data.get('import_method', 'paste')
        
        # Prepare payload for backend API
        payload = {
            'descr': data.get('description', 'Imported CA'),
            'trust': 'enabled',  # Default trust level
        }
        
        if import_method == 'container':
            # Container import
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
                        
                        cert_pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
                        key_pem = None
                        if private_key:
                            key_pem = private_key.private_bytes(
                                encoding=serialization.Encoding.PEM,
                                format=serialization.PrivateFormat.PKCS8,
                                encryption_algorithm=serialization.NoEncryption()
                            ).decode()
                        
                        payload['crt'] = cert_pem
                        payload['prv'] = key_pem
                    except Exception as e:
                        if container_format == 'pkcs12':
                            raise
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
                    except:
                        pass
                
                if 'crt' not in payload:
                    return jsonify({'error': 'Unable to parse container file'}), 400
                    
            except Exception as e:
                return jsonify({'error': f'Container parsing failed: {str(e)}'}), 400
        else:
            # PEM paste or upload
            payload['crt'] = data.get('certificate')
            payload['prv'] = data.get('private_key')  # Optional for CAs
            
            if not payload['crt']:
                return jsonify({'error': 'CA certificate is required'}), 400
        
        # Get access token and call backend API
        token = session.get('access_token')
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Call the CA creation endpoint
        response = requests.post(
            f"{request.url_root}api/v1/ca",
            headers=headers,
            json=payload,
            verify=False
        )
        
        if response.status_code in [200, 201]:
            return jsonify({'success': True, 'message': 'CA imported successfully'}), 200
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
            return '<div class="text-yellow-600">No HTTPS certificate found</div>'
        
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
        <dl class="grid grid-cols-1 gap-4">
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Subject</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white font-mono">{subject}</dd>
            </div>
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Issuer</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white font-mono">{issuer}</dd>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Valid From</dt>
                    <dd class="mt-1 text-sm text-gray-900 dark:text-white">{not_before}</dd>
                </div>
                <div>
                    <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Valid Until</dt>
                    <dd class="mt-1 text-sm text-gray-900 dark:text-white">{not_after}</dd>
                </div>
            </div>
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Serial Number</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white font-mono">{serial}</dd>
            </div>
        </dl>
        '''
    except Exception as e:
        return f'<div class="text-red-600">Error: {str(e)}</div>'


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
        
        flash('HTTPS certificate regenerated. Please restart the server.', 'success')
        return '', 200
    except Exception as e:
        flash(f'Error regenerating certificate: {str(e)}', 'error')
        return str(e), 500


@ui_bp.route('/api/ui/config/users')
@login_required
def config_users():
    """Get users list"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/auth/users",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<div class="p-8 text-center text-gray-500">No users</div>'
        
        users = response.json()
        
        html = '''
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead class="bg-gray-50 dark:bg-gray-700">
                    <tr>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
        '''
        
        for user in users:
            html += f'''
                    <tr>
                        <td>{user['username']}</td>
                        <td>{user['email']}</td>
                        <td>
                            <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-100">
                                {user['role']}
                            </span>
                        </td>
                        <td>
                            <button onclick="$dispatch('open-modal', {{ modal: 'changePasswordModal', userId: {user['id']} }})"
                                    class="text-blue-600 hover:text-blue-900 dark:text-blue-400 dark:hover:text-blue-300 mr-3">
                                Change Password
                            </button>
            '''
            
            if user['username'] != 'admin':
                html += f'''
                            <button hx-delete="/api/ui/config/user/{user['id']}"
                                    hx-confirm="Delete user {user['username']}?"
                                    hx-swap="none"
                                    class="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300">
                                Delete
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
        return f'<div class="p-8 text-red-600">Error: {str(e)}</div>'


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
        password = request.form.get('password')
        
        response = requests.put(
            f"{request.url_root}api/v1/auth/users/{user_id}",
            headers=headers,
            json={'password': password},
            verify=False
        )
        
        if response.status_code == 200:
            flash('Password changed successfully', 'success')
            return '<script>htmx.trigger("body", "refreshUsers")</script>', 200
        else:
            error_msg = response.json().get('error', 'Unknown error')
            flash(f'Error changing password: {error_msg}', 'error')
            return '', response.status_code
    except Exception as e:
        flash(f'Error changing password: {str(e)}', 'error')
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
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/system/stats",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<div class="text-red-600">Error loading stats</div>'
        
        stats = response.json()
        
        # Get database file size
        import os
        db_path = str(Config.DATABASE_PATH)
        db_size = 0
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path) / (1024 * 1024)  # MB
        
        return f'''
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg">
                <p class="text-2xl font-bold text-blue-600 dark:text-blue-400">{stats.get('cas', 0)}</p>
                <p class="text-sm text-gray-600 dark:text-gray-400">CAs</p>
            </div>
            <div class="bg-green-50 dark:bg-green-900/20 p-4 rounded-lg">
                <p class="text-2xl font-bold text-green-600 dark:text-green-400">{stats.get('certificates', 0)}</p>
                <p class="text-sm text-gray-600 dark:text-gray-400">Certificates</p>
            </div>
            <div class="bg-purple-50 dark:bg-purple-900/20 p-4 rounded-lg">
                <p class="text-2xl font-bold text-purple-600 dark:text-purple-400">{stats.get('users', 0)}</p>
                <p class="text-sm text-gray-600 dark:text-gray-400">Users</p>
            </div>
            <div class="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded-lg">
                <p class="text-2xl font-bold text-yellow-600 dark:text-yellow-400">{db_size:.2f} MB</p>
                <p class="text-sm text-gray-600 dark:text-gray-400">Database Size</p>
            </div>
        </div>
        '''
    except Exception as e:
        return f'<div class="text-red-600">Error: {str(e)}</div>'


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
        <dl class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Version</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white">UCM 1.0.0</dd>
            </div>
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Python Version</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white">{platform.python_version()}</dd>
            </div>
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Operating System</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white">{platform.system()} {platform.release()}</dd>
            </div>
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Uptime</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white">{uptime_hours}h {uptime_minutes}m</dd>
            </div>
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Database Path</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white font-mono">''' + str(Config.DATABASE_PATH) + '''</dd>
            </div>
            <div>
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Data Directory</dt>
                <dd class="mt-1 text-sm text-gray-900 dark:text-white font-mono">''' + str(DATA_DIR) + '''/</dd>
            </div>
        </dl>
        '''
    except Exception as e:
        return f'<div class="text-red-600">Error: {str(e)}</div>'


# CA Detail Pages
@ui_bp.route('/ca/<ca_id>')
@login_required
def ca_detail(ca_id):
    """View CA details"""
    try:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/ca/{ca_id}",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            flash('CA not found', 'error')
            return redirect(url_for('ui.ca_list'))
        
        ca = response.json()
        return render_template('ca/detail.html', ca=ca)
    except Exception as e:
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
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/certificates/{cert_id}",
            headers=headers,
            verify=False
        )
        
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
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        response = requests.get(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<div class="p-8 text-center text-gray-500">No certificates</div>'
        
        all_certs = response.json()
        ca_certs = [c for c in all_certs if c.get('ca_id') == ca_id]
        
        if not ca_certs:
            return '<div class="p-8 text-center text-gray-500 dark:text-gray-400">No certificates issued by this CA</div>'
        
        html = '''
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead class="bg-gray-50 dark:bg-gray-700">
                    <tr>
                        <th>Subject</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Valid Until</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
        '''
        
        for cert in ca_certs:
            # Badge for status instead of just icon
            status_badge = {
                'active': '<span class="badge-outline badge-success"><i class="fas fa-circle-check"></i> Active</span>',
                'revoked': '<span class="badge-outline badge-danger"><i class="fas fa-ban"></i> Revoked</span>',
                'pending': '<span class="badge-outline badge-warning"><i class="fas fa-clock"></i> Pending</span>'
            }.get(cert.get('status', 'active'), '<span class="badge-outline badge-secondary"><i class="fas fa-circle"></i> Unknown</span>')
            
            html += f'''
                <tr>
                    <td>
                        <a href="/certificates/{cert['id']}" class="text-blue-600 hover:text-blue-900 dark:text-blue-400 dark:hover:text-blue-300 font-medium">
                            {cert.get('common_name', cert.get('subject', 'N/A'))}
                        </a>
                    </td>
                    <td>
                        {cert.get('cert_type', 'server')}
                    </td>
                    <td>
                        {status_badge}
                    </td>
                    <td>
                        {cert.get('not_valid_after', 'N/A')[:10] if cert.get('not_valid_after') else 'N/A'}
                    </td>
                    <td>
                        <a href="/certificates/{cert['id']}" class="text-blue-600 hover:text-blue-900 dark:text-blue-400 dark:hover:text-blue-300">
                            View
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
        return f'<div class="p-8 text-red-600">Error: {str(e)}</div>'


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
            
            flash('HTTPS certificate imported successfully. Please restart the server.', 'success')
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


@ui_bp.route('/api/ui/config/managed-certs-list')
@login_required
def managed_certs_list():
    """Get list of managed certificates suitable for HTTPS"""
    try:
        token = session.get('access_token')
        if not token:
            return '<div class="p-8 text-center text-red-600">Session expired</div>'
        
        headers = {'Authorization': f'Bearer {token}'}
        
        # Get all certificates via API
        response = requests.get(
            f"{request.url_root}api/v1/certificates/",
            headers=headers,
            verify=False
        )
        
        if response.status_code != 200:
            return '<div class="p-8 text-center text-red-600">Failed to load certificates</div>'
        
        from datetime import datetime
        now = datetime.utcnow()
        
        # Filter valid certs (not CSRs, not revoked)
        all_certs = response.json()
        # A certificate is valid if it has a serial number and valid dates (not a CSR)
        certs = [c for c in all_certs 
                if not c.get('revoked', False) 
                and c.get('serial_number') 
                and c.get('valid_from')
                and c.get('has_private_key', False)]  # Need private key for HTTPS
        
        # Sort by expiration
        certs.sort(key=lambda x: x.get('valid_to', ''), reverse=True)
        
        if not certs:
            return '''
            <div class="text-center py-8">
                <i class="fas fa-certificate text-gray-400 text-4xl mb-3"></i>
                <p class="text-gray-500 dark:text-gray-400">No valid certificates found</p>
                <p class="text-sm text-gray-400 dark:text-gray-500 mt-2">Create a certificate first, then select it here</p>
            </div>
            '''
        
        html = '''
        <div class="overflow-y-auto max-h-96">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead class="bg-gray-50 dark:bg-gray-700 sticky top-0">
                    <tr>
                        <th>Subject</th>
                        <th>Valid Until</th>
                        <th>Type</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
        '''
        
        for cert in certs:
            # Parse subject for CN
            subject = cert.get('subject', '')
            cn = cert.get('descr', 'Unknown')
            if 'CN=' in subject:
                for part in subject.split(','):
                    if 'CN=' in part:
                        cn = part.split('CN=')[1].strip()
                        break
            
            # Format date
            valid_to = cert.get('valid_to', '')[:10] if cert.get('valid_to') else 'N/A'
            
            # Calculate days left
            try:
                from datetime import datetime
                if cert.get('valid_to'):
                    exp_date = datetime.fromisoformat(cert['valid_to'].replace('Z', '+00:00'))
                    days_left = (exp_date - datetime.utcnow().replace(tzinfo=exp_date.tzinfo)).days
                else:
                    days_left = 0
            except:
                days_left = 0
            
            # Color based on days left
            if days_left < 30:
                date_class = 'text-red-600 dark:text-red-400'
            elif days_left < 90:
                date_class = 'text-yellow-600 dark:text-yellow-400'
            else:
                date_class = 'text-green-600 dark:text-green-400'
            
            cert_type = cert.get('cert_type', 'unknown')
            
            # Check if has private key (from API)
            has_key = cert.get('has_private_key', False)
            
            html += f'''
                <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                    <td>
                        <div class="flex items-center">
                            <i class="fas fa-certificate text-blue-500 mr-2"></i>
                            {cn}
                        </div>
                        <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
                            {'ID: ' + str(cert.get('id', 'N/A'))}
                        </div>
                    </td>
                    <td>
                        {valid_to}
                        <div class="text-xs text-gray-500 dark:text-gray-400">({days_left} days)</div>
                    </td>
                    <td>
                        <span>
                            {cert_type}
                        </span>
                    </td>
                    <td>
            '''
            
            if has_key:
                html += f'''
                        <button hx-post="/api/ui/config/use-managed-cert/{cert['id']}" 
                                hx-confirm="Use this certificate for HTTPS? The server will restart."
                                hx-swap="none"
                                @htmx:after-request="if($event.detail.successful) {{ showToast('Certificate applied successfully! Please restart the server.', 'success'); $dispatch('close-modal'); }}"
                                class="btn btn-success text-xs">
                            <i class="fas fa-check mr-1"></i>Use This
                        </button>
                '''
            else:
                html += '''
                        <span class="" title="Private key not available">
                            <i class="fas fa-key-skeleton mr-1"></i>No Key
                        </span>
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
        return f'<div class="p-8 text-red-600">Error: {str(e)}</div>'


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
            
            flash('HTTPS certificate updated successfully. Please restart the server.', 'success')
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
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th>CA Name</th>
                        <th>OCSP Status</th>
                        <th>OCSP URL</th>
                        <th>Cached Responses</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
        '''
        
        for ca in cas:
            cached_count = OCSPResponse.query.filter_by(ca_id=ca.id).count()
            
            status_badge = ''
            if ca.ocsp_enabled:
                status_badge = '<span class="badge badge-success"><i class="fas fa-check mr-1"></i>Enabled</span>'
            else:
                status_badge = '<span class="badge badge-secondary"><i class="fas fa-times mr-1"></i>Disabled</span>'
            
            ocsp_url_display = ca.ocsp_url if ca.ocsp_url else '<span class="text-gray-400">Not configured</span>'
            
            html += f'''
                <tr>
                    <td>
                        <div class="font-medium">{ca.descr}</div>
                        <div class="text-xs text-gray-500">{ca.refid}</div>
                    </td>
                    <td>{status_badge}</td>
                    <td><code class="text-xs">{ocsp_url_display}</code></td>
                    <td class="text-center">{cached_count}</td>
                    <td>
                        <a href="/ca/{ca.id}" class="text-blue-600 hover:text-blue-800 text-sm">
                            <i class="fas fa-cog mr-1"></i>Configure
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
        return f'<div class="text-red-600">Error loading OCSP status: {str(e)}</div>'


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
        return '<span class="text-red-600">Error</span>'


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
    
    cert_path = Path('/opt/ucm/backend/data/https_cert.pem')
    
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
        
        # Format expiry date (compatible with all cryptography versions)
        expires = cert.not_valid_after.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        cert_type = 'Self-Signed' if source == 'auto' else 'UCM Managed'
        
        result = {
            'type': cert_type,
            'subject': subject_str,
            'expires': expires,
            'source': source,
            'issuer': cert.issuer.rfc4514_string()
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
        key_path = Path(f'/opt/ucm/backend/data/private/cert_{cert.refid}.key')
        if not key_path.exists():
            # Try refid-based naming
            key_path = Path(f'/opt/ucm/backend/data/private/{cert.refid}.key')
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
            cert_file = Path(f'/opt/ucm/backend/data/certs/{cert.refid}.crt')
            
            key_file = Path(f'/opt/ucm/backend/data/private/{cert.refid}.key')
            
            if not cert_file.exists() or not key_file.exists():
                return jsonify({'success': False, 'error': 'Certificate or key file not found'}), 404
            
            # Copy to HTTPS location
            https_cert = Path('/opt/ucm/backend/data/https_cert.pem')
            https_key = Path('/opt/ucm/backend/data/https_key.pem')
            
            # Backup current cert
            if https_cert.exists():
                shutil.copy(https_cert, str(https_cert) + '.backup')
            if https_key.exists():
                shutil.copy(https_key, str(https_key) + '.backup')
            
            # Copy new cert
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
                cert_id_config = SystemConfig(key='https_cert_id', value=str(cert_id))
                db.session.add(cert_id_config)
            else:
                cert_id_config.value = str(cert_id)
            
            db.session.commit()
            
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
        subprocess.Popen(['systemctl', 'restart', 'ucm'])
        
        return jsonify({'success': True}), 200
        
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
        cert_path = Path('/opt/ucm/backend/data/https_cert.pem')
        key_path = Path('/opt/ucm/backend/data/https_key.pem')
        
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
        subprocess.Popen(['systemctl', 'restart', 'ucm'])
        
        return jsonify({'success': True}), 200
        
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
            <div class="text-center p-8">
                <i class="bi bi-person-badge fs-1 text-muted"></i>
                <p class="mt-3 text-muted">No ACME accounts yet</p>
                <small>Accounts will appear here when ACME clients register</small>
            </div>
            '''
        
        html = '''
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Account ID</th>
                        <th>Status</th>
                        <th>Contacts</th>
                        <th>JWK Thumbprint</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for account in accounts:
            status_badge = 'success' if account[2] == 'valid' else 'secondary'
            contacts = account[3] or '[]'
            created = datetime.fromisoformat(account[4]).strftime('%Y-%m-%d %H:%M')
            
            html += f'''
                <tr>
                    <td><code class="small">{account[1][:24]}...</code></td>
                    <td><span class="badge bg-{status_badge}">{account[2]}</span></td>
                    <td class="small">{contacts}</td>
                    <td><code class="small">{account[5]}...</code></td>
                    <td>{created}</td>
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
            <div class="text-center p-8">
                <i class="bi bi-file-earmark-text fs-1 text-muted"></i>
                <p class="mt-3 text-muted">No ACME orders yet</p>
                <small>Orders will appear here when certificates are requested</small>
            </div>
            '''
        
        html = '''
        <div class="table-responsive">
            <table class="table table-hover">
                <thead>
                    <tr>
                        <th>Order ID</th>
                        <th>Status</th>
                        <th>Identifiers</th>
                        <th>Account</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for order in orders:
            status_colors = {
                'pending': 'warning',
                'ready': 'info',
                'processing': 'primary',
                'valid': 'success',
                'invalid': 'danger'
            }
            status_badge = status_colors.get(order[2], 'secondary')
            created = datetime.fromisoformat(order[4]).strftime('%Y-%m-%d %H:%M')
            
            html += f'''
                <tr>
                    <td><code class="small">{order[1][:24]}...</code></td>
                    <td><span class="badge bg-{status_badge}">{order[2]}</span></td>
                    <td class="small">{order[3]}</td>
                    <td><code class="small">{order[5][:16] if order[5] else 'N/A'}...</code></td>
                    <td>{created}</td>
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
