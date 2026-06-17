# medelite-facility-snapshot

![Deployment](https://img.shields.io/badge/Status-Live-green)
![Platform](https://img.shields.io/badge/Platform-Streamlit-red)
![Data](https://img.shields.io/badge/Data-CMS-blue)

A streamlined **Facility Assessment Snapshot** tool — part of the INFINITE platform by MEDELITE. Retrieve CMS provider data by CCN, input manual facility metrics, and export branded PDF reports.

---

## Live App

**Deployed:** https://medelite-facility-snapshot-md5mg7eyuvarztgrtnapuj.streamlit.app

---

## Features

- **CCN Lookup** — Enter a CMS Certification Number (e.g., `686123`) to fetch live provider data from the [CMS Provider Data Catalog](https://data.cms.gov/provider-data/dataset/4pq5-n9py)
- **Facility Name Override** — Manually override the CMS facility name if needed
- **Manual Inputs** — Capture EMR System, Current Census, Type of Patient, Special Programs, and custom Notes
- **PDF Export** — Download a branded PDF snapshot report with facility data and manual inputs
- **Static Branding** — INFINITE — Managed by MEDELITE banner is always visible

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Streamlit (Python) |
| Data API | CMS Provider Data Catalog (dataset `4pq5-n9py`) |
| PDF Export | fpdf2 |
| HTTP Requests | requests |
| Deployment | Streamlit Cloud |

---

## Project Structure

```
medelite-facility-snapshot/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

---

## Run Locally

```bash
# Clone the repo
git clone https://github.com/mmaklai/medelite-facility-snapshot.git
cd medelite-facility-snapshot

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## Deployment

The app is deployed on **Streamlit Cloud** and auto-deploys on every push to `main`.

Deployment settings:
- **Repository:** mmaklai/medelite-facility-snapshot
- **Branch:** main
- **Main file:** app.py

---

## Data Source & Field Mappings

All provider data is fetched from the **CMS Provider Data Catalog** (`4pq5-n9py`)[^1] using the REST API with a `$where` filter on `provider_number`.

[^1]: https://data.cms.gov/provider-data/dataset/4pq5-n9py

| App Field | CMS API Field (`4pq5-n9py`) |
|-----------|------------------------------|
| Facility Name | `provider_name` |
| Address | `provider_address` |
| City | `provider_city` |
| State | `provider_state` |
| ZIP | `provider_zip_code` |
| Phone | `provider_phone` |
| Facility Type | `facility_type` |
| Ownership | `ownership` |
| Bed Count | `total_staffed_beds` |
| CCRC | `ccrc` |
| Medicare Participation | `medicare_participation` |
| Hospital Referral Region | `region` |
| CCN (Provider Number) | `provider_number` |

---

## Known Limitations

- **STR/LT Hospitalization Metrics (Facility Specific)** — Per-facility short-term and long-term hospitalization/ED scores are not exposed through any public CMS Provider Data Catalog API endpoint. The app currently displays state and national averages (sourced from the CMS State/US Averages dataset xcdc-v8bm), with facility-specific rows marked as "Not Reported" — consistent with how CMS Care Compare itself handles facilities without sufficient claims volume. A future enhancement could explore scraping the Care Compare web interface or requesting a bulk data export directly from CMS.

- **PDF Hyperlinks** —  The Medicare Care Compare link in the exported PDF is dynamically generated using the searched CCN (e.g., https://www.medicare.gov/care-compare/details/nursing-home/686123). Clicking it requires a PDF viewer that supports embedded hyperlinks (Adobe Acrobat, Chrome PDF viewer).

---

## License

Proprietary — INFINITE by MEDELITE. All rights reserved.
