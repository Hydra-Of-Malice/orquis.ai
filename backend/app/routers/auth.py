"""
Auth router — register, login, refresh token, profile.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from app.models.models import User, Org

router = APIRouter(tags=["Auth"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    org_name: Optional[str] = None  # If None, a personal org is created


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _user_response(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "org_id": user.org_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/auth/register", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create org
    org_name = req.org_name or f"{req.display_name}'s Workspace"
    slug = org_name.lower().replace(" ", "-").replace("'", "")[:50]
    # Ensure unique slug
    existing_org = await db.execute(select(Org).where(Org.slug == slug))
    if existing_org.scalar_one_or_none():
        slug = f"{slug}-{datetime.now(timezone.utc).strftime('%f')[:6]}"

    org = Org(name=org_name, slug=slug)
    db.add(org)
    await db.flush()  # Get org.id before creating user

    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        display_name=req.display_name,
        role="admin",  # First user in org is admin
        org_id=org.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": _user_response(user),
    }


@router.post("/auth/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": _user_response(user),
    }


@router.post("/auth/refresh")
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return _user_response(current_user)


@router.patch("/auth/me")
async def update_me(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.display_name is not None:
        current_user.display_name = req.display_name
    if req.avatar_url is not None:
        current_user.avatar_url = req.avatar_url
    await db.commit()
    await db.refresh(current_user)
    return _user_response(current_user)
