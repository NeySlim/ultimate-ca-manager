"""
Pro Dependencies Checker
Automatically checks and installs missing Pro dependencies
"""

import subprocess
import sys
import logging

logger = logging.getLogger(__name__)

# Pro feature dependencies mapping
PRO_DEPENDENCIES = {
    'ldap': {
        'package': 'ldap3',
        'import': 'ldap3',
        'description': 'LDAP/Active Directory integration',
        'version': '>=2.9.1'
    },
    'saml': {
        'package': 'python3-saml',
        'import': 'onelogin.saml2',
        'description': 'SAML SSO support',
        'version': '>=1.16.0',
        'system_deps': {
            'apt': ['libxmlsec1-dev', 'libxmlsec1-openssl'],
            'dnf': ['xmlsec1-devel', 'xmlsec1-openssl-devel'],
            'yum': ['xmlsec1-devel', 'xmlsec1-openssl-devel'],
        }
    },
    'oauth': {
        'package': 'python-jose',
        'import': 'jose',
        'description': 'OAuth2/OIDC JWT support',
        'version': '>=3.3.0'
    },
    'hsm': {
        'package': 'PyKCS11',
        'import': 'PyKCS11',
        'description': 'HSM/PKCS#11 support',
        'version': '>=1.5.12',
        'system_deps': {
            'apt': ['libengine-pkcs11-openssl'],
            'dnf': ['opensc'],
            'yum': ['opensc'],
        }
    }
}


def check_dependency(dep_name):
    """Check if a dependency is installed"""
    dep = PRO_DEPENDENCIES.get(dep_name)
    if not dep:
        return True
    
    try:
        __import__(dep['import'])
        return True
    except ImportError:
        return False


def check_all_dependencies():
    """Check all Pro dependencies and return missing ones"""
    missing = []
    for name, dep in PRO_DEPENDENCIES.items():
        if not check_dependency(name):
            missing.append({
                'name': name,
                'package': dep['package'],
                'description': dep['description']
            })
    return missing


def install_dependency(dep_name, auto_install=False):
    """Install a missing dependency"""
    dep = PRO_DEPENDENCIES.get(dep_name)
    if not dep:
        return False, f"Unknown dependency: {dep_name}"
    
    package = dep['package']
    version = dep.get('version', '')
    
    if not auto_install:
        return False, f"Run: pip install {package}{version}"
    
    try:
        logger.info(f"Installing {package}...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--break-system-packages', 
             f"{package}{version}"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Installed {package}")
            return True, f"Installed {package}"
        else:
            logger.error(f"Failed to install {package}: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Installation timed out"
    except Exception as e:
        return False, str(e)


def install_missing_dependencies(auto_install=False):
    """Check and optionally install all missing dependencies"""
    missing = check_all_dependencies()
    
    if not missing:
        logger.info("✅ All Pro dependencies are installed")
        return True, []
    
    results = []
    for dep in missing:
        if auto_install:
            success, message = install_dependency(dep['name'], auto_install=True)
            results.append({
                'name': dep['name'],
                'success': success,
                'message': message
            })
        else:
            results.append({
                'name': dep['name'],
                'success': False,
                'message': f"Missing: {dep['package']} ({dep['description']})"
            })
    
    all_success = all(r['success'] for r in results)
    return all_success, results


def ensure_pro_dependencies(app):
    """
    Called during app startup to ensure Pro dependencies are available.
    Checks and auto-installs if UCM_AUTO_INSTALL_DEPS=true
    """
    missing = check_all_dependencies()
    
    if not missing:
        return True
    
    # Log missing dependencies
    logger.warning(f"⚠️ Missing Pro dependencies: {[d['name'] for d in missing]}")
    
    # Check if auto-install is enabled
    auto_install = app.config.get('AUTO_INSTALL_DEPS', False)
    
    if auto_install:
        logger.info("🔧 Auto-installing missing Pro dependencies...")
        success, results = install_missing_dependencies(auto_install=True)
        
        if success:
            logger.info("✅ All Pro dependencies installed successfully")
            # Need to reload modules
            return True
        else:
            failed = [r for r in results if not r['success']]
            logger.error(f"❌ Failed to install: {[f['name'] for f in failed]}")
            for f in failed:
                logger.error(f"   {f['name']}: {f['message']}")
            return False
    else:
        # Just warn and continue (features will gracefully degrade)
        logger.warning("To auto-install, set UCM_AUTO_INSTALL_DEPS=true in environment")
        logger.warning("Or manually run: pip install ldap3 python3-saml python-jose PyKCS11")
        return False


def get_dependency_status():
    """Get status of all Pro dependencies for API/UI"""
    status = {}
    for name, dep in PRO_DEPENDENCIES.items():
        installed = check_dependency(name)
        status[name] = {
            'installed': installed,
            'package': dep['package'],
            'description': dep['description'],
            'required_for': name.upper()
        }
    return status
