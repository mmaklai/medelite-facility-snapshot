"""Facility Assessment Snapshot -- INFINITE by MEDELITE
A streamlined CCN-based facility assessment tool."""

import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import fpdf

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
DATASET_PAGE_URL = "https://data.cms.gov/provider-data/dataset/4pq5-n9py"
CMS_DATASTORE_URL = "https://data.cms.gov/provider-data/api/1/datastore/query/4pq5-n9py/0"

def get_csv_download_url() -> str:
    """Fetch the current CSV download URL from the dataset page.
    The download link URL changes dynamically with each dataset update.
    """
    try:
        resp = requests.get(DATASET_PAGE_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        download_link = soup.find("a", href=lambda h: h and h.endswith(".csv") and "NH_Provider" in h)
        if download_link and download_link.get("href"):
            href = download_link["href"]
            if href.startswith("/"):
                return "https://data.cms.gov" + href
            return href
    except Exception as e:
        st.warning(f"Could not fetch CSV URL from dataset page: {e}")
    raise ValueError("Could not find CSV download URL on dataset page.")

def fetch_cms_data_api(ccn: str) -> dict:
    """Fetch facility data from CMS Provider Data Catalog using API.
    NOTE: The $where filter on this endpoint is known to be unreliable.
    It may return results for a different CCN than requested.
    Falls back to CSV-based local filtering if no results or wrong CCN.
    """
    try:
        params = {
            "$where": f"cms_certification_number_ccn = '{ccn}'",
            "limit": 1
        }
        response = requests.get(CMS_DATASTORE_URL, params=params, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get("results"):
            record = result["results"][0]
            # Verify the returned CCN matches what we asked for
            returned_ccn = record.get("cms_certification_number_ccn", "").strip()
            if returned_ccn == ccn:
                return record
    except Exception as e:
        st.warning(f"API fetch error: {e}")
    return {}

def fetch_cms_data_csv(ccn: str) -> dict:
    """Fetch facility data by downloading the full CSV dataset and filtering locally.
    Uses pandas for efficient row-level filtering by CCN.
    The CSV download URL is fetched dynamically from the dataset page.
    """
    with st.spinner("Fetching CSV download URL and downloading full dataset..."):
        try:
            csv_url = get_csv_download_url()
            response = requests.get(csv_url, timeout=300)
            response.raise_for_status()
            # Use pandas to read CSV from the response text
            from io import StringIO
            df = pd.read_csv(StringIO(response.text))
            # Filter by CCN
            match = df[df["cms_certification_number_ccn"].astype(str).str.strip() == ccn]
            if not match.empty:
                return match.iloc[0].to_dict()
            return {}
        except Exception as e:
            st.error(f"CSV fetch error: {e}")
            return {}

def fetch_cms_data(ccn: str) -> dict:
    """Fetch facility data - tries API first (with CCN verification), falls back to CSV."""
    cms_data = fetch_cms_data_api(ccn)
    if cms_data:
        return cms_data
    st.info("API returned no results or wrong CCN. Fetching full dataset for local filtering...")
    return fetch_cms_data_csv(ccn)

def generate_pdf(facility_name: str, override_name: str, manual_data: dict, cms_data: dict) -> bytes:
    """Generate a branded PDF report."""
    pdf = fpdf.FPDF(format="A4")
    pdf.add_page()
    pdf.set_fill_color(0, 51, 102)
    pdf.rect(0, 0, 210, 15, fill=True, style="F")
    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "INFINITE - Managed by MEDELITE", align="C")
    pdf.ln(20)
    pdf.set_font("Arial", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "Facility Assessment Snapshot", align="C")
    pdf.ln(10)
    display_name = override_name.strip() if override_name.strip() else facility_name
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, f"Facility: {display_name}", align="L")
    pdf.ln(6)
    provider_num = cms_data.get("cms_certification_number_ccn", "N/A")
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 6, f"CCN: {provider_num}", align="L")
    pdf.ln(6)
    med_url = "https://data.cms.gov/provider-data/dataset/4pq5-n9py"
    pdf.cell(0, 8, "View on CMS Provider Data Catalog", link=med_url)
    pdf.ln(10)
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
    ]
    for label, key in fields:
        val = cms_data.get(key, "N/A")
        if val:
            pdf.cell(0, 5, f"{label}: {val}")
        pdf.ln(5)
    pdf.ln(3)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Manual Inputs", align="L")
    pdf.ln(6)
    pdf.set_font("Arial", "", 11)
    for key, val in manual_data.items():
        if val:
            pdf.cell(0, 5, f"{key}: {val}")
        pdf.ln(5)
    pdf.set_y(-15)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 6, "Generated by INFINITE - Managed by MEDELITE", align="C")
    return pdf.output(dest="S").encode("latin-1")

st.title("Facility Assessment Snapshot")
st.markdown("Enter a CCN (e.g., `015010`) to retrieve CMS provider data.")

col1, col2 = st.columns([1, 2])
with col1:
    ccn = st.text_input("CCN (Provider Number)", placeholder="e.g., 015010", key="ccn_input")
    override_name = st.text_input("Facility Name Override (Optional)", placeholder="Leave blank to use CMS name")
    st.subheader("Manual Inputs")
    manual_data = {}
    manual_data["EMR System"] = st.text_input("EMR System", placeholder="e.g., Epic, Cerner")
    manual_data["Current Census"] = st.text_input("Current Census", placeholder="e.g., 120")
    manual_data["Type of Patient"] = st.text_input("Type of Patient", placeholder="e.g., Acute, LTAC, Rehab")
    manual_data["Special Programs"] = st.text_area("Special Programs", placeholder="e.g., Dialysis, Wound Care")
    manual_data["Notes"] = st.text_area("Additional Notes", placeholder="Any additional notes...")
    fetch_clicked = st.button("Fetch CMS Data", type="primary")

if fetch_clicked and ccn:
    with st.spinner("Fetching data from CMS..."):
        cms_data = fetch_cms_data(ccn)
        if cms_data:
            st.success("CMS data retrieved successfully!")
            facility_name = cms_data.get("provider_name", "Unknown")
            display_name = override_name.strip() if override_name.strip() else facility_name
            with col2:
                st.subheader(f"Facility: {display_name}")
                st.write(f"**CCN:** {cms_data.get('cms_certification_number_ccn', 'N/A')}")
                st.write(f"**Type:** {cms_data.get('provider_type', 'N/A')}")
                st.write(f"**Ownership:** {cms_data.get('ownership_type', 'N/A')}")
                st.write(f"**Address:** {cms_data.get('provider_address', 'N/A')}, {cms_data.get('citytown', 'N/A')}, {cms_data.get('state', 'N/A')} {cms_data.get('zip_code', 'N/A')}")
                st.write(f"**Phone:** {cms_data.get('telephone_number', 'N/A')}")
                st.write(f"**Beds:** {cms_data.get('number_of_certified_beds', 'N/A')}")
                st.info("Note: STR/LT hospitalization metrics and some quality ratings are not available in the CMS 4pq5-n9py dataset.")
                if st.button("Download PDF Report"):
                    pdf_bytes = generate_pdf(facility_name, override_name, manual_data, cms_data)
                    st.download_button(
                        label="Download Report PDF",
                        data=pdf_bytes,
                        file_name=f"Snapshot_{display_name.replace(' ', '_')}.pdf",
                        mime="application/pdf"
                    )
        else:
            st.error(f"No CMS data found for CCN: {ccn}. Please check the number and try again.")
elif fetch_clicked and not ccn:
    st.warning("Please enter a CCN to proceed.")

st.markdown("---")
st.markdown("Powered by [CMS Provider Data Catalog](https://data.cms.gov/provider-data/dataset/4pq5-n9py) | INFINITE - Managed by MEDELITE")
