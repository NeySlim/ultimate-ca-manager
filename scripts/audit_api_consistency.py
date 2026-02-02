#!/usr/bin/env python3
"""
API Consistency Audit
Detect mismatches between frontend service calls and backend API endpoints
"""
import re
import os
import sys
import json
from pathlib import Path
from collections import defaultdict

# Colors for terminal output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'

def extract_frontend_calls(frontend_dir):
    """Extract all apiClient calls from frontend services"""
    calls = []
    
    for f in Path(frontend_dir).rglob('*.js'):
        try:
            content = f.read_text()
            
            # Pattern 1: apiClient.method('/static/path')
            pattern1 = r"apiClient\.(get|post|put|patch|delete)\(['\"]([^'\"`\$]+)['\"]"
            for method, path in re.findall(pattern1, content):
                calls.append({
                    'method': method.upper(),
                    'path': path.split('?')[0],  # Remove query params
                    'file': str(f.relative_to(frontend_dir.parent.parent))
                })
            
            # Pattern 2: apiClient.method(`/path/${id}`) - template literals
            pattern2 = r"apiClient\.(get|post|put|patch|delete)\(`([^`]+)`"
            for method, path in re.findall(pattern2, content):
                # Normalize template variables to {id}
                normalized = re.sub(r'\$\{[^}]+\}', '{id}', path)
                normalized = normalized.split('?')[0]  # Remove query params
                calls.append({
                    'method': method.upper(),
                    'path': normalized,
                    'file': str(f.relative_to(frontend_dir.parent.parent))
                })
                
        except Exception as e:
            print(f"Warning: Could not read {f}: {e}")
    
    # Deduplicate
    seen = set()
    unique_calls = []
    for call in calls:
        key = (call['method'], call['path'])
        if key not in seen:
            seen.add(key)
            unique_calls.append(call)
    
    return unique_calls


def extract_backend_routes(backend_dir):
    """Extract all routes from backend Flask blueprints"""
    routes = []
    
    for f in Path(backend_dir).rglob('*.py'):
        try:
            content = f.read_text()
            
            # Find blueprint prefix
            prefix_match = re.search(r"Blueprint\([^,]+,\s*[^,]+,\s*url_prefix=['\"]([^'\"]+)['\"]", content)
            prefix = prefix_match.group(1) if prefix_match else ''
            
            # Pattern for route decorators
            # Matches: @bp.route('/path', methods=['GET', 'POST'])
            # Also matches: @bp.route('/path') (defaults to GET)
            route_pattern = r"@(\w+)\.route\(['\"]([^'\"]+)['\"](?:[^)]*methods=\[([^\]]+)\])?"
            
            for bp_name, path, methods_str in re.findall(route_pattern, content):
                # Default to GET if no methods specified
                if methods_str:
                    methods = re.findall(r"'(\w+)'", methods_str)
                else:
                    methods = ['GET']
                
                # Build full path
                if path.startswith('/api'):
                    full_path = path
                else:
                    full_path = prefix + path
                
                # Normalize path parameters
                full_path = re.sub(r'<(?:int:)?(\w+)>', r'{\1}', full_path)
                full_path = re.sub(r'\{[^}]+\}', '{id}', full_path)
                
                for m in methods:
                    routes.append({
                        'method': m,
                        'path': full_path,
                        'file': str(f.relative_to(backend_dir.parent))
                    })
        except Exception as e:
            print(f"Warning: Could not read {f}: {e}")
    
    return routes


def normalize_path(path):
    """Normalize path for comparison"""
    # Remove /api/v2 prefix
    path = re.sub(r'^/api/v2', '', path)
    # Normalize all path parameters to {id}
    path = re.sub(r'\{[^}]+\}', '{id}', path)
    path = re.sub(r'/\d+', '/{id}', path)
    return path


def find_duplicate_implementations(backend_dir):
    """Find functions that might be duplicated across files"""
    function_locations = defaultdict(list)
    
    for f in Path(backend_dir).rglob('*.py'):
        try:
            content = f.read_text()
            # Find all function definitions
            for match in re.finditer(r"def\s+(\w+)\s*\(", content):
                func_name = match.group(1)
                # Skip private/magic methods and common utilities
                if func_name.startswith('_') or func_name in ['get', 'post', 'put', 'delete', 'validate', 'parse']:
                    continue
                function_locations[func_name].append(str(f.relative_to(backend_dir.parent)))
        except Exception:
            pass
    
    # Find duplicates (same function name in multiple files)
    duplicates = {
        name: files for name, files in function_locations.items()
        if len(set(files)) > 1  # In more than one unique file
    }
    
    return duplicates


def audit(frontend_dir, backend_dir, verbose=False):
    """Run the full audit"""
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}🔍 API Consistency Audit{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    # Extract calls and routes
    print(f"{CYAN}Extracting frontend API calls...{RESET}")
    frontend_calls = extract_frontend_calls(Path(frontend_dir))
    print(f"  Found {len(frontend_calls)} unique API calls")
    
    print(f"{CYAN}Extracting backend routes...{RESET}")
    backend_routes = extract_backend_routes(Path(backend_dir))
    print(f"  Found {len(backend_routes)} routes\n")
    
    # Build lookup sets
    backend_lookup = {}
    for r in backend_routes:
        key = (r['method'], normalize_path(r['path']))
        backend_lookup[key] = r
    
    frontend_lookup = {}
    for c in frontend_calls:
        key = (c['method'], normalize_path(c['path']))
        frontend_lookup[key] = c
    
    issues = []
    
    # Check for missing backend endpoints
    print(f"{YELLOW}━━━ Missing Backend Endpoints ━━━{RESET}")
    missing_endpoints = []
    for call in frontend_calls:
        key = (call['method'], normalize_path(call['path']))
        if key not in backend_lookup:
            missing_endpoints.append(call)
    
    if missing_endpoints:
        print(f"{RED}❌ {len(missing_endpoints)} missing endpoints:{RESET}")
        for m in missing_endpoints:
            print(f"   {m['method']:6} {m['path']}")
            if verbose:
                print(f"          └─ {m['file']}")
            issues.append(('missing_endpoint', m))
    else:
        print(f"{GREEN}✅ All frontend calls have matching backend endpoints{RESET}")
    
    # Check for unused backend routes (optional, verbose only)
    if verbose:
        print(f"\n{YELLOW}━━━ Unused Backend Routes ━━━{RESET}")
        unused_routes = []
        for route in backend_routes:
            key = (route['method'], normalize_path(route['path']))
            if key not in frontend_lookup:
                # Skip utility endpoints
                skip_patterns = ['/health', '/metrics', '/docs', '/swagger', '/acme/', '/scep/', '/.well-known']
                if not any(p in route['path'] for p in skip_patterns):
                    unused_routes.append(route)
        
        if unused_routes:
            print(f"{YELLOW}⚠️  {len(unused_routes)} potentially unused routes:{RESET}")
            for r in unused_routes[:15]:
                print(f"   {r['method']:6} {r['path']}")
            if len(unused_routes) > 15:
                print(f"   ... and {len(unused_routes) - 15} more")
        else:
            print(f"{GREEN}✅ All routes appear to be used{RESET}")
    
    # Check for duplicate function implementations
    print(f"\n{YELLOW}━━━ Duplicate Implementations ━━━{RESET}")
    duplicates = find_duplicate_implementations(Path(backend_dir))
    
    # Filter to important duplicates
    important_keywords = ['user', 'login', 'auth', 'register', 'certificate', 'credential']
    important_duplicates = {
        name: files for name, files in duplicates.items()
        if any(kw in name.lower() for kw in important_keywords)
    }
    
    if important_duplicates:
        print(f"{RED}⚠️  {len(important_duplicates)} potential duplicate implementations:{RESET}")
        for name, files in important_duplicates.items():
            unique_files = list(set(files))
            print(f"   {name}()")
            for f in unique_files[:3]:
                print(f"      └─ {f}")
            issues.append(('duplicate', name, unique_files))
    else:
        print(f"{GREEN}✅ No critical duplicates found{RESET}")
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Summary:{RESET}")
    print(f"  Frontend API calls: {len(frontend_calls)}")
    print(f"  Backend routes:     {len(backend_routes)}")
    print(f"  Missing endpoints:  {RED if missing_endpoints else GREEN}{len(missing_endpoints)}{RESET}")
    print(f"  Duplicates:         {RED if important_duplicates else GREEN}{len(important_duplicates)}{RESET}")
    
    total_issues = len(missing_endpoints) + len(important_duplicates)
    if total_issues:
        print(f"\n{RED}❌ {total_issues} issues found{RESET}")
        return 1
    else:
        print(f"\n{GREEN}✅ No critical issues found{RESET}")
        return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Audit API consistency')
    parser.add_argument('--frontend', default='frontend/src/services', help='Frontend services directory')
    parser.add_argument('--backend', default='backend/api', help='Backend API directory')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--strict', action='store_true', help='Exit with error if issues found')
    
    args = parser.parse_args()
    
    # Find project root
    if os.path.exists('/root/ucm-src-pro'):
        os.chdir('/root/ucm-src-pro')
    
    result = audit(args.frontend, args.backend, args.verbose)
    
    if args.strict and result != 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
