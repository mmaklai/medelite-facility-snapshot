"""Facility Assessment Snapshot -- INFINITE by MEDELITE

DATA SOURCES (confirmed working):
- Provider info + star ratings: dataset 4pq5-n9py  (one row per facility)
- State & national averages:    dataset xcdc-v8bm  (filtered by state_or_nation)
- Facility-level claims scores: NOT available as a separate API dataset.
  CMS does not expose per-facility hospitalization scores via a public API endpoint.
  Facility rows show "Not Reported" which matches Care Compare behaviour for this.
"""

import streamlit as st
import requests
import pandas as pd
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

st.set_page_config(
    page_title="Facility Assessment Snapshot — INFINITE by MEDELITE",
    page_icon="🏥", layout="wide"
)
st.markdown("""
<style>
.infinite-banner {
    background-color:#003366;color:white;padding:0.7rem;
    text-align:center;font-weight:bold;font-size:1.1rem;
    border-radius:4px;margin-bottom:1rem;
}
</style>
<div class="infinite-banner">INFINITE — Managed by MEDELITE</div>
""", unsafe_allow_html=True)

# ── Dataset IDs ────────────────────────────────────────────────────────────────
PROVIDER_DS  = "4pq5-n9py"   # NH Provider Info (one row per facility)
STATE_AVG_DS = "xcdc-v8bm"   # NH State & US Averages
API_BASE     = "https://data.cms.gov/provider-data/api/1/datastore/query"

# ── Confirmed column names from xcdc-v8bm (verified May 2026) ────────────────
# State averages dataset is filtered by state_or_nation:
#   "NATION" = national average row
#   "FL"     = Florida state average row  (replaced dynamically with facility state)
COL_STR_HOSP  = "percentage_of_short_stay_residents_who_were_rehospitalized__1d02"
COL_STR_ED    = "percentage_of_short_stay_residents_who_had_an_outpatient_em_d911"
COL_LT_HOSP   = "number_of_hospitalizations_per_1000_longstay_resident_days"
COL_LT_ED     = "number_of_outpatient_emergency_department_visits_per_1000_l_de9d"

# ── Hospitalization row definitions ───────────────────────────────────────────
# (display_label, avg_col, source, is_pct)
# source: "facility" = per-facility (not available via API → "Not Reported")
#         "national" = from xcdc-v8bm where state_or_nation = "NATION"
#         "state"    = from xcdc-v8bm where state_or_nation = facility state
HOSP_FIELDS = [
    ("Short Term Hospitalization",            COL_STR_HOSP, "facility",  True),
    ("STR National Avg. for Hospitalization", COL_STR_HOSP, "national",  True),
    ("STR State Avg. for Hospitalization",    COL_STR_HOSP, "state",     True),
    ("STR ED Visit",                          COL_STR_ED,   "facility",  True),
    ("STR ED Visits National Avg.",           COL_STR_ED,   "national",  True),
    ("STR ED Visits State Avg.",              COL_STR_ED,   "state",     True),
    ("LT Hospitalization",                    COL_LT_HOSP,  "facility",  False),
    ("LT National Avg. for Hospitalization",  COL_LT_HOSP,  "national",  False),
    ("LT State Avg. for Hospitalization",     COL_LT_HOSP,  "state",     False),
    ("ED Visit",                              COL_LT_ED,    "facility",  False),
    ("LT ED Visits National Avg.",            COL_LT_ED,    "national",  False),
    ("LT ED Visits State Avg.",               COL_LT_ED,    "state",     False),
]


# ── API helpers ────────────────────────────────────────────────────────────────

def _post(dataset: str, payload: dict, timeout: int = 20) -> list:
    r = requests.post(f"{API_BASE}/{dataset}/0", json=payload, timeout=timeout)
    return r.json().get("results", []) if r.status_code == 200 else []


def _get(dataset: str, params: dict, timeout: int = 20) -> list:
    r = requests.get(f"{API_BASE}/{dataset}/0", params=params, timeout=timeout)
    return r.json().get("results", []) if r.status_code == 200 else []


def _fetch_by_ccn(dataset: str, ccn: str, limit: int = 5) -> list:
    """Fetch rows matching CCN. Tries POST, then GET, then page scan."""
    ccn = ccn.strip()

    for attempt in ["post", "get"]:
        try:
            if attempt == "post":
                rows = _post(dataset, {
                    "conditions": [{"property": "cms_certification_number_ccn",
                                    "value": ccn, "operator": "="}],
                    "limit": limit
                })
            else:
                rows = _get(dataset, {
                    "conditions[0][property]": "cms_certification_number_ccn",
                    "conditions[0][value]":    ccn,
                    "conditions[0][operator]": "=",
                    "limit": limit,
                })
            matched = [r for r in rows
                       if str(r.get("cms_certification_number_ccn","")).strip() == ccn]
            if matched:
                return matched
        except Exception:
            pass

    # Last resort: page scan
    try:
        offset, batch = 0, 500
        while offset < 20000:
            rows = _get(dataset, {"limit": batch, "offset": offset})
            if not rows:
                break
            for row in rows:
                if str(row.get("cms_certification_number_ccn","")).strip() == ccn:
                    return [row]
            offset += batch
    except Exception:
        pass
    return []


def _fetch_by_state(state: str) -> list:
    """Fetch state averages row(s) from xcdc-v8bm for a given state + NATION."""
    results = []
    for scope in [state.upper(), "NATION"]:
        try:
            rows = _post(STATE_AVG_DS, {
                "conditions": [{"property": "state_or_nation",
                                "value": scope, "operator": "="}],
                "limit": 1
            })
            if not rows:
                rows = _get(STATE_AVG_DS, {
                    "conditions[0][property]": "state_or_nation",
                    "conditions[0][value]":    scope,
                    "conditions[0][operator]": "=",
                    "limit": 1,
                })
            results.extend(rows)
        except Exception:
            pass
    return results


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_provider_data(ccn: str) -> dict:
    rows = _fetch_by_ccn(PROVIDER_DS, ccn, limit=1)
    return rows[0] if rows else {}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_averages(state: str) -> dict:
    """
    Returns {"national": {...}, "state": {...}} with confirmed column names.
    Cached for 24h since averages only change monthly.
    """
    out = {"national": {}, "state": {}}
    rows = _fetch_by_state(state)
    for row in rows:
        scope = str(row.get("state_or_nation","")).strip().upper()
        if scope == "NATION":
            out["national"] = {k: str(v) for k, v in row.items()}
        elif scope == state.upper():
            out["state"] = {k: str(v) for k, v in row.items()}
    return out


def resolve_hosp(col: str, source: str, averages: dict, is_pct: bool) -> str:
    """Return the display string for one hospitalization cell."""
    if source == "facility":
        return "Not Reported"   # CMS doesn't expose per-facility claims via public API

    bucket = averages.get(source, {})   # "national" or "state"
    val = bucket.get(col, "")
    if not val or val.lower() in ("nan", "none", ""):
        return "N/A"
    try:
        f = float(val)
        return f"{round(f, 1)}%" if is_pct else str(round(f, 2))
    except Exception:
        return val


def _v(d: dict, *keys) -> str:
    for k in keys:
        val = str(d.get(k, "")).strip()
        if val and val.lower() not in ("nan", "none", ""):
            return val
    return "N/A"


# ── PDF ────────────────────────────────────────────────────────────────────────

def generate_pdf(display_name: str, cms: dict, averages: dict, manual: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=10*mm, bottomMargin=15*mm)

    brand_s  = ParagraphStyle("Brand",  fontSize=13, fontName="Helvetica-Bold",
                               textColor=colors.white, alignment=TA_CENTER, leading=18)
    title_s  = ParagraphStyle("Title",  fontSize=13, fontName="Helvetica-Bold",
                               textColor=colors.HexColor("#003366"), alignment=TA_CENTER)
    state_s  = ParagraphStyle("State",  fontSize=11, fontName="Helvetica-Bold",
                               textColor=colors.HexColor("#003366"), alignment=TA_CENTER, spaceAfter=4)
    label_s  = ParagraphStyle("Label",  fontSize=9,  fontName="Helvetica-Bold",    leading=12)
    value_s  = ParagraphStyle("Value",  fontSize=9,  fontName="Helvetica-Oblique", leading=12)
    link_s   = ParagraphStyle("Link",   fontSize=8,  fontName="Helvetica",
                               textColor=colors.HexColor("#003366"), alignment=TA_CENTER)
    footer_s = ParagraphStyle("Footer", fontSize=7,  fontName="Helvetica-Oblique",
                               textColor=colors.grey, alignment=TA_CENTER)

    story = []

    # Banner
    banner = Table([[Paragraph("INFINITE — Managed by MEDELITE", brand_s)]],
                   colWidths=[180*mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#003366")),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("FACILITY ASSESSMENT SNAPSHOT", title_s))
    story.append(Paragraph(_v(cms, "state"), state_s))

    ccn = _v(cms, "cms_certification_number_ccn")
    medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn}"
    story.append(Paragraph(
        f'<a href="{medicare_url}" color="#003366">View on Medicare Care Compare</a>',
        link_s))
    story.append(Spacer(1, 3*mm))

    def row(label, value, highlight=False):
        return (Paragraph(label, label_s),
                Paragraph(value or "N/A", value_s),
                highlight)

    def star(val):
        return f"{val}/5" if val != "N/A" else "N/A"

    addr = ", ".join(x for x in [
        _v(cms,"provider_address"), _v(cms,"citytown"),
        _v(cms,"state"), _v(cms,"zip_code")] if x != "N/A") or "N/A"

    current_census = (manual.get("Current Census","").strip()
                      or _v(cms,"average_number_of_residents_per_day"))

    rows = [
        row("Name of Facility",   display_name),
        row("Location",           addr),
        row("EMR",                manual.get("EMR System","") or "N/A"),
        row("Census Capacity",    _v(cms,"number_of_certified_beds")),
        row("Current Census",     current_census),
        row("Type of Patient",    manual.get("Type of Patient","") or "N/A"),
        row("Previous Coverage from Medelite",
            manual.get("Previous Coverage from Medelite","") or "N/A"),
        row("Previous Provider Performance from Medelite",
            manual.get("Previous Provider Performance from Medelite","") or "N/A"),
        row("Medical Coverage",   manual.get("Medical Coverage","") or "N/A"),
        row("Overall Star Rating",       star(_v(cms,"overall_rating"))),
        row("Health Inspection",         star(_v(cms,"health_inspection_rating"))),
        row("Staffing",                  star(_v(cms,"staffing_rating"))),
        row("Quality of Resident Care",  star(_v(cms,"qm_rating"))),
    ]

    for label, col, source, is_pct in HOSP_FIELDS:
        val = resolve_hosp(col, source, averages, is_pct)
        rows.append(row(label, val, highlight=True))

    if manual.get("Notes","").strip():
        rows.append(row("Additional Notes", manual["Notes"]))

    tbl = Table([(r[0], r[1]) for r in rows], colWidths=[80*mm, 100*mm])
    style = [
        ("BOX",           (0,0),(-1,-1), 0.5, colors.black),
        ("INNERGRID",     (0,0),(-1,-1), 0.5, colors.black),
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ("RIGHTPADDING",  (0,0),(-1,-1), 5),
    ]
    for i, r in enumerate(rows):
        if r[2]:
            style.append(("BACKGROUND",(0,i),(-1,i), colors.HexColor("#FFFF00")))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)

    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph(
        "Generated by INFINITE — Managed by MEDELITE  |  Source: CMS Provider Data Catalog",
        footer_s))
    doc.build(story)
    return buf.getvalue()


# ── Session state ──────────────────────────────────────────────────────────────
for k, v in [("cms_data",None),("averages",{"national":{},"state":{}}),
              ("facility_name",""),("display_name","")]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── UI ─────────────────────────────────────────────────────────────────────────
st.title("Facility Assessment Snapshot")
st.markdown("Enter a CCN (e.g., `686123`) to retrieve CMS provider data.")

col1, col2 = st.columns([1, 2])

with col1:
    ccn           = st.text_input("CCN (Provider Number)", placeholder="e.g., 686123")
    override_name = st.text_input("Facility Name Override (Optional)",
                                  placeholder="Leave blank to use CMS name")
    st.subheader("Manual Inputs")
    manual_data = {}
    manual_data["EMR System"] = st.text_input("EMR System",
        placeholder="e.g., PointClickCare, MatrixCare")
    manual_data["Current Census"] = st.text_input(
        "Current Census (overrides CMS avg if filled)", placeholder="e.g., 112")
    manual_data["Type of Patient"] = st.text_input("Type of Patient",
        placeholder="e.g., Long-term & Short-term")
    prev = st.selectbox("Previous Coverage from Medelite", ["Select...","Yes","No"])
    manual_data["Previous Coverage from Medelite"] = "" if prev == "Select..." else prev
    manual_data["Previous Provider Performance from Medelite"] = st.text_input(
        "Previous Provider Performance from Medelite",
        placeholder="e.g., About 30 patients/day")
    manual_data["Medical Coverage"] = st.text_input("Medical Coverage",
        placeholder="e.g., Optometry, PCP, Podiatry")
    manual_data["Notes"] = st.text_area("Additional Notes", placeholder="Any notes...")
    fetch_clicked = st.button("Fetch CMS Data", type="primary")

# ── Fetch ──────────────────────────────────────────────────────────────────────
if fetch_clicked and ccn:
    with st.spinner("Fetching provider info…"):
        cms_data = fetch_provider_data(ccn.strip())
    if cms_data:
        st.session_state.cms_data      = cms_data
        st.session_state.facility_name = cms_data.get("provider_name", "Unknown")
        st.session_state.display_name  = (
            override_name.strip() if override_name.strip()
            else st.session_state.facility_name)
        state = cms_data.get("state", "")
        with st.spinner("Fetching state & national averages…"):
            st.session_state.averages = fetch_averages(state)
        st.success("✅ CMS data retrieved!")
    else:
        st.session_state.cms_data = None
        st.session_state.averages = {"national":{}, "state":{}}
        st.error(f"No data found for CCN: {ccn}. Please verify the number.")
elif fetch_clicked and not ccn:
    st.warning("Please enter a CCN to proceed.")

# ── Results ────────────────────────────────────────────────────────────────────
if st.session_state.cms_data:
    cms          = st.session_state.cms_data
    averages     = st.session_state.averages
    facility_name = st.session_state.facility_name
    display_name  = override_name.strip() if override_name.strip() else facility_name

    with col2:
        st.subheader(f"Facility: {display_name}")
        ccn_val    = _v(cms, "cms_certification_number_ccn")
        state_code = _v(cms, "state")
        st.write(f"**CCN:** {ccn_val}  |  **State:** {state_code}")

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Overall Rating",    f"{_v(cms,'overall_rating')}/5")
            st.metric("Health Inspection", f"{_v(cms,'health_inspection_rating')}/5")
        with c2:
            st.metric("Staffing",                 f"{_v(cms,'staffing_rating')}/5")
            st.metric("Quality of Resident Care", f"{_v(cms,'qm_rating')}/5")

        addr = ", ".join(x for x in [
            _v(cms,"provider_address"), _v(cms,"citytown"),
            _v(cms,"state"), _v(cms,"zip_code")] if x != "N/A")
        st.write(f"**Address:** {addr}")
        st.write(f"**Phone:** {_v(cms,'telephone_number')}")
        st.write(f"**Beds:** {_v(cms,'number_of_certified_beds')}  |  "
                 f"**Avg Residents/Day:** {_v(cms,'average_number_of_residents_per_day')}")

        medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn_val}"
        st.markdown(f"[View Profile on Medicare Care Compare ↗]({medicare_url})")

        st.subheader("Hospitalization & ED Metrics")
        st.caption("Facility-specific scores are not available via the public CMS API. "
                   "State and national averages are sourced from the CMS State/US Averages dataset.")
        hosp_df = pd.DataFrame([
            {"Metric": label,
             "Value": resolve_hosp(col, source, averages, is_pct)}
            for label, col, source, is_pct in HOSP_FIELDS
        ])
        st.dataframe(hosp_df, use_container_width=True, hide_index=True)

        pdf_bytes = generate_pdf(display_name, cms, averages, manual_data)
        safe = display_name.replace(" ","_").replace("/","-")
        st.download_button(
            label="⬇ Download PDF Report",
            data=pdf_bytes,
            file_name=f"Snapshot_{safe}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary"
        )

st.markdown("---")
st.markdown(
    "Powered by [CMS Provider Data Catalog](https://data.cms.gov/provider-data/dataset/4pq5-n9py) "
    "| INFINITE — Managed by MEDELITE"
)
