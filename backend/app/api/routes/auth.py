# ============================================
# app/api/routes/auth.py
# Admin login endpoint
# ============================================

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Admin
from app.schemas import AdminLogin, Token
from app.services.auth import (
    create_access_token,
    get_username_from_token,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


# ============================================
# LOGIN ENDPOINT
# ============================================
@router.post("/token", response_model=Token)
def login(credentials: AdminLogin, db: Session = Depends(get_db)):
    """Admin login endpoint."""
    admin = db.query(Admin).filter(Admin.username == credentials.username).first()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username ya password galat hai",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(credentials.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username ya password galat hai",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": admin.username})

    return Token(access_token=access_token, token_type="bearer")


# ============================================
# DEPENDENCY: Current Admin Get Karo
# ============================================
def get_current_admin(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Admin:
    """Token se current admin nikalo."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalid ya expired hai",
        headers={"WWW-Authenticate": "Bearer"},
    )

    username = get_username_from_token(token)
    if username is None:
        raise credentials_exception

    admin = db.query(Admin).filter(Admin.username == username).first()
    if admin is None:
        raise credentials_exception

    return admin