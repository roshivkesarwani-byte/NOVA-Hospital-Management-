"""Drives the real Streamlit app headlessly: every role logs in and opens
every screen, with demo data and with an empty database."""
import os
import sys

import pytest
from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import database as db  # noqa: E402

PAGES = {
    "nurse": ["Dashboard", "Patient List", "Record Temperature", "Temperature History"],
    "doctor": ["Dashboard", "Patient Monitoring", "Discharge Eligible", "Visit History", "Treatment Records"],
    "admin": ["Dashboard", "Room Management", "Admit Patient", "Discharge Queue", "Notifications", "Hospital Performance"],
}


def _login(role):
    import streamlit as st
    st.cache_resource.clear()
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    assert not at.exception
    at.text_input[0].set_value(role)
    at.text_input[1].set_value(f"{role}123")
    at.button[0].click().run()
    assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("seed", [True, False], ids=["demo-data", "empty-db"])
@pytest.mark.parametrize("role", list(PAGES))
def test_every_screen_renders(tmp_path, role, seed):
    db.configure(f"sqlite:///{tmp_path / 'nova.db'}")
    db.init_db(seed_demo=seed)
    at = _login(role)
    assert at.session_state["user"]["role"] == role
    nav_keys = {b.key for b in at.button if b.key and b.key.startswith("nav_")}
    assert nav_keys == {f"nav_{p}" for p in PAGES[role]} | {"nav_logout"}  # no other role's screens
    for page in PAGES[role]:
        at.button(key=f"nav_{page}").click().run()
        assert not at.exception, (page, at.exception)
        assert at.session_state["page"] == page


def test_wrong_password_is_rejected(tmp_path):
    db.configure(f"sqlite:///{tmp_path / 'nova.db'}")
    db.init_db()
    import streamlit as st
    st.cache_resource.clear()
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60).run()
    at.text_input[0].set_value("nurse")
    at.text_input[1].set_value("wrong")
    at.button[0].click().run()
    assert "user" not in at.session_state
    assert any("Incorrect" in e.value for e in at.error)


def test_forced_page_of_another_role_is_ignored(tmp_path):
    db.configure(f"sqlite:///{tmp_path / 'nova.db'}")
    db.init_db()
    at = _login("nurse")
    at.session_state["page"] = "Discharge Queue"  # admin screen
    at.run()
    assert not at.exception
    assert at.session_state["page"] == "Dashboard"
