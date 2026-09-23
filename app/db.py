import os
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, ForeignKey, JSON, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

URL = os.getenv('DATABASE_URL', 'sqlite:///./org_agent.db')
engine = create_engine(URL, connect_args={'check_same_thread': False} if URL.startswith('sqlite') else {}, pool_pre_ping=True)
if URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
Session = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc).isoformat()

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    phase: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Fragment(Base):
    __tablename__ = 'fragments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), index=True)
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    locator: Mapped[dict] = mapped_column(JSON)

class Analysis(Base):
    __tablename__ = 'analyses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    result: Mapped[dict] = mapped_column(JSON)
