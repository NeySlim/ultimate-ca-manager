"""
Update Service - Check and install updates from GitHub releases
"""
import hashlib
import os
import re
import logging
from pathlib import Path

import time

import requests

from config.settings import Config, DATA_DIR

logger = logging.getLogger('ucm.updates')

# Use system CA bundle if certifi's is missing (e.g. incomplete wheel install)
_ca_bundle = None
try:
    import certifi
    if os.path.isfile(certifi.where()):
        _ca_bundle = certifi.where()
except (ImportError, Exception):
    pass
if not _ca_bundle:
    for p in ('/etc/ssl/certs/ca-certificates.crt', '/etc/pki/tls/certs/ca-bundle.crt'):
        if os.path.isfile(p):
            _ca_bundle = p
            break

# GitHub repo
REPO = "NeySlim/ultimate-ca-manager"

# Simple cache to avoid GitHub rate limits (5 min TTL)
_releases_cache = {'data': None, 'ts': 0, 'ttl': 300}


def get_github_repo():
    """Get the GitHub repo"""
    return REPO


def get_current_version():
    """Get currently installed version from single source of truth"""
    # Use Config.APP_VERSION as primary source (reads from package.json)
    return Config.APP_VERSION


def get_installed_at():
    """Best-effort install time of the running version (#308).

    The VERSION file at the install root is rewritten by every install path
    (package upgrade, unattended update, manual deploy), so its mtime is a
    dependable "installed at" even for updates UCM did not perform itself.
    """
    try:
        from config.settings import BASE_DIR
        version_path = BASE_DIR / 'VERSION'
        if version_path.exists():
            from datetime import datetime, timezone
            return datetime.fromtimestamp(
                version_path.stat().st_mtime, tz=timezone.utc
            ).isoformat()
    except Exception as e:
        logger.debug(f"Could not read VERSION mtime: {e}")
    return None


def parse_version(version_str):
    """Parse version string to tuple for comparison.
    
    Supports both Major.Build (2.48) and legacy semver (2.1.6) formats.
    Pre-release suffixes (-dev, -beta, -rc) are ranked lower than release.
    """
    version_str = version_str.lstrip('v')
    
    # Handle pre-release versions (e.g., 2.48-dev, 2.1.0-beta2)
    parts = version_str.split('-')
    main_version = parts[0]
    prerelease = parts[1] if len(parts) > 1 else None
    
    # Parse main version numbers
    try:
        numbers = tuple(int(x) for x in main_version.split('.'))
    except ValueError:
        numbers = (0, 0, 0)
    
    # Pad to 3 numbers for consistent comparison (2.48 → 2.48.0)
    while len(numbers) < 3:
        numbers = numbers + (0,)
    
    # Pre-release versions are considered lower than release
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


def invalidate_update_cache():
    """Invalidate the releases cache to force a fresh fetch"""
    _releases_cache['data'] = None
    _releases_cache['ts'] = 0


def check_for_updates(include_prereleases=False, include_dev=False, force=False,
                      channel=None):
    """
    Check GitHub for available updates

    Args:
        include_prereleases: Include alpha, beta, rc versions
        include_dev: Include dev versions (implies include_prereleases)
        force: Bypass cache
        channel: Strict release channel ('stable' | 'rc') used by the
            automatic check. Overrides include_prereleases: 'stable' accepts
            final releases only, 'rc' accepts final releases plus rcN
            prereleases — alpha/beta/dev tags never qualify for either.

    Returns dict with:
        - update_available: bool
        - current_version: str
        - latest_version: str
        - release_notes: str
        - download_url: str
        - published_at: str
    """
    if include_dev:
        include_prereleases = True
    repo = get_github_repo()
    current = get_current_version()
    
    try:
        # Get releases from GitHub API (with cache to avoid rate limits)
        now = time.time()
        if not force and _releases_cache['data'] and (now - _releases_cache['ts']) < _releases_cache['ttl']:
            releases = _releases_cache['data']
        else:
            url = f"https://api.github.com/repos/{repo}/releases"
            headers = {'Accept': 'application/vnd.github.v3+json'}
            # Use token if available (60 req/h without, 5000 with)
            github_token = os.environ.get('GITHUB_TOKEN') or os.environ.get('UCM_GITHUB_TOKEN')
            if github_token:
                headers['Authorization'] = f'token {github_token}'
            
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=_ca_bundle or True)
                response.raise_for_status()
                releases = response.json()
                _releases_cache['data'] = releases
                _releases_cache['ts'] = now
            except requests.exceptions.HTTPError as e:
                raise
        
        if not releases:
            return {
                'update_available': False,
                'current_version': current,
                'latest_version': current,
                'message': 'No releases found'
            }
        
        # Find latest applicable release by version (don't trust API order)
        candidates = []
        for release in releases:
            if release.get('draft'):
                continue
            if release.get('prerelease'):
                tag = release.get('tag_name', '').lstrip('v')
                suffix = tag.split('-', 1)[1] if '-' in tag else ''
                if channel is not None:
                    # Strict channels: 'stable' takes no prerelease at all;
                    # 'rc' takes rcN only — alpha/beta/dev never qualify.
                    if channel != 'rc' or not suffix.startswith('rc'):
                        continue
                else:
                    if not include_prereleases:
                        continue
                    if suffix.startswith('dev') and not include_dev:
                        continue
            candidates.append(release)
        
        # Sort by parsed version, highest first
        candidates.sort(key=lambda r: parse_version(r.get('tag_name', '')), reverse=True)
        latest_release = candidates[0] if candidates else None
        
        # Find release matching current version for its notes
        current_release_notes = ''
        current_published_at = ''
        for release in releases:
            tag = release.get('tag_name', '').lstrip('v')
            if tag == current and not release.get('draft'):
                current_release_notes = release.get('body', '')
                current_published_at = release.get('published_at', '')
                break
        
        if not latest_release:
            return {
                'update_available': False,
                'current_version': current,
                'latest_version': current,
                'current_release_notes': current_release_notes,
                'current_published_at': current_published_at,
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
        checksum_assets = {}
        checksum_url = None

        for asset in latest_release.get('assets', []):
            name = asset['name']
            if is_docker:
                download_url = f"ghcr.io/neyslim/ultimate-ca-manager:{latest_version}"
                package_name = name
                break
            elif name.endswith('.sha256'):
                checksum_assets[name[:-len('.sha256')]] = asset
            elif name.endswith('.deb') and not deb_asset:
                deb_asset = asset
            elif name.endswith('.rpm') and not rpm_asset:
                rpm_asset = asset

        if not is_docker:
            chosen = deb_asset if is_deb and deb_asset else (rpm_asset if is_rpm and rpm_asset else None)
            if chosen:
                download_url = chosen['browser_download_url']
                package_name = chosen['name']
                checksum_asset = checksum_assets.get(package_name)
                if checksum_asset:
                    checksum_url = checksum_asset['browser_download_url']
        
        update_available = compare_versions(latest_version, current) > 0
        
        return {
            'update_available': update_available,
            'current_version': current,
            'latest_version': latest_version,
            'release_notes': latest_release.get('body', ''),
            'current_release_notes': current_release_notes,
            'current_published_at': current_published_at,
            'download_url': download_url,
            'package_name': package_name,
            'checksum_url': checksum_url,
            'published_at': latest_release.get('published_at'),
            'html_url': latest_release.get('html_url'),
            'prerelease': latest_release.get('prerelease', False),
            'repo': repo
        }
        
    except requests.RequestException as e:
        return {
            'update_available': False,
            'current_version': current,
            'error': f'Failed to check for updates: {str(e)}'
        }


def fetch_expected_sha256(checksum_url, package_name):
    """Fetch a release's .sha256 asset and return the hex digest for package_name.

    The asset is `sha256sum <pkg>` output: one or more "HEX  filename" lines.
    Returns the lowercase hex digest, or None when no line matches the package.
    """
    response = requests.get(checksum_url, timeout=30, allow_redirects=True,
                            verify=_ca_bundle or True)
    response.raise_for_status()
    # GitHub publishes ``ucm_2.223~rc1_all.deb`` as ``ucm_2.223.rc1_all.deb``
    # (tilde is not allowed in asset names) while the checksum line keeps the
    # package's own name, so a release-candidate package never matched and
    # the rc channel refused every install. Compare the names with the same
    # transform applied, the way the watcher already tolerates it for the
    # installed version.
    def _asset_name(name):
        return os.path.basename(name).replace('~', '.')

    expected = None
    wanted = _asset_name(package_name)
    for line in response.text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, fname = parts[0].lower(), parts[-1].lstrip('*')
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            continue
        if _asset_name(fname) == wanted:
            expected = digest
            break
    return expected


def download_update(download_url, package_name, expected_sha256=None):
    """
    Download update package to DATA_DIR/updates (accessible by ucm-watcher.service)

    Note: Cannot use /tmp because ucm.service has PrivateTmp=true,
    so files in /tmp are invisible to other services.

    When expected_sha256 is given, the download is hashed on the fly and the
    file is deleted (and an Exception raised) on mismatch — nothing with a
    wrong digest ever stays on disk for the install watcher to pick up.

    Returns path to downloaded file
    """
    # SECURITY: Sanitize package_name to prevent path traversal.
    safe_name = os.path.basename(package_name)
    if not safe_name or safe_name != package_name:
        logger.warning(
            f"Path traversal attempt in package_name blocked: {package_name!r}, "
            f"using sanitized name: {safe_name!r}"
        )
    if not safe_name:
        raise Exception("Invalid package name after sanitization")
    
    update_dir = os.path.join(str(DATA_DIR), 'updates')
    os.makedirs(update_dir, exist_ok=True)
    file_path = os.path.join(update_dir, safe_name)
    
    if not os.path.abspath(file_path).startswith(os.path.abspath(update_dir)):
        raise Exception("Resolved file path escapes update directory")
    
    try:
        logger.info(f"Auto-update: downloading {download_url} to {file_path}")
        response = requests.get(download_url, stream=True, timeout=300, allow_redirects=True, verify=_ca_bundle or True)
        response.raise_for_status()

        hasher = hashlib.sha256()
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                hasher.update(chunk)

        if expected_sha256:
            actual = hasher.hexdigest()
            if actual != expected_sha256.lower():
                raise Exception(
                    f"Checksum mismatch for {safe_name}: "
                    f"expected {expected_sha256.lower()}, got {actual}"
                )
            logger.info(f"Auto-update: SHA256 verified for {safe_name}")

        file_size = os.path.getsize(file_path)
        logger.info(f"Auto-update: downloaded {file_size} bytes to {file_path}")
        return file_path
    
    except Exception as e:
        # Clean up on failure
        if os.path.exists(file_path):
            os.remove(file_path)
        raise Exception(f"Download failed: {str(e)}")


def install_update(package_path, *, to_version=None, initiated_by='admin'):
    """
    Install downloaded update package via systemd path-activated watcher.

    Writes an atomic operation manifest (.update_manifest.json) then the
    package path to /opt/ucm/data/.update_pending, which triggers the
    ucm-watcher.path systemd unit. The ucm-watcher.service runs as root
    (no NoNewPrivileges restriction), handles dpkg/rpm install + restart, and
    writes a durable .update_result.json consumed by consume_update_result()
    after the restart — only that result decides installed vs failed.
    """
    if not package_path.endswith('.deb') and not package_path.endswith('.rpm'):
        raise Exception(f"Unknown package format: {package_path}")

    # Drain a not-yet-consumed result from a previous operation before this
    # one can overwrite it (the watcher writes results to a fixed path).
    try:
        consume_update_result()
    except Exception as e:
        logger.warning(f"Could not drain previous update result: {e}")

    trigger_file = Path(DATA_DIR) / '.update_pending'
    if trigger_file.exists():
        # One operation at a time: a second trigger while the watcher is (or
        # should be) working would interleave manifests and results.
        raise Exception("An update operation is already pending — retry after it completes")

    try:
        import json as _json
        import uuid
        manifest = {
            'op_id': uuid.uuid4().hex,
            'package_path': package_path,
            'from_version': get_current_version(),
            'to_version': to_version,
            'initiated_by': initiated_by,
            'initiated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        manifest_path = Path(DATA_DIR) / '.update_manifest.json'
        tmp_path = Path(DATA_DIR) / '.update_manifest.json.tmp'
        tmp_path.write_text(_json.dumps(manifest))
        os.replace(tmp_path, manifest_path)

        logger.info(f"Auto-update: writing trigger for {package_path}")
        # Atomic rename: systemd's PathExists= sees the trigger the moment it
        # is created, so it must never be observable half-written.
        trigger_tmp = Path(DATA_DIR) / '.update_pending.tmp'
        trigger_tmp.write_text(package_path)
        os.replace(trigger_tmp, trigger_file)

        logger.info(f"Auto-update: trigger written, ucm-watcher.path will handle install + restart")
        return True
    except Exception as e:
        raise Exception(f"Install trigger failed: {str(e)}")


def consume_update_result():
    """Consume the watcher's durable install result exactly once (#301).

    The watcher writes .update_result.json (atomic rename) after performing
    the actual dpkg/rpm install and verifying the installed package version.
    The first check after the post-install restart consumes it and emits the
    truthful outcome: system.update_installed only for a verified install,
    system.update_failed otherwise. Returns the parsed result or None.

    Consumption is crash-safe (review S-02): the file is CLAIMED by atomic
    rename to .update_result.processing, processed, then deleted — a crash
    mid-processing leaves the claimed file for the next pass instead of
    losing the result, and the op_id replay guard keeps that retry from
    emitting the same outcome twice.
    """
    import json as _json
    result_path = Path(DATA_DIR) / '.update_result.json'
    claimed_path = Path(DATA_DIR) / '.update_result.processing'
    if result_path.exists():
        try:
            # A fresh result supersedes a stale claim from a crashed pass
            os.replace(result_path, claimed_path)
        except OSError as e:
            logger.error(f"Could not claim update result file: {e}")
            return None
    if not claimed_path.exists():
        return None
    try:
        data = _json.loads(claimed_path.read_text())
    except Exception as e:
        logger.error(f"Unreadable update result file, discarding: {e}")
        data = None
    if not isinstance(data, dict):
        try:
            claimed_path.unlink()
        except OSError:
            pass
        return None
    op_id = data.get('op_id')
    if op_id and _cfg_get(_RESULT_OP_KEY) == op_id:
        # Already processed on a previous pass (crash between marker and
        # cleanup) — just finish the cleanup, never re-emit.
        try:
            claimed_path.unlink()
        except OSError:
            pass
        return None

    from services.audit_service import AuditService
    from services.webhook_service import emit_update_installed, emit_update_failed
    payload = {
        'current_version': data.get('from_version'),
        'latest_version': data.get('to_version'),
        'installed_version': data.get('installed_version'),
        'op_id': data.get('op_id'),
    }
    actor = data.get('initiated_by') or 'system'

    def _version_matches(detected, target):
        # Tolerate the packaging transforms (review S-01): the prerelease
        # separator '-' becomes '~' in DEB/RPM versions (2.215-rc1 ships as
        # 2.215~rc1), and a package revision ('-1') may be appended.
        d = (detected or '').replace('~', '-').strip()
        t = (target or '').replace('~', '-').strip()
        if not d or not t:
            return False
        base = re.sub(r'-\d+$', '', d)
        return d == t or base == t

    # Independent backend check on top of the watcher's own verification:
    # 'installed' additionally requires the recorded installed_version to
    # match the target — a watcher result claiming success without a
    # matching version is downgraded to a failure.
    verified = (
        data.get('status') == 'installed'
        and _version_matches(data.get('installed_version'), data.get('to_version'))
    )
    if data.get('status') == 'installed' and not verified:
        data['status'] = 'failed'
        if not data.get('step'):
            data['step'] = 'verify'
        if not data.get('error'):
            data['error'] = (
                f"installed version {data.get('installed_version')!r} does not "
                f"match target {data.get('to_version')!r}"
            )

    if verified:
        AuditService.log_action(
            action='settings_update', resource_type='system', resource_id='ucm',
            resource_name='UCM Auto-Update',
            details=(
                f"Update to {data.get('to_version')} installed and verified "
                f"(installed version: {data.get('installed_version')})"
            ),
            success=True, username=actor,
        )
        emit_update_installed(payload, actor=actor)
        logger.info(f"Update result consumed: installed {data.get('installed_version')}")
    else:
        payload['error'] = (data.get('error') or 'unknown failure')[:500]
        payload['step'] = data.get('step')
        AuditService.log_action(
            action='settings_update', resource_type='system', resource_id='ucm',
            resource_name='UCM Auto-Update',
            details=(
                f"Update to {data.get('to_version')} FAILED at step "
                f"{data.get('step') or '?'}: {payload['error']}"
            ),
            success=False, username=actor,
        )
        emit_update_failed(payload, actor=actor)
        logger.error(f"Update result consumed: FAILED ({payload['error']})")

    # Outcome emitted (durably queued via the bus): record the replay guard,
    # then finish the claim cleanup.
    if op_id:
        _cfg_set(_RESULT_OP_KEY, op_id)
    try:
        claimed_path.unlink()
    except OSError as e:
        logger.warning(f"Could not remove processed update result: {e}")
    return data


def get_update_history():
    """Get history of updates (from audit log)"""
    return []


# SystemConfig keys driving the scheduled task (#301)
UPDATE_CHANNEL_KEY = 'update_check_channel'          # 'stable' | 'rc'
AUTO_UPDATE_ENABLED_KEY = 'auto_update_enabled'      # 'true' | 'false' (default off)
AUTO_UPDATE_HOUR_KEY = 'auto_update_hour'            # local hour 0-23 (default 3)
UPDATE_POPUP_ENABLED_KEY = 'update_popup_enabled'    # 'true' | 'false' (default off, #308)
UPDATE_POPUP_BASELINE_KEY = 'update_popup_baseline_version'  # version running when enabled
_LAST_CHECK_TS_KEY = 'update_last_check_ts'
_NOTIFIED_VERSION_KEY = 'update_notified_version'
_ATTEMPTED_VERSION_KEY = 'auto_update_attempted_version'
# op_id of the last processed watcher result — replay guard for the
# claim/process/delete consumption (review S-02)
_RESULT_OP_KEY = 'update_result_last_op'


def _cfg_get(key, default=None):
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row and row.value is not None else default


def _cfg_stage(key, value):
    """Stage a SystemConfig write on the session without committing."""
    from models import db, SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = str(value)
    else:
        db.session.add(SystemConfig(key=key, value=str(value)))


def _cfg_set(key, value):
    """Persist one setting. Returns True on commit, False on failure —
    callers guarding critical markers (attempted-version) must check it."""
    from models import db
    _cfg_stage(key, value)
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Failed to persist {key}: {e}")
        return False


def _cfg_set_many(values):
    """Persist several settings in ONE transaction. Raises on commit failure
    so API callers can report an error instead of a partial success."""
    from models import db
    for key, value in values.items():
        _cfg_stage(key, value)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def get_update_settings():
    """Current update automation settings (defaults applied)."""
    try:
        hour = int(_cfg_get(AUTO_UPDATE_HOUR_KEY, '3'))
    except (TypeError, ValueError):
        hour = 3
    return {
        'channel': 'rc' if _cfg_get(UPDATE_CHANNEL_KEY, 'stable') == 'rc' else 'stable',
        'auto_install': _cfg_get(AUTO_UPDATE_ENABLED_KEY, 'false') == 'true',
        'hour': hour if 0 <= hour <= 23 else 3,
        'popup_enabled': _cfg_get(UPDATE_POPUP_ENABLED_KEY, 'false') == 'true',
        'popup_baseline_version': _cfg_get(UPDATE_POPUP_BASELINE_KEY, ''),
    }


def _notify_update_available(result):
    """Emit the bus event once per newly seen version. Returns True when the
    deduplication marker was durably persisted (review R-05)."""
    latest = result['latest_version']
    if _cfg_get(_NOTIFIED_VERSION_KEY) == latest:
        return True
    from services.webhook_service import emit_update_available
    emit_update_available({
        'current_version': result['current_version'],
        'latest_version': latest,
        'html_url': result.get('html_url'),
        'prerelease': result.get('prerelease', False),
    })
    if not _cfg_set(_NOTIFIED_VERSION_KEY, latest):
        logger.warning(
            "Update notification emitted but the deduplication marker could "
            "not be persisted — the next check may notify again"
        )
        return False
    logger.info(
        f"Update available: {result['current_version']} -> {latest}"
    )
    return True


def _auto_install(result):
    """Unattended install — checksum verification is mandatory here."""
    from datetime import datetime
    from services.audit_service import AuditService

    latest = result['latest_version']
    if os.getenv('UCM_DOCKER') == '1' or not result.get('download_url'):
        return
    if _cfg_get(_ATTEMPTED_VERSION_KEY) == latest:
        return  # one attempt per version — no overnight crash loops

    def refuse(reason):
        logger.warning(f"Auto-update to {latest} refused: {reason}")
        AuditService.log_action(
            action='settings_update', resource_type='system', resource_id='ucm',
            resource_name='UCM Auto-Update',
            details=f"Unattended update to {latest} refused: {reason}",
            success=False,
        )

    # Mark before acting so a crash mid-install is not retried nightly.
    # If the marker cannot be persisted, do NOT install: an unattended
    # install without its anti-repeat marker could loop every night.
    if not _cfg_set(_ATTEMPTED_VERSION_KEY, latest):
        return refuse('could not persist the attempted-version marker')

    if not result.get('checksum_url'):
        return refuse('release publishes no SHA256 checksum')
    try:
        expected = fetch_expected_sha256(result['checksum_url'], result['package_name'])
    except Exception as e:
        return refuse(f'checksum fetch failed ({e})')
    if not expected:
        return refuse('checksum asset does not cover this package')

    try:
        package_path = download_update(
            result['download_url'], result['package_name'], expected_sha256=expected
        )
    except Exception as e:
        return refuse(str(e))

    # Write the install trigger FIRST — audit and webhook must never claim an
    # install that was not even initiated (review F-05). The watcher performs
    # the actual dpkg/rpm install after this process restarts, so the audit
    # wording stays 'triggered', not 'installed'.
    try:
        install_update(package_path, to_version=latest, initiated_by='scheduler')
    except Exception as e:
        return refuse(f'install trigger failed ({e})')

    AuditService.log_action(
        action='settings_update', resource_type='system', resource_id='ucm',
        resource_name='UCM Auto-Update',
        details=(
            f"Unattended update from {result['current_version']} to {latest} "
            f"(SHA256 verified): install triggered at "
            f"{datetime.now().strftime('%H:%M')} — performed by the update "
            f"watcher on restart"
        ),
        success=True,
    )
    # Only 'initiated' here — system.update_installed / system.update_failed
    # are emitted by consume_update_result() from the watcher's durable
    # result, after the install actually happened and was version-verified.
    from services.webhook_service import emit_update_initiated
    emit_update_initiated({
        'current_version': result['current_version'],
        'latest_version': latest,
    }, actor='scheduler')
    logger.info(f"Auto-update to {latest} triggered")


def scheduled_update_check():
    """Hourly task: daily update check + notification, opt-in unattended install.

    The check itself runs at most once a day (and additionally in the
    configured install hour); the install only in that hour, only when
    auto_update_enabled is on, and only with a verified SHA256 (#301).
    """
    from datetime import datetime
    # First tick after a post-install restart: consume the watcher's durable
    # result and emit the truthful installed/failed outcome.
    try:
        consume_update_result()
    except Exception as e:
        logger.error(f"Failed to consume update result: {e}")
    try:
        settings = get_update_settings()
        now = time.time()
        try:
            last_check = float(_cfg_get(_LAST_CHECK_TS_KEY, '0') or 0)
        except (TypeError, ValueError):
            last_check = 0
        in_install_window = (
            settings['auto_install'] and datetime.now().hour == settings['hour']
        )
        if (now - last_check) < 20 * 3600 and not in_install_window:
            return

        result = check_for_updates(channel=settings['channel'])
        _cfg_set(_LAST_CHECK_TS_KEY, str(int(now)))

        if result.get('error'):
            logger.warning(f"Update check failed: {result['error']}")
            return
        if not result.get('update_available'):
            return

        _notify_update_available(result)
        if in_install_window:
            _auto_install(result)
    except Exception as e:
        logger.warning(f"Scheduled update check error: {e}")
