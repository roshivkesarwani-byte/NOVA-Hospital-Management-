"""Design system for NOVA: theme CSS and reusable presentation components.

All user-supplied text is HTML-escaped with ``esc`` before it is rendered."""
from __future__ import annotations

import html
from datetime import date, datetime

import plotly.graph_objects as go
import streamlit as st

import config
import logic

NAVY, TEAL, MINT, BG, CARD = "#142D3A", "#176B65", "#EAF3F2", "#F7F9FA", "#FFFFFF"
TEXT, MUTED, BORDER = "#25343B", "#77858B", "#E2E8EA"
GREEN, AMBER, RED = "#2E7D5B", "#B7791F", "#C2544D"

ICONS = {
    "bed": '<path d="M3 18v-7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v7M3 14h18M3 18v2M21 18v2M7 9V6h10v3"/>',
    "thermo": '<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>',
    "steth": '<path d="M6 3v6a4 4 0 0 0 8 0V3M10 13v3a5 5 0 0 0 10 0v-2"/><circle cx="20" cy="12" r="2"/>',
    "alert": '<path d="M12 4 2.5 20h19L12 4zM12 10v4M12 17v.5"/>',
    "door": '<path d="M5 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17M3 21h18M12.5 12v.5M16 7h2a1 1 0 0 1 1 1v13"/>',
    "clip": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 10h6M9 14h6"/>',
    "chart": '<path d="M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6"/>',
    "heart": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def icon(name: str, size: int = 20) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def fmt_date(value) -> str:
    if not value:
        return "-"
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return d.strftime("%d %b %Y")


def fmt_dt(value) -> str:
    if not value:
        return "-"
    d = value if isinstance(value, datetime) else logic.parse_ts(value)
    return d.strftime("%d %b %Y, %H:%M")


def fmt_time(value) -> str:
    return logic.parse_ts(value).strftime("%H:%M") if value else "-"


def fmt_temp(value) -> str:
    return "-" if value is None else f"{value:.1f} °C"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
html, body, .stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp [data-testid="stMarkdownContainer"] {{ font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif; }}
.stApp {{ background: {BG}; color: {TEXT}; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{ padding: 2.2rem 2.2rem 3rem; max-width: 1380px; }}
h1, h2, h3 {{ color: {NAVY}; letter-spacing: -0.01em; }}

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"] {{ background: {NAVY}; border-right: 0; }}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: .5rem; }}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .3rem; }}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
section[data-testid="stSidebar"] .stButton > button {{
  width: 100%; justify-content: flex-start; text-align: left; background: transparent; border: 0;
  color: #C5D3D8; border-radius: 8px; padding: .55rem .8rem; min-height: 2.5rem; font-weight: 500; box-shadow: none; }}
section[data-testid="stSidebar"] .stButton > button > div {{ width: 100%; display: flex; justify-content: flex-start; }}
section[data-testid="stSidebar"] .stButton > button > div > span {{ justify-content: flex-start; gap: .6rem; }}
section[data-testid="stSidebar"] .stButton > button p {{ font-size: .93rem; }}
section[data-testid="stSidebar"] .stMarkdownBadge {{ background: #F0B54A !important; color: #3A2A05 !important; font-size: .68rem !important; font-weight: 600; margin-left: .3rem; }}
section[data-testid="stSidebar"] .st-key-nav_logout button > div {{ justify-content: center; }}
section[data-testid="stSidebar"] .stButton > button:hover {{ background: rgba(255,255,255,.07); color: #fff; }}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{ background: {TEAL}; color: #fff; }}
section[data-testid="stSidebar"] .stButton > button:focus-visible {{ outline: 2px solid #8FD3CB; outline-offset: 1px; }}
section[data-testid="stSidebar"] .st-key-nav_logout button {{ border: 1px solid rgba(255,255,255,.22); justify-content: center; }}
.nv-brand {{ padding: .2rem .4rem 1rem; border-bottom: 1px solid rgba(255,255,255,.1); margin-bottom: .7rem; }}
.nv-brand .nv-logo {{ display: flex; align-items: center; gap: .55rem; color: #fff; font-size: 1.45rem; font-weight: 700; letter-spacing: .14em; }}
.nv-brand .nv-mark {{ width: 34px; height: 34px; border-radius: 9px; background: {TEAL}; display: grid; place-items: center; color: #fff; }}
.nv-brand .nv-sub {{ color: #8FA4AC; font-size: .74rem; margin-top: .35rem; letter-spacing: .02em; }}
.nv-navlabel {{ color: #7F959D; font-size: .68rem; letter-spacing: .12em; text-transform: uppercase; padding: .5rem .5rem .9rem; }}
.nv-userbox {{ margin-top: 1.2rem; padding: .8rem .7rem; border-top: 1px solid rgba(255,255,255,.1); color: #C5D3D8; font-size: .8rem; line-height: 1.5; }}
.nv-userbox b {{ color: #fff; font-size: .9rem; font-weight: 600; display: block; }}
.nv-userbox .nv-role {{ display: inline-block; margin: .25rem 0 .45rem; padding: .08rem .5rem; border-radius: 999px; background: rgba(255,255,255,.1); font-size: .7rem; color: #D8E6E4; }}

/* ---------- page header ---------- */
.nv-top {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; flex-wrap: wrap;
  padding-bottom: 1rem; margin-bottom: 1.1rem; border-bottom: 1px solid {BORDER}; }}
.nv-top h1 {{ font-size: 1.5rem; font-weight: 600; margin: 0; padding: 0; color: {NAVY}; }}
.nv-top .nv-desc {{ color: {MUTED}; font-size: .88rem; margin-top: .15rem; }}
.nv-top .nv-meta {{ display: flex; gap: .5rem; flex-wrap: wrap; }}
.nv-chip {{ display: inline-flex; align-items: center; gap: .35rem; background: {CARD}; border: 1px solid {BORDER};
  border-radius: 999px; padding: .3rem .75rem; font-size: .78rem; color: {TEXT}; white-space: nowrap; }}
.nv-chip svg {{ color: {TEAL}; }}
.nv-section {{ font-size: 1rem; font-weight: 600; color: {NAVY}; margin: 1.3rem 0 .6rem; }}
.nv-section small {{ font-weight: 400; color: {MUTED}; font-size: .8rem; margin-left: .4rem; }}
.nv-demo {{ background: {MINT}; border: 1px solid #CFE3E0; color: #2B5752; border-radius: 8px; padding: .45rem .8rem;
  font-size: .78rem; margin-bottom: 1rem; }}

/* ---------- KPI cards ---------- */
.nv-kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .9rem; margin-bottom: .4rem; }}
.nv-kpi {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 1rem 1.1rem; min-height: 112px;
  box-shadow: 0 1px 2px rgba(20,45,58,.04); display: flex; flex-direction: column; justify-content: space-between; }}
.nv-kpi .nv-kl {{ display: flex; justify-content: space-between; align-items: center; color: {MUTED}; font-size: .8rem; font-weight: 500; }}
.nv-kpi .nv-ki {{ width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center; background: {MINT}; color: {TEAL}; }}
.nv-kpi .nv-kv {{ font-size: 1.85rem; font-weight: 600; color: {NAVY}; line-height: 1.1; font-variant-numeric: tabular-nums; }}
.nv-kpi .nv-ks {{ font-size: .76rem; color: {MUTED}; margin-top: .15rem; }}
.nv-kpi.warning .nv-ki {{ background: #FBF1DC; color: {AMBER}; }} .nv-kpi.success .nv-ki {{ background: #E3F2EA; color: {GREEN}; }}
.nv-kpi.danger .nv-ki {{ background: #F9E7E5; color: {RED}; }}

/* ---------- badges ---------- */
.nv-badge {{ display: inline-block; padding: .14rem .6rem; border-radius: 999px; font-size: .74rem; font-weight: 600; white-space: nowrap; }}
.nv-badge.success {{ background: #E3F2EA; color: #216346; }} .nv-badge.warning {{ background: #FBF1DC; color: #8A5A12; }}
.nv-badge.danger {{ background: #F9E7E5; color: #A23E38; }} .nv-badge.neutral {{ background: #EEF1F2; color: #56656B; }}
.nv-badge.info {{ background: {MINT}; color: {TEAL}; }}

/* ---------- cards & tables ---------- */
.nv-card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 1.1rem 1.2rem;
  box-shadow: 0 1px 2px rgba(20,45,58,.04); }}
.nv-card h4 {{ margin: 0 0 .6rem; padding: 0; font-size: .95rem; font-weight: 600; color: {NAVY}; }}
.nv-info {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .9rem 1.2rem; }}
.nv-info > div > span {{ display: block; color: {MUTED}; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; }}
.nv-info > div > b {{ font-weight: 600; color: {TEXT}; font-size: .93rem; }}
.nv-tablewrap {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; overflow-x: auto;
  box-shadow: 0 1px 2px rgba(20,45,58,.04); }}
table.nv-table {{ width: 100%; border-collapse: collapse; font-size: .86rem; }}
table.nv-table th {{ text-align: left; padding: .65rem .9rem; font-size: .72rem; font-weight: 600; color: {MUTED};
  text-transform: uppercase; letter-spacing: .06em; background: #FAFBFC; border-bottom: 1px solid {BORDER}; white-space: nowrap; }}
table.nv-table th, table.nv-table td {{ border-left: 0 !important; border-right: 0 !important; border-top: 0 !important; }}
table.nv-table td {{ padding: .65rem .9rem; border-bottom: 1px solid #EEF2F3; color: {TEXT}; vertical-align: middle; }}
table.nv-table tr:last-child td {{ border-bottom: 0; }}
.nv-mono {{ font-variant-numeric: tabular-nums; font-weight: 600; color: {NAVY}; }}
.nv-sub2 {{ color: {MUTED}; font-size: .78rem; }}

[class*="st-key-nvtable_"] {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; gap: 0 !important;
  box-shadow: 0 1px 2px rgba(20,45,58,.04); overflow: hidden; }}
[class*="st-key-nvhead_"] {{ background: #FAFBFC; border-bottom: 1px solid {BORDER}; padding: .6rem .9rem; }}
[class*="st-key-nvhead_"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
[class*="st-key-nvhead_"] [data-testid="stMarkdownContainer"] p {{ margin: 0; }}
.stPlotlyChart {{ background: #FFFFFF; border: 1px solid #E2E8EA; border-radius: 12px; padding: .5rem; overflow: hidden; box-sizing: border-box; }}
[data-testid="stVerticalBlockBorderWrapper"] .stPlotlyChart {{ border: 0; padding: 0; }}
[class*="st-key-nvhead_"] .nv-th {{ font-size: .72rem; font-weight: 600; color: {MUTED}; text-transform: uppercase; letter-spacing: .06em; }}
[class*="st-key-nvrow_"] {{ padding: .42rem .9rem; border-bottom: 1px solid #EEF2F3; }}
[class*="st-key-nvrow_"]:last-child {{ border-bottom: 0; }}
[class*="st-key-nvrow_"] .nv-cell {{ font-size: .87rem; color: {TEXT}; overflow-wrap: anywhere; }}
[class*="st-key-nvrow_"] [data-testid="stMarkdownContainer"] p {{ margin: 0; }}
[class*="st-key-nvrow_"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0; }}
[class*="st-key-nvrow_"] .stButton > button {{ min-height: 2.1rem; padding: .2rem .6rem; }}
[class*="st-key-nvrow_"] .stButton > button p {{ font-size: .82rem; }}
.nv-cell .nv-lbl {{ display: none; }}

/* ---------- widgets ---------- */
.stMain .stButton > button, .stMain .stFormSubmitButton > button, div[role="dialog"] .stButton > button {{
  border-radius: 8px; min-height: 2.5rem; font-weight: 500; border: 1px solid #CBD5D8; }}
.stMain .stButton > button[kind="primary"], .stMain .stFormSubmitButton > button[kind="primary"],
div[role="dialog"] .stButton > button[kind="primary"] {{ background: {TEAL}; border-color: {TEAL}; color: #fff; }}
.stMain .stButton > button[kind="primary"]:hover, .stMain .stFormSubmitButton > button[kind="primary"]:hover {{ background: #125750; border-color: #125750; }}
[data-testid="stForm"] {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 1.2rem 1.3rem; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 12px; }}
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input, .stTimeInput input {{ background: #fff; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 500; }}

/* ---------- misc ---------- */
.nv-empty {{ background: {CARD}; border: 1px dashed #CBD5D8; border-radius: 12px; padding: 2.2rem 1rem; text-align: center; color: {MUTED}; }}
.nv-empty .nv-ei {{ width: 44px; height: 44px; border-radius: 12px; background: {MINT}; color: {TEAL}; display: grid; place-items: center; margin: 0 auto .6rem; }}
.nv-empty b {{ display: block; color: {NAVY}; font-size: .95rem; margin-bottom: .15rem; }}
.nv-eligible {{ background: #E3F2EA; border: 1px solid #B9DCC9; color: #1D5A3F; border-radius: 12px; padding: .8rem 1.1rem;
  font-weight: 700; letter-spacing: .08em; font-size: .9rem; margin-bottom: .8rem; }}
.nv-eligible span {{ display: block; font-weight: 400; letter-spacing: 0; font-size: .8rem; margin-top: .15rem; }}
.nv-rooms {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); gap: .5rem; }}
.nv-room {{ border-radius: 9px; padding: .5rem .55rem; border: 1px solid {BORDER}; background: {CARD}; font-size: .78rem; min-height: 54px; }}
.nv-room b {{ display: block; font-size: .84rem; color: {NAVY}; }}
.nv-room.occ {{ background: {NAVY}; border-color: {NAVY}; color: #C5D3D8; }} .nv-room.occ b {{ color: #fff; }}
.nv-room.avail span {{ color: {GREEN}; }}
.nv-note {{ border-left: 3px solid {TEAL}; background: {CARD}; border-radius: 0 10px 10px 0; padding: .7rem .9rem; margin-bottom: .55rem;
  border-top: 1px solid {BORDER}; border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER}; font-size: .86rem; }}
.nv-note.unread {{ border-left-color: {AMBER}; background: #FFFCF5; }}
.nv-note b {{ color: {NAVY}; }} .nv-note .nv-sub2 {{ margin-top: .2rem; }}
.nv-login-brand {{ text-align: center; margin: 7vh 0 1.2rem; }}
.nv-login-brand .nv-mark {{ width: 54px; height: 54px; border-radius: 14px; background: {NAVY}; color: #fff; display: grid; place-items: center; margin: 0 auto .8rem; }}
.nv-login-brand h1 {{ font-size: 2rem; letter-spacing: .2em; margin: 0; padding: 0; color: {NAVY}; font-weight: 700; }}
.nv-login-brand p {{ color: {MUTED}; margin: .2rem 0 0; font-size: .9rem; }}
.nv-foot {{ text-align: center; color: {MUTED}; font-size: .74rem; margin-top: 1rem; }}

@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"] {{ padding: 3.2rem 1rem 2rem; }}
  [class*="st-key-nvhead_"] {{ display: none; }}
  [class*="st-key-nvrow_"] {{ padding: .8rem .9rem; }}
  [class*="st-key-nvrow_"] [data-testid="stHorizontalBlock"] {{ gap: .35rem; }}
  [class*="st-key-nvrow_"] [data-testid="stColumn"] {{ min-height: 1.4rem; }}
  [class*="st-key-nvrow_"] .nv-cell {{ display: flex; align-items: center; flex-wrap: wrap; gap: .3rem; line-height: 1.5; }}
  .nv-cell .nv-lbl {{ display: inline-block; min-width: 9.5rem; color: {MUTED}; font-size: .74rem; }}
  .nv-kpis {{ grid-template-columns: repeat(2, 1fr); }} .nv-kpi .nv-kv {{ font-size: 1.5rem; }}
}}
</style>
"""


def inject_css(hide_sidebar: bool = False) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if hide_sidebar:
        st.markdown('<style>section[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],'
                    '[data-testid="stExpandSidebarButton"]{display:none!important}</style>', unsafe_allow_html=True)


def badge(text: str, tone: str = "neutral") -> str:
    return f'<span class="nv-badge {tone}">{esc(text)}</span>'


def temp_badge(temp) -> str:
    if temp is None:
        return '<span class="nv-sub2">-</span>'
    fever = logic.is_fever(temp)
    return f'<span class="nv-mono">{temp:.1f} °C</span> ' + badge("Fever" if fever else "No Fever", "danger" if fever else "success")


def status_badge(status: str) -> str:
    tone = {"Admitted": "info", "Discharge Approved": "warning", "Discharged": "success", "Deceased": "neutral",
            "Pending": "warning", "Recorded Today": "success", "Ready for Visit": "info", "Not Ready": "warning",
            "Visit Completed": "success", "Approved": "warning", "Completed": "success", "Cancelled": "neutral",
            "Cured": "success", "Available": "success", "Occupied": "neutral"}.get(status, "neutral")
    return badge(status, tone)


def page_header(title: str, description: str, user: dict, today: date) -> None:
    import auth
    st.markdown(
        f'<div class="nv-top"><div><h1>{esc(title)}</h1><div class="nv-desc">{esc(description)}</div></div>'
        f'<div class="nv-meta"><span class="nv-chip">{icon("clock", 14)} Hospital date: {today.strftime("%a, %d %b %Y")}</span>'
        f'<span class="nv-chip">{icon("users", 14)} {esc(user["full_name"])} &middot; {esc(auth.ROLE_LABELS[user["role"]])}</span>'
        f'</div></div>', unsafe_allow_html=True)


def demo_banner() -> None:
    st.markdown('<div class="nv-demo"><b>Fictional demonstration data.</b> All patients and records shown are invented. '
                'NOVA is a prototype and is not approved for real patient care.</div>', unsafe_allow_html=True)


def section(title: str, hint: str = "") -> None:
    st.markdown(f'<div class="nv-section">{esc(title)}<small>{esc(hint)}</small></div>', unsafe_allow_html=True)


def kpis(cards: list[dict]) -> None:
    """cards: dicts with label, value, icon and optional sub / tone."""
    parts = []
    for c in cards:
        sub = f'<div class="nv-ks">{esc(c["sub"])}</div>' if c.get("sub") else ""
        parts.append(f'<div class="nv-kpi {c.get("tone", "")}"><div class="nv-kl"><span>{esc(c["label"])}</span>'
                     f'<span class="nv-ki">{icon(c["icon"], 18)}</span></div>'
                     f'<div><div class="nv-kv">{esc(c["value"])}</div>{sub}</div></div>')
    st.markdown(f'<div class="nv-kpis">{"".join(parts)}</div>', unsafe_allow_html=True)


def empty(title: str, text: str = "", icon_name: str = "clip") -> None:
    st.markdown(f'<div class="nv-empty"><div class="nv-ei">{icon(icon_name, 22)}</div><b>{esc(title)}</b>{esc(text)}</div>',
                unsafe_allow_html=True)


def info_card(title: str, items: list[tuple[str, str]]) -> None:
    """items: (label, already-safe html value)."""
    cells = "".join(f"<div><span>{esc(k)}</span><b>{v}</b></div>" for k, v in items)
    st.markdown(f'<div class="nv-card"><h4>{esc(title)}</h4><div class="nv-info">{cells}</div></div>', unsafe_allow_html=True)


def html_table(headers: list[str], rows: list[list[str]], empty_title: str = "Nothing to show",
               empty_text: str = "") -> None:
    """Read-only table. Cells must already be safe HTML (use esc / badge)."""
    if not rows:
        empty(empty_title, empty_text)
        return
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    st.markdown(f'<div class="nv-tablewrap"><table class="nv-table"><thead><tr>{head}</tr></thead>'
                f'<tbody>{body}</tbody></table></div>', unsafe_allow_html=True)


def action_table(key: str, headers: list[str], weights: list[float], rows: list[dict],
                 empty_title: str = "Nothing to show", empty_text: str = "", empty_icon: str = "clip"):
    """Table with a working button in the last column of each row.

    rows: dicts with ``id``, ``cells`` (safe HTML, one per header except the
    last), ``action`` (button label or None) and optional ``primary`` /
    ``disabled`` / ``help``. Returns the id of the row whose button was clicked."""
    if not rows:
        empty(empty_title, empty_text, empty_icon)
        return None
    clicked = None
    with st.container(key=f"nvtable_{key}"):
        with st.container(key=f"nvhead_{key}"):
            for col, h in zip(st.columns(weights), headers):
                col.markdown(f'<div class="nv-th">{esc(h)}</div>', unsafe_allow_html=True)
        for r in rows:
            with st.container(key=f"nvrow_{key}_{r['id']}"):
                cols = st.columns(weights, vertical_alignment="center")
                for col, h, cell in zip(cols, headers, r["cells"]):
                    col.markdown(f'<div class="nv-cell"><span class="nv-lbl">{esc(h)}</span>{cell}</div>',
                                 unsafe_allow_html=True)
                if r.get("action"):
                    if cols[-1].button(r["action"], key=f"btn_{key}_{r['id']}", width="stretch",
                                       type="primary" if r.get("primary") else "secondary",
                                       disabled=r.get("disabled", False), help=r.get("help")):
                        clicked = r["id"]
    return clicked


def flash(kind: str, message: str) -> None:
    st.session_state["flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("flash", None)
    if item:
        kind, message = item
        {"success": st.success, "warning": st.warning, "error": st.error, "info": st.info}[kind](message)
        if kind == "success":
            st.toast(message)


def temperature_chart(readings: list[dict], height: int = 300) -> go.Figure:
    """Line chart of readings; fever points are red, non-fever points green."""
    xs = [r["reading_date"] for r in readings]
    ys = [r["temperature_c"] for r in readings]
    fever = [logic.is_fever(y) for y in ys]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#9FB3BA", width=2), hoverinfo="skip", showlegend=False))
    for flag, name, colour, symbol in ((True, "Fever", RED, "diamond"), (False, "No fever", GREEN, "circle")):
        px = [x for x, f in zip(xs, fever) if f == flag]
        py = [y for y, f in zip(ys, fever) if f == flag]
        fig.add_trace(go.Scatter(x=px, y=py, mode="markers", name=name,
                                 marker=dict(color=colour, size=11, symbol=symbol, line=dict(color="#fff", width=1.5)),
                                 hovertemplate="%{x|%d %b %Y}<br>%{y:.1f} °C<extra>" + name + "</extra>"))
    fig.add_hline(y=config.FEVER_THRESHOLD_C, line=dict(color=RED, width=1, dash="dash"),
                  annotation_text=f"Fever threshold {config.FEVER_THRESHOLD_C:.1f} °C",
                  annotation_position="top left", annotation_font=dict(size=11, color=RED))
    lo = min(ys + [36.0]) - 0.4
    hi = max(ys + [config.FEVER_THRESHOLD_C]) + 0.6
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="#fff", font=dict(family="IBM Plex Sans, sans-serif", color=TEXT, size=12),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      xaxis=dict(type="date", tickformat="%d %b", dtick=86400000.0, gridcolor="#EEF2F3"),
                      yaxis=dict(title="°C", range=[lo, hi], gridcolor="#EEF2F3"))
    return fig


def occupancy_donut(occupied: int, available: int, total: int) -> go.Figure:
    fig = go.Figure(go.Pie(values=[occupied, available], labels=["Occupied", "Available"], hole=.68, sort=False,
                           marker=dict(colors=[NAVY, "#BFE0DB"], line=dict(color="#fff", width=2)),
                           textinfo="none", hovertemplate="%{label}: %{value} of " + str(total) + "<extra></extra>"))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="IBM Plex Sans, sans-serif", color=TEXT),
                      legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=.5),
                      annotations=[dict(text=f"<b>{occupied}</b> / {total}<br><span style='font-size:12px'>occupied</span>",
                                        showarrow=False, font=dict(size=24, color=NAVY))])
    return fig


def performance_bar(rate: float | None, benchmark: float) -> go.Figure:
    value = rate or 0
    colour = GREEN if rate is not None and rate >= benchmark else AMBER
    fig = go.Figure(go.Bar(x=[value], y=[""], orientation="h", marker=dict(color=colour), width=.5,
                           hovertemplate="Success rate %{x:.1f}%<extra></extra>"))
    fig.add_vline(x=benchmark, line=dict(color=NAVY, width=2, dash="dash"),
                  annotation_text=f"Benchmark {benchmark:.0f}%", annotation_position="top")
    fig.update_layout(height=130, margin=dict(l=10, r=20, t=30, b=25), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#F1F4F5",
                      font=dict(family="IBM Plex Sans, sans-serif", color=TEXT, size=12),
                      xaxis=dict(range=[0, 100], ticksuffix="%", showgrid=False), yaxis=dict(showticklabels=False))
    return fig


PLOTLY_CONFIG = {"displayModeBar": False}
