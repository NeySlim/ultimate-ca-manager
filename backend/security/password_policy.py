"""
Password Policy Module
Enforces password strength requirements for user accounts.

Default policy:
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 digit
- At least 1 special character
"""

import re
import logging
from typing import Tuple, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PasswordPolicy:
    """Password policy configuration"""
    min_length: int = 8
    max_length: int = 128
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    # Common weak passwords to reject
    blacklist: List[str] = field(default_factory=lambda: [
        'password', 'password1', 'password123',
        '12345678', '123456789', '1234567890',
        'qwerty', 'qwerty123', 'letmein',
        'admin', 'admin123', 'administrator',
        'changeme', 'changeme123', 'welcome',
        'abc123', 'monkey', 'dragon', 'master',
        'password!', 'P@ssword1', 'P@ssw0rd',
    ])


# Default policy instance
DEFAULT_POLICY = PasswordPolicy()


def validate_password(
    password: str, 
    policy: Optional[PasswordPolicy] = None,
    username: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """
    Validate password against policy.
    
    Args:
        password: Password to validate
        policy: Password policy (uses DEFAULT_POLICY if None)
        username: Optional username to check against
        
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    if policy is None:
        policy = DEFAULT_POLICY
    
    errors = []
    
    if not password:
        return False, ["Password is required"]
    
    # Length checks
    if len(password) < policy.min_length:
        errors.append(f"Password must be at least {policy.min_length} characters")
    
    if len(password) > policy.max_length:
        errors.append(f"Password must be at most {policy.max_length} characters")
    
    # Character class checks
    if policy.require_uppercase and not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    
    if policy.require_lowercase and not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    
    if policy.require_digit and not re.search(r'\d', password):
        errors.append("Password must contain at least one digit")
    
    if policy.require_special:
        # Escape special regex chars
        escaped_chars = re.escape(policy.special_chars)
        if not re.search(f'[{escaped_chars}]', password):
            errors.append(f"Password must contain at least one special character ({policy.special_chars})")
    
    # Blacklist check (case-insensitive)
    if password.lower() in [p.lower() for p in policy.blacklist]:
        errors.append("Password is too common, please choose a stronger one")
    
    # Username similarity check
    if username:
        username_lower = username.lower()
        password_lower = password.lower()
        
        if username_lower in password_lower:
            errors.append("Password cannot contain your username")
        
        if password_lower in username_lower and len(password) < len(username):
            errors.append("Password is too similar to username")
    
    # Sequential character check (e.g., 'abc', '123', 'qwe')
    if _has_sequential_chars(password, 4):
        errors.append("Password cannot contain 4 or more sequential characters")
    
    # Repeated character check (e.g., 'aaaa')
    if _has_repeated_chars(password, 4):
        errors.append("Password cannot contain 4 or more repeated characters")
    
    return len(errors) == 0, errors


def _has_sequential_chars(password: str, min_seq: int) -> bool:
    """Check for sequential characters (abc, 123, etc.)"""
    sequences = [
        'abcdefghijklmnopqrstuvwxyz',
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        '0123456789',
        'qwertyuiop',
        'asdfghjkl',
        'zxcvbnm',
    ]
    
    for seq in sequences:
        for i in range(len(seq) - min_seq + 1):
            if seq[i:i + min_seq] in password or seq[i:i + min_seq][::-1] in password:
                return True
    
    return False


def _has_repeated_chars(password: str, min_repeat: int) -> bool:
    """Check for repeated characters (aaaa, 1111, etc.)"""
    for i in range(len(password) - min_repeat + 1):
        if len(set(password[i:i + min_repeat])) == 1:
            return True
    return False


def get_password_strength(password: str) -> dict:
    """
    Calculate password strength score and feedback.
    
    Returns:
        {
            'score': int (0-100),
            'level': str ('weak', 'fair', 'good', 'strong'),
            'feedback': list[str]
        }
    """
    if not password:
        return {'score': 0, 'level': 'weak', 'feedback': ['Password is empty']}
    
    score = 0
    feedback = []
    
    # Length scoring (up to 30 points)
    length = len(password)
    if length >= 8:
        score += 10
    if length >= 12:
        score += 10
    if length >= 16:
        score += 10
    
    if length < 8:
        feedback.append("Use at least 8 characters")
    
    # Character variety scoring (up to 40 points)
    has_upper = bool(re.search(r'[A-Z]', password))
    has_lower = bool(re.search(r'[a-z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]', password))
    
    if has_upper:
        score += 10
    else:
        feedback.append("Add uppercase letters")
    
    if has_lower:
        score += 10
    else:
        feedback.append("Add lowercase letters")
    
    if has_digit:
        score += 10
    else:
        feedback.append("Add numbers")
    
    if has_special:
        score += 10
    else:
        feedback.append("Add special characters")
    
    # Uniqueness scoring (up to 20 points)
    unique_chars = len(set(password))
    unique_ratio = unique_chars / length
    
    if unique_ratio > 0.7:
        score += 20
    elif unique_ratio > 0.5:
        score += 10
    else:
        feedback.append("Use more varied characters")
    
    # Penalty for common patterns
    if password.lower() in DEFAULT_POLICY.blacklist:
        score = min(score, 10)
        feedback = ["This password is too common"]
    
    if _has_sequential_chars(password, 4):
        score -= 10
        feedback.append("Avoid sequential characters")
    
    if _has_repeated_chars(password, 3):
        score -= 10
        feedback.append("Avoid repeated characters")
    
    # Clamp score
    score = max(0, min(100, score))
    
    # Determine level
    if score >= 80:
        level = 'strong'
    elif score >= 60:
        level = 'good'
    elif score >= 40:
        level = 'fair'
    else:
        level = 'weak'
    
    return {
        'score': score,
        'level': level,
        'feedback': feedback if feedback else ['Password looks good!']
    }


def get_policy_requirements(policy: Optional[PasswordPolicy] = None) -> dict:
    """
    Get human-readable policy requirements.
    
    Returns:
        Dictionary describing password requirements
    """
    if policy is None:
        policy = DEFAULT_POLICY
    
    requirements = {
        'min_length': policy.min_length,
        'max_length': policy.max_length,
        'rules': []
    }
    
    requirements['rules'].append(f"At least {policy.min_length} characters")
    
    if policy.require_uppercase:
        requirements['rules'].append("At least one uppercase letter (A-Z)")
    
    if policy.require_lowercase:
        requirements['rules'].append("At least one lowercase letter (a-z)")
    
    if policy.require_digit:
        requirements['rules'].append("At least one number (0-9)")
    
    if policy.require_special:
        requirements['rules'].append(f"At least one special character ({policy.special_chars})")
    
    return requirements
