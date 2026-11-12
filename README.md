# NOVA — Hospital Management System

*Smarter Care. Better Coordination.*

A working Streamlit prototype of the nurse → doctor → admin workflow: daily temperature
recording, fever-free tracking, doctor visits, discharge approval, admission, room
management and hospital success rate.

> **Demonstration prototype.** All patient data is fictional. NOVA is not a certified
> clinical system and must not be used for real patient care. The 38.0 °C fever
> threshold is a demonstration assumption that requires clinical approval.

## Test logins

| Role  | Username | Password    |
|-------|----------|-------------|
| Nurse | `nurse`  | `nurse123`  |
| Doctor| `doctor` | `doctor123` |
| Admin | `admin`  | `admin123`  |

Passwords are stored as salted PBKDF2-SHA256 hashes. To change one:
`python manage.py set-password nurse`. To choose different passwords before the first
start, set `NOVA_NURSE_PASSWORD`, `NOVA_DOCTOR_PASSWORD`, `NOVA_ADMIN_PASSWORD`.

## Run locally

```bash
cd nova_hospital
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Requires Python 3.10+. The first start creates `nova.db` (SQLite) next to the code with
the 74 rooms, the three accounts and the demo patients. Data survives restarts. Delete
`nova.db` to start again from scratch, or set `NOVA_SEED_DEMO=0` to start with an empty
hospital.

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repository (`.gitignore` already excludes `nova.db` and
   `secrets.toml`).
2. On <https://share.streamlit.io> choose **Create app**, pick the repository and set the
   main file to `app.py`.
3. Under **Advanced settings → Secrets**, add `DATABASE_URL` (next section), then deploy.

Without `DATABASE_URL` the cloud app still runs on SQLite, but Community Cloud's disk is
temporary: data is lost whenever the app restarts. Use a database for anything you want
to keep.

## Persistent online storage (Supabase / PostgreSQL)

1. Create a project at <https://supabase.com>.
2. Open **Connect** and copy the **Session pooler** connection string (the direct
   connection is IPv6-only and may not be reachable from Community Cloud).
3. Add it as a secret — never in the code:

   ```toml
   DATABASE_URL = "postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
   ```

   Locally, put the same line in `.streamlit/secrets.toml` (see
   `secrets.toml.example`) or export `DATABASE_URL` as an environment variable.

NOVA creates its tables, rooms, accounts and demo data on first start. Any PostgreSQL
database works the same way.

## Architecture

```
app.py            entry point: login, role-based navigation, routing
auth.py           password hashing, login, the role → permission map
services.py       every database operation; checks permissions, runs in a transaction, writes the audit log
logic.py          pure rules: fever classification, fever-free streak, eligibility, success rate
database.py       SQLAlchemy engine + schema (SQLite or PostgreSQL), initialisation
seed.py           fictional demonstration data
ui.py             design system: CSS, KPI cards, tables, badges, charts
views_nurse.py / views_doctor.py / views_admin.py   the screens for each role
config.py         timezone, fever threshold, room count, benchmark, demo accounts
manage.py         command-line helper (init, set-password)
tests/            the 18 acceptance scenarios + headless screen tests
```

`config.py`, `services.py`, `seed.py`, the three `views_*.py` files and `manage.py` are
additions to the suggested structure, made to keep each file small and single-purpose.

**Tables:** `users`, `patients`, `rooms`, `temperature_readings`, `doctor_visits`,
`treatments`, `discharge_approvals`, `notifications`, `audit_logs` (plus a one-row
`app_meta` settings table).

**Rules enforced by the database itself**

- One patient per room — unique index on `room_id` for patients still occupying a room.
- One current reading per patient per day — unique index; a correction marks the old
  row `is_current = 0` and inserts a new row that points back to it.
- One doctor visit per patient per day; one open discharge approval per patient.
- A deceased patient cannot be marked cured; a discharged patient must be cured.
- Discharge completion is recorded on the doctor's approval row, so a completed
  discharge cannot exist without an approval.

**Access control.** Each role only gets its own screens, and there are no URL
parameters to manipulate. Independently of the UI, every function in `services.py`
checks the permission map in `auth.py` and raises `PermissionDenied` otherwise.

**Daily reset.** "Temperature recorded today", "visit completed today", the fever-free
streak and eligibility are never stored. They are derived from dated records each time
a page loads, so they are correct after midnight without any scheduled job.

## Assumptions

Where the specification left room for interpretation, this is what was implemented:

1. **One reading per patient per day.** The reading date is always the current hospital
   day (the time is editable, not in the future). This prevents back-dating a fever-free
   streak. Corrections are allowed on the same calendar day only.
2. **Fever-free days** are complete calendar days ending yesterday, each with a reading
   below the threshold. Today never counts; a fever recorded today resets the count to 0
   immediately; a day with no reading breaks the streak. Exactly 38.0 °C counts as fever.
3. **Discharge Approved patients stay on active lists** (and still get temperatures and
   visits) until admin completes the discharge.
4. **Death.** The room stays occupied until admin presses **Release Room** in the
   Discharge Queue ("administrative closure"). Admin is notified automatically. The
   death counts towards the success rate as soon as it is recorded. Recording a death
   cancels any open discharge approval.
5. **"Ready for visit"** on the doctor dashboard counts every patient whose temperature
   is recorded today, including those already visited (shown as "n visited today").
6. **Valid temperature range** is 30.0–45.0 °C; anything else is rejected.
7. **Hospital timezone** is `Asia/Kolkata` (`NOVA_TIMEZONE` to change). Timestamps are
   stored in hospital local time.
8. **Demo data is dated relative to the day it is loaded.** After a day or more without
   readings the sample streaks correctly fall to 0; use **Reset Demo Data** (Admin →
   Dashboard) before a demonstration.
9. **Admin sees no clinical data** (temperatures, treatments, visit notes); the nurse
   sees temperatures but not treatment records.
10. Login credentials are not shown on the login page; they are listed in this README.

## Workflows

**Nurse.** The dashboard shows occupied patients, temperatures pending and completed
today, and a searchable/filterable patient table. **Record** opens the recording form
(patient fields read-only); saving turns the patient from *Pending* to *Recorded Today*
at once. **Correct** edits today's reading; the original stays in the correction audit
trail on the Temperature History screen.

**Doctor.** The dashboard shows admitted / ready / not ready / discharge-eligible counts
and the hospital success rate. Patient Monitoring lists every patient with latest
temperature, fever-free days, visit status and eligibility; **View Details** opens the
patient with a temperature chart (fever points in red), readings, visit and treatment
history. From there the doctor records treatment and notes, marks today's visit
completed (blocked while the temperature is pending), approves discharge for eligible
patients, or records a death (confirmation required).

**Admin.** The dashboard shows capacity (74), occupied, available, pending discharges
and success rate, with an occupancy chart. Admit Patient registers a patient into an
available room and generates the patient ID. An approved discharge appears in the
Discharge Queue and raises a notification badge immediately; **Complete Discharge**
marks the patient Discharged / Cured and frees the room. Hospital Performance compares
the success rate with the 85% benchmark.

## Testing

```bash
pip install pytest
python -m pytest tests -q
```

To run the scenario suite against PostgreSQL instead of a temporary SQLite file
(the target database's `public` tables are dropped and recreated):

```bash
NOVA_TEST_DATABASE_URL="postgresql://user:pass@host:5432/dbname" python -m pytest tests/test_scenarios.py -q
```

| #  | Scenario | Automated test |
|----|----------|----------------|
| 1  | Recording changes Pending → Recorded Today; duplicates and impossible values refused | `test_01` |
| 2  | Same-day correction shown; original kept in audit trail; next-day correction refused | `test_02` |
| 3  | Visit cannot be completed while temperature is pending | `test_03` |
| 4  | Recorded temperature → Ready for Visit → Visit Completed | `test_04` |
| 5  | Two full fever-free days: not eligible, approval refused | `test_05` |
| 6  | Three full fever-free days: eligible (days counted, not readings) | `test_06` |
| 7  | Fever, missing day, or fever today breaks the streak | `test_07` |
| 8  | Approval appears in admin queue with notification; room not freed | `test_08` |
| 9  | Completion frees the room; history preserved; cannot complete twice or unapproved | `test_09` |
| 10 | Death: off active lists, counted as deceased, room held until released | `test_10` |
| 11 | Success rate from finalised outcomes only; N/A when none | `test_11` |
| 12 | Admission validates input, generates ID, assigns the room | `test_12` |
| 13 | A room cannot hold two patients (service check and database index) | `test_13` |
| 14 | Statuses roll over after midnight with nothing deleted | `test_14` |
| 15 | 29 cross-role operations refused; passwords hashed | `test_15` |
| 16 | Data persists after the engine is closed and reopened | `test_16` |
| 17 | Every query works on an empty database | `test_17` |
| 18 | Occupancy equals actual assignments through admit / discharge / death / reset | `test_18` |

`tests/test_app_smoke.py` additionally starts the real app headlessly, logs in as each
role, opens every screen with demo data and with an empty database, and checks that a
role cannot reach another role's screen.

### Manual checklist for a demonstration

1. Admin → Dashboard → **Reset Demo Data**.
2. Nurse: record a temperature for a *Pending* patient; correct it; open Temperature History.
3. Doctor: open a *Not Ready* patient (visit button disabled); open an eligible patient,
   complete the visit, **Approve Discharge**.
4. Admin: badge on Notifications; Discharge Queue → **Complete Discharge**; check Room
   Management and Hospital Performance.
5. Doctor: **Record Death** on a patient; Admin: **Release Room**.
6. Admin: admit a new patient into the freed room; confirm the nurse sees them.
7. Stop and restart the app; confirm everything is still there.
