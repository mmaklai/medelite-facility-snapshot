"""Facility Assessment Snapshot -- INFINITE by MEDELITE
A streamlined CCN-based facility assessment tool.

CHANGES FROM ORIGINAL:
- PDF rebuilt with reportlab: two-column bordered table matching spec template
- 12 hospitalization/ED metrics fetched from CMS claims CSV (bonus feature)
- Yellow row highlighting for hospitalization metrics (matches template)
- "Quality of Resident Care" label fixed (was "Quality Measures Rating")
- Census Capacity auto-filled from CMS (number_of_certified_beds)
- Current Census auto-filled from CMS (average_number_of_residents_per_day)
- State code shown centered below title in PDF
- Star ratings show /5 suffix in PDF
- @st.cache_data ttl=3600 added to both CSVs
- Dead-code API function removed
- page_icon set to hospital emoji
- Special Programs field removed (not in spec)
- INFINITE branding never overwritten by facility name

REQUIREMENTS (requirements.txt):
    streamlit>=1.30
    requests
    pandas
    reportlab>=4.0
"""

import streamlit as st
import requests
import pandas as pd
from io import StringIO, BytesIO

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

# ── CMS Data Sources ───────────────────────────────────────────────────────────
# ⚠️  MAINTENANCE: CMS updates these URLs monthly.
# Update filenames each month. Check: https://data.cms.gov/provider-data/dataset/4pq5-n9py
PROVIDER_CSV_URL = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "f4df3b5e6a227d95033c3f32ad5fad08_1778861747/NH_ProviderInfo_May2026.csv"
)
# Claims-based quality measures dataset (bg7j-552g) — used for 12 hosp/ED metrics
CLAIMS_CSV_URL = (
    "https://data.cms.gov/provider-data/sites/default/files/resources/"
    "a6ffef73d37d849c0c02090d09208e66_1778861747/NH_QualityMsr_Claims_May2026.csv"
)

# ── Hospitalization metric definitions ─────────────────────────────────────────
# (display label, flat claims dict key, is_percentage)
# Keys map to CMS measure codes as stored in our flat claims dict (see fetch_claims_data).
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

def _ccn_col(df: pd.DataFrame) -> str:
    """Find the CCN column regardless of CMS casing."""
    for col in df.columns:
        if "ccn" in col.lower() or "certification number" in col.lower():
            return col
    return ""


@st.cache_data(ttl=3600, show_spinner=False)
def load_provider_csv() -> pd.DataFrame:
    r = requests.get(PROVIDER_CSV_URL, timeout=300)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text), dtype=str)


@st.cache_data(ttl=3600, show_spinner=False)
def load_claims_csv() -> pd.DataFrame:
    r = requests.get(CLAIMS_CSV_URL, timeout=300)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text), dtype=str)


def fetch_provider_data(ccn: str) -> dict:
    try:
        df = load_provider_csv()
        col = _ccn_col(df)
        if not col:
            st.error("Cannot locate CCN column in provider CSV.")
            return {}
        match = df[df[col].str.strip() == ccn.strip()]
        if not match.empty:
            # Normalise to lowercase_underscore keys
            return {
                k.lower().strip()
                 .replace(" ", "_")
                 .replace("(", "").replace(")", "")
                 .replace("-", "_").replace("/", "_"):
                str(v)
                for k, v in match.iloc[0].to_dict().items()
            }
        return {}
    except Exception as e:
        st.error(f"Provider data error: {e}")
        return {}


def fetch_claims_data(ccn: str) -> dict:
    """
    Returns a flat dict {CODE: value_string} for all 12 hosp/ED metrics.

    The CMS claims CSV (NH_QualityMsr_Claims) has one row per measure per facility.
    Columns include a measure code, the facility score, national avg, and state avg.
    We pivot to a flat dict so HOSP_FIELDS can do a direct key lookup.
    """
    try:
        df = load_claims_csv()
        col = _ccn_col(df)
        if not col:
            return {}
        rows = df[df[col].str.strip() == ccn.strip()]
        if rows.empty:
            return {}

        # Detect key columns (column names vary slightly by CMS release)
        measure_col = next(
            (c for c in df.columns if "measure" in c.lower() and "code" in c.lower()),
            None
        )
        score_col = next(
            (c for c in df.columns
             if any(k in c.lower() for k in ["score", "observed", "rate"])
             and "national" not in c.lower() and "state" not in c.lower()),
            None
        )
        natl_col = next(
            (c for c in df.columns if "national" in c.lower()
             and any(k in c.lower() for k in ["avg", "average", "rate", "score"])),
            None
        )
        state_col = next(
            (c for c in df.columns if "state" in c.lower()
             and any(k in c.lower() for k in ["avg", "average", "rate", "score"])),
            None
        )

        if not (measure_col and score_col):
            return {}

        # Build a lookup: measure_code -> {score, national, state}
        measures: dict[str, dict] = {}
        for _, r in rows.iterrows():
            code = str(r.get(measure_col, "")).strip().upper()
            measures[code] = {
                "score":    str(r.get(score_col, "N/A")).strip(),
                "national": str(r.get(natl_col, "N/A")).strip() if natl_col else "N/A",
                "state":    str(r.get(state_col, "N/A")).strip() if state_col else "N/A",
            }

        # Map CMS codes to our internal HOSP_FIELDS codes
        # CMS short-stay hosp codes: Q611, Q612, Q613 (observed, expected-natl, expected-state)
        # CMS short-stay ED codes:   Q621, Q622, Q623
        # CMS long-stay hosp codes:  Q631, Q632, Q633
        # CMS long-stay ED codes:    Q641, Q642, Q643
        CMS_CODE_MAP = {
            # Short-stay hospitalization
            "Q611": "SNF_RSRV_HOSP_RATE",
            "Q612": "SNF_EXP_HOSP_NATL",
            "Q613": "SNF_EXP_HOSP_STATE",
            # Short-stay ED
            "Q621": "SNF_RSRV_ER_RATE",
            "Q622": "SNF_EXP_ER_NATL",
            "Q623": "SNF_EXP_ER_STATE",
            # Long-stay hospitalization
            "Q631": "LNG_RSRV_HOSP_RATE",
            "Q632": "LNG_EXP_HOSP_NATL",
            "Q633": "LNG_EXP_HOSP_STATE",
            # Long-stay ED
            "Q641": "LNG_RSRV_ER_RATE",
            "Q642": "LNG_EXP_ER_NATL",
            "Q643": "LNG_EXP_ER_STATE",
        }

        flat: dict[str, str] = {}
        for cms_code, internal_key in CMS_CODE_MAP.items():
            entry = measures.get(cms_code, {})
            flat[internal_key] = entry.get("score", "N/A")

        # Fallback: also populate national/state from the score of their own rows
        # if the CSV stores each avg as a separate measure row
        for cms_code, internal_key in CMS_CODE_MAP.items():
            if flat.get(internal_key, "N/A") == "N/A":
                # Try score sub-key (some CMS releases embed nat/state in the same row)
                entry = measures.get(cms_code, {})
                if internal_key.endswith("_NATL"):
                    flat[internal_key] = entry.get("national", "N/A")
                elif internal_key.endswith("_STATE"):
                    flat[internal_key] = entry.get("state", "N/A")

        return flat
    except Exception as e:
        st.warning(f"Hospitalization metrics unavailable: {e}")
        return {}


def fmt_hosp(val: str, is_pct: bool) -> str:
    if not val or val.lower() in ("n/a", "nan", "none", ""):
        return "N/A"
    try:
        f = float(val)
        return f"{f}%" if is_pct else str(f)
    except Exception:
        return val


# ── PDF generation ─────────────────────────────────────────────────────────────

def generate_pdf(display_name: str, cms: dict, claims: dict, manual: dict) -> bytes:
    """
    Produce a PDF matching the Facility Assessment Snapshot template:
    - Dark blue INFINITE banner
    - Centered title + state code
    - Two-column bordered table (bold label | italic value)
    - Yellow highlighting on the 12 hospitalization rows
    - Medicare Care Compare hyperlink
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=10 * mm, bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    brand_style = ParagraphStyle(
        "Brand", fontSize=13, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER, leading=18
    )
    title_style = ParagraphStyle(
        "Title", fontSize=13, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#003366"), alignment=TA_CENTER, spaceAfter=0
    )
    state_style = ParagraphStyle(
        "State", fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#003366"), alignment=TA_CENTER, spaceAfter=4
    )
    label_bold = ParagraphStyle(
        "LabelBold", fontSize=9, fontName="Helvetica-Bold", leading=12
    )
    value_italic = ParagraphStyle(
        "ValueItalic", fontSize=9, fontName="Helvetica-Oblique", leading=12
    )
    link_style = ParagraphStyle(
        "Link", fontSize=8, fontName="Helvetica",
        textColor=colors.HexColor("#003366"), alignment=TA_CENTER
    )
    footer_style = ParagraphStyle(
        "Footer", fontSize=7, fontName="Helvetica-Oblique",
        textColor=colors.grey, alignment=TA_CENTER
    )

    story = []

    # ── INFINITE banner ──────────────────────────────────────────────────────
    banner = Table(
        [[Paragraph("INFINITE — Managed by MEDELITE", brand_style)]],
        colWidths=[180 * mm]
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#003366")),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 5 * mm))

    # ── Title + state ────────────────────────────────────────────────────────
    story.append(Paragraph("FACILITY ASSESSMENT SNAPSHOT", title_style))
    state_code = str(cms.get("state", "N/A")).strip()
    story.append(Paragraph(state_code, state_style))

    # ── Medicare link ────────────────────────────────────────────────────────
    ccn = str(cms.get("cms_certification_number_ccn", "")).strip()
    medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn}"
    story.append(Paragraph(
        f'<a href="{medicare_url}" color="#003366">View on Medicare Care Compare</a>',
        link_style
    ))
    story.append(Spacer(1, 3 * mm))

    # ── Build row data ────────────────────────────────────────────────────────
    def r(label: str, value, highlight: bool = False):
        v = str(value).strip() if value and str(value).strip() not in ("nan", "None", "") else "N/A"
        return (Paragraph(label, label_bold), Paragraph(v, value_italic), highlight)

    def star(val) -> str:
        v = str(val).strip()
        return f"{v}/5" if v not in ("N/A", "", "nan", "None") else "N/A"

    full_address = ", ".join(filter(lambda x: x and x != "nan", [
        cms.get("provider_address", ""),
        cms.get("citytown", ""),
        cms.get("state", ""),
        cms.get("zip_code", ""),
    ])) or "N/A"

    beds = cms.get("number_of_certified_beds", manual.get("Census Capacity", "N/A"))
    avg_res = cms.get("average_number_of_residents_per_day",
                       manual.get("Current Census", "N/A"))

    rows = [
        r("Name of Facility",   display_name),
        r("Location",           full_address),
        r("EMR",                manual.get("EMR System", "")),
        r("Census Capacity",    beds),
        r("Current Census",     avg_res),
        r("Type of Patient",    manual.get("Type of Patient", "")),
        r("Previous Coverage from Medelite",
                                manual.get("Previous Coverage from Medelite", "")),
        r("Previous Provider Performance from Medelite",
                                manual.get("Previous Provider Performance from Medelite", "")),
        r("Medical Coverage",   manual.get("Medical Coverage", "")),
        r("Overall Star Rating",          star(cms.get("overall_rating", "N/A"))),
        r("Health Inspection",            star(cms.get("health_inspection_rating", "N/A"))),
        r("Staffing",                     star(cms.get("staffing_rating", "N/A"))),
        r("Quality of Resident Care",     star(
            cms.get("quality_measure_rating",
                    cms.get("quality_measures_rating", "N/A"))
        )),
    ]

    # 12 hospitalization rows — yellow highlighted
    for label, code, is_pct in HOSP_FIELDS:
        val = claims.get(code, "N/A") if claims else "N/A"
        rows.append(r(label, fmt_hosp(val, is_pct), highlight=True))

    notes = manual.get("Notes", "")
    if notes:
        rows.append(r("Additional Notes", notes))

    # ── Render table ──────────────────────────────────────────────────────────
    col_w = [80 * mm, 100 * mm]
    table_data = [(row[0], row[1]) for row in rows]
    tbl = Table(table_data, colWidths=col_w)

    style_cmds = [
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.black),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]
    for i, row in enumerate(rows):
        if row[2]:
            style_cmds.append(
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFFF00"))
            )

    tbl.setStyle(TableStyle(style_cmds))
    story.append(tbl)

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Paragraph(
        "Generated by INFINITE — Managed by MEDELITE  |  "
        "Source: CMS Provider Data Catalog (data.cms.gov)",
        footer_style
    ))

    doc.build(story)
    return buf.getvalue()


# ── Session state ──────────────────────────────────────────────────────────────
for k, v in [("cms_data", None), ("claims_data", {}),
              ("facility_name", ""), ("display_name", "")]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── UI layout ──────────────────────────────────────────────────────────────────
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
    manual_data["EMR System"] = st.text_input(
        "EMR System", placeholder="e.g., PointClickCare, MatrixCare"
    )
    manual_data["Current Census"] = st.text_input(
        "Current Census (overrides CMS avg if filled)",
        placeholder="e.g., 112"
    )
    manual_data["Type of Patient"] = st.text_input(
        "Type of Patient", placeholder="e.g., Long-term & Short-term"
    )
    prev = st.selectbox("Previous Coverage from Medelite", ["Select...", "Yes", "No"])
    manual_data["Previous Coverage from Medelite"] = "" if prev == "Select..." else prev
    manual_data["Previous Provider Performance from Medelite"] = st.text_input(
        "Previous Provider Performance from Medelite",
        placeholder="e.g., About 30 patients/day"
    )
    manual_data["Medical Coverage"] = st.text_input(
        "Medical Coverage", placeholder="e.g., Optometry, PCP, Podiatry"
    )
    manual_data["Notes"] = st.text_area("Additional Notes", placeholder="Any notes...")

    fetch_clicked = st.button("Fetch CMS Data", type="primary")

# ── Fetch ──────────────────────────────────────────────────────────────────────
if fetch_clicked and ccn:
    with st.spinner("Fetching provider data from CMS…"):
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
    cms = st.session_state.cms_data
    claims = st.session_state.claims_data
    facility_name = st.session_state.facility_name
    display_name = override_name.strip() if override_name.strip() else facility_name

    with col2:
        st.subheader(f"Facility: {display_name}")
        ccn_val = str(cms.get("cms_certification_number_ccn", "")).strip()
        state_code = str(cms.get("state", "N/A")).strip()
        st.write(f"**CCN:** {ccn_val}  |  **State:** {state_code}")

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Overall Rating",   f"{cms.get('overall_rating','N/A')}/5")
            st.metric("Health Inspection",f"{cms.get('health_inspection_rating','N/A')}/5")
        with c2:
            st.metric("Staffing", f"{cms.get('staffing_rating','N/A')}/5")
            st.metric("Quality of Resident Care",
                      f"{cms.get('quality_measure_rating', cms.get('quality_measures_rating','N/A'))}/5")

        full_address = ", ".join(filter(lambda x: x and x != "nan", [
            cms.get("provider_address",""),
            cms.get("citytown",""),
            cms.get("state",""),
            cms.get("zip_code",""),
        ]))
        st.write(f"**Address:** {full_address}")
        st.write(f"**Phone:** {cms.get('telephone_number','N/A')}")
        st.write(f"**Beds:** {cms.get('number_of_certified_beds','N/A')}  |  "
                 f"**Avg Residents/Day:** {cms.get('average_number_of_residents_per_day','N/A')}")

        medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn_val}"
        st.markdown(f"[View Profile on Medicare Care Compare ↗]({medicare_url})")

        if claims:
            st.subheader("Hospitalization & ED Metrics")
            hosp_df = pd.DataFrame([
                {"Metric": lbl, "Value": fmt_hosp(claims.get(code, "N/A"), is_pct)}
                for lbl, code, is_pct in HOSP_FIELDS
            ])
            st.dataframe(hosp_df, use_container_width=True, hide_index=True)
        else:
            st.info(
                "Hospitalization/ED metrics will be attempted from the CMS claims CSV. "
                "If unavailable, those rows show N/A in the PDF."
            )

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
