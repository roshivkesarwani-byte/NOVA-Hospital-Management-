"""Doctor screens: dashboard, monitoring + patient detail, discharge
eligibility, visit history and treatment records."""
from __future__ import annotations

from datetime import date, datetime

import streamlit as st

import config
import services
import ui
from views_common import attempt, goto

REQ = config.REQUIRED_FEVER_FREE_DAYS


def _eligibility_cell(p: dict) -> str:
    if p["status"] == "Discharge Approved":
        return ui.badge("Approved", "warning")
    if p["eligible"]:
        return ui.badge("Eligible", "success")
    return f'<span class="nv-sub2">Not eligible</span>'


def _streak_cell(p: dict) -> str:
    return f'<span class="nv-mono">{p["fever_free_days"]}</span> <span class="nv-sub2">/ {REQ} days</span>'


def _performance_card(user: dict) -> None:
    s = services.success_stats(user)
    rate = "N/A" if s["rate"] is None else f'{s["rate"]:.1f}%'
    tone = "neutral" if s["rate"] is None else "success" if s["rate"] >= s["benchmark"] else "warning"
    ui.info_card("Hospital success rate (head doctor review)", [
        ("Success rate", f'<span style="font-size:1.4rem">{rate}</span>'), ("Benchmark", f'{s["benchmark"]:.0f}%'),
        ("Cured", str(s["cured"])), ("Deceased", str(s["deceased"])), ("Status", ui.badge(s["status"], tone))])


def dashboard(user: dict, now: datetime) -> None:
    data = services.patient_overview(user, now)
    ready = [p for p in data if p["ready_for_visit"]]
    eligible = [p for p in data if p["eligible"]]
    ui.kpis([
        {"label": "Total admitted patients", "value": len(data), "icon": "users"},
        {"label": "Ready for visit", "value": len(ready), "icon": "steth", "tone": "success",
         "sub": f'{sum(1 for p in ready if p["visited_today"])} visited today'},
        {"label": "Not ready", "value": len(data) - len(ready), "icon": "clock",
         "tone": "warning" if len(data) > len(ready) else "", "sub": "Temperature pending"},
        {"label": "Discharge eligible", "value": len(eligible), "icon": "check", "sub": f"{REQ}+ fever-free days"},
    ])
    st.write("")
    _performance_card(user)
    ui.section("Awaiting today's visit", "Temperature recorded, visit not yet completed")
    waiting = [p for p in ready if not p["visited_today"]]
    rows = [{"id": p["patient_id"], "action": "View Details",
             "cells": [f'<span class="nv-mono">{ui.esc(p["patient_id"])}</span>', ui.esc(p["name"]), ui.esc(p["room_id"]),
                       ui.temp_badge(p["today_temp"]), _streak_cell(p), _eligibility_cell(p)]} for p in waiting]
    clicked = ui.action_table("doc_dash", ["Patient ID", "Patient Name", "Room", "Today's Temperature", "Fever-free",
                                           "Discharge", "Action"], [1, 2, .8, 1.9, 1.2, 1.2, 1.2], rows,
                              "No visits waiting", "Every patient with a recorded temperature has been visited today.", "steth")
    if clicked:
        goto("Patient Monitoring", doc_patient=clicked)


def monitoring(user: dict, now: datetime) -> None:
    if st.session_state.get("doc_patient"):
        _detail(user, now, st.session_state["doc_patient"])
        return
    data = services.patient_overview(user, now)
    if not data:
        ui.empty("No admitted patients", "Patients appear here as soon as admin admits them.", "bed")
        return
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("Search", placeholder="Search by patient name or ID", label_visibility="collapsed").strip().lower()
    visit = c2.selectbox("Visit status", ["All visit statuses", "Ready for Visit", "Not Ready", "Visit Completed"],
                         label_visibility="collapsed")
    elig = c3.selectbox("Eligibility", ["All patients", "Discharge eligible", "Fever today"], label_visibility="collapsed")
    rows = []
    for p in data:
        if query and query not in p["name"].lower() and query not in p["patient_id"].lower():
            continue
        if visit != "All visit statuses" and p["visit_status"] != visit:
            continue
        if elig == "Discharge eligible" and not p["eligible"]:
            continue
        if elig == "Fever today" and not (p["today_temp"] is not None and p["today_temp"] >= config.FEVER_THRESHOLD_C):
            continue
        latest = ui.temp_badge(p["latest_temp"])
        if p["latest_temp"] is not None and p["today_temp"] is None:
            latest += f' <span class="nv-sub2">({ui.fmt_date(p["latest_date"])[:6]})</span>'
        rows.append({"id": p["patient_id"], "action": "View Details",
                     "cells": [f'<span class="nv-mono">{ui.esc(p["patient_id"])}</span>', ui.esc(p["name"]),
                               ui.esc(p["room_id"]), latest, _streak_cell(p), ui.status_badge(p["visit_status"]),
                               _eligibility_cell(p)]})
    clicked = ui.action_table("doc_mon", ["Patient ID", "Patient Name", "Room", "Latest Temperature", "Fever-free",
                                          "Visit Status", "Discharge", "Action"], [1, 1.8, .7, 2.1, 1.1, 1.4, 1.1, 1.2],
                              rows, "No patients match these filters", "Clear the search or change the filters.")
    if clicked:
        goto("Patient Monitoring", doc_patient=clicked)


@st.dialog("Approve discharge")
def _approve_dialog(user: dict, p: dict, streak: int) -> None:
    st.markdown(f"Approve discharge for **{p['name']}** ({p['patient_id']}, room {p['room_id']})?")
    st.caption(f"{streak} complete consecutive fever-free days. Admin is notified immediately; the room stays "
               "occupied until admin completes the discharge.")
    note = st.text_area("Discharge note (optional)", max_chars=1000)
    c1, c2 = st.columns(2)
    if c1.button("Approve discharge", type="primary", width="stretch"):
        ok, _ = attempt(services.approve_discharge, user, p["patient_id"], note)
        if ok:
            ui.flash("success", f"Discharge approved for {p['name']}. Admin has been notified.")
            st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Record patient death")
def _death_dialog(user: dict, p: dict, now: datetime) -> None:
    st.markdown(f"Record the death of **{p['name']}** ({p['patient_id']}, room {p['room_id']}).")
    st.caption("This cannot be undone from the application. The room remains occupied until admin releases it.")
    c1, c2 = st.columns(2)
    d = c1.date_input("Date of death", value=now.date(), min_value=date.fromisoformat(p["admission_date"]),
                      max_value=now.date(), format="DD/MM/YYYY")
    t = c2.time_input("Time of death", value=now.time().replace(second=0), step=60)
    note = st.text_area("Clinical note (optional)", max_chars=1000)
    confirmed = st.checkbox("I confirm this patient has died.")
    b1, b2 = st.columns(2)
    if b1.button("Record death", type="primary", width="stretch", disabled=not confirmed):
        ok, _ = attempt(services.record_death, user, p["patient_id"], datetime.combine(d, t), note)
        if ok:
            ui.flash("success", f"Death recorded for {p['name']}. Admin has been notified to release room {p['room_id']}.")
            goto("Patient Monitoring")
    if b2.button("Cancel", width="stretch"):
        st.rerun()


def _detail(user: dict, now: datetime, patient_id: str) -> None:
    if st.button("Back to patient list", icon=":material/arrow_back:"):
        goto("Patient Monitoring")
    overview = {p["patient_id"]: p for p in services.patient_overview(user, now)}
    p = overview.get(patient_id)
    if not p:
        st.warning("This patient is no longer on the active patient list.")
        return
    readings = services.temperature_history(user, patient_id)
    visits = services.visit_history(user, patient_id)
    treatments = services.treatment_records(user, patient_id)

    if p["eligible"]:
        st.markdown(f'<div class="nv-eligible">ELIGIBLE FOR DISCHARGE<span>{p["fever_free_days"]} complete consecutive '
                    'fever-free days. This is an administrative flag - discharge requires your approval.</span></div>',
                    unsafe_allow_html=True)
    ui.info_card(f'{p["name"]}  ·  {p["patient_id"]}', [
        ("Age / Gender", f'{ui.esc(p["age"])} · {ui.esc(p["gender"])}'), ("Room", ui.esc(p["room_id"])),
        ("Admission date", ui.fmt_date(p["admission_date"])), ("Current status", ui.status_badge(p["status"])),
        ("Today's temperature", ui.temp_badge(p["today_temp"]) if p["today_temp"] is not None else ui.status_badge("Pending")),
        ("Fever-free days", _streak_cell(p)), ("Today's visit", ui.status_badge(p["visit_status"])),
        ("Contact", ui.esc(p["contact"] or "-"))])
    if p["initial_notes"]:
        st.caption(f"Admission note: {p['initial_notes']}")

    a1, a2, _ = st.columns([1.4, 1.4, 4])
    if p["eligible"] and a1.button("Approve Discharge", type="primary", width="stretch"):
        _approve_dialog(user, p, p["fever_free_days"])
    if a2.button("Record Death", width="stretch"):
        _death_dialog(user, p, now)

    ui.section("Temperature history", f"Fever threshold {config.FEVER_THRESHOLD_C:.1f} °C (demonstration assumption)")
    if readings:
        st.plotly_chart(ui.temperature_chart(readings), width="stretch", config=ui.PLOTLY_CONFIG)
    else:
        ui.empty("No readings yet", "The nurse has not recorded a temperature for this patient.", "thermo")

    tab_visit, tab_temps, tab_visits, tab_treat = st.tabs(["Today's visit", "All readings", "Visit history", "Treatment history"])
    with tab_visit:
        if p["visited_today"]:
            st.success("Today's visit has been completed. Further treatment records can still be added below.")
        elif not p["ready_for_visit"]:
            st.warning("Today's temperature is pending. The visit cannot be marked as completed until the nurse records it.")
        with st.form(f"visit_form_{patient_id}", clear_on_submit=True):
            treatment = st.text_input("Treatment administered", max_chars=300)
            notes = st.text_area("Clinical notes", max_chars=2000, height=110)
            b1, b2, _ = st.columns([1.6, 1.6, 3])
            save_visit = b1.form_submit_button("Mark Visit Completed", type="primary", width="stretch",
                                               disabled=p["visited_today"] or not p["ready_for_visit"])
            save_only = b2.form_submit_button("Save Treatment Record", width="stretch")
        if save_visit:
            ok, _ = attempt(services.complete_visit, user, patient_id, treatment, notes)
            if ok:
                ui.flash("success", f"Today's visit completed for {p['name']}.")
                st.rerun()
        if save_only:
            ok, _ = attempt(services.add_treatment, user, patient_id, treatment, notes)
            if ok:
                ui.flash("success", f"Treatment record saved for {p['name']}.")
                st.rerun()
    with tab_temps:
        ui.html_table(["Date", "Time", "Temperature", "Recorded by"],
                      [[ui.fmt_date(r["reading_date"]), ui.fmt_time(r["recorded_at"]), ui.temp_badge(r["temperature_c"]),
                        ui.esc(r["recorded_by_name"])] for r in reversed(readings)], "No readings yet")
    with tab_visits:
        ui.html_table(["Visit date", "Completed at", "Doctor", "Notes"],
                      [[ui.fmt_date(v["visit_date"]), ui.fmt_time(v["completed_at"]), ui.esc(v["doctor_name"]),
                        ui.esc(v["notes"] or "-")] for v in visits], "No visits yet",
                      "Completed visits for this patient appear here.")
    with tab_treat:
        ui.html_table(["Recorded", "Type", "Treatment", "Notes", "Doctor"],
                      [[ui.fmt_dt(t["recorded_at"]), ui.badge(t["entry_type"], "info"), ui.esc(t["treatment"] or "-"),
                        ui.esc(t["notes"] or "-"), ui.esc(t["doctor_name"])] for t in treatments],
                      "No treatment records", "Treatments and clinical notes for this patient appear here.")


def discharge_eligible(user: dict, now: datetime) -> None:
    data = services.patient_overview(user, now)
    eligible = [p for p in data if p["eligible"]]
    st.caption(f"Patients with {REQ} or more complete consecutive fever-free days. Eligibility is an administrative "
               "flag, not a medical decision - review each patient before approving.")
    rows = [{"id": p["patient_id"], "action": "Review", "primary": True,
             "cells": [f'<span class="nv-mono">{ui.esc(p["patient_id"])}</span>', ui.esc(p["name"]), ui.esc(p["room_id"]),
                       _streak_cell(p), ui.temp_badge(p["latest_temp"]), ui.status_badge(p["temp_status"])]}
            for p in eligible]
    clicked = ui.action_table("doc_elig", ["Patient ID", "Patient Name", "Room", "Fever-free", "Latest Temperature",
                                           "Today's Reading", "Action"], [1, 2, .8, 1.2, 1.9, 1.4, 1.1], rows,
                              "No patients are eligible for discharge",
                              f"Patients appear here after {REQ} complete consecutive fever-free days.", "check")
    if clicked:
        goto("Patient Monitoring", doc_patient=clicked)
    ui.section("Approved - awaiting administrative completion")
    ui.html_table(["Patient ID", "Patient Name", "Room", "Approved", "Approved by", "Note"],
                  [[f'<span class="nv-mono">{ui.esc(a["patient_id"])}</span>', ui.esc(a["patient_name"]), ui.esc(a["room_id"]),
                    ui.fmt_dt(a["approved_at"]), ui.esc(a["doctor_name"]), ui.esc(a["note"] or "-")]
                   for a in services.approved_awaiting_admin(user)],
                  "Nothing awaiting admin", "Approved discharges appear here until admin completes them.")


def visit_history(user: dict, now: datetime) -> None:
    visits = services.visit_history(user)
    c1, c2 = st.columns([2, 1])
    query = c1.text_input("Search", placeholder="Search by patient name or ID", label_visibility="collapsed").strip().lower()
    only_today = c2.toggle("Today only")
    today = now.date().isoformat()
    rows = [[ui.fmt_date(v["visit_date"]), ui.fmt_time(v["completed_at"]),
             f'<span class="nv-mono">{ui.esc(v["patient_id"])}</span>', ui.esc(v["patient_name"]), ui.esc(v["room_id"]),
             ui.esc(v["doctor_name"]), ui.esc(v["notes"] or "-")]
            for v in visits
            if (not query or query in v["patient_name"].lower() or query in v["patient_id"].lower())
            and (not only_today or v["visit_date"] == today)]
    ui.html_table(["Visit date", "Time", "Patient ID", "Patient", "Room", "Doctor", "Notes"], rows,
                  "No visits found", "Completed doctor visits appear here.")


def treatment_records(user: dict, now: datetime) -> None:
    records = services.treatment_records(user)
    query = st.text_input("Search", placeholder="Search by patient name or ID", label_visibility="collapsed").strip().lower()
    rows = [[ui.fmt_dt(t["recorded_at"]), f'<span class="nv-mono">{ui.esc(t["patient_id"])}</span>', ui.esc(t["patient_name"]),
             ui.badge(t["entry_type"], "info"), ui.esc(t["treatment"] or "-"), ui.esc(t["notes"] or "-"),
             ui.esc(t["doctor_name"])]
            for t in records if not query or query in t["patient_name"].lower() or query in t["patient_id"].lower()]
    ui.html_table(["Recorded", "Patient ID", "Patient", "Type", "Treatment", "Notes", "Doctor"], rows,
                  "No treatment records found", "Treatments and clinical notes recorded by doctors appear here.")
