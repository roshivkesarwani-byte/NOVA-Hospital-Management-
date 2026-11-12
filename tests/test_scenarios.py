"""The 18 acceptance scenarios from the NOVA specification, run against a
real database. By default a throw-away SQLite file is used; set
NOVA_TEST_DATABASE_URL to run the same suite against PostgreSQL."""
import os
import sys
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import auth  # noqa: E402
import database as db  # noqa: E402
import logic  # noqa: E402
import services as sv  # noqa: E402

DAY1 = datetime(2026, 3, 2, 9, 0, 0)  # an arbitrary hospital "now"


def later(days=0, hours=0):
    return DAY1 + timedelta(days=days, hours=hours)


@pytest.fixture
def hospital(tmp_path):
    """Empty hospital (no demo patients) with the three accounts."""
    url = os.getenv("NOVA_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'nova.db'}"
    db.configure(url)
    if not url.startswith("sqlite"):
        db.metadata.drop_all(db.engine())
    db.init_db(seed_demo=False)
    return {r: auth.authenticate(r, f"{r}123") for r in ("nurse", "doctor", "admin")}


def admit(h, name="Test Patient", room="R001", now=DAY1):
    return sv.admit_patient(h["admin"], name, 40, "Female", room, now.date(), now=now)


def overview(h, pid, now):
    return next(p for p in sv.patient_overview(h["doctor"], now) if p["patient_id"] == pid)


def record_days(h, pid, temps, start=DAY1):
    """Record one reading per day starting at `start`; None skips a day."""
    for i, t in enumerate(temps):
        if t is not None:
            sv.record_temperature(h["nurse"], pid, t, now=start + timedelta(days=i))


def test_01_recording_changes_pending_to_recorded_today(hospital):
    pid = admit(hospital)
    assert overview(hospital, pid, DAY1)["temp_status"] == "Pending"
    sv.record_temperature(hospital["nurse"], pid, 37.2, now=DAY1)
    row = overview(hospital, pid, DAY1)
    assert row["temp_status"] == "Recorded Today" and row["today_temp"] == 37.2
    with pytest.raises(sv.ValidationError):  # duplicate same-day reading is refused
        sv.record_temperature(hospital["nurse"], pid, 37.5, now=later(hours=1))
    for bad in (12, 60, None, "abc", float("nan")):  # impossible values are refused
        with pytest.raises(sv.ValidationError):
            sv.record_temperature(hospital["nurse"], pid, bad, now=later(days=1))


def test_02_same_day_correction_keeps_original_in_audit_trail(hospital):
    pid = admit(hospital)
    sv.record_temperature(hospital["nurse"], pid, 39.2, now=DAY1)
    sv.correct_temperature(hospital["nurse"], pid, 37.2, "typo", now=later(hours=1))
    assert overview(hospital, pid, later(hours=1))["today_temp"] == 37.2
    assert [r["temperature_c"] for r in sv.temperature_history(hospital["nurse"], pid)] == [37.2]
    trail = sv.correction_trail(hospital["nurse"], pid)
    assert len(trail) == 1 and trail[0]["original_c"] == 39.2 and trail[0]["corrected_c"] == 37.2
    with db.engine().connect() as conn:
        assert db.scalar(conn, "SELECT COUNT(*) FROM temperature_readings WHERE patient_id = :p", p=pid) == 2
        assert db.scalar(conn, "SELECT COUNT(*) FROM audit_logs WHERE action = 'temperature.corrected'") == 1
    with pytest.raises(sv.ValidationError):  # next day: yesterday's reading can no longer be corrected
        sv.correct_temperature(hospital["nurse"], pid, 36.9, now=later(days=1))
    assert sv.temperature_history(hospital["nurse"], pid)[0]["temperature_c"] == 37.2


def test_03_visit_blocked_while_temperature_pending(hospital):
    pid = admit(hospital)
    assert overview(hospital, pid, DAY1)["visit_status"] == "Not Ready"
    with pytest.raises(sv.ValidationError):
        sv.complete_visit(hospital["doctor"], pid, now=DAY1)
    assert sv.visit_history(hospital["doctor"], pid) == []


def test_04_recorded_temperature_makes_patient_ready_for_visit(hospital):
    pid = admit(hospital)
    sv.record_temperature(hospital["nurse"], pid, 37.0, now=DAY1)
    assert overview(hospital, pid, DAY1)["visit_status"] == "Ready for Visit"
    sv.complete_visit(hospital["doctor"], pid, "Observation", "Stable", now=later(hours=2))
    assert overview(hospital, pid, later(hours=2))["visit_status"] == "Visit Completed"
    assert len(sv.treatment_records(hospital["doctor"], pid)) == 1
    with pytest.raises(sv.ValidationError):  # no duplicate visit on the same day
        sv.complete_visit(hospital["doctor"], pid, now=later(hours=3))


def test_05_two_full_fever_free_days_is_not_eligible(hospital):
    pid = admit(hospital)
    record_days(hospital, pid, [37.0, 37.1, 36.9])  # days 1-3; "today" is day 3
    row = overview(hospital, pid, later(days=2))
    assert row["fever_free_days"] == 2 and not row["eligible"]  # today is partial and does not count
    with pytest.raises(sv.ValidationError):
        sv.approve_discharge(hospital["doctor"], pid, now=later(days=2))


def test_06_three_full_fever_free_days_is_eligible(hospital):
    pid = admit(hospital)
    record_days(hospital, pid, [37.0, 37.1, 36.9])
    row = overview(hospital, pid, later(days=3))  # day 4, nothing recorded yet today
    assert row["fever_free_days"] == 3 and row["eligible"]
    # Several readings' worth of data on fewer days must not count (days, not readings).
    pid2 = admit(hospital, "Second Patient", "R002")
    sv.record_temperature(hospital["nurse"], pid2, 37.0, now=later(days=2))
    sv.correct_temperature(hospital["nurse"], pid2, 36.8, now=later(days=2, hours=1))
    sv.correct_temperature(hospital["nurse"], pid2, 36.9, now=later(days=2, hours=2))
    assert overview(hospital, pid2, later(days=3))["fever_free_days"] == 1


def test_07_fever_or_missing_reading_breaks_streak(hospital):
    fever = admit(hospital, "Fever Case", "R001")
    record_days(hospital, fever, [37.0, 37.0, 38.0, 37.0])  # 38.0 counts as fever (>= threshold)
    assert overview(hospital, fever, later(days=4))["fever_free_days"] == 1
    missing = admit(hospital, "Missing Case", "R002")
    record_days(hospital, missing, [37.0, 37.0, None, 37.0])
    assert overview(hospital, missing, later(days=4))["fever_free_days"] == 1
    gap = admit(hospital, "Gap Yesterday", "R003")
    record_days(hospital, gap, [37.0, 37.0, 37.0])
    assert overview(hospital, gap, later(days=4))["fever_free_days"] == 0  # nothing recorded yesterday
    today_fever = admit(hospital, "Fever Today", "R004")
    record_days(hospital, today_fever, [37.0, 37.0, 37.0, 38.6])
    row = overview(hospital, today_fever, later(days=3))
    assert row["fever_free_days"] == 0 and not row["eligible"]  # fever today resets immediately


def test_08_doctor_approval_reaches_admin_queue_immediately(hospital):
    pid = admit(hospital)
    record_days(hospital, pid, [37.0, 37.0, 37.0])
    assert sv.discharge_queue(hospital["admin"]) == [] and sv.unread_notifications(hospital["admin"]) == 0
    sv.approve_discharge(hospital["doctor"], pid, "Fit for discharge", now=later(days=3))
    queue = sv.discharge_queue(hospital["admin"])
    assert [q["patient_id"] for q in queue] == [pid]
    assert queue[0]["doctor_name"] == hospital["doctor"]["full_name"] and queue[0]["approved_at"]
    assert sv.unread_notifications(hospital["admin"]) == 1
    assert sv.get_patient(hospital["admin"], pid)["status"] == "Discharge Approved"
    assert sv.occupancy(hospital["admin"])["occupied"] == 1  # room is NOT freed by approval
    with pytest.raises(sv.ValidationError):  # cannot approve twice
        sv.approve_discharge(hospital["doctor"], pid, now=later(days=3))


def test_09_admin_completion_frees_the_room(hospital):
    pid = admit(hospital, room="R010")
    record_days(hospital, pid, [37.0, 37.0, 37.0])
    aid = sv.approve_discharge(hospital["doctor"], pid, now=later(days=3))
    sv.complete_discharge(hospital["admin"], aid, now=later(days=3, hours=1))
    p = sv.get_patient(hospital["admin"], pid)
    assert (p["status"], p["outcome"], p["occupying_room"]) == ("Discharged", "Cured", 0)
    assert "R010" in sv.available_rooms(hospital["admin"])
    assert sv.occupancy(hospital["admin"]) == {"total": 74, "occupied": 0, "available": 74, "consistent": True}
    assert sv.active_patients(hospital["admin"]) == []
    assert len(sv.temperature_history(hospital["doctor"], pid)) == 3  # history preserved
    assert sv.notifications(hospital["admin"])[0]["is_read"] == 1 and len(sv.notifications(hospital["admin"])) == 1
    with pytest.raises(sv.ValidationError):  # cannot complete twice / without an approval
        sv.complete_discharge(hospital["admin"], aid, now=later(days=3, hours=2))
    with pytest.raises(sv.ValidationError):
        sv.complete_discharge(hospital["admin"], 9999)


def test_10_death_excluded_from_active_and_counted_as_deceased(hospital):
    pid = admit(hospital, room="R020")
    other = admit(hospital, "Other Patient", "R021")
    with pytest.raises(sv.ValidationError):  # future time refused
        sv.record_death(hospital["doctor"], pid, later(days=1), now=later(hours=1))
    sv.record_death(hospital["doctor"], pid, later(hours=1), "note", now=later(hours=1))
    assert [p["patient_id"] for p in sv.active_patients(hospital["doctor"])] == [other]
    assert [p["patient_id"] for p in sv.patient_overview(hospital["nurse"], later(hours=1))] == [other]
    stats = sv.success_stats(hospital["admin"])
    assert (stats["cured"], stats["deceased"], stats["rate"]) == (0, 1, 0.0)
    assert sv.occupancy(hospital["admin"])["occupied"] == 2  # room held until administrative closure
    assert sv.unread_notifications(hospital["admin"]) == 1
    sv.release_room(hospital["admin"], pid, now=later(hours=2))
    assert sv.occupancy(hospital["admin"])["occupied"] == 1 and "R020" in sv.available_rooms(hospital["admin"])
    with pytest.raises(sv.ValidationError):  # nothing further can be recorded for the patient
        sv.record_temperature(hospital["nurse"], pid, 37.0, now=later(hours=3))
    with pytest.raises(Exception):  # the database itself refuses "deceased but cured"
        with db.engine().begin() as conn:
            conn.execute(text("UPDATE patients SET outcome = 'Cured' WHERE patient_id = :p"), {"p": pid})


def test_11_success_rate_from_finalised_outcomes_only(hospital):
    assert sv.success_stats(hospital["admin"])["rate"] is None  # N/A, no division by zero
    assert logic.benchmark_status(None) == "N/A"
    pids = [admit(hospital, f"Patient {chr(65 + i)}", f"R{i + 1:03d}") for i in range(8)]
    for pid in pids[:7]:
        record_days(hospital, pid, [37.0, 37.0, 37.0])
    for pid in pids[:6]:  # six cured
        sv.complete_discharge(hospital["admin"], sv.approve_discharge(hospital["doctor"], pid, now=later(days=3)), now=later(days=3))
    sv.record_death(hospital["doctor"], pids[7], later(days=3), now=later(days=3))  # one deceased
    sv.approve_discharge(hospital["doctor"], pids[6], now=later(days=3))  # approved but not finalised
    stats = sv.success_stats(hospital["doctor"])
    assert (stats["cured"], stats["deceased"]) == (6, 1)
    assert stats["rate"] == pytest.approx(6 / 7 * 100) and stats["status"] == "Above benchmark"
    assert logic.success_rate(4, 1) == 80.0 and logic.benchmark_status(80.0) == "Below benchmark"
    assert logic.benchmark_status(85.0) == "Above benchmark"


def test_12_admission_assigns_an_available_room(hospital):
    assert len(sv.available_rooms(hospital["admin"])) == 74
    pid = sv.admit_patient(hospital["admin"], "  Asha   Rao ", 31, "Female", "R042", DAY1.date(), "+91 00000 00001", "note", now=DAY1)
    p = sv.get_patient(hospital["admin"], pid)
    assert pid == "P0001" and (p["name"], p["room_id"], p["status"]) == ("Asha Rao", "R042", "Admitted")
    assert "R042" not in sv.available_rooms(hospital["admin"])
    assert [x["patient_id"] for x in sv.patient_overview(hospital["nurse"], DAY1)] == [pid]  # on every dashboard
    assert [x["patient_id"] for x in sv.patient_overview(hospital["doctor"], DAY1)] == [pid]
    assert sv.admit_patient(hospital["admin"], "Second One", 50, "Male", "R043", DAY1.date(), now=DAY1) == "P0002"
    for bad in (dict(name=""), dict(age=150), dict(age=None), dict(gender="?"), dict(room_id="R999"), dict(room_id=None),
                dict(contact="abc"), dict(admission_date=DAY1.date() + timedelta(days=1))):
        args = {"name": "Valid Name", "age": 30, "gender": "Male", "room_id": "R050", "admission_date": DAY1.date(), **bad}
        with pytest.raises(sv.ValidationError):
            sv.admit_patient(hospital["admin"], now=DAY1, **args)
    assert sv.occupancy(hospital["admin"])["occupied"] == 2


def test_13_room_cannot_hold_two_active_patients(hospital):
    admit(hospital, "First Patient", "R005")
    with pytest.raises(sv.ValidationError):
        admit(hospital, "Second Patient", "R005")
    with pytest.raises(Exception):  # even raw SQL is stopped by the unique index
        with db.engine().begin() as conn:
            conn.execute(db.patients.insert().values(patient_id="RAW", name="Raw", age=1, gender="Other", room_id="R005",
                                                     admission_date="2026-03-02", created_at="2026-03-02 09:00:00"))
    assert sv.occupancy(hospital["admin"])["occupied"] == 1


def test_14_daily_statuses_roll_over_by_date(hospital):
    pid = admit(hospital)
    sv.record_temperature(hospital["nurse"], pid, 37.0, now=DAY1)
    sv.complete_visit(hospital["doctor"], pid, now=later(hours=1))
    late = datetime(2026, 3, 2, 23, 59, 0)
    assert overview(hospital, pid, late)["visit_status"] == "Visit Completed"
    after_midnight = datetime(2026, 3, 3, 0, 1, 0)  # nobody touched the app at midnight
    row = overview(hospital, pid, after_midnight)
    assert (row["temp_status"], row["visit_status"], row["today_temp"]) == ("Pending", "Not Ready", None)
    assert row["fever_free_days"] == 1  # yesterday is now a complete day
    assert len(sv.temperature_history(hospital["nurse"], pid)) == 1  # nothing deleted
    assert len(sv.visit_history(hospital["doctor"], pid)) == 1
    sv.record_temperature(hospital["nurse"], pid, 36.9, now=later(days=1))  # a new day accepts a new reading
    sv.complete_visit(hospital["doctor"], pid, now=later(days=1, hours=1))
    assert len(sv.visit_history(hospital["doctor"], pid)) == 2


def test_15_unauthorised_roles_are_refused(hospital):
    n, d, a = hospital["nurse"], hospital["doctor"], hospital["admin"]
    pid = admit(hospital)
    record_days(hospital, pid, [37.0, 37.0, 37.0])
    now = later(days=3)
    denied = [
        (sv.approve_discharge, (n, pid)), (sv.complete_discharge, (n, 1)), (sv.record_death, (n, pid, now)),
        (sv.admit_patient, (n, "X Y", 30, "Male", "R002", now.date())), (sv.add_treatment, (n, pid, "t", "n")),
        (sv.complete_visit, (n, pid)), (sv.treatment_records, (n,)), (sv.visit_history, (n,)),
        (sv.release_room, (n, pid)), (sv.reset_demo_data, (n,)), (sv.success_stats, (n,)),
        (sv.admit_patient, (d, "X Y", 30, "Male", "R002", now.date())), (sv.complete_discharge, (d, 1)),
        (sv.release_room, (d, pid)), (sv.record_temperature, (d, pid, 37.0)), (sv.reset_demo_data, (d,)),
        (sv.available_rooms, (d,)), (sv.notifications, (d,)),
        (sv.record_temperature, (a, pid, 37.0)), (sv.correct_temperature, (a, pid, 37.0)),
        (sv.add_treatment, (a, pid, "t", "n")), (sv.complete_visit, (a, pid)), (sv.approve_discharge, (a, pid)),
        (sv.record_death, (a, pid, now)), (sv.temperature_history, (a, pid)), (sv.patient_overview, (a,)),
        (sv.treatment_records, (a,)),
        (sv.approve_discharge, (None, pid)), (sv.record_temperature, ({"id": 1, "role": "superuser"}, pid, 37.0)),
    ]
    for fn, args in denied:
        with pytest.raises(auth.PermissionDenied):
            fn(*args)
    assert sv.get_patient(a, pid)["status"] == "Admitted" and sv.discharge_queue(a) == []
    assert auth.authenticate("nurse", "wrong") is None and auth.authenticate("nobody", "nurse123") is None
    with db.engine().connect() as conn:  # passwords are stored hashed, never in clear text
        hashes = [r["password_hash"] for r in db.rows(conn, "SELECT password_hash FROM users")]
    assert all(h.startswith("pbkdf2_sha256$") and "123" not in h.split("$")[0] for h in hashes)
    assert not any(h in ("nurse123", "doctor123", "admin123") for h in hashes)


def test_16_data_persists_after_restart(hospital):
    pid = admit(hospital, room="R033")
    sv.record_temperature(hospital["nurse"], pid, 37.4, now=DAY1)
    url = db.engine().url.render_as_string(hide_password=False)
    db.configure(url)  # dispose every connection and reopen, as an app restart does
    db.init_db()       # start-up initialisation must not wipe or duplicate anything
    nurse = auth.authenticate("nurse", "nurse123")
    row = next(p for p in sv.patient_overview(nurse, DAY1) if p["patient_id"] == pid)
    assert (row["room_id"], row["today_temp"]) == ("R033", 37.4)
    with db.engine().connect() as conn:
        assert db.scalar(conn, "SELECT COUNT(*) FROM rooms") == 74
        assert db.scalar(conn, "SELECT COUNT(*) FROM users") == 3
        assert db.scalar(conn, "SELECT COUNT(*) FROM patients") == 1


def test_17_works_with_an_empty_database(hospital):
    n, d, a = hospital["nurse"], hospital["doctor"], hospital["admin"]
    assert sv.patient_overview(n, DAY1) == [] and sv.patient_overview(d, DAY1) == []
    assert sv.active_patients(a) == [] and sv.discharge_queue(a) == [] and sv.notifications(a) == []
    assert sv.visit_history(d) == [] and sv.treatment_records(d) == [] and sv.finalised_outcomes(a) == []
    assert sv.occupancy(a) == {"total": 74, "occupied": 0, "available": 74, "consistent": True}
    assert sv.success_stats(a)["rate"] is None and sv.success_stats(a)["status"] == "N/A"
    assert len(sv.room_overview(a)) == 74 and not sv.has_demo_data()


def test_18_occupancy_always_matches_room_assignments(hospital):
    a = hospital["admin"]

    def check(expected):
        occ = sv.occupancy(a)
        rooms = sv.room_overview(a)
        assert occ["consistent"] and occ["total"] == 74 == len(rooms)
        assert occ["occupied"] == expected == sum(1 for r in rooms if r["patient_id"]) == sum(1 for r in rooms if r["status"] == "Occupied")
        assert occ["available"] == 74 - expected == len(sv.available_rooms(a))

    check(0)
    pids = [admit(hospital, f"Patient {chr(65 + i)}", f"R{i + 1:03d}") for i in range(5)]
    check(5)
    for pid in pids[:2]:
        record_days(hospital, pid, [37.0, 37.0, 37.0])
    aid = sv.approve_discharge(hospital["doctor"], pids[0], now=later(days=3))
    check(5)  # approval does not free the room
    sv.complete_discharge(a, aid, now=later(days=3))
    check(4)
    sv.record_death(hospital["doctor"], pids[2], later(days=3), now=later(days=3))
    check(4)  # death keeps the room until closure
    sv.release_room(a, pids[2], now=later(days=3))
    check(3)
    admit(hospital, "Reuses Room", "R001", now=later(days=3))  # a freed room can be assigned again
    check(4)
    sv.reset_demo_data(a, now=later(days=3))
    check(15)


def test_demo_data_covers_every_workflow_state(hospital):
    sv.reset_demo_data(hospital["admin"], now=DAY1)
    rows = sv.patient_overview(hospital["doctor"], DAY1)
    assert 15 <= len(rows) + len(sv.finalised_outcomes(hospital["admin"])) <= 20
    streaks = {r["fever_free_days"] for r in rows}
    assert {0, 1, 2, 3} <= streaks and any(s > 3 for s in streaks)
    assert any(r["temp_status"] == "Pending" for r in rows) and any(r["eligible"] for r in rows)
    assert any(r["visit_status"] == "Ready for Visit" for r in rows)
    assert any(r["today_temp"] and r["today_temp"] >= 38 for r in rows)
    assert len(sv.discharge_queue(hospital["admin"])) >= 1 and sv.unread_notifications(hospital["admin"]) >= 1
    assert sv.success_stats(hospital["admin"])["rate"] == 80.0
    assert any(sv.correction_trail(hospital["nurse"], r["patient_id"]) for r in rows)
    with db.engine().connect() as conn:
        assert db.scalar(conn, "SELECT COUNT(*) FROM patients WHERE is_demo = 0") == 0


def test_streak_rules_pure():
    t = date(2026, 3, 10)
    d = lambda n: t - timedelta(days=n)  # noqa: E731
    assert logic.fever_free_streak({}, t) == 0
    assert logic.fever_free_streak({t: 36.8}, t) == 0
    assert logic.fever_free_streak({d(1): 37, d(2): 37, d(3): 37, d(4): 39}, t) == 3
    assert logic.fever_free_streak({d(1): 37.9, d(2): 38.0}, t) == 1
    assert logic.fever_free_streak({d(2): 37, d(3): 37, d(4): 37}, t) == 0
    assert logic.is_discharge_eligible(3, "Admitted") and not logic.is_discharge_eligible(2, "Admitted")
    assert not logic.is_discharge_eligible(5, "Discharge Approved")
