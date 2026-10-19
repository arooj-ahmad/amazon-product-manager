# ============================================
# app/schemas/admin.py
# Admin authentication ke liye schemas
# ============================================

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================
# LOGIN REQUEST
# ============================================
class AdminLogin(BaseModel):
    """Admin login kare — username aur password bhejega"""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)


# ============================================
# TOKEN RESPONSE
# ============================================
class Token(BaseModel):
    """Login successful hone par JWT token return hoga"""

    access_token: str
    token_type: str = "bearer"


# ============================================
# TOKEN PAYLOAD (JWT ke andar ka data)
# ============================================
class TokenData(BaseModel):
    """JWT token ke andar ye data hoga"""

    username: Optional[str] = None


# ============================================
# ADMIN RESPONSE (Sensitive fields ke bina)
# ============================================
class AdminResponse(BaseModel):
    """Admin ki public info — password_hash NAHI"""

    id: int
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)