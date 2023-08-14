"""Test models."""
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Text,
    Boolean,
    DateTime,
    select,
    Date,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import expression

from app.db import db

Base = db.Model
metadata = Base.metadata


class Comment(Base):
    """one-to-many with users."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    body = Column(Text)
    created = Column(DateTime, nullable=False, default=datetime.utcnow)

    user = relationship("User", back_populates="comments")


class User(Base):
    """base class."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    logins = Column(Integer, nullable=False, default=0)
    note = Column(String(256), nullable=True)
    supervisor_id = Column(
        ForeignKey("users.id"),
        nullable=True,
    )
    start_date = Column(Date)
    created = Column(DateTime, nullable=False, default=datetime.utcnow)

    comments = relationship("Comment", back_populates="user")
    roles = relationship("Role", secondary="user_roles", back_populates="users")
    reports = relationship("User", backref=backref("supervisor", remote_side=[id]))

    @hybrid_property
    def is_supervisor(self) -> bool:
        """Return whether user is a supervisor."""
        return self.supervisor_id is None

    @is_supervisor.expression
    def is_supervisor(cls) -> expression:
        """Return SQL expression for is_supervisor."""
        return cls.supervisor_id.is_(None)

    @hybrid_property
    def username_supervisor_id(self) -> str:
        """Concat a couple fields to make a str hybrid property."""
        return f"{self.username}{self.supervisor_id}"

    @username_supervisor_id.expression
    def username_supervisor_id(cls) -> expression:
        """Return SQL expression."""
        return select(cls.username.concat(cls.supervisor_id)).correlate(cls).as_scalar()


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(
        ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    role_id = Column(
        ForeignKey("roles.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        primary_key=True,
    )


class Role(Base):
    """many-to-many with users."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)

    users = relationship("User", secondary="user_roles", back_populates="roles")
