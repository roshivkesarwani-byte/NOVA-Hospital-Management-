"""Nurse screens: dashboard, patient list, record temperature, history."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

import config
import services
import ui
from views_common import attempt, goto, pick_patient


def _temp_kpis(data: list[dict]) -> None:
    pending = sum(1 for p in data if p["temp_status"] == "Pending")
    ui.kpis([
        {"label": "Total occupied patients", "value": len(data), "icon": "bed", "sub": "Currently admitted"},
        {"label": "Temperatures pending", "value": pending, "icon": "clock", "tone": "warning" if pending else "",
         "sub": "Not yet recorded today"},
        {"label": "Temperatures completed today", "value": len(data) - pending, "icon": "check", "tone": "success",
         "sub": "Recorded today"},
    ])


def dashboard(user: dict, now: datetime) -> None:
    data = services.patient_overview(user, now)
    _temp_kpis(data)
    ui.section("Patients", "Record or correct today's temperature")
    if not data:
        ui.empty("No admitted patients", "Patients appear here as soon as admin admits them.", "bed")
        return
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("Search", placeholder="Search by patient name or ID", label_visibility="collapsed").strip().lower()
    room = c2.selectbox("Room", ["All rooms"] + [p["room_id"] for p in data], label_visibility="collapsed")
    status = c3.selectbox("Temperature status", ["All statuses", "Pending", "Recorded Today"], label_visibility="collapsed")
    rows = []
    for p in data:
        if query and query not in p["name"].lower() and query not in p["patient_id"].lower():
            continue
        if room != "All rooms" and p["room_id"] != room:
            continue
        if status != "All statuses" and p["temp_status"] != status:
            continue
        pending = p["temp_status"] == "Pending"
        rows.append({"id": p["patient_id"], "action": "Record" if pending else "Correct", "primary": pending,
                     "cells": [f'<span class="nv-mono">{ui.esc(p["patient_id"])}</span>', ui.esc(p["name"]),
                               ui.esc(p["room_id"]), ui.esc(p["age"]), ui.status_badge(p["temp_status"]),
                               ui.temp_badge(p["today_temp"])]})
    clicked = ui.action_table("nurse_dash", ["Patient ID", "Patient Name", "Room Number", "Age", "Temperature Status",
                                             "Today's Temperature", "Action"], [1, 2, 1, .7, 1.4, 1.9, 1.1], rows,
                              "No patients match these filters", "Clear the search or change the filters.")
    if clicked:
        goto("Record Temperature", temp_patient=clicked)


def patient_list(user: dict, now: datetime) -> None:
    data = services.patient_overview(user, now)
    occ = services.occupancy(user)
    ui.kpis([
        {"label": "Occupied rooms", "value": f'{occ["occupied"]} / {occ["total"]}', "icon": "door"},
        {"label": "Admitted patients", "value": len(data), "icon": "users"},
    ])
    ui.section("All admitted patients")
    rows = [{"id": p["patient_id"], "action": "History",
             "cells": [f'<span class="nv-mono">{ui.esc(p["patient_id"])}</span>', ui.esc(p["name"]), ui.esc(p["room_id"]),
                       f'{ui.esc(p["age"])} · {ui.esc(p["gender"])}', ui.fmt_date(p["admission_date"]),
                       ui.status_badge(p["temp_status"])]} for p in data]
    clicked = ui.action_table("nurse_list", ["Patient ID", "Patient Name", "Room Number", "Age / Gender",
                                             "Admission Date", "Temperature Today", "Readings"],
                              [1, 2, 1, 1.3, 1.3, 1.4, 1], rows, "No admitted patients",
                              "Patients appear here as soon as admin admits them.")
    if clicked:
        goto("Temperature History", hist_patient=clicked)


def record_temperature(user: dict, now: datetime) -> None:
    data = services.patient_overview(user, now)
    if not data:
        ui.empty("No admitted patients", "There is nobody to record a temperature for yet.", "thermo")
        return
    p = pick_patient(data, "temp_patient")
    if not p:
        ui.empty("Select a patient", "Choose a patient above to record today's temperature.", "thermo")
        return
    pid = p["patient_id"]
    existing = p["today_temp"] is not None
    editing = existing and st.session_state.get("temp_editing") == pid

    if existing and not editing:
        ui.info_card("Recorded today", [("Temperature", ui.temp_badge(p["today_temp"])),
                                        ("Recorded at", ui.fmt_time(p["today_recorded_at"])),
                                        ("Status", ui.status_badge("Recorded Today"))])
        st.write("")
        st.caption("One reading is kept per patient per day. A reading can be corrected on the same calendar day; "
                   "the original value stays in the audit trail.")
        c1, c2, _ = st.columns([1.4, 1.4, 4])
        if c1.button("Correct today's reading", type="primary", width="stretch"):
            st.session_state["temp_editing"] = pid
            st.rerun()
        if c2.button("Back to dashboard", width="stretch"):
            goto("Dashboard")
        return

    default_time = st.session_state.setdefault(f"temp_default_time_{pid}", now.time().replace(second=0))
    with st.form(f"temp_form_{pid}_{'edit' if editing else 'new'}"):
        st.markdown(f"**{'Correct today' + chr(39) + 's reading' if editing else 'Record temperature'}**")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Patient name", value=p["name"], disabled=True)
        c2.text_input("Patient ID", value=pid, disabled=True)
        c3.text_input("Room number", value=p["room_id"], disabled=True)
        d1, d2, d3 = st.columns(3)
        temp = d1.number_input("Temperature (°C)", value=None, step=0.1, format="%.1f",
                               placeholder=f"{config.TEMP_MIN_C:.0f} - {config.TEMP_MAX_C:.0f}")
        d2.date_input("Date", value=now.date(), disabled=True, format="DD/MM/YYYY",
                      help="Readings are always recorded for the current hospital day.")
        at_time = d3.time_input("Time", value=default_time, step=60)
        reason = None
        if editing:
            st.caption(f"Currently recorded: {ui.fmt_temp(p['today_temp'])} at {ui.fmt_time(p['today_recorded_at'])}.")
            reason = st.text_input("Reason for correction (optional)", max_chars=200)
        b1, b2, _ = st.columns([1.3, 1, 4])
        save = b1.form_submit_button("Save Correction" if editing else "Save Temperature", type="primary", width="stretch")
        cancel = b2.form_submit_button("Cancel", width="stretch")
    if cancel:
        st.session_state.pop(f"temp_default_time_{pid}", None)
        goto("Dashboard")
    if save:
        if temp is None:
            st.error("Enter the temperature in °C.")
            return
        recorded_at = datetime.combine(now.date(), at_time)
        if editing:
            ok, _ = attempt(services.correct_temperature, user, pid, temp, reason, recorded_at)
        else:
            ok, _ = attempt(services.record_temperature, user, pid, temp, recorded_at)
        if ok:
            st.session_state.pop(f"temp_default_time_{pid}", None)
            ui.flash("success", f"Temperature {'corrected' if editing else 'saved'} for {p['name']}: {temp:.1f} °C.")
            goto("Dashboard")


def temperature_history(user: dict, now: datetime) -> None:
    data = services.patient_overview(user, now)
    if not data:
        ui.empty("No admitted patients", "Temperature history appears once patients are admitted.", "chart")
        return
    p = pick_patient(data, "hist_patient")
    if not p:
        ui.empty("Select a patient", "Choose a patient above to see previous temperature readings.", "chart")
        return
    readings = services.temperature_history(user, p["patient_id"])
    ui.info_card(p["name"], [("Patient ID", ui.esc(p["patient_id"])), ("Room", ui.esc(p["room_id"])),
                             ("Admission date", ui.fmt_date(p["admission_date"])),
                             ("Today", ui.status_badge(p["temp_status"]))])
    ui.section("Readings", f"Fever threshold {config.FEVER_THRESHOLD_C:.1f} °C (demonstration assumption)")
    if not readings:
        ui.empty("No readings yet", "Readings appear here once they are recorded.", "thermo")
        return
    st.plotly_chart(ui.temperature_chart(readings), width="stretch", config=ui.PLOTLY_CONFIG)
    ui.html_table(["Date", "Time", "Temperature", "Recorded by"],
                  [[ui.fmt_date(r["reading_date"]), ui.fmt_time(r["recorded_at"]), ui.temp_badge(r["temperature_c"]),
                    ui.esc(r["recorded_by_name"])] for r in reversed(readings)])
    trail = services.correction_trail(user, p["patient_id"])
    ui.section("Correction audit trail", "Original values are never overwritten")
    ui.html_table(["Date", "Original value", "Corrected value", "Corrected by", "Corrected at", "Reason"],
                  [[ui.fmt_date(t["reading_date"]), ui.fmt_temp(t["original_c"]), ui.fmt_temp(t["corrected_c"]),
                    ui.esc(t["corrected_by"]), ui.fmt_dt(t["corrected_at"]), ui.esc(t["correction_reason"] or "-")]
                   for t in trail], "No corrections", "No reading for this patient has been corrected.")
