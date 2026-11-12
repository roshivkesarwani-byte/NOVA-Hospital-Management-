"""Central configuration for NOVA. Every value can be overridden with an
environment variable (or a root-level Streamlit secret, which Streamlit
exposes as an environment variable)."""
from __future__ import annotations

import os

APP_NAME = "NOVA"
APP_SUBTITLE = "Hospital Management System"
APP_TAGLINE = "Smarter Care. Better Coordination."

# Hospital calendar days are computed in this timezone.
HOSPITAL_TIMEZONE = os.getenv("NOVA_TIMEZONE", "Asia/Kolkata")

# DEMONSTRATION ASSUMPTION - requires clinical approval before any real use.
FEVER_THRESHOLD_C = float(os.getenv("NOVA_FEVER_THRESHOLD_C", "38.0"))
REQUIRED_FEVER_FREE_DAYS = int(os.getenv("NOVA_REQUIRED_FEVER_FREE_DAYS", "3"))

# Readings outside this range are rejected as impossible / mistyped.
TEMP_MIN_C = 30.0
TEMP_MAX_C = 45.0

TOTAL_ROOMS = 74
SUCCESS_BENCHMARK_PCT = 85.0

# Local SQLite file used when no DATABASE_URL is configured.
SQLITE_PATH = os.getenv("NOVA_SQLITE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "nova.db"))

# Demo accounts, created on first start only. To change a password later use
#   python manage.py set-password <username>
# or set these variables before the first start.
DEMO_USERS = [
    {"username": "nurse", "password": os.getenv("NOVA_NURSE_PASSWORD", "nurse123"),
     "role": "nurse", "full_name": "Meera Pillai"},
    {"username": "doctor", "password": os.getenv("NOVA_DOCTOR_PASSWORD", "doctor123"),
     "role": "doctor", "full_name": "Dr. Arjun Rao"},
    {"username": "admin", "password": os.getenv("NOVA_ADMIN_PASSWORD", "admin123"),
     "role": "admin", "full_name": "Kavita Shah"},
]

# Set NOVA_SEED_DEMO=0 to start with an empty hospital instead of demo data.
SEED_DEMO_ON_FIRST_RUN = os.getenv("NOVA_SEED_DEMO", "1") != "0"
