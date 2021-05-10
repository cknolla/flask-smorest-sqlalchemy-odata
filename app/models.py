"""Test models."""
from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db import db

Base = db.Model
metadata = Base.metadata


class Comment(Base):
    """one-to-many with users."""
    __tablename__ = 'comments'

    id = Column(Integer, primary_key=True)
    user_id = Column(
        ForeignKey('users.id', ondelete='RESTRICT', onupdate='CASCADE'),
        nullable=False,
    )
    body = Column(Text)

    user = relationship('User')


class User(Base):
    """base class."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False, unique=True, index=True)


class Role(Base):
    """many-to-many with users."""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)


def seed():
    user1 = User(
        username='user1',
    )
    admin_role = Role(
        name='admin',
    )
    comment1 = Comment(
        user=user1,
        body='some text',
    )
    db.session.add_all([
        user1,
        admin_role,
        comment1,
    ])
    db.session.flush()
    db.session.commit()
