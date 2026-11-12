"""All database operations for NOVA.

Every function takes the logged-in ``user`` and checks the permission map in
auth.py before touching data, so access control is enforced here on the
server side regardless of what the UI shows. Each write runs inside a single
database transaction and leaves an audit-log entry.

``now`` is injectable so date-dependent behaviour can be tested."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.exc import IntegrityError

import auth
import config
import database as db
import logic

ACTIVE = "('Admitted','Discharge Approved')"
GENDERS = ("Female", "Male", "Other")


class ValidationError(Exception):
    """Raised when input or the current state makes an action invalid."""


def _now(now: datetime | None) -> datetime:
    return (now or logic.hospital_now()).replace(microsecond=0)


def _clean(value, limit: int = 2000) -> str | None:
    value = (value or "").strip()
    return value[:limit] if value else None


def _active_patient(conn, patient_id: str) -> dict:
    p = db.one(conn, "SELECT * FROM patients WHERE patient_id = :p", p=patient_id)
    if not p:
        raise ValidationError("Patient not found.")
    if p["status"] not in ("Admitted", "Discharge Approved"):
        raise ValidationError(f"{p['name']} is no longer an active patient ({p['status']}).")
    return p


def _readings_by_day(conn, patient_id: str) -> dict[date, float]:
    rs = db.rows(conn, "SELECT reading_date, temperature_c FROM temperature_readings "
                       "WHERE patient_id = :p AND is_current = 1", p=patient_id)
    return {date.fromisoformat(r["reading_date"]): r["temperature_c"] for r in rs}


# ----------------------------------------------------------------- reads ---

def patient_overview(user: dict, now: datetime | None = None) -> list[dict]:
    """Active patients with every date-derived status computed for 'today'.

    Nothing here is stored: temperature status, visit status, streak and
    eligibility are derived from dated records each time, so they roll over
    correctly at midnight even if nobody has the application open."""
    auth.require(user, "view_temperatures")
    today = _now(now).date()
    with db.engine().connect() as conn:
        pts = db.rows(conn, f"SELECT * FROM patients WHERE status IN {ACTIVE} ORDER BY room_id")
        rds = db.rows(conn, f"""SELECT r.patient_id, r.reading_date, r.temperature_c, r.recorded_at
                                FROM temperature_readings r JOIN patients p ON p.patient_id = r.patient_id
                                WHERE r.is_current = 1 AND p.status IN {ACTIVE}""")
        visits = db.rows(conn, "SELECT patient_id, completed_at FROM doctor_visits WHERE visit_date = :d",
                         d=today.isoformat())
    by_patient: dict[str, dict[date, dict]] = {}
    for r in rds:
        by_patient.setdefault(r["patient_id"], {})[date.fromisoformat(r["reading_date"])] = r
    visited = {v["patient_id"]: v["completed_at"] for v in visits}
    out = []
    for p in pts:
        days = by_patient.get(p["patient_id"], {})
        temps = {d: r["temperature_c"] for d, r in days.items()}
        todays = days.get(today)
        latest_day = max(days) if days else None
        streak = logic.fever_free_streak(temps, today)
        out.append({**p,
                    "today_temp": todays["temperature_c"] if todays else None,
                    "today_recorded_at": todays["recorded_at"] if todays else None,
                    "temp_status": "Recorded Today" if todays else "Pending",
                    "latest_temp": days[latest_day]["temperature_c"] if latest_day else None,
                    "latest_date": latest_day.isoformat() if latest_day else None,
                    "fever_free_days": streak,
                    "eligible": logic.is_discharge_eligible(streak, p["status"]),
                    "ready_for_visit": todays is not None,
                    "visited_today": p["patient_id"] in visited,
                    "visit_status": ("Visit Completed" if p["patient_id"] in visited
                                     else "Ready for Visit" if todays else "Not Ready")})
    return out


def active_patients(user: dict) -> list[dict]:
    auth.require(user, "view_patients")
    with db.engine().connect() as conn:
        return db.rows(conn, f"SELECT * FROM patients WHERE status IN {ACTIVE} ORDER BY room_id")


def get_patient(user: dict, patient_id: str) -> dict | None:
    auth.require(user, "view_patients")
    with db.engine().connect() as conn:
        return db.one(conn, "SELECT * FROM patients WHERE patient_id = :p", p=patient_id)


def temperature_history(user: dict, patient_id: str) -> list[dict]:
    """Current (non-superseded) readings, oldest first."""
    auth.require(user, "view_temperatures")
    with db.engine().connect() as conn:
        rs = db.rows(conn, """SELECT r.*, u.full_name AS recorded_by_name FROM temperature_readings r
                              JOIN users u ON u.id = r.recorded_by
                              WHERE r.patient_id = :p AND r.is_current = 1 ORDER BY r.reading_date""", p=patient_id)
    for r in rs:
        r["classification"] = logic.classify(r["temperature_c"])
    return rs


def correction_trail(user: dict, patient_id: str) -> list[dict]:
    """Every superseded reading together with the value that replaced it."""
    auth.require(user, "view_temperatures")
    with db.engine().connect() as conn:
        return db.rows(conn, """SELECT old.reading_date, old.temperature_c AS original_c,
                                       old.recorded_at AS original_at, ou.full_name AS original_by,
                                       new.temperature_c AS corrected_c, new.created_at AS corrected_at,
                                       nu.full_name AS corrected_by, new.correction_reason
                                FROM temperature_readings new
                                JOIN temperature_readings old ON old.id = new.supersedes_id
                                JOIN users ou ON ou.id = old.recorded_by
                                JOIN users nu ON nu.id = new.recorded_by
                                WHERE new.patient_id = :p ORDER BY new.id""", p=patient_id)


def fever_free_days(user: dict, patient_id: str, now: datetime | None = None) -> int:
    auth.require(user, "view_temperatures")
    with db.engine().connect() as conn:
        return logic.fever_free_streak(_readings_by_day(conn, patient_id), _now(now).date())


def visit_history(user: dict, patient_id: str | None = None) -> list[dict]:
    auth.require(user, "view_clinical")
    where = "WHERE v.patient_id = :p" if patient_id else ""
    with db.engine().connect() as conn:
        return db.rows(conn, f"""SELECT v.*, p.name AS patient_name, p.room_id, u.full_name AS doctor_name
                                 FROM doctor_visits v JOIN patients p ON p.patient_id = v.patient_id
                                 JOIN users u ON u.id = v.doctor_id {where}
                                 ORDER BY v.completed_at DESC""", **({"p": patient_id} if patient_id else {}))


def treatment_records(user: dict, patient_id: str | None = None) -> list[dict]:
    auth.require(user, "view_clinical")
    where = "WHERE t.patient_id = :p" if patient_id else ""
    with db.engine().connect() as conn:
        return db.rows(conn, f"""SELECT t.*, p.name AS patient_name, p.room_id, u.full_name AS doctor_name
                                 FROM treatments t JOIN patients p ON p.patient_id = t.patient_id
                                 JOIN users u ON u.id = t.doctor_id {where}
                                 ORDER BY t.recorded_at DESC, t.id DESC""", **({"p": patient_id} if patient_id else {}))


def room_overview(user: dict) -> list[dict]:
    """All 74 rooms with their current occupant (if any)."""
    auth.require(user, "view_rooms")
    with db.engine().connect() as conn:
        return db.rows(conn, """SELECT r.room_id, r.status, p.patient_id, p.name AS patient_name,
                                       p.status AS patient_status, p.admission_date
                                FROM rooms r LEFT JOIN patients p
                                  ON p.room_id = r.room_id AND p.occupying_room = 1
                                ORDER BY r.room_id""")


def occupancy(user: dict) -> dict:
    """Occupancy counted from actual room assignments (never a stored total)."""
    auth.require(user, "view_rooms")
    with db.engine().connect() as conn:
        total = db.scalar(conn, "SELECT COUNT(*) FROM rooms")
        occupied = db.scalar(conn, "SELECT COUNT(*) FROM patients WHERE occupying_room = 1")
        flagged = db.scalar(conn, "SELECT COUNT(*) FROM rooms WHERE status = 'Occupied'")
        mismatch = db.scalar(conn, """SELECT COUNT(*) FROM rooms r WHERE
                 (r.status = 'Occupied') <> EXISTS (SELECT 1 FROM patients p
                                                     WHERE p.room_id = r.room_id AND p.occupying_room = 1)""")
    return {"total": total, "occupied": occupied, "available": total - occupied,
            "consistent": occupied == flagged and mismatch == 0}


def available_rooms(user: dict) -> list[str]:
    auth.require(user, "admit_patient")
    with db.engine().connect() as conn:
        return [r["room_id"] for r in db.rows(conn, """SELECT room_id FROM rooms r WHERE status = 'Available'
                 AND NOT EXISTS (SELECT 1 FROM patients p WHERE p.room_id = r.room_id AND p.occupying_room = 1)
                 ORDER BY room_id""")]


def discharge_queue(user: dict, status: str = "Approved") -> list[dict]:
    auth.require(user, "view_discharge_queue")
    order = "a.completed_at DESC" if status == "Completed" else "a.approved_at"
    with db.engine().connect() as conn:
        return db.rows(conn, f"""SELECT a.*, p.name AS patient_name, p.room_id, d.full_name AS doctor_name,
                                        c.full_name AS completed_by_name
                                 FROM discharge_approvals a JOIN patients p ON p.patient_id = a.patient_id
                                 JOIN users d ON d.id = a.doctor_id LEFT JOIN users c ON c.id = a.completed_by
                                 WHERE a.status = :s ORDER BY {order}""", s=status)


def approved_awaiting_admin(user: dict) -> list[dict]:
    """Doctor's read-only view of approvals not yet completed by admin."""
    auth.require(user, "approve_discharge")
    with db.engine().connect() as conn:
        return db.rows(conn, """SELECT a.*, p.name AS patient_name, p.room_id, d.full_name AS doctor_name
                                FROM discharge_approvals a JOIN patients p ON p.patient_id = a.patient_id
                                JOIN users d ON d.id = a.doctor_id WHERE a.status = 'Approved'
                                ORDER BY a.approved_at""")


def pending_closures(user: dict) -> list[dict]:
    """Deceased patients whose room has not yet been administratively released."""
    auth.require(user, "release_room")
    with db.engine().connect() as conn:
        return db.rows(conn, "SELECT * FROM patients WHERE status = 'Deceased' AND occupying_room = 1 ORDER BY outcome_at")


def notifications(user: dict) -> list[dict]:
    auth.require(user, "view_notifications")
    with db.engine().connect() as conn:
        return db.rows(conn, "SELECT * FROM notifications WHERE target_role = :r ORDER BY created_at DESC, id DESC",
                       r=user["role"])


def unread_notifications(user: dict) -> int:
    if not auth.can(user, "view_notifications"):
        return 0
    with db.engine().connect() as conn:
        return db.scalar(conn, "SELECT COUNT(*) FROM notifications WHERE target_role = :r AND is_read = 0", r=user["role"])


def success_stats(user: dict) -> dict:
    """Success rate from finalised outcomes only (admitted patients excluded)."""
    auth.require(user, "view_performance")
    with db.engine().connect() as conn:
        cured = db.scalar(conn, "SELECT COUNT(*) FROM patients WHERE status = 'Discharged' AND outcome = 'Cured'")
        deceased = db.scalar(conn, "SELECT COUNT(*) FROM patients WHERE status = 'Deceased' AND outcome = 'Deceased'")
    rate = logic.success_rate(cured, deceased)
    return {"cured": cured, "deceased": deceased, "finalised": cured + deceased, "rate": rate,
            "benchmark": config.SUCCESS_BENCHMARK_PCT, "status": logic.benchmark_status(rate)}


def finalised_outcomes(user: dict) -> list[dict]:
    auth.require(user, "view_performance")
    with db.engine().connect() as conn:
        return db.rows(conn, """SELECT patient_id, name, admission_date, outcome, outcome_at FROM patients
                                WHERE outcome IS NOT NULL ORDER BY outcome_at DESC""")


def has_demo_data() -> bool:
    with db.engine().connect() as conn:
        return bool(db.scalar(conn, "SELECT COUNT(*) FROM patients WHERE is_demo = 1"))


# ---------------------------------------------------------- nurse writes ---

def _check_reading_input(temp_c, recorded_at: datetime | None, now: datetime) -> tuple[float, datetime]:
    if not logic.is_valid_temperature(temp_c):
        raise ValidationError(f"Enter a temperature between {config.TEMP_MIN_C:.1f} and "
                              f"{config.TEMP_MAX_C:.1f} °C.")
    recorded_at = (recorded_at or now).replace(microsecond=0)
    if recorded_at.date() != now.date():
        raise ValidationError("Readings can only be recorded for the current hospital day.")
    if recorded_at > now + timedelta(minutes=1):
        raise ValidationError("The reading time cannot be in the future.")
    return round(float(temp_c), 1), recorded_at


def record_temperature(user: dict, patient_id: str, temp_c, recorded_at: datetime | None = None,
                       now: datetime | None = None) -> int:
    auth.require(user, "record_temperature")
    now = _now(now)
    temp, recorded_at = _check_reading_input(temp_c, recorded_at, now)
    try:
        with db.engine().begin() as conn:
            p = _active_patient(conn, patient_id)
            day = now.date().isoformat()
            if db.one(conn, "SELECT id FROM temperature_readings WHERE patient_id = :p AND reading_date = :d "
                            "AND is_current = 1", p=patient_id, d=day):
                raise ValidationError(f"A temperature has already been recorded for {p['name']} today. "
                                      "Use 'Correct reading' to change it.")
            rid = conn.execute(db.temperature_readings.insert().values(
                patient_id=patient_id, reading_date=day, recorded_at=logic.ts(recorded_at), temperature_c=temp,
                recorded_by=user["id"], is_current=1, created_at=logic.ts(now))).inserted_primary_key[0]
            db.log_audit(conn, user, "temperature.recorded", "temperature_reading", rid,
                         {"patient_id": patient_id, "temperature_c": temp}, logic.ts(now))
            return rid
    except IntegrityError:
        raise ValidationError("A temperature has already been recorded for this patient today.") from None


def correct_temperature(user: dict, patient_id: str, temp_c, reason: str | None = None,
                        recorded_at: datetime | None = None, now: datetime | None = None) -> int:
    """Same-day correction. The original row is kept (is_current = 0) and the
    new row points back to it, so the full history stays auditable."""
    auth.require(user, "correct_temperature")
    now = _now(now)
    temp, recorded_at = _check_reading_input(temp_c, recorded_at, now)
    with db.engine().begin() as conn:
        _active_patient(conn, patient_id)
        old = db.one(conn, "SELECT * FROM temperature_readings WHERE patient_id = :p AND reading_date = :d "
                           "AND is_current = 1", p=patient_id, d=now.date().isoformat())
        if not old:
            raise ValidationError("There is no reading from today to correct. Corrections are only "
                                  "permitted on the same calendar day.")
        if abs(old["temperature_c"] - temp) < 0.05:
            raise ValidationError("The corrected value is the same as the recorded value.")
        conn.execute(db.temperature_readings.update().where(db.temperature_readings.c.id == old["id"])
                     .values(is_current=0))
        rid = conn.execute(db.temperature_readings.insert().values(
            patient_id=patient_id, reading_date=old["reading_date"], recorded_at=logic.ts(recorded_at),
            temperature_c=temp, recorded_by=user["id"], is_current=1, supersedes_id=old["id"],
            correction_reason=_clean(reason, 500), created_at=logic.ts(now))).inserted_primary_key[0]
        db.log_audit(conn, user, "temperature.corrected", "temperature_reading", rid,
                     {"patient_id": patient_id, "original_reading_id": old["id"],
                      "original_c": old["temperature_c"], "corrected_c": temp,
                      "reason": _clean(reason, 500)}, logic.ts(now))
        return rid


# --------------------------------------------------------- doctor writes ---

def add_treatment(user: dict, patient_id: str, treatment: str | None, notes: str | None,
                  now: datetime | None = None) -> int:
    auth.require(user, "record_treatment")
    now = _now(now)
    treatment, notes = _clean(treatment), _clean(notes)
    if not treatment and not notes:
        raise ValidationError("Enter the treatment administered or a clinical note.")
    with db.engine().begin() as conn:
        _active_patient(conn, patient_id)
        tid = conn.execute(db.treatments.insert().values(
            patient_id=patient_id, doctor_id=user["id"], entry_type="Treatment" if treatment else "Clinical Note",
            treatment=treatment, notes=notes, recorded_at=logic.ts(now))).inserted_primary_key[0]
        db.log_audit(conn, user, "treatment.recorded", "treatment", tid, {"patient_id": patient_id}, logic.ts(now))
        return tid


def complete_visit(user: dict, patient_id: str, treatment: str | None = None, notes: str | None = None,
                   now: datetime | None = None) -> int:
    auth.require(user, "complete_visit")
    now = _now(now)
    day = now.date().isoformat()
    treatment, notes = _clean(treatment), _clean(notes)
    try:
        with db.engine().begin() as conn:
            p = _active_patient(conn, patient_id)
            if not db.one(conn, "SELECT id FROM temperature_readings WHERE patient_id = :p AND reading_date = :d "
                                "AND is_current = 1", p=patient_id, d=day):
                raise ValidationError(f"Today's temperature for {p['name']} has not been recorded yet. "
                                      "The visit cannot be completed until the nurse records it.")
            if db.one(conn, "SELECT id FROM doctor_visits WHERE patient_id = :p AND visit_date = :d",
                      p=patient_id, d=day):
                raise ValidationError("Today's visit has already been completed for this patient.")
            vid = conn.execute(db.doctor_visits.insert().values(
                patient_id=patient_id, visit_date=day, doctor_id=user["id"], notes=notes,
                completed_at=logic.ts(now))).inserted_primary_key[0]
            if treatment or notes:
                conn.execute(db.treatments.insert().values(
                    patient_id=patient_id, doctor_id=user["id"], visit_id=vid,
                    entry_type="Treatment" if treatment else "Clinical Note",
                    treatment=treatment, notes=notes, recorded_at=logic.ts(now)))
            db.log_audit(conn, user, "visit.completed", "doctor_visit", vid, {"patient_id": patient_id}, logic.ts(now))
            return vid
    except IntegrityError:
        raise ValidationError("Today's visit has already been completed for this patient.") from None


def approve_discharge(user: dict, patient_id: str, note: str | None = None, now: datetime | None = None) -> int:
    auth.require(user, "approve_discharge")
    now = _now(now)
    try:
        with db.engine().begin() as conn:
            p = _active_patient(conn, patient_id)
            if p["status"] != "Admitted":
                raise ValidationError("Discharge has already been approved for this patient.")
            streak = logic.fever_free_streak(_readings_by_day(conn, patient_id), now.date())
            if not logic.is_discharge_eligible(streak, p["status"]):
                raise ValidationError(f"{p['name']} is not eligible for discharge: {streak} of "
                                      f"{config.REQUIRED_FEVER_FREE_DAYS} complete fever-free days.")
            aid = conn.execute(db.discharge_approvals.insert().values(
                patient_id=patient_id, doctor_id=user["id"], approved_at=logic.ts(now),
                fever_free_days=streak, note=_clean(note), status="Approved")).inserted_primary_key[0]
            conn.execute(db.patients.update().where(db.patients.c.patient_id == patient_id)
                         .values(status="Discharge Approved"))
            conn.execute(db.notifications.insert().values(
                target_role="admin", kind="discharge_approved", patient_id=patient_id,
                title=f"Discharge approved: {p['name']} ({patient_id})",
                message=f"{user['full_name']} approved discharge for {p['name']} in room {p['room_id']}. "
                        "Complete the discharge to release the room.",
                created_at=logic.ts(now), is_read=0))
            db.log_audit(conn, user, "discharge.approved", "discharge_approval", aid,
                         {"patient_id": patient_id, "fever_free_days": streak}, logic.ts(now))
            return aid
    except IntegrityError:
        raise ValidationError("Discharge has already been approved for this patient.") from None


def record_death(user: dict, patient_id: str, death_at: datetime, note: str | None = None,
                 now: datetime | None = None) -> None:
    auth.require(user, "record_death")
    now = _now(now)
    if death_at is None:
        raise ValidationError("Enter the date and time of death.")
    death_at = death_at.replace(microsecond=0)
    if death_at > now + timedelta(minutes=1):
        raise ValidationError("The date and time of death cannot be in the future.")
    with db.engine().begin() as conn:
        p = _active_patient(conn, patient_id)
        if death_at.date() < date.fromisoformat(p["admission_date"]):
            raise ValidationError("The date of death cannot be earlier than the admission date.")
        conn.execute(db.patients.update().where(db.patients.c.patient_id == patient_id)
                     .values(status="Deceased", outcome="Deceased", outcome_at=logic.ts(death_at)))
        conn.execute(db.discharge_approvals.update()
                     .where(db.discharge_approvals.c.patient_id == patient_id,
                            db.discharge_approvals.c.status == "Approved").values(status="Cancelled"))
        if _clean(note):
            conn.execute(db.treatments.insert().values(
                patient_id=patient_id, doctor_id=user["id"], entry_type="Death Note",
                notes=_clean(note), recorded_at=logic.ts(now)))
        conn.execute(db.notifications.insert().values(
            target_role="admin", kind="death_recorded", patient_id=patient_id,
            title=f"Administrative closure required: {p['name']} ({patient_id})",
            message=f"{user['full_name']} recorded the death of {p['name']}. Room {p['room_id']} stays "
                    "occupied until it is released from the Discharge Queue.",
            created_at=logic.ts(now), is_read=0))
        db.log_audit(conn, user, "patient.death_recorded", "patient", patient_id,
                     {"death_at": logic.ts(death_at)}, logic.ts(now))


# ---------------------------------------------------------- admin writes ---

def admit_patient(user: dict, name: str, age, gender: str, room_id: str, admission_date: date,
                  contact: str | None = None, initial_notes: str | None = None,
                  now: datetime | None = None) -> str:
    auth.require(user, "admit_patient")
    now = _now(now)
    name = " ".join((name or "").split())
    errors = []
    if len(name) < 2 or len(name) > 100 or not re.fullmatch(r"[^\W\d_][\w .'\-]*", name):
        errors.append("Enter the patient's full name (letters, spaces, . ' - only).")
    try:
        age_int = int(age)
        if isinstance(age, float) and age != age_int or not 0 <= age_int <= 120:
            raise ValueError
    except (TypeError, ValueError):
        age_int = None
        errors.append("Enter an age between 0 and 120.")
    if gender not in GENDERS:
        errors.append("Select a gender.")
    contact = _clean(contact, 30)
    if contact and not re.fullmatch(r"\+?\d[\d\s\-]{6,18}", contact):
        errors.append("Contact number should contain 7-15 digits (optional leading +).")
    if not isinstance(admission_date, date):
        errors.append("Enter the admission date.")
    elif admission_date > now.date():
        errors.append("The admission date cannot be in the future.")
    if not room_id:
        errors.append("Select an available room.")
    if errors:
        raise ValidationError(" ".join(errors))
    try:
        with db.engine().begin() as conn:
            room = db.one(conn, "SELECT * FROM rooms WHERE room_id = :r", r=room_id)
            if not room:
                raise ValidationError("That room does not exist.")
            if room["status"] != "Available" or db.one(
                    conn, "SELECT 1 AS x FROM patients WHERE room_id = :r AND occupying_room = 1", r=room_id):
                raise ValidationError(f"Room {room_id} is already occupied. Select another room.")
            seq = conn.execute(db.patients.insert().values(
                patient_id=f"tmp-{uuid.uuid4().hex}", name=name, age=age_int, gender=gender, contact=contact,
                admission_date=admission_date.isoformat(), initial_notes=_clean(initial_notes),
                room_id=room_id, occupying_room=1, status="Admitted", is_demo=0,
                created_by=user["id"], created_at=logic.ts(now))).inserted_primary_key[0]
            patient_id = f"P{seq:04d}"
            conn.execute(db.patients.update().where(db.patients.c.seq == seq).values(patient_id=patient_id))
            conn.execute(db.rooms.update().where(db.rooms.c.room_id == room_id).values(status="Occupied"))
            db.log_audit(conn, user, "patient.admitted", "patient", patient_id, {"room_id": room_id}, logic.ts(now))
            return patient_id
    except IntegrityError:
        raise ValidationError(f"Room {room_id} was just assigned to another patient. Select another room.") from None


def _release(conn, patient: dict, now: datetime) -> None:
    conn.execute(db.patients.update().where(db.patients.c.patient_id == patient["patient_id"])
                 .values(occupying_room=0, room_released_at=logic.ts(now)))
    conn.execute(db.rooms.update().where(db.rooms.c.room_id == patient["room_id"]).values(status="Available"))


def complete_discharge(user: dict, approval_id: int, now: datetime | None = None) -> str:
    """Admin completes a discharge - only possible for a doctor-approved one."""
    auth.require(user, "complete_discharge")
    now = _now(now)
    with db.engine().begin() as conn:
        a = db.one(conn, "SELECT * FROM discharge_approvals WHERE id = :i", i=approval_id)
        if not a or a["status"] != "Approved":
            raise ValidationError("This discharge has not been approved by a doctor, or was already completed.")
        p = db.one(conn, "SELECT * FROM patients WHERE patient_id = :p", p=a["patient_id"])
        if p["status"] != "Discharge Approved":
            raise ValidationError("This patient is not awaiting discharge completion.")
        conn.execute(db.discharge_approvals.update().where(db.discharge_approvals.c.id == approval_id)
                     .values(status="Completed", completed_by=user["id"], completed_at=logic.ts(now)))
        conn.execute(db.patients.update().where(db.patients.c.patient_id == p["patient_id"])
                     .values(status="Discharged", outcome="Cured", outcome_at=logic.ts(now)))
        _release(conn, p, now)
        conn.execute(db.notifications.update()
                     .where(db.notifications.c.patient_id == p["patient_id"],
                            db.notifications.c.kind == "discharge_approved", db.notifications.c.is_read == 0)
                     .values(is_read=1, read_at=logic.ts(now)))
        db.log_audit(conn, user, "discharge.completed", "discharge_approval", approval_id,
                     {"patient_id": p["patient_id"], "room_released": p["room_id"]}, logic.ts(now))
        return p["patient_id"]


def release_room(user: dict, patient_id: str, now: datetime | None = None) -> str:
    """Administrative closure for a deceased patient: frees the room."""
    auth.require(user, "release_room")
    now = _now(now)
    with db.engine().begin() as conn:
        p = db.one(conn, "SELECT * FROM patients WHERE patient_id = :p", p=patient_id)
        if not p or p["status"] != "Deceased" or not p["occupying_room"]:
            raise ValidationError("Only the room of a deceased patient awaiting closure can be released here.")
        _release(conn, p, now)
        conn.execute(db.notifications.update()
                     .where(db.notifications.c.patient_id == patient_id,
                            db.notifications.c.kind == "death_recorded", db.notifications.c.is_read == 0)
                     .values(is_read=1, read_at=logic.ts(now)))
        db.log_audit(conn, user, "room.released", "patient", patient_id, {"room_id": p["room_id"]}, logic.ts(now))
        return p["room_id"]


def mark_notification_read(user: dict, notification_id: int | None = None, now: datetime | None = None) -> None:
    """Mark one notification (or all, when id is None) as read. History is kept."""
    auth.require(user, "view_notifications")
    n = db.notifications
    stmt = n.update().where(n.c.target_role == user["role"], n.c.is_read == 0)
    if notification_id is not None:
        stmt = stmt.where(n.c.id == notification_id)
    with db.engine().begin() as conn:
        conn.execute(stmt.values(is_read=1, read_at=logic.ts(_now(now))))


def reset_demo_data(user: dict, now: datetime | None = None) -> None:
    """Erase all patient data and reload the fictional demonstration set."""
    auth.require(user, "reset_demo_data")
    import seed
    now = _now(now)
    with db.engine().begin() as conn:
        seed.clear_all(conn)
        seed.load_demo_data(conn, now)
        conn.execute(db.app_meta.update().where(db.app_meta.c.key == "demo_seeded").values(value="1"))
        db.log_audit(conn, user, "demo.reset", "system", None, None, logic.ts(now))
