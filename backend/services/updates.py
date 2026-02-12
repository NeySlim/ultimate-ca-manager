"""
Update Service - Check and install updates from GitHub releases

UCM is now fully open-source (Community edition).
"""
import os
import re
import json
import shutil
import tempfile
import subprocess
from datetime import datetime
from functools import lru_cache
from flask import current_app

import requests

from config.settings import Config

# GitHub repo (community only, pro is archived)
REPO = "NeySlim/ultimate-ca-manager"

# Cache timeout for version check (5 minutes)
VERSION_CACHE_TIMEOUT = 300


def get_edition():
    """UCM is now fully open-source community edition"""
    return 'community'


def get_github_repo():
    """Get the GitHub repo"""
    return REPO


def get_current_version():
    """Get currently installed version from single source of truth"""
    # Use Config.APP_VERSION as primary source (reads from package.json)
    return Config.APP_VERSION


def parse_version(version_str):
    """Parse version string to tuple for comparison"""
    # Remove 'v' prefix if present
    version_str = version_str.lstrip('v')
    
    # Handle pre-release versions (e.g., 2.0.0-beta2)
    parts = version_str.split('-')
    main_version = parts[0]
    prerelease = parts[1] if len(parts) > 1 else None
    
    # Parse main version numbers
    try:
        numbers = tuple(int(x) for x in main_version.split('.'))
    except ValueError:
        numbers = (0, 0, 0)
    
    # Pad to 3 numbers
    while len(numbers) < 3:
        numbers = numbers + (0,)
    
    # Pre-release versions are considered lower than release
    # beta2 > beta1, rc1 > beta2
    prerelease_order = 0
    if prerelease:
        num_match = re.search(r'\d+', prerelease)
        num = int(num_match.group()) if num_match else 0
        if prerelease.startswith('dev'):
            prerelease_order = 50 + num
        elif prerelease.startswith('alpha'):
            prerelease_order = 100 + num
        elif prerelease.startswith('beta'):
            prerelease_order = 200 + num
        elif prerelease.startswith('rc'):
            prerelease_order = 300 + num
    else:
        prerelease_order = 999  # Release version is highest
    
    return numbers + (prerelease_order,)


def compare_versions(v1, v2):
    """Compare two version strings. Returns: -1 if v1<v2, 0 if equal, 1 if v1>v2"""
    t1 = parse_version(v1)
    t2 = parse_version(v2)
    
    if t1 < t2:
        return -1
    elif t1 > t2:
        return 1
    return 0


def check_for_updates(include_prereleases=False):
    """
    Check GitHub for available updates
    
    Returns dict with:
        - update_available: bool
        - current_version: str
        - latest_version: str
        - release_notes: str
        - download_url: str
        - published_at: str
        - edition: str
    """
    repo = get_github_repo()
    edition = get_edition()
    current = get_current_version()
    
    try:
        # Get releases from GitHub API
        url = f"https://api.github.com/repos/{repo}/releases"
        headers = {'Accept': 'application/vnd.github.v3+json'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            releases = response.json()
        except requests.exceptions.HTTPError as e:
            raise
        
        if not releases:
            return {
                'update_available': False,
                'current_version': current,
                'latest_version': current,
                'edition': edition,
                'message': 'No releases found'
            }
        
        # Find latest applicable release
        latest_release = None
        for release in releases:
            if release.get('draft'):
                continue
            if release.get('prerelease'):
                if not include_prereleases:
                    continue
                # Only include alpha, beta, rc — skip dev and other tags
                tag = release.get('tag_name', '').lstrip('v')
                suffix = tag.split('-', 1)[1] if '-' in tag else ''
                if not any(suffix.startswith(p) for p in ('alpha', 'beta', 'rc')):
                    continue
            latest_release = release
            break
        
        if not latest_release:
            # If no stable release, use latest prerelease
            for release in releases:
                if not release.get('draft'):
                    latest_release = release
                    break
        
        if not latest_release:
            return {
                'update_available': False,
                'current_version': current,
                'latest_version': current,
                'edition': edition,
                'message': 'No applicable releases found'
            }
        
        latest_version = latest_release['tag_name'].lstrip('v')
        
        # Find appropriate download asset
        download_url = None
        package_name = None
        
        # Detect package type (deb takes priority over rpm if both exist)
        is_docker = os.getenv('UCM_DOCKER') == '1'
        is_deb = os.path.exists('/usr/bin/dpkg')
        is_rpm = os.path.exists('/usr/bin/rpm') and not is_deb
        
        # Collect all matching assets, then pick the best one
        deb_asset = None
        rpm_asset = None
        
        for asset in latest_release.get('assets', []):
            name = asset['name']
            if is_docker:
                download_url = f"ghcr.io/neyslim/ultimate-ca-manager:{latest_version}"
                package_name = name
                break
            elif name.endswith('.deb') and not deb_asset:
                deb_asset = asset
            elif name.endswith('.rpm') and not rpm_asset:
                rpm_asset = asset
        
        if not is_docker:
            chosen = deb_asset if is_deb and deb_asset else (rpm_asset if is_rpm and rpm_asset else None)
            if chosen:
                download_url = chosen['browser_download_url']
                package_name = chosen['name']
        
        update_available = compare_versions(latest_version, current) > 0
        
        return {
            'update_available': update_available,
            'current_version': current,
            'latest_version': latest_version,
            'release_notes': latest_release.get('body', ''),
            'download_url': download_url,
            'package_name': package_name,
            'published_at': latest_release.get('published_at'),
            'html_url': latest_release.get('html_url'),
            'prerelease': latest_release.get('prerelease', False),
            'edition': edition,
            'repo': repo
        }
        
    except requests.RequestException as e:
        return {
            'update_available': False,
            'current_version': current,
            'edition': edition,
            'error': f'Failed to check for updates: {str(e)}'
        }


def download_update(download_url, package_name):
    """
    Download update package to temp directory
    
    Returns path to downloaded file
    """
    temp_dir = tempfile.mkdtemp(prefix='ucm_update_')
    file_path = os.path.join(temp_dir, package_name)
    
    try:
        import logging
        logger = logging.getLogger('ucm.updates')
        logger.info(f"Auto-update: downloading {download_url} to {file_path}")
        response = requests.get(download_url, stream=True, timeout=300, allow_redirects=True)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(file_path)
        logger.info(f"Auto-update: downloaded {file_size} bytes to {file_path}")
        return file_path
    
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise Exception(f"Download failed: {str(e)}")


def install_update(package_path):
    """
    Install downloaded update package via systemd path-activated updater.
    
    Writes the package path to /opt/ucm/data/.update_pending which triggers
    the ucm-updater.path systemd unit. The ucm-updater.service runs as root
    (no NoNewPrivileges restriction) and handles dpkg/rpm install + restart.
    """
    if not package_path.endswith('.deb') and not package_path.endswith('.rpm'):
        raise Exception(f"Unknown package format: {package_path}")
    
    try:
        import logging
        from pathlib import Path
        logger = logging.getLogger('ucm.updates')
        
        trigger_file = Path(Config.DATA_DIR) / '.update_pending'
        logger.info(f"Auto-update: writing trigger for {package_path}")
        trigger_file.write_text(package_path)
        
        logger.info(f"Auto-update: trigger written, ucm-updater.path will handle install + restart")
        return True
    except Exception as e:
        raise Exception(f"Install trigger failed: {str(e)}")


def get_update_history():
    """Get history of updates (from audit log)"""
    # This would query audit logs for update events
    # For now, return empty list
    return []
