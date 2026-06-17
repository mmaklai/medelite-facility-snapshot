"""Facility Assessment Snapshot -- INFINITE by MEDELITE
A streamlined CCN-based facility assessment tool."""

import streamlit as st
import requests
import pandas as pd
import fpdf
from io import StringIO

st.set_page_config(
    page_title="Facility Assessment Snapshot -- INFINITE by MEDELITE",
    page_icon="",
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
        border-radius: 0;
    }
    .report-body {
        padding: 0.5rem 0;
    }
    </style>
    <div class="infinite-banner">INFINITE - Managed by MEDELITE</div>
    """,
    unsafe_allow_html=True
)

# CMS Provider Data Catalog
CMS_DATASTORE_URL = "https://data.cms.gov/provider-data/api/1/datastore/query/4pq5-n9py/0"
PROVIDER_CSV_URL = "https://data.cms.gov/provider-data/sites/default/files/resources/f4df3b5e6a227d95033c3f32ad5fad08_1778861747/NH_ProviderInfo_May2026.csv"



def fetch_cms_data_api(ccn: str) -> dict:
    try:
        params = {
            "$where": f"cms_certification_number_ccn='{ccn}'",
            "$limit": 1
        }
        response = requests.get(CMS_DATASTORE_URL, params=params, timeout=20)
        response.raise_for_status()
        result = response.json()
        rows = result.get("results", [])
        if rows:
            row = rows[0]
            if str(row.get("cms_certification_number_ccn", "")).strip() == ccn.strip():
                return row
        return {}
    except Exception as e:
        st.warning(f"API fetch error: {e}")
        return {}
        
@st.cache_data(show_spinner=False)
def load_provider_csv() -> pd.DataFrame:
    response = requests.get(PROVIDER_CSV_URL, timeout=300)
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text), dtype={"cms_certification_number_ccn": str})

def fetch_cms_data_csv(ccn: str) -> dict:
    try:
        df = load_provider_csv()
        match = df[df["cms_certification_number_ccn"].astype(str).str.strip() == ccn.strip()]
        if not match.empty:
            return match.iloc[0].to_dict()
        return {}
    except Exception as e:
        st.error(f"CSV fetch error: {e}")
        return {}



def fetch_cms_data(ccn: str) -> dict:
    return fetch_cms_data_csv(ccn)

def generate_pdf(facility_name: str, override_name: str, manual_data: dict, cms_data: dict) -> bytes:
    """Generate a branded PDF report."""
    pdf = fpdf.FPDF(format="A4")
    pdf.add_page()

    # Header Bar
    pdf.set_fill_color(0, 51, 102)
    pdf.rect(0, 0, 210, 15, style="F")
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "INFINITE - Managed by MEDELITE", align="C")

    pdf.ln(20)
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "Facility Assessment Snapshot", align="C")
    pdf.ln(6)

    # State abbreviation dynamic code
    state_code = cms_data.get("state", "N/A")
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 6, f"State: {state_code}", align="C")
    pdf.ln(10)

    display_name = override_name.strip() if override_name.strip() else facility_name
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"Facility: {display_name}", align="L")
    pdf.ln(6)

    provider_num = cms_data.get("cms_certification_number_ccn", "N/A")
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 6, f"CCN: {provider_num}", align="L")
    pdf.ln(6)

    # Medicare Care Compare hyperlink (FIX G1)
    medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{provider_num}"
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 8, "View on Medicare Care Compare", link=medicare_url)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # CMS Provider Profile
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "CMS Provider Profile", align="L")
    pdf.ln(6)
    pdf.set_font("Arial", "", 11)

    fields = [
        ("Facility Name", "provider_name"),
        ("Address", "provider_address"),
        ("City", "citytown"),
        ("State", "state"),
        ("ZIP", "zip_code"),
        ("Phone", "telephone_number"),
        ("Facility Type", "provider_type"),
        ("Ownership", "ownership_type"),
        ("Bed Count", "number_of_certified_beds"),
        ("CCRC", "continuing_care_retirement_community"),
        # Star Ratings (FIX G2)
        ("Overall Rating", "overall_rating"),
        ("Health Inspection Rating", "health_inspection_rating"),
        ("Staffing Rating", "staffing_rating"),
        ("Quality Measures Rating", "quality_measures_rating"),
    ]
    for label, key in fields:
        val = cms_data.get(key, "N/A")
        if val:
            pdf.cell(0, 5, f"{label}: {val}")
            pdf.ln(5)

    pdf.ln(3)

    # Manual Inputs
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Manual Inputs", align="L")
    pdf.ln(6)
    pdf.set_font("Arial", "", 11)
    for key, val in manual_data.items():
        if val and key != "_csrf_token":
            pdf.cell(0, 5, f"{key}: {val}")
            pdf.ln(5)

    pdf.set_y(-15)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 6, "Generated by INFINITE - Managed by MEDELITE", align="C")
    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, bytes):
        return pdf_output
    return pdf_output.encode("latin-1")

if "cms_data" not in st.session_state:
    st.session_state.cms_data = None
if "display_name" not in st.session_state:
    st.session_state.display_name = ""
if "facility_name" not in st.session_state:
    st.session_state.facility_name = ""
st.title("Facility Assessment Snapshot")
st.markdown("Enter a CCN (e.g., `015010`) to retrieve CMS provider data.")

col1, col2 = st.columns([1, 2])

with col1:
    ccn = st.text_input("CCN (Provider Number)", placeholder="e.g., 015010", key="ccn_input")
    override_name = st.text_input("Facility Name Override (Optional)", placeholder="Leave blank to use CMS name")

    st.subheader("Manual Inputs")
    manual_data = {}
    manual_data["EMR System"] = st.text_input("EMR System", placeholder="e.g., Epic, Cerner")
    manual_data["Census Capacity"] = st.text_input("Census Capacity (Beds)", placeholder="Auto-filled from CMS")
    manual_data["Current Census"] = st.text_input("Current Census", placeholder="e.g., 120")
    manual_data["Type of Patient"] = st.text_input("Type of Patient", placeholder="e.g., Acute, LTAC, Rehab")
    # FIX G3-G5: Missing manual fields
    manual_data["Previous Coverage from Medelite"] = st.selectbox(
        "Previous Coverage from Medelite",
        ["Select...", "Yes", "No"]
    )
    if manual_data["Previous Coverage from Medelite"] == "Select...":
        manual_data["Previous Coverage from Medelite"] = ""
    manual_data["Previous Provider Performance from Medelite"] = st.text_input(
        "Previous Provider Performance from Medelite",
        placeholder="e.g., About 30 patients/day"
    )
    manual_data["Medical Coverage"] = st.text_input(
        "Medical Coverage",
        placeholder="e.g., Optometry, PCP, Podiatry"
    )
    manual_data["Special Programs"] = st.text_area("Special Programs", placeholder="e.g., Dialysis, Wound Care")
    manual_data["Notes"] = st.text_area("Additional Notes", placeholder="Any additional notes...")

    fetch_clicked = st.button("Fetch CMS Data", type="primary")

if fetch_clicked and ccn:
    with st.spinner("Fetching data from CMS..."):
        cms_data = fetch_cms_data(ccn)
        if cms_data:
            st.session_state.cms_data = cms_data
            st.session_state.facility_name = cms_data.get("provider_name", "Unknown")
            st.session_state.display_name = (
                override_name.strip() if override_name.strip() else st.session_state.facility_name
            )
            st.success("CMS data retrieved successfully!")
        else:
            st.session_state.cms_data = None
            st.error(f"No CMS data found for CCN: {ccn}. Please check the number and try again.")
elif fetch_clicked and not ccn:
    st.warning("Please enter a CCN to proceed.")

        

if st.session_state.cms_data:
    cms_data = st.session_state.cms_data
    facility_name = st.session_state.facility_name
    display_name = override_name.strip() if override_name.strip() else facility_name
    state_code = cms_data.get("state", "N/A")

    with col2:
        st.subheader(f"Facility: {display_name}")
        st.write(f"**CCN:** {cms_data.get('cms_certification_number_ccn', 'N/A')}")
        st.write(f"**State:** {state_code}")
        st.write(f"**Overall Rating:** {cms_data.get('overall_rating', 'N/A')}/5")
        st.write(f"**Health Inspection:** {cms_data.get('health_inspection_rating', 'N/A')}/5")
        st.write(f"**Staffing:** {cms_data.get('staffing_rating', 'N/A')}/5")
        st.write(f"**Quality Measures:** {cms_data.get('quality_measures_rating', 'N/A')}/5")
        st.write(f"**Type:** {cms_data.get('provider_type', 'N/A')}")
        st.write(f"**Ownership:** {cms_data.get('ownership_type', 'N/A')}")
        st.write(f"**Address:** {cms_data.get('provider_address', 'N/A')}, {cms_data.get('citytown', 'N/A')}, {cms_data.get('state', 'N/A')} {cms_data.get('zip_code', 'N/A')}")
        st.write(f"**Phone:** {cms_data.get('telephone_number', 'N/A')}")
        st.write(f"**Beds:** {cms_data.get('number_of_certified_beds', 'N/A')}")

        provider_num = cms_data.get('cms_certification_number_ccn', '')
        medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{provider_num}"
        st.markdown(f"[View Profile on Medicare Care Compare]({medicare_url})", unsafe_allow_html=True)

        st.info("Note: STR/LT hospitalization metrics and some quality ratings are not available in the CMS 4pq5-n9py dataset.")

        pdf_bytes = generate_pdf(facility_name, override_name, manual_data, cms_data)
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=f"Snapshot_{display_name.replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

       

st.markdown("---")
st.markdown("Powered by [CMS Provider Data Catalog](https://data.cms.gov/provider-data/dataset/4pq5-n9py) | INFINITE - Managed by MEDELITE")
