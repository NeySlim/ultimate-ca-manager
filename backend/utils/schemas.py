"""
Request Validation Schemas - UCM Backend
Pydantic models for API request/response validation
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Literal
from datetime import datetime


# ============================================
# Auth Schemas
# ============================================

class LoginRequest(BaseModel):
    """Login request validation"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class PasswordChangeRequest(BaseModel):
    """Password change request"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=200)
    
    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


# ============================================
# User Schemas
# ============================================

class UserCreateRequest(BaseModel):
    """User creation request"""
    username: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8)
    role: Literal['admin', 'operator', 'viewer'] = 'viewer'
    active: bool = True


class UserUpdateRequest(BaseModel):
    """User update request"""
    email: Optional[EmailStr] = None
    role: Optional[Literal['admin', 'operator', 'viewer']] = None
    active: Optional[bool] = None


# ============================================
# CA Schemas
# ============================================

class CACreateRequest(BaseModel):
    """CA creation request"""
    commonName: str = Field(..., min_length=1, max_length=200, alias='common_name')
    organization: Optional[str] = Field(None, max_length=200)
    organizationalUnit: Optional[str] = Field(None, max_length=200, alias='organizational_unit')
    country: Optional[str] = Field(None, min_length=2, max_length=2)
    state: Optional[str] = Field(None, max_length=100)
    locality: Optional[str] = Field(None, max_length=100)
    keyAlgo: Literal['RSA', 'ECDSA'] = Field('RSA', alias='key_algo')
    keySize: str = Field('2048', alias='key_size')  # RSA: 2048/4096, ECDSA: P-256/P-384
    validityYears: int = Field(10, ge=1, le=30, alias='validity_years')
    caType: Literal['root', 'intermediate'] = Field('root', alias='ca_type')
    parentCaId: Optional[int] = Field(None, alias='parent_ca_id')
    
    class Config:
        populate_by_name = True


class CAUpdateRequest(BaseModel):
    """CA update request"""
    description: Optional[str] = Field(None, max_length=500)
    ocsp_enabled: Optional[bool] = None
    ocsp_url: Optional[str] = None
    cdp_enabled: Optional[bool] = None
    cdp_url: Optional[str] = None


# ============================================
# Certificate Schemas
# ============================================

class CertificateCreateRequest(BaseModel):
    """Certificate creation request"""
    ca_id: int = Field(..., gt=0)
    common_name: str = Field(..., min_length=1, max_length=200)
    organization: Optional[str] = Field(None, max_length=200)
    country: Optional[str] = Field(None, min_length=2, max_length=2)
    validity_days: int = Field(365, ge=1, le=3650)
    key_type: Literal['RSA-2048', 'RSA-4096', 'ECDSA-P256', 'ECDSA-P384'] = 'RSA-2048'
    san_dns: Optional[List[str]] = Field(default_factory=list)
    san_ip: Optional[List[str]] = Field(default_factory=list)
    san_email: Optional[List[str]] = Field(default_factory=list)
    template_id: Optional[int] = None


class CertificateRevokeRequest(BaseModel):
    """Certificate revocation request"""
    reason: Literal[
        'unspecified', 'keyCompromise', 'caCompromise', 
        'affiliationChanged', 'superseded', 'cessationOfOperation'
    ] = 'unspecified'


# ============================================
# CSR Schemas
# ============================================

class CSRSignRequest(BaseModel):
    """CSR signing request"""
    ca_id: int = Field(..., gt=0)
    validity_days: int = Field(365, ge=1, le=3650)
    template_id: Optional[int] = None


# ============================================
# Template Schemas
# ============================================

class TemplateCreateRequest(BaseModel):
    """Certificate template creation"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    template_type: Literal['web_server', 'client_auth', 'code_signing', 'email', 'vpn', 'custom'] = 'custom'
    key_type: Literal['RSA-2048', 'RSA-4096', 'ECDSA-P256', 'ECDSA-P384'] = 'RSA-2048'
    validity_days: int = Field(365, ge=1, le=3650)
    key_usage: Optional[List[str]] = Field(default_factory=list)
    extended_key_usage: Optional[List[str]] = Field(default_factory=list)


# ============================================
# Settings Schemas
# ============================================

class GeneralSettingsRequest(BaseModel):
    """General settings update"""
    organization_name: Optional[str] = Field(None, max_length=200)
    default_validity_days: Optional[int] = Field(None, ge=1, le=3650)
    default_key_type: Optional[str] = None


class EmailSettingsRequest(BaseModel):
    """Email/SMTP settings"""
    smtp_host: Optional[str] = Field(None, max_length=200)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_user: Optional[str] = Field(None, max_length=100)
    smtp_password: Optional[str] = Field(None, max_length=200)
    smtp_tls: Optional[bool] = None
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = Field(None, max_length=100)


class BackupSettingsRequest(BaseModel):
    """Backup settings"""
    auto_backup_enabled: Optional[bool] = None
    backup_retention_days: Optional[int] = Field(None, ge=1, le=365)
    backup_schedule: Optional[str] = None  # cron expression


# ============================================
# ACME Schemas
# ============================================

class ACMEAccountCreateRequest(BaseModel):
    """ACME account creation"""
    email: EmailStr
    terms_agreed: bool = Field(..., description="Must agree to terms of service")


# ============================================
# Validation Helper
# ============================================

from functools import wraps
from flask import request
from pydantic import ValidationError
from utils.response import error_response


def validate_request(schema_class):
    """
    Decorator to validate request body against a Pydantic schema
    
    Usage:
        @bp.route('/api/v2/users', methods=['POST'])
        @validate_request(UserCreateRequest)
        def create_user(validated_data):
            # validated_data is the Pydantic model instance
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                data = request.get_json() or {}
                validated = schema_class(**data)
                return f(validated, *args, **kwargs)
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    field = '.'.join(str(x) for x in error['loc'])
                    errors.append(f"{field}: {error['msg']}")
                return error_response(f"Validation error: {'; '.join(errors)}", 400)
        return wrapped
    return decorator
