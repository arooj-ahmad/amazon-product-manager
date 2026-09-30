# ============================================
# app/database.py
# SQLAlchemy database engine aur session setup
# Supabase PostgreSQL se connection
# ============================================

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings


# ----------------------------------------
# Database Engine
# ----------------------------------------
# pool_pre_ping=True → connection stale ho jaye toh
#   automatically reconnect karega (Supabase pooler ke liye zaroori)
# pool_recycle=300 → 5 minute baad connection refresh karega
#   (pooler timeout se bachne ke liye)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,  # True karein toh SQL queries console par print hongi (debugging ke liye)
)


# ----------------------------------------
# Session Factory
# ----------------------------------------
# Har request ke liye ek naya session banayenge
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ----------------------------------------
# Base Class for Models
# ----------------------------------------
# Saare SQLAlchemy models isse inherit karenge
Base = declarative_base()


# ----------------------------------------
# Dependency: Get DB Session
# ----------------------------------------
def get_db():
    """
    FastAPI dependency — har request ke liye ek session deta hai
    aur request complete hone par automatically close kar deta hai.

    Usage in route:
        @router.get("/")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()