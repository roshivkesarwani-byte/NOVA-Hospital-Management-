"""NOVA - Hospital Management System (Streamlit entry point).

Run with:  streamlit run app.py"""
from __future__ import annotations

import streamlit as st

import auth
import config
import database as db
import logic
import services
import ui
import views_admin
import views_doctor
import views_nurse
from views_common import DETAIL_KEYS

st.set_page_config(page_title="NOVA - Hospital Management System", page_icon=":material/local_hospital:",
                   layout="wide", initial_sidebar_state="auto")

# role -> ordered list of (page name, material icon, description, render function)
NAV = {
    "nurse": [
        ("Dashboard", "dashboard", "Today's temperature round at a glance.", views_nurse.dashboard),
        ("Patient List", "groups", "All admitted patients and occupied rooms.", views_nurse.patient_list),
        ("Record Temperature", "thermostat", "Record or correct today's reading.", views_nurse.record_temperature),
        ("Temperature History", "show_chart", "Previous readings and corrections.", views_nurse.temperature_history),
    ],
    "doctor": [
        ("Dashboard", "dashboard", "Clinical overview for today.", views_doctor.dashboard),
        ("Patient Monitoring", "monitor_heart", "Readiness, fever tracking and patient detail.", views_doctor.monitoring),
        ("Discharge Eligible", "task_alt", "Patients who have completed the fever-free period.", views_doctor.discharge_eligible),
        ("Visit History", "event_available", "Completed doctor visits.", views_doctor.visit_history),
        ("Treatment Records", "medication", "Treatments and clinical notes.", views_doctor.treatment_records),
    ],
    "admin": [
        ("Dashboard", "dashboard", "Hospital operations overview.", views_admin.dashboard),
        ("Room Management", "meeting_room", "Occupancy of all 74 rooms.", views_admin.room_management),
        ("Admit Patient", "person_add", "Register a new patient and assign a room.", views_admin.admit_patient),
        ("Discharge Queue", "logout", "Complete doctor-approved discharges.", views_admin.discharge_queue),
        ("Notifications", "notifications", "Automatic alerts from the clinical team.", views_admin.notifications),
        ("Hospital Performance", "insights", "Success rate against the 85% benchmark.", views_admin.performance),
    ],
}


@st.cache_resource(show_spinner="Preparing NOVA...")
def _initialise() -> bool:
    db.init_db()
    return True


def _login_page() -> None:
    ui.inject_css(hide_sidebar=True)
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown(f'<div class="nv-login-brand"><div class="nv-mark">{ui.icon("heart", 28)}</div><h1>{config.APP_NAME}</h1>'
                    f'<p>{config.APP_SUBTITLE}</p><p style="font-size:.8rem">{config.APP_TAGLINE}</p></div>',
                    unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username", max_chars=50, autocomplete="username")
            password = st.text_input("Password", type="password", max_chars=100, autocomplete="current-password")
            submitted = st.form_submit_button("Log in", type="primary", width="stretch")
        if submitted:
            if not username.strip() or not password:
                st.error("Enter both your username and password.")
            else:
                user = auth.authenticate(username, password)
                if user:
                    st.session_state.clear()
                    st.session_state["user"] = user
                    st.session_state["page"] = "Dashboard"
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
        st.markdown('<div class="nv-foot">Demonstration prototype with fictional data. Not for real patient care.</div>',
                    unsafe_allow_html=True)


def _navigate(page: str) -> None:
    for key in DETAIL_KEYS:
        st.session_state.pop(key, None)
    st.session_state["page"] = page


def _logout() -> None:
    st.session_state.clear()


def _sidebar(user: dict, pages: list, current: str, today) -> None:
    unread = services.unread_notifications(user)
    with st.sidebar:
        st.markdown(f'<div class="nv-brand"><div class="nv-logo"><span class="nv-mark">{ui.icon("heart", 20)}</span>'
                    f'{config.APP_NAME}</div><div class="nv-sub">{config.APP_TAGLINE}</div></div>'
                    '<div class="nv-navlabel">Menu</div>', unsafe_allow_html=True)
        for name, material, _desc, _fn in pages:
            label = name
            if name == "Notifications" and unread:
                label = f"{name} :orange-badge[{unread} new]"
            st.button(label, key=f"nav_{name}", icon=f":material/{material}:", width="stretch",
                      type="primary" if name == current else "secondary", on_click=_navigate, args=(name,))
        st.markdown(f'<div class="nv-userbox">Signed in as<b>{ui.esc(user["full_name"])}</b>'
                    f'<span class="nv-role">{ui.esc(auth.ROLE_LABELS[user["role"]])}</span><br>'
                    f'Hospital date<br><b style="font-weight:500">{today.strftime("%A, %d %B %Y")}</b></div>',
                    unsafe_allow_html=True)
        st.button("Log out", key="nav_logout", icon=":material/logout:", width="stretch", on_click=_logout)


def main() -> None:
    _initialise()
    session_user = st.session_state.get("user")
    # Re-validate the session against the database on every run.
    user = auth.current_user(session_user["id"]) if session_user else None
    if not user:
        st.session_state.pop("user", None)
        _login_page()
        return
    st.session_state["user"] = user

    ui.inject_css()
    now = logic.hospital_now()
    pages = NAV[user["role"]]  # only this role's screens exist for this session
    names = [p[0] for p in pages]
    if st.session_state.get("page") not in names:
        st.session_state["page"] = "Dashboard"
    current = st.session_state["page"]
    _sidebar(user, pages, current, now.date())

    name, _icon, description, render = pages[names.index(current)]
    ui.page_header(name, description, user, now.date())
    if services.has_demo_data():
        ui.demo_banner()
    ui.show_flash()
    try:
        render(user, now)
    except auth.PermissionDenied as exc:
        st.error(str(exc))


main()
