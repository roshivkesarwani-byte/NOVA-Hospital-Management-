"""Fictional demonstration data. Every person and record here is invented.

Dates are generated relative to the current hospital day so that the demo
always shows every workflow state (pending, fever, 1/2/3+ fever-free days,
approved discharge, finalised outcomes)."""
from __future__ import annotations

from datetime import datetime, time, timedelta

import database as db
import logic

# (name, age, gender, room, days since admission, readings {days_ago: temp}, extras)
# days_ago = 0 is today. A missing key means no reading was taken that day.
ACTIVE_PATIENTS = [
    ("Aarav Mehta", 34, "Male", "R003", 4, {3: 39.1, 2: 38.8, 1: 38.6, 0: 38.4}, {}),
    ("Diya Kapoor", 27, "Female", "R007", 3, {2: 38.9, 1: 38.3}, {}),
    ("Kabir Nair", 52, "Male", "R011", 4, {3: 39.0, 2: 38.5, 1: 37.4, 0: 37.2}, {}),
    ("Ishita Banerjee", 41, "Female", "R012", 5, {4: 38.7, 3: 38.2, 2: 37.5, 1: 37.1, 0: 36.9}, {}),
    ("Rohan Verma", 63, "Male", "R015", 5, {4: 39.2, 3: 38.4, 2: 37.6, 1: 37.3}, {}),
    ("Sneha Kulkarni", 30, "Female", "R018", 6, {5: 38.8, 4: 38.1, 3: 37.4, 2: 37.0, 1: 36.8, 0: 36.9}, {}),
    ("Vikram Sethi", 58, "Male", "R021", 6, {5: 39.0, 4: 38.2, 3: 37.3, 2: 37.1, 1: 36.9}, {}),
    ("Ananya Reddy", 22, "Female", "R024", 7, {6: 38.6, 5: 38.0, 4: 37.2, 3: 37.0, 2: 36.8, 1: 36.7, 0: 36.8},
     {"visited": True}),
    ("Farhan Qureshi", 46, "Male", "R029", 8, {7: 38.9, 6: 38.3, 5: 37.4, 4: 37.1, 3: 36.9, 2: 36.8, 1: 36.7, 0: 36.6},
     {"approved": True}),
    ("Lakshmi Iyer", 69, "Female", "R033", 5, {4: 37.4, 3: 37.2, 1: 37.0, 0: 37.1}, {}),
    ("Nikhil Joshi", 38, "Male", "R036", 6, {5: 38.5, 4: 37.3, 3: 37.1, 2: 37.0, 1: 38.4, 0: 38.1}, {}),
    ("Pooja Chawla", 25, "Female", "R040", 0, {}, {}),
    ("Sameer Bhatt", 55, "Male", "R044", 5, {4: 38.7, 3: 37.2, 2: 37.0, 1: 36.9, 0: 38.3}, {}),
    ("Tara D'Souza", 33, "Female", "R051", 6, {5: 38.4, 4: 38.1, 3: 37.3, 2: 37.0, 1: 36.9, 0: 37.0}, {}),
    ("Yash Malhotra", 48, "Male", "R058", 3, {2: 38.6, 1: 37.5, 0: 37.2}, {"corrected_from": 39.2}),
]

# (name, age, gender, room, admitted days ago, outcome days ago, outcome)
CLOSED_PATIENTS = [
    ("Meenal Shah", 44, "Female", "R005", 14, 6, "Cured"),
    ("Harish Pandey", 61, "Male", "R009", 13, 5, "Cured"),
    ("Ritu Saxena", 29, "Female", "R016", 11, 3, "Cured"),
    ("Dev Arora", 36, "Male", "R027", 10, 2, "Cured"),
    ("Gopal Menon", 78, "Male", "R031", 12, 4, "Deceased"),
]

ALL_TABLES = ["notifications", "audit_logs", "discharge_approvals", "treatments", "doctor_visits",
              "temperature_readings", "patients"]


def clear_all(conn) -> None:
    conn.execute(db.temperature_readings.update().values(supersedes_id=None))
    for table in ALL_TABLES:
        conn.execute(db.metadata.tables[table].delete())
    conn.execute(db.rooms.update().values(status="Available"))


def load_demo_data(conn, now: datetime) -> None:
    today = now.date()
    uid = {r["role"]: r for r in db.rows(conn, "SELECT id, role, full_name FROM users ORDER BY id")}
    nurse, doctor, admin = uid["nurse"]["id"], uid["doctor"]["id"], uid["admin"]["id"]
    next_seq = (db.scalar(conn, "SELECT COALESCE(MAX(seq), 0) FROM patients") or 0) + 1

    def at(days_ago: int, hh: int, mm: int) -> str:
        stamp = datetime.combine(today - timedelta(days=days_ago), time(hh, mm))
        return logic.ts(min(stamp, now))  # never in the future

    def add_patient(name, age, gender, room, admitted_ago, **extra) -> str:
        nonlocal next_seq
        pid = f"P{next_seq:04d}"
        next_seq += 1
        conn.execute(db.patients.insert().values(
            patient_id=pid, name=name, age=age, gender=gender, contact=None,
            admission_date=(today - timedelta(days=admitted_ago)).isoformat(),
            initial_notes="Fictional demonstration record.", room_id=room, is_demo=1,
            created_by=admin, created_at=at(admitted_ago, 10, 0),
            **{"occupying_room": 1, "status": "Admitted", **extra}))
        return pid

    def add_reading(pid, days_ago, temp, minute=10, **extra) -> int:
        return conn.execute(db.temperature_readings.insert().values(
            patient_id=pid, reading_date=(today - timedelta(days=days_ago)).isoformat(),
            recorded_at=at(days_ago, 8, minute), temperature_c=temp, recorded_by=nurse,
            created_at=at(days_ago, 8, minute), **{"is_current": 1, **extra})).inserted_primary_key[0]

    def add_visit(pid, days_ago, treatment) -> None:
        vid = conn.execute(db.doctor_visits.insert().values(
            patient_id=pid, visit_date=(today - timedelta(days=days_ago)).isoformat(), doctor_id=doctor,
            notes="Routine review (demo).", completed_at=at(days_ago, 11, 30))).inserted_primary_key[0]
        conn.execute(db.treatments.insert().values(
            patient_id=pid, doctor_id=doctor, visit_id=vid, entry_type="Treatment", treatment=treatment,
            notes="Routine review (demo).", recorded_at=at(days_ago, 11, 30)))

    for i, (name, age, gender, room, admitted_ago, readings, extra) in enumerate(ACTIVE_PATIENTS):
        pid = add_patient(name, age, gender, room, admitted_ago)
        conn.execute(db.rooms.update().where(db.rooms.c.room_id == room).values(status="Occupied"))
        for days_ago, temp in sorted(readings.items(), reverse=True):
            if days_ago == 0 and "corrected_from" in extra:
                old = add_reading(pid, 0, extra["corrected_from"], minute=5, is_current=0)
                add_reading(pid, 0, temp, minute=20, supersedes_id=old,
                            correction_reason="Typing error on first entry (demo).")
                db.log_audit(conn, {"id": nurse, "username": "nurse", "role": "nurse"}, "temperature.corrected",
                             "temperature_reading", old, {"patient_id": pid, "original_c": extra["corrected_from"],
                                                          "corrected_c": temp}, at(0, 8, 20))
            else:
                add_reading(pid, days_ago, temp, minute=5 + (i * 3) % 50)
            if days_ago >= 1:  # past days: the doctor visited after each reading
                fever = logic.is_fever(temp)
                add_visit(pid, days_ago, "Antipyretic and oral fluids (demo)" if fever else "Observation (demo)")
        if extra.get("visited"):
            add_visit(pid, 0, "Observation (demo)")
        if extra.get("approved"):
            add_visit(pid, 0, "Observation (demo)")
            streak = logic.fever_free_streak({today - timedelta(days=d): t for d, t in readings.items()}, today)
            conn.execute(db.discharge_approvals.insert().values(
                patient_id=pid, doctor_id=doctor, approved_at=at(0, 11, 45), fever_free_days=streak,
                note="Fit for discharge (demo).", status="Approved"))
            conn.execute(db.patients.update().where(db.patients.c.patient_id == pid).values(status="Discharge Approved"))
            conn.execute(db.notifications.insert().values(
                target_role="admin", kind="discharge_approved", patient_id=pid,
                title=f"Discharge approved: {name} ({pid})",
                message=f"{uid['doctor']['full_name']} approved discharge for {name} in room {room}. "
                        "Complete the discharge to release the room.",
                created_at=at(0, 11, 45), is_read=0))

    for name, age, gender, room, admitted_ago, outcome_ago, outcome in CLOSED_PATIENTS:
        cured = outcome == "Cured"
        pid = add_patient(name, age, gender, room, admitted_ago, occupying_room=0,
                          status="Discharged" if cured else "Deceased", outcome=outcome,
                          outcome_at=at(outcome_ago, 15, 0), room_released_at=at(outcome_ago, 15, 0))
        stay = admitted_ago - outcome_ago
        for n, days_ago in enumerate(range(admitted_ago - 1, outcome_ago - 1, -1)):
            if cured:
                temp = 38.6 if n < stay - 4 else 37.0
            else:
                temp = 39.4
            add_reading(pid, days_ago, temp)
        if cured:
            conn.execute(db.discharge_approvals.insert().values(
                patient_id=pid, doctor_id=doctor, approved_at=at(outcome_ago, 12, 0), fever_free_days=3,
                note="Fit for discharge (demo).", status="Completed", completed_by=admin,
                completed_at=at(outcome_ago, 15, 0)))
            conn.execute(db.notifications.insert().values(
                target_role="admin", kind="discharge_approved", patient_id=pid,
                title=f"Discharge approved: {name} ({pid})",
                message=f"{uid['doctor']['full_name']} approved discharge for {name} in room {room}.",
                created_at=at(outcome_ago, 12, 0), is_read=1, read_at=at(outcome_ago, 15, 0)))
