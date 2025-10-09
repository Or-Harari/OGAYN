from __future__ import annotations

from sqlalchemy import Column, Integer, String
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    workspace_root = Column(String, nullable=False)


class BotProcess(Base):
    __tablename__ = "bot_processes"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, index=True, nullable=False)
    pid = Column(Integer, nullable=True)
    status = Column(String, default="stopped")
    config_path = Column(String, nullable=True)
    exit_code = Column(Integer, nullable=True)
    last_error = Column(String, nullable=True)


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String, nullable=False)
    userdir = Column(String, nullable=False)  # absolute path to this bot's user_data
    status = Column(String, default="stopped")
    pid = Column(Integer, nullable=True)
    config_path = Column(String, nullable=True)
    mode = Column(String, nullable=True)  # live | dryrun | backstage
    active_strategy = Column(String, nullable=True)  # JSON string storing active strategy spec
