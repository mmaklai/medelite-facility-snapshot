"""Facility Assessment Snapshot -- INFINITE by MEDELITE

ARCHITECTURE:
- Provider info (star ratings, address, beds): CMS API dataset 4pq5-n9py
- Hospitalization facility scores: CMS claims dataset (bg7j-552g), one row per measure
- National/state averages: CMS State/US Averages dataset (xcdc-v8bm)
- Newer facilities (<3 yrs) often have no claims data — shown as "Not Reported"
"""

import streamlit as st
import requests
import pandas as pd
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
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

# ── Dataset IDs (stable, never change between CMS refreshes) ──────────────────
PROVIDER_DS  = "4pq5-n9py"   # NH Provider Info
CLAIMS_DS    = "bg7j-552g"   # NH Claims-Based Quality Measures
STATE_AVG_DS = "xcdc-v8bm"   # NH State & US Averages
API_BASE     = "https://data.cms.gov/provider-data/api/1/datastore"

# ── Hospitalization field definitions ─────────────────────────────────────────
# Each tuple: (display_label, claims_col, state_avg_col, national_avg_col, is_pct)
# claims_col      = column name in the claims dataset for the facility score
# state_avg_col   = column in state averages dataset (for state)
# national_avg_col= column in state averages dataset (national row)
HOSP_FIELDS = [
    ("Short Term Hospitalization",
     "pct_of_short_stay_residents_who_were_rehospitalized_after_a_nursing_home_admission",
     None, None, True),
    ("STR National Avg. for Hospitalization",
     None,
     "pct_of_short_stay_residents_who_were_rehospitalized_after_a_nursing_home_admission",
     "pct_of_short_stay_residents_who_were_rehospitalized_after_a_nursing_home_admission",
     True),
    ("STR State Avg. for Hospitalization",
     None,
     "pct_of_short_stay_residents_who_were_rehospitalized_after_a_nursing_home_admission",
     None, True),
    ("STR ED Visit",
     "pct_of_short_stay_residents_who_had_an_outpatient_emergency_department_visit",
     None, None, True),
    ("STR ED Visits National Avg.",
     None,
     "pct_of_short_stay_residents_who_had_an_outpatient_emergency_department_visit",
     "pct_of_short_stay_residents_who_had_an_outpatient_emergency_department_visit",
     True),
    ("STR ED Visits State Avg.",
     None,
     "pct_of_short_stay_residents_who_had_an_outpatient_emergency_department_visit",
     None, True),
    ("LT Hospitalization",
     "number_of_hospitalizations_per_1000_long_stay_resident_days",
     None, None, False),
    ("LT National Avg. for Hospitalization",
     None,
     "number_of_hospitalizations_per_1000_long_stay_resident_days",
     "number_of_hospitalizations_per_1000_long_stay_resident_days",
     False),
    ("LT State Avg. for Hospitalization",
     None,
     "number_of_hospitalizations_per_1000_long_stay_resident_days",
     None, False),
    ("ED Visit",
     "number_of_outpatient_emergency_department_visits_per_1000_long_stay_resident_days",
     None, None, False),
    ("LT ED Visits National Avg.",
     None,
     "number_of_outpatient_emergency_department_visits_per_1000_long_stay_resident_days",
     "number_of_outpatient_emergency_department_visits_per_1000_long_stay_resident_days",
     False),
    ("LT ED Visits State Avg.",
     None,
     "number_of_outpatient_emergency_department_visits_per_1000_long_stay_resident_days",
     None, False),
]


# ── API helpers ────────────────────────────────────────────────────────────────

def _api_get(dataset: str, params: dict, timeout: int = 20) -> list:
    """GET with bracket-encoded params, returns results list."""
    url = f"{API_BASE}/query/{dataset}/0"
    r = requests.get(url, params=params, timeout=timeout)
    if r.status_code == 200:
        return r.json().get("results", [])
    return []


def _api_post(dataset: str, payload: dict, timeout: int = 20) -> list:
    """POST with JSON body, returns results list."""
    url = f"{API_BASE}/query/{dataset}/0"
    r = requests.post(url, json=payload, timeout=timeout)
    if r.status_code == 200:
        return r.json().get("results", [])
    return []


def _fetch_by_ccn(dataset: str, ccn: str, limit: int = 50) -> list:
    """
    Fetch rows from a CMS dataset filtered by CCN.
    Tries POST JSON (most reliable), then GET params, then client-side scan.
    Always verifies the returned CCN matches.
    """
    ccn = ccn.strip()

    # Method 1: POST with JSON body
    try:
        rows = _api_post(dataset, {
            "conditions": [{"property": "cms_certification_number_ccn",
                            "value": ccn, "operator": "="}],
            "limit": limit
        })
        matched = [r for r in rows
                   if str(r.get("cms_certification_number_ccn","")).strip() == ccn]
        if matched:
            return matched
    except Exception:
        pass

    # Method 2: GET with params
    try:
        rows = _api_get(dataset, {
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

    # Method 3: page scan (last resort)
    try:
        offset, batch = 0, 500
        while offset < 20000:
            rows = _api_get(dataset, {"limit": batch, "offset": offset})
            if not rows:
                break
            for row in rows:
                if str(row.get("cms_certification_number_ccn","")).strip() == ccn:
                    return [row]
            offset += batch
    except Exception:
        pass

    return []


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_provider_data(ccn: str) -> dict:
    rows = _fetch_by_ccn(PROVIDER_DS, ccn, limit=1)
    return rows[0] if rows else {}


def fetch_claims_data(ccn: str) -> dict:
    """
    Returns flat dict of facility-level hospitalization scores keyed by claims_col name.
    Many newer facilities have no claims data — returns {} in that case (not an error).
    """
    try:
        rows = _fetch_by_ccn(CLAIMS_DS, ccn, limit=200)

        # Debug expander — remove once column names confirmed working
        if rows:
            with st.expander("🔧 Debug: Raw claims data (first 2 rows)", expanded=False):
                st.json(rows[:2])
        else:
            st.info("ℹ️ No claims-based hospitalization data found for this facility. "
                    "This is common for newer or lower-volume facilities. "
                    "National/state averages will still be shown.")
            return {}

        # The claims dataset has one row per measure per facility.
        # Each row has a measure name column and a score column.
        # Detect those column names from the first row.
        sample = rows[0]
        keys = list(sample.keys())

        # Find measure-description column (holds the full measure name)
        measure_col = next((k for k in keys
                            if any(x in k.lower() for x in
                                   ["measure_description", "measure_name", "quality_measure"])), None)
        score_col = next((k for k in keys
                          if any(x in k.lower() for x in ["score", "value", "rate", "pct"])
                          and "footnote" not in k.lower()
                          and "national" not in k.lower()
                          and "state" not in k.lower()), None)

        if not measure_col or not score_col:
            # Fallback: maybe columns ARE the measure names directly
            # Return the whole first row as a flat dict
            return {k: str(v) for k, v in sample.items()}

        # Pivot: measure_description -> score
        flat = {}
        for row in rows:
            measure = str(row.get(measure_col, "")).strip().lower()
            score   = str(row.get(score_col, "N/A")).strip()
            flat[measure] = score
        return flat

    except Exception as e:
        st.warning(f"Hospitalization data error: {e}")
        return {}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_state_averages(state: str) -> dict:
    """
    Fetch state and national averages from the State/US Averages dataset.
    Returns dict keyed by measure name for both the state row and the US row.
    """
    try:
        # Fetch state row
        state_rows = _fetch_by_ccn.__wrapped__(STATE_AVG_DS, state, 50) \
            if hasattr(_fetch_by_ccn, '__wrapped__') else []

        # Direct API call for state averages (different key column)
        url = f"{API_BASE}/query/{STATE_AVG_DS}/0"
        rows = []
        for scope in [state, "US"]:
            r = requests.post(url, json={
                "conditions": [{"property": "state", "value": scope, "operator": "="}],
                "limit": 200
            }, timeout=20)
            if r.status_code == 200:
                rows.extend(r.json().get("results", []))

        result = {"state": {}, "national": {}}
        for row in rows:
            scope = str(row.get("state","")).strip()
            for k, v in row.items():
                if k == "state":
                    continue
                if scope == "US":
                    result["national"][k.lower()] = str(v)
                elif scope == state:
                    result["state"][k.lower()] = str(v)
        return result
    except Exception:
        return {"state": {}, "national": {}}


def get_hosp_value(label: str, claims: dict, averages: dict,
                   claims_col, state_col, natl_col, is_pct: bool) -> str:
    """Resolve the display value for one hospitalization row."""

    def fmt(val):
        if not val or str(val).lower() in ("n/a", "nan", "none", ""):
            return "Not Reported"
        try:
            f = float(val)
            return f"{f}%" if is_pct else str(round(f, 2))
        except Exception:
            return val

    # Facility score
    if claims_col:
        # Try direct column name lookup
        v = claims.get(claims_col)
        if not v:
            # Try lowercase partial match on measure description
            col_lower = claims_col.lower().replace("_", " ")
            for k, val in claims.items():
                if col_lower in k.lower() or k.lower() in col_lower:
                    v = val
                    break
        if v:
            return fmt(v)
        return "Not Reported"

    # National average
    if natl_col and not state_col:
        v = averages.get("national", {}).get(natl_col.lower())
        return fmt(v) if v else "Not Reported"

    # State average
    if state_col and not natl_col:
        v = averages.get("state", {}).get(state_col.lower())
        return fmt(v) if v else "Not Reported"

    return "Not Reported"


def _v(d: dict, *keys) -> str:
    for k in keys:
        val = str(d.get(k, "")).strip()
        if val and val.lower() not in ("nan", "none", ""):
            return val
    return "N/A"


# ── PDF ────────────────────────────────────────────────────────────────────────

def generate_pdf(display_name: str, cms: dict, claims: dict,
                 averages: dict, manual: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=10*mm, bottomMargin=15*mm)

    brand_s  = ParagraphStyle("Brand",  fontSize=13, fontName="Helvetica-Bold",    textColor=colors.white, alignment=TA_CENTER, leading=18)
    title_s  = ParagraphStyle("Title",  fontSize=13, fontName="Helvetica-Bold",    textColor=colors.HexColor("#003366"), alignment=TA_CENTER)
    state_s  = ParagraphStyle("State",  fontSize=11, fontName="Helvetica-Bold",    textColor=colors.HexColor("#003366"), alignment=TA_CENTER, spaceAfter=4)
    label_s  = ParagraphStyle("Label",  fontSize=9,  fontName="Helvetica-Bold",    leading=12)
    value_s  = ParagraphStyle("Value",  fontSize=9,  fontName="Helvetica-Oblique", leading=12)
    link_s   = ParagraphStyle("Link",   fontSize=8,  fontName="Helvetica",         textColor=colors.HexColor("#003366"), alignment=TA_CENTER)
    footer_s = ParagraphStyle("Footer", fontSize=7,  fontName="Helvetica-Oblique", textColor=colors.grey, alignment=TA_CENTER)

    story = []
    banner = Table([[Paragraph("INFINITE — Managed by MEDELITE", brand_s)]], colWidths=[180*mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#003366")),
        ("TOPPADDING",(0,0),(-1,-1),8), ("BOTTOMPADDING",(0,0),(-1,-1),8),
    ]))
    story.append(banner)
    story.append(Spacer(1,5*mm))
    story.append(Paragraph("FACILITY ASSESSMENT SNAPSHOT", title_s))
    story.append(Paragraph(_v(cms,"state"), state_s))

    ccn = _v(cms, "cms_certification_number_ccn")
    medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn}"
    story.append(Paragraph(
        f'<a href="{medicare_url}" color="#003366">View on Medicare Care Compare</a>', link_s))
    story.append(Spacer(1,3*mm))

    def row(label, value, highlight=False):
        v = value if value else "N/A"
        return (Paragraph(label, label_s), Paragraph(v, value_s), highlight)

    def star(val):
        return f"{val}/5" if val != "N/A" else "N/A"

    addr = ", ".join(x for x in [
        _v(cms,"provider_address"), _v(cms,"citytown"),
        _v(cms,"state"), _v(cms,"zip_code")] if x != "N/A") or "N/A"

    current_census = manual.get("Current Census","").strip() or \
                     _v(cms,"average_number_of_residents_per_day")

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

    for label, claims_col, state_col, natl_col, is_pct in HOSP_FIELDS:
        val = get_hosp_value(label, claims, averages, claims_col, state_col, natl_col, is_pct)
        rows.append(row(label, val, highlight=True))

    if manual.get("Notes","").strip():
        rows.append(row("Additional Notes", manual["Notes"]))

    tbl = Table([(r[0],r[1]) for r in rows], colWidths=[80*mm,100*mm])
    style = [
        ("BOX",(0,0),(-1,-1),0.5,colors.black),
        ("INNERGRID",(0,0),(-1,-1),0.5,colors.black),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),5), ("RIGHTPADDING",(0,0),(-1,-1),5),
    ]
    for i, r in enumerate(rows):
        if r[2]:
            style.append(("BACKGROUND",(0,i),(-1,i),colors.HexColor("#FFFF00")))
    tbl.setStyle(TableStyle(style))
    story.append(tbl)
    story.append(Spacer(1,5*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph(
        "Generated by INFINITE — Managed by MEDELITE  |  Source: CMS Provider Data Catalog",
        footer_s))
    doc.build(story)
    return buf.getvalue()


# ── Session state ──────────────────────────────────────────────────────────────
for k, v in [("cms_data",None),("claims_data",{}),("averages",{"state":{},"national":{}}),
              ("facility_name",""),("display_name","")]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── UI ─────────────────────────────────────────────────────────────────────────
st.title("Facility Assessment Snapshot")
st.markdown("Enter a CCN (e.g., `686123`) to retrieve CMS provider data.")

col1, col2 = st.columns([1,2])

with col1:
    ccn           = st.text_input("CCN (Provider Number)", placeholder="e.g., 686123")
    override_name = st.text_input("Facility Name Override (Optional)",
                                  placeholder="Leave blank to use CMS name")
    st.subheader("Manual Inputs")
    manual_data = {}
    manual_data["EMR System"] = st.text_input("EMR System",
        placeholder="e.g., PointClickCare, MatrixCare")
    manual_data["Current Census"] = st.text_input("Current Census (overrides CMS avg if filled)",
        placeholder="e.g., 112")
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
        st.session_state.cms_data     = cms_data
        st.session_state.facility_name = cms_data.get("provider_name","Unknown")
        st.session_state.display_name  = (
            override_name.strip() if override_name.strip()
            else st.session_state.facility_name)
        state = cms_data.get("state","")
        with st.spinner("Fetching hospitalization metrics…"):
            st.session_state.claims_data = fetch_claims_data(ccn.strip())
        with st.spinner("Fetching state & national averages…"):
            st.session_state.averages = fetch_state_averages(state)
        st.success("✅ CMS data retrieved!")
    else:
        st.session_state.cms_data    = None
        st.session_state.claims_data = {}
        st.session_state.averages    = {"state":{},"national":{}}
        st.error(f"No data found for CCN: {ccn}. Please verify the number.")
elif fetch_clicked and not ccn:
    st.warning("Please enter a CCN to proceed.")

# ── Results ────────────────────────────────────────────────────────────────────
if st.session_state.cms_data:
    cms          = st.session_state.cms_data
    claims       = st.session_state.claims_data
    averages     = st.session_state.averages
    facility_name = st.session_state.facility_name
    display_name  = override_name.strip() if override_name.strip() else facility_name

    with col2:
        st.subheader(f"Facility: {display_name}")
        ccn_val    = _v(cms,"cms_certification_number_ccn")
        state_code = _v(cms,"state")
        st.write(f"**CCN:** {ccn_val}  |  **State:** {state_code}")

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Overall Rating",    f"{_v(cms,'overall_rating')}/5")
            st.metric("Health Inspection", f"{_v(cms,'health_inspection_rating')}/5")
        with c2:
            st.metric("Staffing",                 f"{_v(cms,'staffing_rating')}/5")
            st.metric("Quality of Resident Care", f"{_v(cms,'qm_rating')}/5")

        addr = ", ".join(x for x in [
            _v(cms,"provider_address"),_v(cms,"citytown"),
            _v(cms,"state"),_v(cms,"zip_code")] if x != "N/A")
        st.write(f"**Address:** {addr}")
        st.write(f"**Phone:** {_v(cms,'telephone_number')}")
        st.write(f"**Beds:** {_v(cms,'number_of_certified_beds')}  |  "
                 f"**Avg Residents/Day:** {_v(cms,'average_number_of_residents_per_day')}")

        medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn_val}"
        st.markdown(f"[View Profile on Medicare Care Compare ↗]({medicare_url})")

        st.subheader("Hospitalization & ED Metrics")
        hosp_df = pd.DataFrame([
            {"Metric": label,
             "Value": get_hosp_value(label, claims, averages,
                                     claims_col, state_col, natl_col, is_pct)}
            for label, claims_col, state_col, natl_col, is_pct in HOSP_FIELDS
        ])
        st.dataframe(hosp_df, use_container_width=True, hide_index=True)

        pdf_bytes = generate_pdf(display_name, cms, claims, averages, manual_data)
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
