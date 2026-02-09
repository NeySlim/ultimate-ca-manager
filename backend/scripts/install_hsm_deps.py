#!/usr/bin/env python3
"""
HSM Dependencies Installer

Installs optional dependencies for HSM providers.
Run with: python3 install_hsm_deps.py [provider]

Providers:
  pkcs11      - PKCS#11 support (SoftHSM, Thales, nCipher, AWS CloudHSM)
  azure       - Azure Key Vault
  gcp         - Google Cloud KMS
  all         - All providers
"""

import subprocess
import sys
import os

# Dependency definitions
DEPENDENCIES = {
    'pkcs11': {
        'name': 'PKCS#11 (SoftHSM, Thales, nCipher, AWS CloudHSM)',
        'packages': ['python-pkcs11>=0.7.0'],
        'system_packages': {
            'debian': ['softhsm2', 'libsofthsm2-dev'],  # For testing
            'rhel': ['softhsm', 'softhsm-devel'],
        },
        'post_install': 'SoftHSM2 installed for testing. Initialize with: softhsm2-util --init-token --slot 0 --label "UCM-HSM"'
    },
    'azure': {
        'name': 'Azure Key Vault',
        'packages': ['azure-keyvault-keys>=4.9.0', 'azure-identity>=1.15.0'],
        'system_packages': {},
        'post_install': 'Configure with Azure AD credentials or Managed Identity.'
    },
    'gcp': {
        'name': 'Google Cloud KMS',
        'packages': ['google-cloud-kms>=2.21.0'],
        'system_packages': {},
        'post_install': 'Configure with service account JSON or application default credentials.'
    },
}


def detect_distro():
    """Detect Linux distribution family"""
    if os.path.exists('/etc/debian_version'):
        return 'debian'
    elif os.path.exists('/etc/redhat-release') or os.path.exists('/etc/fedora-release'):
        return 'rhel'
    return 'unknown'


def run_command(cmd, check=True):
    """Run a shell command"""
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  Error: {result.stderr}")
        return False
    return True


def install_system_packages(packages, distro):
    """Install system packages"""
    if not packages:
        return True
    
    if distro == 'debian':
        cmd = ['apt-get', 'install', '-y'] + packages
    elif distro == 'rhel':
        cmd = ['dnf', 'install', '-y'] + packages
    else:
        print(f"  Warning: Cannot install system packages on {distro}")
        return True
    
    return run_command(cmd, check=False)


def install_python_packages(packages):
    """Install Python packages"""
    cmd = [sys.executable, '-m', 'pip', 'install', '--quiet'] + packages
    return run_command(cmd)


def install_provider(provider_key):
    """Install a single provider's dependencies"""
    if provider_key not in DEPENDENCIES:
        print(f"Unknown provider: {provider_key}")
        return False
    
    provider = DEPENDENCIES[provider_key]
    print(f"\n{'='*60}")
    print(f"Installing: {provider['name']}")
    print('='*60)
    
    # Detect distro for system packages
    distro = detect_distro()
    
    # Install system packages if any
    sys_pkgs = provider['system_packages'].get(distro, [])
    if sys_pkgs:
        print(f"\n  System packages: {', '.join(sys_pkgs)}")
        if os.geteuid() == 0:
            install_system_packages(sys_pkgs, distro)
        else:
            print(f"  Note: Run as root to install: {' '.join(sys_pkgs)}")
    
    # Install Python packages
    print(f"\n  Python packages: {', '.join(provider['packages'])}")
    success = install_python_packages(provider['packages'])
    
    if success:
        print(f"\n  ✅ {provider['name']} installed successfully!")
        if provider.get('post_install'):
            print(f"  ℹ️  {provider['post_install']}")
    else:
        print(f"\n  ❌ Failed to install {provider['name']}")
    
    return success


def verify_provider(provider_key):
    """Verify a provider is installed and working"""
    print(f"\nVerifying {provider_key}...")
    
    if provider_key == 'pkcs11':
        try:
            import pkcs11
            print(f"  ✅ python-pkcs11 version: {pkcs11.__version__ if hasattr(pkcs11, '__version__') else 'installed'}")
            return True
        except ImportError:
            print("  ❌ python-pkcs11 not installed")
            return False
    
    elif provider_key == 'azure':
        try:
            from azure.keyvault.keys import KeyClient
            from azure.identity import DefaultAzureCredential
            print("  ✅ azure-keyvault-keys installed")
            return True
        except ImportError as e:
            print(f"  ❌ Azure libraries not installed: {e}")
            return False
    
    elif provider_key == 'gcp':
        try:
            from google.cloud import kms_v1
            print("  ✅ google-cloud-kms installed")
            return True
        except ImportError as e:
            print(f"  ❌ GCP libraries not installed: {e}")
            return False
    
    return False


def show_status():
    """Show installation status of all providers"""
    print("\nHSM Provider Status")
    print("="*60)
    
    for key, provider in DEPENDENCIES.items():
        installed = verify_provider(key)
        status = "✅ Installed" if installed else "❌ Not installed"
        print(f"  {provider['name']}: {status}")
    
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCurrent status:")
        show_status()
        print("Usage: python3 install_hsm_deps.py <provider>")
        print("       python3 install_hsm_deps.py all")
        print("       python3 install_hsm_deps.py status")
        sys.exit(0)
    
    action = sys.argv[1].lower()
    
    if action == 'status':
        show_status()
        sys.exit(0)
    
    if action == 'all':
        providers = list(DEPENDENCIES.keys())
    else:
        providers = [action]
    
    success_count = 0
    for provider in providers:
        if install_provider(provider):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Installed {success_count}/{len(providers)} providers")
    print('='*60)
    
    # Show final status
    show_status()


if __name__ == '__main__':
    main()
