"""
JWT Rotation Cleanup Service

Automatically removes the previous JWT secret key after the grace period (24h).
This ensures old tokens become invalid while giving users time to re-authenticate.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path


def scheduled_jwt_cleanup():
    """
    Check if JWT_SECRET_KEY_PREVIOUS should be cleaned up.
    Called by scheduler every hour.
    """
    rotation_file = Path('/opt/ucm/data/jwt_rotation.json')
    
    if not rotation_file.exists():
        return
    
    try:
        rotation_info = json.loads(rotation_file.read_text())
        
        # Already cleaned up
        if rotation_info.get('cleaned_up_at'):
            return
        
        rotated_at = rotation_info.get('rotated_at')
        expires_hours = rotation_info.get('previous_expires_hours', 24)
        
        if not rotated_at:
            return
        
        rotated_dt = datetime.fromisoformat(rotated_at)
        expires_dt = rotated_dt + timedelta(hours=expires_hours)
        
        if datetime.now() < expires_dt:
            return
        
        # Time to clean up - remove JWT_SECRET_KEY_PREVIOUS from .env
        cleanup_previous_jwt_key()
        
        # Mark as cleaned up (prevents re-running)
        rotation_info['cleaned_up_at'] = datetime.now().isoformat()
        rotation_file.write_text(json.dumps(rotation_info))
        
        import logging
        logging.getLogger(__name__).info(f"Removed previous JWT key (rotated at {rotated_at})")
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"JWT cleanup error: {e}")


def cleanup_previous_jwt_key():
    """Remove JWT_SECRET_KEY_PREVIOUS from the environment file"""
    is_docker = os.environ.get('UCM_DOCKER', '').lower() in ('1', 'true')
    
    if is_docker:
        env_path = Path('/app/backend/.env')
        if not env_path.exists():
            env_path = Path('/app/.env')
    else:
        env_path = Path('/etc/ucm/ucm.env')
    
    if not env_path.exists():
        return
    
    lines = env_path.read_text().splitlines()
    new_lines = [line for line in lines if not line.strip().startswith('JWT_SECRET_KEY_PREVIOUS=')]
    
    env_path.write_text('\n'.join(new_lines) + '\n')
    
    # Log the cleanup
    try:
        from services.audit_service import AuditService
        AuditService.log_action(
            action='jwt_previous_cleanup',
            resource_type='security',
            details='Previous JWT secret key removed after 24h grace period',
            success=True
        )
    except:
        pass
