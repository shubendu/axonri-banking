"""
SQLite database setup with WAL mode.

WAL (Write-Ahead Logging) mode allows concurrent reads during writes.
Critical because ingestion (write) runs as a background task while
users are querying (read).

Tables:
    users          — staff and admin accounts
    documents      — document registry with ingestion status
    query_logs     — every query for audit trail and admin UI
    installations  — for future multi-bank/multi-branch support
"""

import os
import uuid
from datetime import datetime
from sqlalchemy import (
    create_engine, event, Column, String, Integer, Text, Float, DateTime
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = os.environ.get("DB_PATH", "/data/axonri.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_conn, connection_record):
    """Set SQLite pragmas for performance and concurrency."""
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL")
    dbapi_conn.execute("PRAGMA cache_size=-64000")    # 64MB page cache
    dbapi_conn.execute("PRAGMA temp_store=MEMORY")
    dbapi_conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username      = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)    # bcrypt hash
    full_name     = Column(String)
    role          = Column(String, nullable=False, default="staff")
    # roles: 'staff' | 'bank_admin' | 'axonri_admin'
    is_active     = Column(Integer, default=1)
    created_at    = Column(String, default=lambda: datetime.utcnow().isoformat())
    last_login    = Column(String)


class DocumentRecord(Base):
    __tablename__ = "documents"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_name      = Column(String, nullable=False)
    file_path     = Column(String, nullable=False)
    source_url    = Column(String)
    corpus_type   = Column(String, default="regulatory")
    status        = Column(String, default="PENDING")
    # status: PENDING | INGESTING | READY | ERROR | SKIPPED
    file_hash     = Column(String)                    # SHA-256 for change detection
    page_count    = Column(Integer, default=0)
    chunk_count   = Column(Integer, default=0)
    vector_count  = Column(Integer, default=0)
    error_message = Column(Text)
    created_at    = Column(String, default=lambda: datetime.utcnow().isoformat())
    ingested_at   = Column(String)
    last_checked  = Column(String)                    # for quarterly update scheduler


class QueryLog(Base):
    __tablename__ = "query_logs"

    id               = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id          = Column(String)
    username         = Column(String)
    query_text       = Column(Text)
    answer_text      = Column(Text)
    sources_json     = Column(Text)                   # JSON array of sources
    input_method     = Column(String, default="text") # 'text' | 'voice'
    model_used       = Column(String)
    tokens_generated = Column(Integer, default=0)
    duration_ms      = Column(Integer, default=0)
    status           = Column(String, default="success")
    # status: success | error | no_context
    created_at       = Column(String, default=lambda: datetime.utcnow().isoformat())


class Installation(Base):
    """For future multi-bank/multi-branch support."""
    __tablename__ = "installations"

    id                  = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_name           = Column(String, nullable=False)
    branch_name         = Column(String)
    city                = Column(String)
    licence_key         = Column(String, unique=True)
    licence_valid_until = Column(String)
    created_at          = Column(String, default=lambda: datetime.utcnow().isoformat())


def init_db() -> None:
    """Create all tables. Safe to call on every startup — idempotent."""
    Base.metadata.create_all(bind=engine)
    _seed_default_admin()


def _seed_default_admin() -> None:
    """Create default admin user if no users exist."""
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            import bcrypt
            default_password = os.environ.get("AXONRI_ADMIN_PASSWORD", "change_me_now")
            hashed = bcrypt.hashpw(default_password.encode(), bcrypt.gensalt()).decode()
            admin = User(
                username="admin",
                password_hash=hashed,
                full_name="Axonri Admin",
                role="axonri_admin",
            )
            db.add(admin)
            db.commit()
            print(f"[db] Created default admin user. Password: {default_password}")
            print("[db] IMPORTANT: Change the admin password immediately!")
    except Exception as e:
        print(f"[db] Could not seed admin user: {e}")
    finally:
        db.close()


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
