#!/usr/bin/env python3
"""
UCM v2.0.0 - Comprehensive E2E Test Suite
Tests all API endpoints and features

Usage:
    python3 e2e_test_suite.py [--base-url URL] [--verbose]
"""

import requests
import json
import time
import sys
import argparse
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

# Disable SSL warnings for self-signed certs
requests.packages.urllib3.disable_warnings()


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


class TestResult:
    def __init__(self, name: str, passed: bool, message: str = "", duration_ms: float = 0):
        self.name = name
        self.passed = passed
        self.message = message
        self.duration_ms = duration_ms


class UCMTestSuite:
    """Comprehensive E2E test suite for UCM v2.0.0"""
    
    def __init__(self, base_url: str = "https://localhost:8443", verbose: bool = False):
        self.base_url = base_url.rstrip('/')
        self.verbose = verbose
        self.session = requests.Session()
        self.session.verify = False
        self.results: List[TestResult] = []
        self.csrf_token: Optional[str] = None
        
        # Test data tracking for cleanup
        self.created_users: List[int] = []
        self.created_cas: List[str] = []
        self.created_certs: List[str] = []
        self.created_groups: List[int] = []
        self.created_roles: List[int] = []
    
    def log(self, msg: str):
        if self.verbose:
            print(f"  {Colors.BLUE}→{Colors.END} {msg}")
    
    def api(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make API request with CSRF token"""
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop('headers', {})
        
        if self.csrf_token and method.upper() in ['POST', 'PUT', 'DELETE', 'PATCH']:
            headers['X-CSRF-Token'] = self.csrf_token
        
        return self.session.request(method, url, headers=headers, **kwargs)
    
    def run_test(self, name: str, test_func) -> TestResult:
        """Run a single test and record result"""
        start = time.time()
        try:
            passed, message = test_func()
            duration = (time.time() - start) * 1000
            result = TestResult(name, passed, message, duration)
        except Exception as e:
            duration = (time.time() - start) * 1000
            result = TestResult(name, False, f"Exception: {str(e)}", duration)
        
        self.results.append(result)
        
        status = f"{Colors.GREEN}✓{Colors.END}" if result.passed else f"{Colors.RED}✗{Colors.END}"
        print(f"  {status} {name} ({result.duration_ms:.0f}ms)")
        if not result.passed and result.message:
            print(f"      {Colors.RED}{result.message}{Colors.END}")
        
        return result
    
    # ==================== AUTHENTICATION TESTS ====================
    
    def test_login_success(self) -> Tuple[bool, str]:
        """Test successful login"""
        r = self.api('POST', '/api/v2/auth/login', json={
            'username': 'admin',
            'password': 'changeme123'
        })
        if r.status_code != 200:
            return False, f"Status {r.status_code}: {r.text[:100]}"
        
        data = r.json().get('data', {})
        self.csrf_token = data.get('csrf_token')
        
        if not data.get('user'):
            return False, "No user data returned"
        if not self.csrf_token:
            return False, "No CSRF token returned"
        
        return True, ""
    
    def test_login_failure(self) -> Tuple[bool, str]:
        """Test login with wrong password"""
        r = self.api('POST', '/api/v2/auth/login', json={
            'username': 'admin',
            'password': 'wrongpassword'
        })
        if r.status_code != 401:
            return False, f"Expected 401, got {r.status_code}"
        return True, ""
    
    def test_session_verify(self) -> Tuple[bool, str]:
        """Test session verification"""
        r = self.api('GET', '/api/v2/auth/verify')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        if not data.get('authenticated'):
            return False, "Not authenticated"
        return True, ""
    
    def test_logout(self) -> Tuple[bool, str]:
        """Test logout"""
        r = self.api('POST', '/api/v2/auth/logout')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_relogin(self) -> Tuple[bool, str]:
        """Re-login for subsequent tests"""
        return self.test_login_success()
    
    # ==================== USER MANAGEMENT TESTS ====================
    
    def test_list_users(self) -> Tuple[bool, str]:
        """Test listing users"""
        r = self.api('GET', '/api/v2/users')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        if not isinstance(data, list):
            return False, "Response is not a list"
        return True, f"Found {len(data)} users"
    
    def test_create_user(self) -> Tuple[bool, str]:
        """Test creating a user"""
        username = f"testuser_{int(time.time())}"
        r = self.api('POST', '/api/v2/users', json={
            'username': username,
            'email': f'{username}@test.local',
            'password': 'Test@Pass123!',
            'role': 'viewer'
        })
        if r.status_code != 201:
            return False, f"Status {r.status_code}: {r.text[:100]}"
        
        user_id = r.json().get('data', {}).get('id')
        if user_id:
            self.created_users.append(user_id)
        return True, f"Created user id={user_id}"
    
    def test_password_policy(self) -> Tuple[bool, str]:
        """Test password policy endpoint"""
        r = self.api('GET', '/api/v2/users/password-policy')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        if 'min_length' not in data:
            return False, "Missing min_length"
        return True, ""
    
    def test_password_strength(self) -> Tuple[bool, str]:
        """Test password strength check"""
        # Weak password
        r = self.api('POST', '/api/v2/users/password-strength', json={'password': 'weak'})
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        # Weak password should have low score or not meet requirements
        if data.get('score', 100) >= 80:
            return False, "Weak password should have low score"
        
        # Strong password
        r = self.api('POST', '/api/v2/users/password-strength', json={'password': 'Str0ng@Pass#2024'})
        data = r.json().get('data', {})
        if data.get('score', 0) < 60:
            return False, "Strong password should have high score"
        
        return True, ""
    
    def test_weak_password_rejected(self) -> Tuple[bool, str]:
        """Test that weak passwords are rejected on user creation"""
        r = self.api('POST', '/api/v2/users', json={
            'username': f'weakpw_{int(time.time())}',
            'email': 'weakpw@test.local',
            'password': 'weak',
            'role': 'viewer'
        })
        if r.status_code == 201:
            # Cleanup if accidentally created
            user_id = r.json().get('data', {}).get('id')
            if user_id:
                self.api('DELETE', f'/api/v2/users/{user_id}')
            return False, "Weak password was accepted"
        return True, ""
    
    # ==================== CA MANAGEMENT TESTS ====================
    
    def test_list_cas(self) -> Tuple[bool, str]:
        """Test listing CAs"""
        r = self.api('GET', '/api/v2/cas')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} CAs"
    
    def test_create_root_ca(self) -> Tuple[bool, str]:
        """Test creating a root CA"""
        ca_name = f"Test-Root-CA-{int(time.time())}"
        r = self.api('POST', '/api/v2/cas', json={
            'commonName': ca_name,
            'organization': 'Test Org',
            'country': 'US',
            'keyAlgo': 'RSA',
            'keySize': 2048,
            'validityYears': 10,
            'type': 'root'
        })
        if r.status_code not in [200, 201]:
            return False, f"Status {r.status_code}: {r.text[:100]}"
        
        data = r.json().get('data', {})
        ca_id = data.get('id')  # Numeric ID
        refid = data.get('refid')  # UUID
        if ca_id:
            self.created_cas.append(str(ca_id))  # Store numeric ID as string
        return True, f"Created CA id={ca_id}"
    
    def test_get_ca_details(self) -> Tuple[bool, str]:
        """Test getting CA details"""
        if not self.created_cas:
            return False, "No CA created to test"
        
        r = self.api('GET', f'/api/v2/cas/{self.created_cas[0]}')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        if not data.get('descr'):
            return False, "No description in response"
        return True, ""
    
    def test_export_ca(self) -> Tuple[bool, str]:
        """Test exporting CA certificate"""
        if not self.created_cas:
            return False, "No CA created to test"
        
        r = self.api('GET', f'/api/v2/cas/{self.created_cas[0]}/export?format=pem')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    # ==================== CERTIFICATE TESTS ====================
    
    def test_list_certificates(self) -> Tuple[bool, str]:
        """Test listing certificates"""
        r = self.api('GET', '/api/v2/certificates')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} certificates"
    
    def test_issue_certificate(self) -> Tuple[bool, str]:
        """Test issuing a certificate"""
        if not self.created_cas:
            return False, "No CA available for signing"
        
        cert_name = f"test-cert-{int(time.time())}"
        r = self.api('POST', '/api/v2/certificates', json={
            'cn': f'{cert_name}.local',
            'ca_id': int(self.created_cas[0]),  # Use numeric CA ID
            'key_type': 'RSA',
            'key_size': 2048,
            'validity_days': 365,
            'cert_type': 'server',
            'san': [f'DNS:{cert_name}.local']
        })
        if r.status_code not in [200, 201]:
            return False, f"Status {r.status_code}: {r.text[:100]}"
        
        data = r.json().get('data', {})
        cert_id = data.get('id')  # Numeric ID
        if cert_id:
            self.created_certs.append(str(cert_id))
        return True, f"Issued cert id={cert_id}"
    
    def test_get_certificate(self) -> Tuple[bool, str]:
        """Test getting certificate details"""
        if not self.created_certs:
            return False, "No certificate created"
        
        r = self.api('GET', f'/api/v2/certificates/{self.created_certs[0]}')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_export_certificate(self) -> Tuple[bool, str]:
        """Test exporting certificate"""
        if not self.created_certs:
            return False, "No certificate created"
        
        r = self.api('GET', f'/api/v2/certificates/{self.created_certs[0]}/export?format=pem')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_revoke_certificate(self) -> Tuple[bool, str]:
        """Test revoking a certificate"""
        if not self.created_certs:
            return False, "No certificate created"
        
        r = self.api('POST', f'/api/v2/certificates/{self.created_certs[0]}/revoke', json={
            'reason': 'testing'
        })
        if r.status_code != 200:
            return False, f"Status {r.status_code}: {r.text[:100]}"
        return True, ""
    
    # ==================== SECURITY TESTS ====================
    
    def test_encryption_status(self) -> Tuple[bool, str]:
        """Test encryption status endpoint"""
        r = self.api('GET', '/api/v2/system/security/encryption-status')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        # Just check it returns valid data
        return True, f"Encryption enabled: {data.get('encryption_enabled')}"
    
    def test_rate_limit_config(self) -> Tuple[bool, str]:
        """Test rate limit config endpoint"""
        r = self.api('GET', '/api/v2/system/security/rate-limit')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        if 'config' not in data:
            return False, "Missing config"
        return True, ""
    
    def test_audit_retention(self) -> Tuple[bool, str]:
        """Test audit retention endpoint"""
        r = self.api('GET', '/api/v2/system/audit/retention')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        if 'retention_days' not in data:
            return False, "Missing retention_days"
        return True, f"Retention: {data.get('retention_days')} days"
    
    def test_expiry_alerts(self) -> Tuple[bool, str]:
        """Test expiry alerts endpoint"""
        r = self.api('GET', '/api/v2/system/alerts/expiry')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        if 'alert_days' not in data:
            return False, "Missing alert_days"
        return True, ""
    
    def test_expiring_certs(self) -> Tuple[bool, str]:
        """Test expiring certificates endpoint"""
        r = self.api('GET', '/api/v2/system/alerts/expiring-certs?days=365')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} expiring certs"
    
    # ==================== EXTENDED FEATURES TESTS ====================
    
    def test_list_groups(self) -> Tuple[bool, str]:
        """Test listing groups (Extended)"""
        r = self.api('GET', '/api/v2/groups')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} groups"
    
    def test_create_group(self) -> Tuple[bool, str]:
        """Test creating a group (Extended)"""
        r = self.api('POST', '/api/v2/groups', json={
            'name': f'Test-Group-{int(time.time())}',
            'description': 'E2E test group',
            'permissions': ['read:certs', 'read:cas']
        })
        if r.status_code not in [200, 201]:
            return False, f"Status {r.status_code}: {r.text[:100]}"
        
        group_id = r.json().get('data', {}).get('id')
        if group_id:
            self.created_groups.append(group_id)
        return True, f"Created group id={group_id}"
    
    def test_list_rbac_roles(self) -> Tuple[bool, str]:
        """Test listing RBAC roles (Extended)"""
        r = self.api('GET', '/api/v2/rbac/roles')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} roles"
    
    def test_list_hsm(self) -> Tuple[bool, str]:
        """Test listing HSM configurations (Extended)"""
        r = self.api('GET', '/api/v2/hsm/providers')
        if r.status_code == 404:
            return True, "HSM endpoint not found (expected in community)"
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} HSM providers"
    
    def test_list_sso(self) -> Tuple[bool, str]:
        """Test listing SSO providers (Extended)"""
        r = self.api('GET', '/api/v2/sso/providers')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} SSO providers"
    
    # ==================== SETTINGS & SYSTEM TESTS ====================
    
    def test_get_settings(self) -> Tuple[bool, str]:
        """Test getting settings"""
        r = self.api('GET', '/api/v2/settings')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_db_stats(self) -> Tuple[bool, str]:
        """Test database stats"""
        r = self.api('GET', '/api/v2/system/db/stats')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', {})
        if 'size_mb' not in data:
            return False, "Missing size_mb"
        return True, f"DB size: {data.get('size_mb')} MB"
    
    def test_list_backups(self) -> Tuple[bool, str]:
        """Test listing backups"""
        r = self.api('GET', '/api/v2/system/backups')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} backups"
    
    def test_audit_logs(self) -> Tuple[bool, str]:
        """Test audit logs"""
        r = self.api('GET', '/api/v2/audit/logs')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} audit entries"
    
    def test_dashboard_stats(self) -> Tuple[bool, str]:
        """Test dashboard stats"""
        r = self.api('GET', '/api/v2/dashboard/stats')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_templates(self) -> Tuple[bool, str]:
        """Test templates endpoint"""
        r = self.api('GET', '/api/v2/templates')
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json().get('data', [])
        return True, f"Found {len(data)} templates"
    
    # ==================== PROTOCOL TESTS ====================
    
    def test_crl_endpoint(self) -> Tuple[bool, str]:
        """Test CRL distribution point"""
        r = self.session.get(f"{self.base_url}/cdp/", verify=False)
        # 404 is OK if no CAs, we just check it's reachable
        if r.status_code not in [200, 404]:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_ocsp_health(self) -> Tuple[bool, str]:
        """Test OCSP responder health"""
        r = self.session.get(f"{self.base_url}/ocsp/health", verify=False)
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_acme_directory(self) -> Tuple[bool, str]:
        """Test ACME directory"""
        r = self.session.get(f"{self.base_url}/acme/directory", verify=False)
        if r.status_code == 404:
            return True, "ACME not configured (expected if no ACME CA)"
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        try:
            data = r.json()
            if 'newAccount' not in data:
                return False, "Missing newAccount in directory"
        except:
            return True, "ACME returned non-JSON (might be HTML error)"
        return True, ""
    
    def test_scep_capabilities(self) -> Tuple[bool, str]:
        """Test SCEP GetCACaps"""
        r = self.session.get(f"{self.base_url}/scep/pkiclient.exe?operation=GetCACaps", verify=False)
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        return True, ""
    
    def test_health_endpoint(self) -> Tuple[bool, str]:
        """Test health check"""
        r = self.session.get(f"{self.base_url}/api/health", verify=False)
        if r.status_code != 200:
            return False, f"Status {r.status_code}"
        
        data = r.json()
        if data.get('status') != 'ok':
            return False, f"Status not ok: {data.get('status')}"
        return True, ""
    
    # ==================== CLEANUP ====================
    
    def cleanup(self):
        """Clean up test data"""
        print(f"\n{Colors.YELLOW}Cleaning up test data...{Colors.END}")
        
        # Delete created certificates
        for refid in self.created_certs:
            try:
                self.api('DELETE', f'/api/v2/certificates/{refid}')
                self.log(f"Deleted certificate {refid}")
            except:
                pass
        
        # Delete created CAs
        for refid in self.created_cas:
            try:
                self.api('DELETE', f'/api/v2/cas/{refid}')
                self.log(f"Deleted CA {refid}")
            except:
                pass
        
        # Delete created users
        for user_id in self.created_users:
            try:
                self.api('DELETE', f'/api/v2/users/{user_id}')
                self.log(f"Deleted user {user_id}")
            except:
                pass
        
        # Delete created groups
        for group_id in self.created_groups:
            try:
                self.api('DELETE', f'/api/v2/groups/{group_id}')
                self.log(f"Deleted group {group_id}")
            except:
                pass
        
        print(f"  {Colors.GREEN}✓{Colors.END} Cleanup complete")
    
    # ==================== RUN ALL TESTS ====================
    
    def run_all(self):
        """Run all test categories"""
        start_time = time.time()
        
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}  UCM v2.0.0 - E2E Test Suite{Colors.END}")
        print(f"{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"  Target: {self.base_url}")
        print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        # Authentication
        print(f"{Colors.BOLD}🔐 Authentication{Colors.END}")
        self.run_test("Login success", self.test_login_success)
        self.run_test("Login failure (wrong password)", self.test_login_failure)
        self.run_test("Session verify", self.test_session_verify)
        self.run_test("Logout", self.test_logout)
        self.run_test("Re-login", self.test_relogin)
        
        # Users
        print(f"\n{Colors.BOLD}👥 User Management{Colors.END}")
        self.run_test("List users", self.test_list_users)
        self.run_test("Password policy", self.test_password_policy)
        self.run_test("Password strength check", self.test_password_strength)
        self.run_test("Create user", self.test_create_user)
        self.run_test("Weak password rejected", self.test_weak_password_rejected)
        
        # CAs
        print(f"\n{Colors.BOLD}🏛️ Certificate Authorities{Colors.END}")
        self.run_test("List CAs", self.test_list_cas)
        self.run_test("Create root CA", self.test_create_root_ca)
        self.run_test("Get CA details", self.test_get_ca_details)
        self.run_test("Export CA", self.test_export_ca)
        
        # Certificates
        print(f"\n{Colors.BOLD}📜 Certificates{Colors.END}")
        self.run_test("List certificates", self.test_list_certificates)
        self.run_test("Issue certificate", self.test_issue_certificate)
        self.run_test("Get certificate", self.test_get_certificate)
        self.run_test("Export certificate", self.test_export_certificate)
        self.run_test("Revoke certificate", self.test_revoke_certificate)
        
        # Security
        print(f"\n{Colors.BOLD}🔒 Security Features{Colors.END}")
        self.run_test("Encryption status", self.test_encryption_status)
        self.run_test("Rate limit config", self.test_rate_limit_config)
        self.run_test("Audit retention", self.test_audit_retention)
        self.run_test("Expiry alerts config", self.test_expiry_alerts)
        self.run_test("Expiring certificates", self.test_expiring_certs)
        
        # Extended Features
        print(f"\n{Colors.BOLD}⭐ Extended Features{Colors.END}")
        self.run_test("List groups", self.test_list_groups)
        self.run_test("Create group", self.test_create_group)
        self.run_test("List RBAC roles", self.test_list_rbac_roles)
        self.run_test("List HSM configs", self.test_list_hsm)
        self.run_test("List SSO providers", self.test_list_sso)
        
        # Settings & System
        print(f"\n{Colors.BOLD}⚙️ Settings & System{Colors.END}")
        self.run_test("Get settings", self.test_get_settings)
        self.run_test("Database stats", self.test_db_stats)
        self.run_test("List backups", self.test_list_backups)
        self.run_test("Audit logs", self.test_audit_logs)
        self.run_test("Dashboard stats", self.test_dashboard_stats)
        self.run_test("Templates", self.test_templates)
        
        # Protocols
        print(f"\n{Colors.BOLD}🌐 Protocol Endpoints{Colors.END}")
        self.run_test("Health endpoint", self.test_health_endpoint)
        self.run_test("CRL distribution point", self.test_crl_endpoint)
        self.run_test("OCSP health", self.test_ocsp_health)
        self.run_test("ACME directory", self.test_acme_directory)
        self.run_test("SCEP capabilities", self.test_scep_capabilities)
        
        # Cleanup
        self.cleanup()
        
        # Summary
        total_time = time.time() - start_time
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        
        print(f"\n{'='*60}")
        print(f"{Colors.BOLD}  RESULTS SUMMARY{Colors.END}")
        print(f"{'='*60}")
        print(f"  Total tests: {total}")
        print(f"  {Colors.GREEN}Passed: {passed}{Colors.END}")
        print(f"  {Colors.RED}Failed: {failed}{Colors.END}")
        print(f"  Duration: {total_time:.1f}s")
        print(f"{'='*60}")
        
        if failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL TESTS PASSED!{Colors.END}\n")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ {failed} TEST(S) FAILED{Colors.END}")
            print(f"\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")
            print()
        
        return failed == 0


def main():
    parser = argparse.ArgumentParser(description='UCM E2E Test Suite')
    parser.add_argument('--base-url', default='https://localhost:8443', help='UCM base URL')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    suite = UCMTestSuite(base_url=args.base_url, verbose=args.verbose)
    success = suite.run_all()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
