"""Authentication (hashed passwords) and role-based permissions."""
from __future__ import annotations

import hashlib
import hmac
import secrets

import database as db
import logic

_ITERATIONS = 240_000

# The single source of truth for what each role may do. Every write and every
# sensitive read in services.py checks this map - the UI is never trusted.
PERMISSIONS: dict[str, frozenset[str]] = {
    "nurse": frozenset({
        "view_patients", "view_rooms", "view_temperatures",
        "record_temperature", "correct_temperature",
    }),
    "doctor": frozenset({
        "view_patients", "view_temperatures", "view_clinical", "complete_visit",
        "record_treatment", "approve_discharge", "record_death", "view_performance",
    }),
    "admin": frozenset({
        "view_patients", "view_rooms", "admit_patient", "view_discharge_queue",
        "complete_discharge", "release_room", "view_notifications",
        "view_performance", "reset_demo_data",
    }),
}

ROLE_LABELS = {"nurse": "Nurse", "doctor": "Doctor", "admin": "Admin Staff"}


class PermissionDenied(Exception):
    """Raised when a user attempts an action their role does not allow."""


def can(user: dict | None, permission: str) -> bool:
    return bool(user) and permission in PERMISSIONS.get(user.get("role", ""), frozenset())


def require(user: dict | None, permission: str) -> None:
    if not can(user, permission):
        role = ROLE_LABELS.get((user or {}).get("role", ""), "This account")
        raise PermissionDenied(f"{role} is not permitted to perform this action ({permission}).")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def _public(row: dict) -> dict:
    return {"id": row["id"], "username": row["username"], "role": row["role"], "full_name": row["full_name"]}


def authenticate(username: str, password: str) -> dict | None:
    """Return the user (without the hash) when credentials are valid."""
    username = (username or "").strip().lower()
    if not username or not password:
        return None
    with db.engine().begin() as conn:
        row = db.one(conn, "SELECT * FROM users WHERE username = :u AND is_active = 1", u=username)
        ok = bool(row) and verify_password(password, row["password_hash"])
        if ok:
            db.log_audit(conn, _public(row), "auth.login", "user", row["id"])
            return _public(row)
        db.log_audit(conn, None, "auth.login_failed", "user", None, {"username": username[:50]})
    return None


def current_user(user_id: int) -> dict | None:
    """Re-read the user from the database (role changes take effect at once)."""
    with db.engine().connect() as conn:
        row = db.one(conn, "SELECT * FROM users WHERE id = :i AND is_active = 1", i=user_id)
    return _public(row) if row else None


def set_password(username: str, new_password: str) -> bool:
    if len(new_password) < 6:
        raise ValueError("Password must be at least 6 characters long.")
    with db.engine().begin() as conn:
        res = conn.execute(db.users.update().where(db.users.c.username == username)
                           .values(password_hash=hash_password(new_password)))
        if res.rowcount:
            db.log_audit(conn, None, "auth.password_changed", "user", username, at=logic.ts(logic.hospital_now()))
        return bool(res.rowcount)
