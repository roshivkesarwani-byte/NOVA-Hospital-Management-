"""Database engine, schema and initialisation.

SQLite is used by default. Set DATABASE_URL (environment variable or Streamlit
secret) to a PostgreSQL / Supabase connection string for persistent online
storage. No credentials are ever stored in source code."""
from __future__ import annotations

import json
import os
import threading

from sqlalchemy import (CheckConstraint, Column, Float, ForeignKey, Index, Integer, MetaData,
                        String, Table, Text, UniqueConstraint, create_engine, event, text)
from sqlalchemy.engine import Connection, Engine

import config

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(50), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(20), nullable=False),
    Column("full_name", String(120), nullable=False),
    Column("is_active", Integer, nullable=False, server_default="1"),
    Column("created_at", String(19), nullable=False),
    CheckConstraint("role IN ('nurse','doctor','admin')", name="ck_users_role"),
)

rooms = Table(
    "rooms", metadata,
    Column("room_id", String(4), primary_key=True),
    Column("status", String(10), nullable=False, server_default="Available"),
    CheckConstraint("status IN ('Available','Occupied')", name="ck_rooms_status"),
)

patients = Table(
    "patients", metadata,
    Column("seq", Integer, primary_key=True),
    Column("patient_id", String(40), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("age", Integer, nullable=False),
    Column("gender", String(20), nullable=False),
    Column("contact", String(30)),
    Column("admission_date", String(10), nullable=False),
    Column("initial_notes", Text),
    Column("room_id", String(4), ForeignKey("rooms.room_id"), nullable=False),
    # 1 while the patient physically holds the room, 0 once it is released.
    Column("occupying_room", Integer, nullable=False, server_default="1"),
    Column("status", String(20), nullable=False, server_default="Admitted"),
    Column("outcome", String(10)),
    Column("outcome_at", String(19)),
    Column("room_released_at", String(19)),
    Column("is_demo", Integer, nullable=False, server_default="0"),
    Column("created_by", Integer, ForeignKey("users.id")),
    Column("created_at", String(19), nullable=False),
    CheckConstraint("status IN ('Admitted','Discharge Approved','Discharged','Deceased')", name="ck_patients_status"),
    CheckConstraint("outcome IS NULL OR outcome IN ('Cured','Deceased')", name="ck_patients_outcome"),
    # A deceased patient can never be recorded as cured, and vice versa.
    CheckConstraint("NOT (status = 'Deceased' AND outcome = 'Cured')", name="ck_patients_deceased_not_cured"),
    CheckConstraint("NOT (status = 'Discharged' AND (outcome IS NULL OR outcome <> 'Cured'))", name="ck_patients_discharged_cured"),
)
# A room can hold only one patient at a time - enforced by the database itself.
Index("uq_one_patient_per_room", patients.c.room_id, unique=True,
      sqlite_where=patients.c.occupying_room == 1, postgresql_where=patients.c.occupying_room == 1)

temperature_readings = Table(
    "temperature_readings", metadata,
    Column("id", Integer, primary_key=True),
    Column("patient_id", String(40), ForeignKey("patients.patient_id"), nullable=False),
    Column("reading_date", String(10), nullable=False),
    Column("recorded_at", String(19), nullable=False),
    Column("temperature_c", Float, nullable=False),
    Column("recorded_by", Integer, ForeignKey("users.id"), nullable=False),
    # Corrections never overwrite: the old row is kept with is_current = 0.
    Column("is_current", Integer, nullable=False, server_default="1"),
    Column("supersedes_id", Integer, ForeignKey("temperature_readings.id")),
    Column("correction_reason", Text),
    Column("created_at", String(19), nullable=False),
)
Index("uq_one_current_reading_per_day", temperature_readings.c.patient_id, temperature_readings.c.reading_date,
      unique=True, sqlite_where=temperature_readings.c.is_current == 1,
      postgresql_where=temperature_readings.c.is_current == 1)

doctor_visits = Table(
    "doctor_visits", metadata,
    Column("id", Integer, primary_key=True),
    Column("patient_id", String(40), ForeignKey("patients.patient_id"), nullable=False),
    Column("visit_date", String(10), nullable=False),
    Column("doctor_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("notes", Text),
    Column("completed_at", String(19), nullable=False),
    UniqueConstraint("patient_id", "visit_date", name="uq_one_visit_per_day"),
)

treatments = Table(
    "treatments", metadata,
    Column("id", Integer, primary_key=True),
    Column("patient_id", String(40), ForeignKey("patients.patient_id"), nullable=False),
    Column("doctor_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("visit_id", Integer, ForeignKey("doctor_visits.id")),
    Column("entry_type", String(20), nullable=False, server_default="Treatment"),
    Column("treatment", Text),
    Column("notes", Text),
    Column("recorded_at", String(19), nullable=False),
)

discharge_approvals = Table(
    "discharge_approvals", metadata,
    Column("id", Integer, primary_key=True),
    Column("patient_id", String(40), ForeignKey("patients.patient_id"), nullable=False),
    Column("doctor_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("approved_at", String(19), nullable=False),
    Column("fever_free_days", Integer, nullable=False),
    Column("note", Text),
    Column("status", String(10), nullable=False, server_default="Approved"),
    # Completion is recorded on the approval row, so a completed discharge
    # cannot exist without the doctor approval it belongs to.
    Column("completed_by", Integer, ForeignKey("users.id")),
    Column("completed_at", String(19)),
    CheckConstraint("status IN ('Approved','Completed','Cancelled')", name="ck_approval_status"),
)
Index("uq_one_open_approval", discharge_approvals.c.patient_id, unique=True,
      sqlite_where=discharge_approvals.c.status == "Approved",
      postgresql_where=discharge_approvals.c.status == "Approved")

notifications = Table(
    "notifications", metadata,
    Column("id", Integer, primary_key=True),
    Column("target_role", String(20), nullable=False),
    Column("kind", String(30), nullable=False),
    Column("title", String(200), nullable=False),
    Column("message", Text, nullable=False),
    Column("patient_id", String(40), ForeignKey("patients.patient_id")),
    Column("created_at", String(19), nullable=False),
    Column("is_read", Integer, nullable=False, server_default="0"),
    Column("read_at", String(19)),
)

audit_logs = Table(
    "audit_logs", metadata,
    Column("id", Integer, primary_key=True),
    Column("at", String(19), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("username", String(50)),
    Column("role", String(20)),
    Column("action", String(60), nullable=False),
    Column("entity_type", String(40)),
    Column("entity_id", String(60)),
    Column("details", Text),
)

app_meta = Table("app_meta", metadata, Column("key", String(50), primary_key=True), Column("value", Text))

_engine: Engine | None = None
_lock = threading.Lock()


def normalise_url(url: str) -> str:
    """Accept the connection strings Supabase / Heroku-style hosts hand out and
    pin the psycopg2 driver (SQLAlchemy's default Postgres driver varies by version)."""
    url = str(url).strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        try:  # Streamlit secrets (only available inside a Streamlit app)
            import streamlit as st
            url = st.secrets.get("DATABASE_URL")
        except Exception:
            url = None
    if not url:
        return f"sqlite:///{config.SQLITE_PATH}"
    return normalise_url(url)


def _make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _record):  # enforce foreign keys on every connection
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
        return eng
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=300)


def configure(url: str | None = None) -> Engine:
    """(Re)create the engine. Called with an explicit URL by the test-suite."""
    global _engine
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = _make_engine(normalise_url(url) if url else database_url())
    return _engine


def engine() -> Engine:
    if _engine is None:
        configure()
    return _engine


def backend_name() -> str:
    return "SQLite (local file)" if engine().dialect.name == "sqlite" else "PostgreSQL"


def rows(conn: Connection, sql: str, **params) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def one(conn: Connection, sql: str, **params) -> dict | None:
    r = conn.execute(text(sql), params).mappings().first()
    return dict(r) if r else None


def scalar(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def log_audit(conn: Connection, user: dict | None, action: str, entity_type: str | None = None,
              entity_id=None, details: dict | None = None, at: str | None = None) -> None:
    import logic
    conn.execute(audit_logs.insert().values(
        at=at or logic.ts(logic.hospital_now()),
        user_id=(user or {}).get("id"), username=(user or {}).get("username"), role=(user or {}).get("role"),
        action=action, entity_type=entity_type, entity_id=None if entity_id is None else str(entity_id),
        details=json.dumps(details, default=str) if details else None))


def init_db(seed_demo: bool | None = None) -> None:
    """Create tables, the 74 rooms and the demo accounts; load demo data once."""
    import auth
    import logic
    import seed

    eng = engine()
    metadata.create_all(eng)
    now = logic.hospital_now()
    with eng.begin() as conn:
        existing = {r["room_id"] for r in rows(conn, "SELECT room_id FROM rooms")}
        missing = [{"room_id": f"R{n:03d}", "status": "Available"}
                   for n in range(1, config.TOTAL_ROOMS + 1) if f"R{n:03d}" not in existing]
        if missing:
            conn.execute(rooms.insert(), missing)
        have = {r["username"] for r in rows(conn, "SELECT username FROM users")}
        for u in config.DEMO_USERS:
            if u["username"] not in have:
                conn.execute(users.insert().values(
                    username=u["username"], password_hash=auth.hash_password(u["password"]),
                    role=u["role"], full_name=u["full_name"], is_active=1, created_at=logic.ts(now)))
        seeded = one(conn, "SELECT value FROM app_meta WHERE key='demo_seeded'")
        want_seed = config.SEED_DEMO_ON_FIRST_RUN if seed_demo is None else seed_demo
        if seeded is None:
            if want_seed:
                seed.load_demo_data(conn, now)
            conn.execute(app_meta.insert().values(key="demo_seeded", value="1" if want_seed else "0"))
