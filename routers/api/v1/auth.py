from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select
from database.session import get_session
from database.models import User, RefreshToken
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Optional
from web.dependencies import _resolve_tenant_from_host

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    is_onboarded: bool = False

class RefreshRequest(BaseModel):
    refresh_token: str

class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    is_onboarded: bool = False

class LogoutRequest(BaseModel):
    refresh_token: str

@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, session: Session = Depends(get_session)):
    # El usuario admin/superadmin ya se crea y se sincroniza contra ADMIN_PASSWORD /
    # SUPERADMIN_PASSWORD en cada arranque (AuthService.create_default_user_and_settings,
    # llamado desde core/startup.py) -- mismo criterio que routers/auth.py: no hace falta
    # ni es seguro un segundo camino que compare password en texto plano contra env vars.
    #
    # username es unico POR TENANT (ver routers/auth.py::login, mismo criterio).
    host_tenant_id = _resolve_tenant_from_host(request.headers.get("host"), session)
    if host_tenant_id:
        user = session.exec(
            select(User).where(User.tenant_id == host_tenant_id, User.username == req.username)
        ).first()
    else:
        user = session.exec(select(User).where(User.username == req.username)).first()

    from services.auth_service import AuthService

    if not user or not user.is_active or user.is_deleted or not AuthService.verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas"
        )

    from services.jwt_service import create_access_token, create_refresh_token, hash_refresh_token
    access = create_access_token(user.id, user.tenant_id, user.role)
    raw_refresh = create_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    
    db_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=refresh_hash,
        expires_at=expires
    )
    session.add(db_token)
    session.commit()
    
    # Fetch is_onboarded from Settings
    from database.models import Settings
    settings = session.exec(select(Settings).where(Settings.tenant_id == user.tenant_id)).first()
    is_onboarded = settings.is_onboarded if settings else False

    return TokenResponse(access_token=access, refresh_token=raw_refresh, is_onboarded=is_onboarded)

@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh(req: RefreshRequest, session: Session = Depends(get_session)):
    from services.jwt_service import hash_refresh_token, create_access_token, create_refresh_token
    r_hash = hash_refresh_token(req.refresh_token)
    db_token = session.exec(select(RefreshToken).where(RefreshToken.token_hash == r_hash)).first()
    if not db_token or db_token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de refresco inválido o revocado"
        )
    
    expires = db_token.expires_at
    if expires.tzinfo is None:
        now = datetime.now()
    else:
        now = datetime.now(timezone.utc)
        
    if expires < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de refresco expirado"
        )
    
    user = session.get(User, db_token.user_id)
    if not user or not user.is_active or user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o no encontrado"
        )
    
    # 1. Revoke the old refresh token
    db_token.revoked_at = now
    session.add(db_token)
    
    # 2. Generate new tokens
    access = create_access_token(user.id, user.tenant_id, user.role)
    raw_refresh = create_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    
    new_expires = datetime.now(timezone.utc) + timedelta(days=7) if expires.tzinfo is not None else datetime.now() + timedelta(days=7)
    new_db_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=refresh_hash,
        expires_at=new_expires
    )
    session.add(new_db_token)
    session.commit()
    
    # Fetch is_onboarded from Settings
    from database.models import Settings
    settings = session.exec(select(Settings).where(Settings.tenant_id == user.tenant_id)).first()
    is_onboarded = settings.is_onboarded if settings else False

    return RefreshResponse(access_token=access, refresh_token=raw_refresh, is_onboarded=is_onboarded)

@router.post("/auth/logout")
def logout(req: LogoutRequest, session: Session = Depends(get_session)):
    from services.jwt_service import hash_refresh_token
    r_hash = hash_refresh_token(req.refresh_token)
    db_token = session.exec(select(RefreshToken).where(RefreshToken.token_hash == r_hash)).first()
    if db_token:
        db_token.revoked_at = datetime.now(timezone.utc) if db_token.expires_at.tzinfo is not None else datetime.now()
        session.add(db_token)
        session.commit()
    return {"message": "Sesión cerrada correctamente"}
