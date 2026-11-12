"""Helpers shared by the role views."""
from __future__ import annotations

import streamlit as st

import auth
import services
import ui

DETAIL_KEYS = ("doc_patient", "temp_patient", "hist_patient", "temp_editing")


def goto(page: str, **state) -> None:
    """Navigate to another screen of the current role and rerun."""
    for key in DETAIL_KEYS:
        st.session_state.pop(key, None)
    st.session_state["page"] = page
    st.session_state.update(state)
    st.rerun()


def attempt(fn, *args, **kwargs):
    """Run a service call; show validation / permission problems to the user.
    Returns (ok, result)."""
    try:
        return True, fn(*args, **kwargs)
    except (services.ValidationError, auth.PermissionDenied) as exc:
        st.error(str(exc))
        return False, None


def patient_label(p: dict) -> str:
    return f"{p['patient_id']}  ·  {p['name']}  ·  Room {p['room_id']}"


def pick_patient(patients: list[dict], state_key: str, label: str = "Patient") -> dict | None:
    """Select box of patients that remembers / honours a pre-selected patient."""
    ids = [p["patient_id"] for p in patients]
    by_id = {p["patient_id"]: p for p in patients}
    current = st.session_state.get(state_key)
    index = ids.index(current) if current in ids else None
    chosen = st.selectbox(label, ids, index=index, format_func=lambda i: patient_label(by_id[i]),
                          placeholder="Select a patient", key=f"pick_{state_key}_{current}")
    if chosen != current:
        st.session_state[state_key] = chosen
        st.session_state.pop("temp_editing", None)
        if chosen is not None:
            st.rerun()
    return by_id.get(chosen)
