"""Facility Assessment Snapshot -- INFINITE by MEDELITE

DATA SOURCE: CMS Provider Data Catalog API (4pq5-n9py)
- Uses the live API instead of CSV download (CSV returns 403 from Streamlit Cloud)
- API endpoint: https://data.cms.gov/provider-data/api/1/datastore/query/4pq5-n9py/0
- Claims/hospitalization metrics: second API call to bg7j-552g dataset
"""

import streamlit as st
import requests
import pandas as pd
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Facility Assessment Snapshot — INFINITE by MEDELITE",
    page_icon="🏥",
    layout="wide"
)

st.markdown(
    """
    <style>
    .infinite-banner {
        background-color: #003366;
        color: white;
        padding: 0.7rem;
        text-align: center;
        font-weight: bold;
        font-size: 1.1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    </style>
    <div class="infinite-banner">INFINITE — Managed by MEDELITE</div>
    """,
    unsafe_allow_html=True
)

# ── CMS API endpoints ──────────────────────────────────────────────────────────
CMS_API_BASE    = "https://data.cms.gov/provider-data/api/1/datastore/query"
PROVIDER_DS     = "4pq5-n9py"   # Nursing Home Provider Info
CLAIMS_DS       = "bg7j-552g"   # Claims-based quality measures (hosp/ED metrics)

# ── Hospitalization metric definitions ─────────────────────────────────────────
# (display label, CMS API measure_code, is_percentage)
# Measure codes from NH_Data_Dictionary claims-based section
HOSP_FIELDS = [
    ("Short Term Hospitalization",            "SNF_RSRV_HOSP_RATE",  True),
    ("STR National Avg. for Hospitalization", "SNF_EXP_HOSP_NATL",   True),
    ("STR State Avg. for Hospitalization",    "SNF_EXP_HOSP_STATE",  True),
    ("STR ED Visit",                          "SNF_RSRV_ER_RATE",    True),
    ("STR ED Visits National Avg.",           "SNF_EXP_ER_NATL",     True),
    ("STR ED Visits State Avg.",              "SNF_EXP_ER_STATE",    True),
    ("LT Hospitalization",                    "LNG_RSRV_HOSP_RATE",  False),
    ("LT National Avg. for Hospitalization",  "LNG_EXP_HOSP_NATL",   False),
    ("LT State Avg. for Hospitalization",     "LNG_EXP_HOSP_STATE",  False),
    ("ED Visit",                              "LNG_RSRV_ER_RATE",    False),
    ("LT ED Visits National Avg.",            "LNG_EXP_ER_NATL",     False),
    ("LT ED Visits State Avg.",               "LNG_EXP_ER_STATE",    False),
]


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_provider_data(ccn: str) -> dict:
    """
    Fetch provider info from CMS API by CCN.
    Uses conditions filter so only one matching row is returned.
    """
    try:
        url = f"{CMS_API_BASE}/{PROVIDER_DS}/0"
        params = {
            "conditions[0][property]": "cms_certification_number_ccn",
            "conditions[0][value]":    ccn.strip(),
            "conditions[0][operator]": "=",
            "limit": 1,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        if results:
            return results[0]
        return {}
    except Exception as e:
        st.error(f"CMS API error: {e}")
        return {}


def fetch_claims_data(ccn: str) -> dict:
    """
    Fetch hospitalization/ED metrics from the CMS claims-based quality measures API.
    Returns a flat dict {internal_code: value_string}.

    The claims dataset has one row per measure per facility.
    We fetch all rows for this CCN, then pivot by measure code.
    """
    try:
        url = f"{CMS_API_BASE}/{CLAIMS_DS}/0"
        params = {
            "conditions[0][property]": "cms_certification_number_ccn",
            "conditions[0][value]":    ccn.strip(),
            "conditions[0][operator]": "=",
            "limit": 100,
        }
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        rows = r.json().get("results", [])
        if not rows:
            return {}

        # Find the measure-code column name from first row keys
        sample_keys = list(rows[0].keys())
        measure_col = next(
            (k for k in sample_keys if "measure_code" in k.lower()), None
        )
        score_col = next(
            (k for k in sample_keys
             if any(x in k.lower() for x in ["score", "observed", "rate"])
             and "national" not in k.lower() and "state" not in k.lower()
             and "footnote" not in k.lower()),
            None
        )
        natl_col = next(
            (k for k in sample_keys
             if "national" in k.lower()
             and any(x in k.lower() for x in ["avg", "average", "rate", "score"])
             and "footnote" not in k.lower()),
            None
        )
        state_col = next(
            (k for k in sample_keys
             if "state" in k.lower()
             and any(x in k.lower() for x in ["avg", "average", "rate", "score"])
             and "footnote" not in k.lower()),
            None
        )

        # Build pivot: cms_measure_code -> {score, national, state}
        measures: dict[str, dict] = {}
        for row in rows:
            code = str(row.get(measure_col, "")).strip().upper() if measure_col else ""
            measures[code] = {
                "score":    str(row.get(score_col, "N/A")).strip() if score_col else "N/A",
                "national": str(row.get(natl_col, "N/A")).strip() if natl_col else "N/A",
                "state":    str(row.get(state_col, "N/A")).strip() if state_col else "N/A",
            }

        # Map CMS measure codes → our internal HOSP_FIELDS keys
        # CMS short-stay codes: Q611 (observed hosp), Q621 (observed ED)
        # CMS long-stay codes:  Q631 (observed hosp), Q641 (observed ED)
        # National/state averages come as sub-fields on the same row
        CMS_MAP = {
            "Q611": ("SNF_RSRV_HOSP_RATE", "score"),
            "Q612": ("SNF_EXP_HOSP_NATL",  "national"),
            "Q613": ("SNF_EXP_HOSP_STATE", "state"),
            "Q621": ("SNF_RSRV_ER_RATE",   "score"),
            "Q622": ("SNF_EXP_ER_NATL",    "national"),
            "Q623": ("SNF_EXP_ER_STATE",   "state"),
            "Q631": ("LNG_RSRV_HOSP_RATE", "score"),
            "Q632": ("LNG_EXP_HOSP_NATL",  "national"),
            "Q633": ("LNG_EXP_HOSP_STATE", "state"),
            "Q641": ("LNG_RSRV_ER_RATE",   "score"),
            "Q642": ("LNG_EXP_ER_NATL",    "national"),
            "Q643": ("LNG_EXP_ER_STATE",   "state"),
        }

        flat: dict[str, str] = {}
        for cms_code, (internal_key, sub_key) in CMS_MAP.items():
            entry = measures.get(cms_code, {})
            flat[internal_key] = entry.get(sub_key, "N/A")

        return flat
    except Exception as e:
        # Claims data is the bonus feature — don't crash the whole app
        st.warning(f"Hospitalization metrics unavailable: {e}")
        return {}


def fmt_hosp(val: str, is_pct: bool) -> str:
    if not val or str(val).lower() in ("n/a", "nan", "none", ""):
        return "N/A"
    try:
        f = float(val)
        return f"{f}%" if is_pct else str(f)
    except Exception:
        return val


def _v(d: dict, *keys) -> str:
    """Get first non-empty value from dict using multiple possible key names."""
    for k in keys:
        val = str(d.get(k, "")).strip()
        if val and val.lower() not in ("nan", "none", ""):
            return val
    return "N/A"


# ── PDF generation ─────────────────────────────────────────────────────────────

def generate_pdf(display_name: str, cms: dict, claims: dict, manual: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=10*mm, bottomMargin=15*mm,
    )

    brand_style  = ParagraphStyle("Brand",  fontSize=13, fontName="Helvetica-Bold",  textColor=colors.white, alignment=TA_CENTER, leading=18)
    title_style  = ParagraphStyle("Title",  fontSize=13, fontName="Helvetica-Bold",  textColor=colors.HexColor("#003366"), alignment=TA_CENTER)
    state_style  = ParagraphStyle("State",  fontSize=11, fontName="Helvetica-Bold",  textColor=colors.HexColor("#003366"), alignment=TA_CENTER, spaceAfter=4)
    label_style  = ParagraphStyle("Label",  fontSize=9,  fontName="Helvetica-Bold",  leading=12)
    value_style  = ParagraphStyle("Value",  fontSize=9,  fontName="Helvetica-Oblique", leading=12)
    link_style   = ParagraphStyle("Link",   fontSize=8,  fontName="Helvetica",        textColor=colors.HexColor("#003366"), alignment=TA_CENTER)
    footer_style = ParagraphStyle("Footer", fontSize=7,  fontName="Helvetica-Oblique", textColor=colors.grey, alignment=TA_CENTER)

    story = []

    # Banner
    banner = Table([[Paragraph("INFINITE — Managed by MEDELITE", brand_style)]], colWidths=[180*mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#003366")),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 5*mm))

    # Title + State
    story.append(Paragraph("FACILITY ASSESSMENT SNAPSHOT", title_style))
    state_code = _v(cms, "state")
    story.append(Paragraph(state_code, state_style))

    # Medicare link
    ccn = _v(cms, "cms_certification_number_ccn")
    medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn}"
    story.append(Paragraph(
        f'<a href="{medicare_url}" color="#003366">View on Medicare Care Compare</a>',
        link_style
    ))
    story.append(Spacer(1, 3*mm))

    def row(label: str, value: str, highlight: bool = False):
        v = value if value and value != "N/A" else "N/A"
        return (Paragraph(label, label_style), Paragraph(v, value_style), highlight)

    def star(val: str) -> str:
        return f"{val}/5" if val != "N/A" else "N/A"

    full_address = ", ".join(filter(lambda x: x not in ("", "N/A"), [
        _v(cms, "provider_address"),
        _v(cms, "citytown"),
        _v(cms, "state"),
        _v(cms, "zip_code"),
    ])) or "N/A"

    rows = [
        row("Name of Facility",   display_name),
        row("Location",           full_address),
        row("EMR",                manual.get("EMR System", "") or "N/A"),
        row("Census Capacity",    _v(cms, "number_of_certified_beds")),
        row("Current Census",     manual.get("Current Census") or _v(cms, "average_number_of_residents_per_day")),
        row("Type of Patient",    manual.get("Type of Patient", "") or "N/A"),
        row("Previous Coverage from Medelite",
                                  manual.get("Previous Coverage from Medelite", "") or "N/A"),
        row("Previous Provider Performance from Medelite",
                                  manual.get("Previous Provider Performance from Medelite", "") or "N/A"),
        row("Medical Coverage",   manual.get("Medical Coverage", "") or "N/A"),
        row("Overall Star Rating",        star(_v(cms, "overall_rating"))),
        row("Health Inspection",          star(_v(cms, "health_inspection_rating"))),
        row("Staffing",                   star(_v(cms, "staffing_rating"))),
        row("Quality of Resident Care",   star(_v(cms, "qm_rating"))),
    ]

    # 12 hospitalization rows (yellow)
    for label, code, is_pct in HOSP_FIELDS:
        val = claims.get(code, "N/A") if claims else "N/A"
        rows.append(row(label, fmt_hosp(val, is_pct), highlight=True))

    if manual.get("Notes"):
        rows.append(row("Additional Notes", manual["Notes"]))

    # Render table
    tbl = Table([(r[0], r[1]) for r in rows], colWidths=[80*mm, 100*mm])
    style_cmds = [
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
            style_cmds.append(("BACKGROUND", (0,i),(-1,i), colors.HexColor("#FFFF00")))
    tbl.setStyle(TableStyle(style_cmds))
    story.append(tbl)

    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph(
        "Generated by INFINITE — Managed by MEDELITE  |  Source: CMS Provider Data Catalog",
        footer_style
    ))

    doc.build(story)
    return buf.getvalue()


# ── Session state ──────────────────────────────────────────────────────────────
for k, v in [("cms_data", None), ("claims_data", {}), ("facility_name", ""), ("display_name", "")]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── UI ─────────────────────────────────────────────────────────────────────────
st.title("Facility Assessment Snapshot")
st.markdown("Enter a CCN (e.g., `686123`) to retrieve CMS provider data.")

col1, col2 = st.columns([1, 2])

with col1:
    ccn = st.text_input("CCN (Provider Number)", placeholder="e.g., 686123")
    override_name = st.text_input(
        "Facility Name Override (Optional)",
        placeholder="Leave blank to use CMS name"
    )

    st.subheader("Manual Inputs")
    manual_data = {}
    manual_data["EMR System"] = st.text_input("EMR System", placeholder="e.g., PointClickCare, MatrixCare")
    manual_data["Current Census"] = st.text_input(
        "Current Census (overrides CMS avg if filled)",
        placeholder="e.g., 112 — auto-filled from CMS if blank"
    )
    manual_data["Type of Patient"] = st.text_input("Type of Patient", placeholder="e.g., Long-term & Short-term")
    prev = st.selectbox("Previous Coverage from Medelite", ["Select...", "Yes", "No"])
    manual_data["Previous Coverage from Medelite"] = "" if prev == "Select..." else prev
    manual_data["Previous Provider Performance from Medelite"] = st.text_input(
        "Previous Provider Performance from Medelite",
        placeholder="e.g., About 30 patients/day"
    )
    manual_data["Medical Coverage"] = st.text_input("Medical Coverage", placeholder="e.g., Optometry, PCP, Podiatry")
    manual_data["Notes"] = st.text_area("Additional Notes", placeholder="Any notes...")

    fetch_clicked = st.button("Fetch CMS Data", type="primary")

# ── Fetch ──────────────────────────────────────────────────────────────────────
if fetch_clicked and ccn:
    with st.spinner("Fetching from CMS API…"):
        cms_data = fetch_provider_data(ccn.strip())
    if cms_data:
        st.session_state.cms_data = cms_data
        st.session_state.facility_name = cms_data.get("provider_name", "Unknown")
        st.session_state.display_name = (
            override_name.strip() if override_name.strip()
            else st.session_state.facility_name
        )
        with st.spinner("Fetching hospitalization & ED metrics…"):
            st.session_state.claims_data = fetch_claims_data(ccn.strip())
        st.success("✅ CMS data retrieved!")
    else:
        st.session_state.cms_data = None
        st.session_state.claims_data = {}
        st.error(f"No data found for CCN: {ccn}. Please verify the number.")
elif fetch_clicked and not ccn:
    st.warning("Please enter a CCN to proceed.")

# ── Results ────────────────────────────────────────────────────────────────────
if st.session_state.cms_data:
    cms    = st.session_state.cms_data
    claims = st.session_state.claims_data
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
            st.metric("Staffing",                  f"{_v(cms,'staffing_rating')}/5")
            st.metric("Quality of Resident Care",  f"{_v(cms,'qm_rating')}/5")

        full_address = ", ".join(filter(lambda x: x not in ("","N/A"), [
            _v(cms,"provider_address"), _v(cms,"citytown"),
            _v(cms,"state"), _v(cms,"zip_code"),
        ]))
        st.write(f"**Address:** {full_address}")
        st.write(f"**Phone:** {_v(cms,'telephone_number')}")
        st.write(f"**Beds:** {_v(cms,'number_of_certified_beds')}  |  **Avg Residents/Day:** {_v(cms,'average_number_of_residents_per_day')}")
        st.write(f"**Type:** {_v(cms,'provider_type')}  |  **Ownership:** {_v(cms,'ownership_type')}")

        medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn_val}"
        st.markdown(f"[View Profile on Medicare Care Compare ↗]({medicare_url})")

        if claims:
            st.subheader("Hospitalization & ED Metrics")
            hosp_df = pd.DataFrame([
                {"Metric": lbl, "Value": fmt_hosp(claims.get(code,"N/A"), is_pct)}
                for lbl, code, is_pct in HOSP_FIELDS
            ])
            st.dataframe(hosp_df, use_container_width=True, hide_index=True)
        else:
            st.info("Hospitalization metrics unavailable — those rows will show N/A in the PDF.")

        pdf_bytes = generate_pdf(display_name, cms, claims, manual_data)
        safe = display_name.replace(" ", "_").replace("/", "-")
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
