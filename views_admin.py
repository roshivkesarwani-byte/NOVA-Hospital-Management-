"""Admin screens: operations dashboard, rooms, admission, discharge queue,
notifications and hospital performance."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

import services
import ui
from views_common import attempt, goto


def _rate_text(stats: dict) -> str:
    return "N/A" if stats["rate"] is None else f'{stats["rate"]:.1f}%'


@st.dialog("Complete discharge")
def _complete_dialog(user: dict, a: dict) -> None:
    st.markdown(f"Complete the discharge of **{a['patient_name']}** ({a['patient_id']})?")
    st.caption(f"Approved by {a['doctor_name']} on {ui.fmt_dt(a['approved_at'])}. The patient will be marked "
               f"Discharged (Cured) and room {a['room_id']} will become available.")
    c1, c2 = st.columns(2)
    if c1.button("Complete Discharge", type="primary", width="stretch"):
        ok, _ = attempt(services.complete_discharge, user, a["id"])
        if ok:
            ui.flash("success", f"Discharge completed for {a['patient_name']}. Room {a['room_id']} is now available.")
            st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Release room")
def _release_dialog(user: dict, p: dict) -> None:
    st.markdown(f"Complete administrative closure for **{p['name']}** ({p['patient_id']}) and release room "
                f"**{p['room_id']}**?")
    st.caption("The patient's records are preserved. The outcome remains Deceased.")
    c1, c2 = st.columns(2)
    if c1.button("Release Room", type="primary", width="stretch"):
        ok, _ = attempt(services.release_room, user, p["patient_id"])
        if ok:
            ui.flash("success", f"Room {p['room_id']} released and is now available.")
            st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Reset demo data")
def _reset_dialog(user: dict) -> None:
    st.markdown("This **permanently erases every patient record** (including any you added) and reloads the "
                "fictional demonstration data, dated relative to today.")
    confirmed = st.checkbox("I understand that all current patient data will be erased.")
    c1, c2 = st.columns(2)
    if c1.button("Reset Demo Data", type="primary", width="stretch", disabled=not confirmed):
        with st.spinner("Reloading demonstration data..."):
            ok, _ = attempt(services.reset_demo_data, user)
        if ok:
            ui.flash("success", "Demonstration data has been reset.")
            st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


def dashboard(user: dict, now: datetime) -> None:
    occ = services.occupancy(user)
    queue = services.discharge_queue(user)
    stats = services.success_stats(user)
    ui.kpis([
        {"label": "Total room capacity", "value": occ["total"], "icon": "door"},
        {"label": "Occupied rooms", "value": occ["occupied"], "icon": "bed"},
        {"label": "Available rooms", "value": occ["available"], "icon": "check", "tone": "success"},
        {"label": "Pending discharge completions", "value": len(queue), "icon": "clip",
         "tone": "warning" if queue else ""},
        {"label": "Success rate", "value": _rate_text(stats), "icon": "heart",
         "tone": "" if stats["rate"] is None else "success" if stats["rate"] >= stats["benchmark"] else "warning",
         "sub": f'Benchmark {stats["benchmark"]:.0f}% · {stats["status"]}'},
    ])
    if not occ["consistent"]:
        st.error("Room status flags do not match room assignments. Please review Room Management.")
    left, right = st.columns([1, 1.6])
    with left:
        ui.section("Room occupancy")
        with st.container(border=True):
            st.plotly_chart(ui.occupancy_donut(occ["occupied"], occ["available"], occ["total"]),
                            width="stretch", config=ui.PLOTLY_CONFIG)
            st.markdown(f'<div class="nv-sub2" style="text-align:center">Occupied {occ["occupied"]} / {occ["total"]}'
                        f' &nbsp;·&nbsp; Available {occ["available"]} / {occ["total"]}</div>', unsafe_allow_html=True)
    with right:
        ui.section("Discharges awaiting completion")
        ui.html_table(["Patient ID", "Patient", "Room", "Approved", "Approving doctor"],
                      [[f'<span class="nv-mono">{ui.esc(a["patient_id"])}</span>', ui.esc(a["patient_name"]),
                        ui.esc(a["room_id"]), ui.fmt_dt(a["approved_at"]), ui.esc(a["doctor_name"])] for a in queue],
                      "No discharges waiting", "Doctor-approved discharges appear here automatically.")
        closures = services.pending_closures(user)
        if closures:
            st.info(f"{len(closures)} deceased patient record(s) await administrative closure and room release.")
        st.write("")
        if st.button("Open Discharge Queue", width="content"):
            goto("Discharge Queue")
    ui.section("Demonstration data")
    with st.container(border=True):
        c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
        c1.markdown("Reload the fictional demo patients, dated relative to today. Use this before a demonstration, "
                    "or after several days when the sample readings have gone stale.")
        if c2.button("Reset Demo Data", width="stretch"):
            _reset_dialog(user)


def room_management(user: dict, now: datetime) -> None:
    rooms = services.room_overview(user)
    occ = services.occupancy(user)
    ui.kpis([
        {"label": "Total rooms", "value": occ["total"], "icon": "door"},
        {"label": "Occupied", "value": f'{occ["occupied"]} / {occ["total"]}', "icon": "bed"},
        {"label": "Available", "value": f'{occ["available"]} / {occ["total"]}', "icon": "check", "tone": "success"},
    ])
    st.progress(occ["occupied"] / occ["total"] if occ["total"] else 0.0,
                text=f'{occ["occupied"]} of {occ["total"]} rooms occupied')
    show = st.segmented_control("Show", ["All rooms", "Occupied", "Available"], default="All rooms",
                                label_visibility="collapsed") or "All rooms"
    tiles = []
    for r in rooms:
        occupied = r["patient_id"] is not None
        if (show == "Occupied" and not occupied) or (show == "Available" and occupied):
            continue
        tiles.append(f'<div class="nv-room {"occ" if occupied else "avail"}"><b>{ui.esc(r["room_id"])}</b>'
                     f'<span>{ui.esc(r["patient_id"]) if occupied else "Available"}</span></div>')
    ui.section("Room map", "R001 - R074")
    if tiles:
        st.markdown(f'<div class="nv-card"><div class="nv-rooms">{"".join(tiles)}</div></div>', unsafe_allow_html=True)
    else:
        ui.empty("No rooms in this view", "Change the filter above.", "door")
    ui.section("Occupied rooms")
    ui.html_table(["Room", "Patient ID", "Patient", "Patient status", "Admission date"],
                  [[f'<span class="nv-mono">{ui.esc(r["room_id"])}</span>', ui.esc(r["patient_id"]), ui.esc(r["patient_name"]),
                    ui.status_badge(r["patient_status"]), ui.fmt_date(r["admission_date"])]
                   for r in rooms if r["patient_id"]],
                  "All rooms are available", "Admit a patient to assign a room.", )


def admit_patient(user: dict, now: datetime) -> None:
    rooms = services.available_rooms(user)
    if not rooms:
        ui.empty("No rooms available", "All 74 rooms are occupied. Complete a discharge to free a room.", "door")
        return
    st.caption(f"{len(rooms)} of 74 rooms available. Fields marked * are required.")
    with st.form("admit_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("Patient name *", max_chars=100)
        age = c2.number_input("Age *", min_value=0, max_value=120, value=None, step=1)
        gender = c3.selectbox("Gender *", services.GENDERS, index=None, placeholder="Select")
        d1, d2, d3 = st.columns([1, 1, 1])
        contact = d1.text_input("Contact number (optional)", max_chars=20)
        admission = d2.date_input("Admission date *", value=now.date(), max_value=now.date(), format="DD/MM/YYYY")
        room = d3.selectbox("Room *", rooms, index=None, placeholder="Select an available room")
        notes = st.text_area("Initial clinical notes (optional)", max_chars=1000, height=90)
        b1, _ = st.columns([1.3, 5])
        submitted = b1.form_submit_button("Admit Patient", type="primary", width="stretch")
    if submitted:
        ok, pid = attempt(services.admit_patient, user, name, age, gender, room, admission, contact, notes)
        if ok:
            ui.flash("success", f"{' '.join(name.split())} admitted as {pid} in room {room}.")
            st.rerun()


def discharge_queue(user: dict, now: datetime) -> None:
    queue = services.discharge_queue(user)
    ui.section("Approved by doctor - awaiting completion", f"{len(queue)} pending")
    rows = [{"id": a["id"], "action": "Complete Discharge", "primary": True,
             "cells": [f'<span class="nv-mono">{ui.esc(a["patient_id"])}</span>', ui.esc(a["patient_name"]),
                       ui.esc(a["room_id"]), ui.fmt_dt(a["approved_at"]), ui.esc(a["doctor_name"]),
                       ui.badge("Awaiting completion", "warning")]} for a in queue]
    clicked = ui.action_table("adm_queue", ["Patient ID", "Patient Name", "Room", "Doctor Approval Date",
                                            "Approving Doctor", "Discharge Status", "Action"],
                              [.9, 1.6, .7, 2, 1.5, 1.6, 1.7], rows, "The discharge queue is empty",
                              "Patients appear here automatically when a doctor approves their discharge.", "check")
    if clicked:
        _complete_dialog(user, next(a for a in queue if a["id"] == clicked))

    closures = services.pending_closures(user)
    if closures:
        ui.section("Administrative closures", "Deceased patients - room still occupied")
        rows = [{"id": p["patient_id"], "action": "Release Room",
                 "cells": [f'<span class="nv-mono">{ui.esc(p["patient_id"])}</span>', ui.esc(p["name"]), ui.esc(p["room_id"]),
                           ui.fmt_dt(p["outcome_at"]), ui.status_badge("Deceased")]} for p in closures]
        clicked = ui.action_table("adm_close", ["Patient ID", "Patient Name", "Room", "Recorded", "Status", "Action"],
                                  [1, 2, .8, 1.6, 1.2, 1.4], rows)
        if clicked:
            _release_dialog(user, next(p for p in closures if p["patient_id"] == clicked))

    ui.section("Completed discharges")
    ui.html_table(["Patient ID", "Patient Name", "Room released", "Approved", "Approving doctor", "Completed", "Completed by", "Status"],
                  [[f'<span class="nv-mono">{ui.esc(a["patient_id"])}</span>', ui.esc(a["patient_name"]), ui.esc(a["room_id"]),
                    ui.fmt_dt(a["approved_at"]), ui.esc(a["doctor_name"]), ui.fmt_dt(a["completed_at"]),
                    ui.esc(a["completed_by_name"]), ui.status_badge("Completed")]
                   for a in services.discharge_queue(user, "Completed")],
                  "No completed discharges yet", "Completed discharges are kept here as a permanent record.")


def notifications(user: dict, now: datetime) -> None:
    items = services.notifications(user)
    unread = [n for n in items if not n["is_read"]]
    c1, c2 = st.columns([4, 1.2], vertical_alignment="center")
    c1.caption(f"{len(unread)} unread · {len(items)} total. Notifications are created automatically and kept as history.")
    if unread and c2.button("Mark all as read", width="stretch"):
        services.mark_notification_read(user)
        st.rerun()
    if not items:
        ui.empty("No notifications", "You will be notified here the moment a doctor approves a discharge.", "clip")
        return
    for n in items:
        is_unread = not n["is_read"]
        with st.container(key=f"note_{n['id']}"):
            cols = st.columns([5, 1.2], vertical_alignment="center")
            state = ui.badge("Unread", "warning") if is_unread else ui.badge("Read", "neutral")
            cols[0].markdown(f'<div class="nv-note {"unread" if is_unread else ""}"><b>{ui.esc(n["title"])}</b> {state}'
                             f'<div>{ui.esc(n["message"])}</div><div class="nv-sub2">{ui.fmt_dt(n["created_at"])}'
                             f'{" · read " + ui.fmt_dt(n["read_at"]) if n["read_at"] else ""}</div></div>',
                             unsafe_allow_html=True)
            if is_unread and cols[1].button("Mark as read", key=f"read_{n['id']}", width="stretch"):
                services.mark_notification_read(user, n["id"])
                st.rerun()


def performance(user: dict, now: datetime) -> None:
    s = services.success_stats(user)
    tone = "" if s["rate"] is None else "success" if s["rate"] >= s["benchmark"] else "warning"
    ui.kpis([
        {"label": "Current success rate", "value": _rate_text(s), "icon": "heart", "tone": tone, "sub": s["status"]},
        {"label": "Cured patients", "value": s["cured"], "icon": "check", "tone": "success", "sub": "Discharged"},
        {"label": "Deceased patients", "value": s["deceased"], "icon": "users"},
        {"label": "Benchmark", "value": f'{s["benchmark"]:.0f}%', "icon": "chart", "sub": "Target success rate"},
    ])
    ui.section("Success rate against benchmark", "Cured / (Cured + Deceased) x 100 - finalised outcomes only")
    if s["rate"] is None:
        ui.empty("Success rate: N/A", "No patient outcomes have been finalised yet, so there is nothing to calculate.", "chart")
    else:
        with st.container(border=True):
            st.plotly_chart(ui.performance_bar(s["rate"], s["benchmark"]), width="stretch", config=ui.PLOTLY_CONFIG)
            gap = s["rate"] - s["benchmark"]
            msg = (f'{s["cured"]} cured of {s["finalised"]} finalised outcomes = {s["rate"]:.1f}%, '
                   f'{abs(gap):.1f} points {"above" if gap >= 0 else "below"} the {s["benchmark"]:.0f}% benchmark.')
            (st.success if gap >= 0 else st.warning)(msg)
    ui.section("Finalised outcomes", "Currently admitted patients are excluded")
    ui.html_table(["Patient ID", "Patient", "Admission date", "Outcome", "Outcome recorded"],
                  [[f'<span class="nv-mono">{ui.esc(o["patient_id"])}</span>', ui.esc(o["name"]), ui.fmt_date(o["admission_date"]),
                    ui.status_badge("Cured" if o["outcome"] == "Cured" else "Deceased"), ui.fmt_dt(o["outcome_at"])]
                   for o in services.finalised_outcomes(user)],
                  "No finalised outcomes", "Outcomes appear here after a discharge is completed or a death is recorded.")
