"""SQLAlchemy mappings for accounts, OTP challenges, and sessions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.domain.roles import Role


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('user', 'admin', 'hr', 'employee', 'student')",
            name="ck_users_role",
        ),
        CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_users_theme"),
        CheckConstraint(
            "two_factor_method IN ('none', 'email_otp', 'totp')",
            name="ck_users_two_factor_method",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    theme: Mapped[str] = mapped_column(String(20), nullable=False, server_default="system")
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=Role.USER.value, server_default="user", index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    two_factor_method: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="email_otp"
    )
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_pending_secret: Mapped[str | None] = mapped_column(String(64))
    avatar_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OtpChallengeModel(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('signup', 'login', 'totp_login')",
            name="ck_otp_challenges_purpose",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )