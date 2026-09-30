# ============================================
# app/models/admin.py
# Admin model — Supabase ke "admins" table se map
# ============================================

from sqlalchemy import BigInteger, Column, DateTime, String, func

from app.database import Base


class Admin(Base):
    """
    Admin user ka SQLAlchemy model.
    Supabase table: admins
    """

    __tablename__ = "admins"

    # ----------------------------------------
    # Primary Key
    # ----------------------------------------
    id = Column(BigInteger, primary_key=True, index=True)

    # ----------------------------------------
    # Credentials
    # ----------------------------------------
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # ----------------------------------------
    # Timestamps
    # ----------------------------------------
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Admin id={self.id} username={self.username}>"