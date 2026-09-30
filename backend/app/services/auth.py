# ============================================
# app/services/auth.py
# JWT authentication aur password hashing
# Sirf admin ke liye
# ============================================

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ----------------------------------------
# Password hashing context
# bcrypt algorithm use kar rahe hain
# ----------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================
# PASSWORD HASHING
# ============================================
def hash_password(password: str) -> str:
    """Plain password ko bcrypt hash mein convert karta hai."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check karta hai ke plain password hashed password se match karta hai ya nahi."""
    return pwd_context.verify(plain_password, hashed_password)


# ============================================
# JWT TOKEN BANANA
# ============================================
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWT access token banata hai."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    return encoded_jwt


# ============================================
# JWT TOKEN VERIFY
# ============================================
def decode_access_token(token: str) -> Optional[dict]:
    """JWT token ko decode aur verify karta hai."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        return None


def get_username_from_token(token: str) -> Optional[str]:
    """Token se username nikalta hai."""
    payload = decode_access_token(token)
    if payload is None:
        return None
    return payload.get("sub")