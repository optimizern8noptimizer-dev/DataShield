from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select, ForeignKey, func, inspect, text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


ROLE_ORDER = {
    "viewer": 10,
    "operator": 20,
    "security_officer": 25,
    "admin": 30,
}


def _now() -> datetime:
    return datetime.utcnow()


def _db_url() -> str:
    return os.environ.get("DS_CONTROL_DB_URL", "sqlite:///./datashield_control.db")


_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    tokens: Mapped[list["AuthToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship(back_populates="tokens")


class JobRecord(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    config_path: Mapped[str] = mapped_column(Text)
    mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tables_json: Mapped[str] = mapped_column(Text, default="[]")
    verbose: Mapped[bool] = mapped_column(Boolean, default=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    worker_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64), index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)
    event_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


class MigrationRecord(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=_now)



def get_engine():
    global _engine
    if _engine is None:
        connect_args = {"check_same_thread": False} if _db_url().startswith("sqlite") else {}
        _engine = create_engine(_db_url(), future=True, pool_pre_ping=True, connect_args=connect_args)
    return _engine



def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal



def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    _upgrade_legacy_schema(engine)
    ensure_bootstrap_admin()


def _upgrade_legacy_schema(engine) -> None:
    inspector = inspect(engine)
    existing = {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    alters = []
    if "jobs" in existing:
        if "worker_name" not in existing["jobs"]:
            alters.append("ALTER TABLE jobs ADD COLUMN worker_name VARCHAR(128)")
        if "attempts" not in existing["jobs"]:
            alters.append("ALTER TABLE jobs ADD COLUMN attempts INTEGER DEFAULT 0")
        if "heartbeat_at" not in existing["jobs"]:
            alters.append("ALTER TABLE jobs ADD COLUMN heartbeat_at DATETIME")
        if "finished_at" not in existing["jobs"]:
            alters.append("ALTER TABLE jobs ADD COLUMN finished_at DATETIME")
    if "audit_events" in existing:
        if "prev_hash" not in existing["audit_events"]:
            alters.append("ALTER TABLE audit_events ADD COLUMN prev_hash VARCHAR(64) DEFAULT '" + ("0"*64) + "'")
        if "event_hash" not in existing["audit_events"]:
            alters.append("ALTER TABLE audit_events ADD COLUMN event_hash VARCHAR(64) DEFAULT ''")
    with engine.begin() as conn:
        for stmt in alters:
            conn.execute(sql_text(stmt))

        # Backfill event_hash for pre-v2.2 rows if needed
        if "audit_events" in existing and ("prev_hash" not in existing["audit_events"] or "event_hash" not in existing["audit_events"]):
            rows = conn.execute(sql_text("SELECT id, event_type, actor, details_json, created_at FROM audit_events ORDER BY id ASC")).fetchall()
            prev_hash = "0" * 64
            for row in rows:
                created_at = row.created_at if isinstance(row.created_at, datetime) else datetime.fromisoformat(str(row.created_at))
                event_hash = _calc_event_hash(row.event_type, row.actor, row.details_json or "{}", created_at, prev_hash)
                conn.execute(sql_text("UPDATE audit_events SET prev_hash=:prev_hash, event_hash=:event_hash WHERE id=:id"), {"prev_hash": prev_hash, "event_hash": event_hash, "id": row.id})
                prev_hash = event_hash



def _hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"



def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, salt, digest = stored_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        candidate = _hash_password(password, salt)
        return secrets.compare_digest(candidate, stored_hash)
    except Exception:
        return False



def ensure_bootstrap_admin() -> None:
    username = str(os.environ.get("DS_BOOTSTRAP_ADMIN", "admin")).strip() or "admin"
    password = str(os.environ.get("DS_BOOTSTRAP_PASSWORD", "admin12345")).strip()
    role = str(os.environ.get("DS_BOOTSTRAP_ROLE", "admin")).strip() or "admin"
    force_sync = str(os.environ.get("DS_BOOTSTRAP_FORCE_SYNC", "0")).strip().lower() in {"1", "true", "yes", "on"}
    Session = get_sessionmaker()
    with Session() as db:
        existing = db.scalar(select(User).where(User.username == username))
        if role not in ROLE_ORDER:
            role = "admin"
        if existing:
            if force_sync:
                existing.password_hash = _hash_password(password)
                existing.role = role
                existing.is_active = True
                db.commit()
            return
        db.add(User(username=username, password_hash=_hash_password(password), role=role, is_active=True))
        db.commit()



def create_user(username: str, password: str, role: str = "viewer", is_active: bool = True) -> dict:
    if role not in ROLE_ORDER:
        raise ValueError(f"Unknown role: {role}")
    Session = get_sessionmaker()
    with Session() as db:
        if db.scalar(select(User).where(User.username == username)):
            raise ValueError("User already exists")
        user = User(username=username, password_hash=_hash_password(password), role=role, is_active=is_active)
        db.add(user)
        db.commit()
        return {"username": user.username, "role": user.role, "is_active": user.is_active}



def authenticate(username: str, password: str, ttl_hours: int = 12) -> dict | None:
    Session = get_sessionmaker()
    with Session() as db:
        user = db.scalar(select(User).where(User.username == username))
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return None
        token = secrets.token_urlsafe(32)
        rec = AuthToken(token=token, user_id=user.id, expires_at=_now() + timedelta(hours=ttl_hours))
        db.add(rec)
        db.commit()
        return {"token": token, "username": user.username, "role": user.role, "expires_at": rec.expires_at.isoformat()}



def get_user_by_token(token: str) -> dict | None:
    Session = get_sessionmaker()
    with Session() as db:
        rec = db.scalar(select(AuthToken).where(AuthToken.token == token, AuthToken.revoked.is_(False)))
        if not rec or rec.expires_at < _now():
            return None
        user = rec.user
        if not user.is_active:
            return None
        return {"username": user.username, "role": user.role, "is_active": user.is_active}



def revoke_token(token: str) -> None:
    Session = get_sessionmaker()
    with Session() as db:
        rec = db.scalar(select(AuthToken).where(AuthToken.token == token))
        if rec:
            rec.revoked = True
            db.commit()



def list_users() -> list[dict]:
    Session = get_sessionmaker()
    with Session() as db:
        rows = db.scalars(select(User).order_by(User.username.asc())).all()
        return [{"username": u.username, "role": u.role, "is_active": u.is_active, "created_at": u.created_at.isoformat()} for u in rows]



def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback



def record_job(job_id: str, created_by: str, config_path: str, mode: str | None, tables_json: str, verbose: bool):
    Session = get_sessionmaker()
    with Session() as db:
        db.add(JobRecord(id=job_id, created_by=created_by, config_path=config_path, mode=mode, tables_json=tables_json, verbose=verbose))
        db.commit()



def update_job(job_id: str, **kwargs):
    Session = get_sessionmaker()
    with Session() as db:
        job = db.get(JobRecord, job_id)
        if not job:
            return
        for k, v in kwargs.items():
            if hasattr(job, k):
                setattr(job, k, v)
        job.updated_at = _now()
        if kwargs.get("status") in {"completed", "failed"}:
            job.finished_at = _now()
        db.commit()



def get_job(job_id: str) -> dict | None:
    Session = get_sessionmaker()
    with Session() as db:
        job = db.get(JobRecord, job_id)
        if not job:
            return None
        return _job_to_dict(job)



def list_jobs(limit: int = 50) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as db:
        rows = db.scalars(select(JobRecord).order_by(JobRecord.started_at.desc()).limit(limit)).all()
        return [_job_to_dict(j) for j in rows]



def claim_next_job(worker_name: str) -> dict | None:
    Session = get_sessionmaker()
    with Session() as db:
        job = db.scalar(select(JobRecord).where(JobRecord.status == "queued").order_by(JobRecord.started_at.asc()).limit(1))
        if not job:
            return None
        job.status = "running"
        job.worker_name = worker_name
        job.attempts = (job.attempts or 0) + 1
        job.heartbeat_at = _now()
        job.updated_at = _now()
        db.commit()
        db.refresh(job)
        return _job_to_dict(job)



def heartbeat_job(job_id: str, worker_name: str):
    update_job(job_id, worker_name=worker_name, heartbeat_at=_now())



def get_queue_stats() -> dict:
    Session = get_sessionmaker()
    with Session() as db:
        def count(status: str) -> int:
            return int(db.scalar(select(func.count()).select_from(JobRecord).where(JobRecord.status == status)) or 0)
        return {
            "queued": count("queued"),
            "running": count("running"),
            "completed": count("completed"),
            "failed": count("failed"),
        }



def _job_to_dict(job: JobRecord) -> dict:
    return {
        "job_id": job.id,
        "created_by": job.created_by,
        "status": job.status,
        "config_path": job.config_path,
        "mode": job.mode,
        "tables": _json_loads(job.tables_json, []),
        "verbose": job.verbose,
        "result": _json_loads(job.result_json, None),
        "error": job.error,
        "worker_name": job.worker_name,
        "attempts": job.attempts,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }



def _calc_event_hash(event_type: str, actor: str, details_json: str, created_at: datetime, prev_hash: str) -> str:
    payload = f"{event_type}|{actor}|{details_json}|{created_at.isoformat()}|{prev_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()



def record_audit_event(event_type: str, actor: str, details_json: str = "{}"):
    Base.metadata.create_all(get_engine())
    Session = get_sessionmaker()
    with Session() as db:
        prev = db.scalar(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1))
        prev_hash = prev.event_hash if prev else "0" * 64
        created_at = _now()
        event_hash = _calc_event_hash(event_type, actor, details_json, created_at, prev_hash)
        db.add(AuditEvent(event_type=event_type, actor=actor, details_json=details_json, created_at=created_at, prev_hash=prev_hash, event_hash=event_hash))
        db.commit()



def list_audit_events(limit: int = 100) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as db:
        rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)).all()
        return [{
            "event_type": e.event_type,
            "actor": e.actor,
            "details": _json_loads(e.details_json, {}),
            "prev_hash": e.prev_hash,
            "event_hash": e.event_hash,
            "created_at": e.created_at.isoformat(),
        } for e in rows]



def verify_audit_chain(limit: int = 1000) -> list[dict]:
    Session = get_sessionmaker()
    with Session() as db:
        rows = db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc()).limit(limit)).all()
        issues = []
        prev_hash = "0" * 64
        for row in rows:
            expected = _calc_event_hash(row.event_type, row.actor, row.details_json, row.created_at, prev_hash)
            if row.prev_hash != prev_hash:
                issues.append({"id": row.id, "issue": "prev_hash_mismatch"})
            if row.event_hash != expected:
                issues.append({"id": row.id, "issue": "event_hash_mismatch"})
            prev_hash = row.event_hash
        return issues
