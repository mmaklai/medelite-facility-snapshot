# medelite-facility-snapshot

![Deployment](https://img.shields.io/badge/Status-Live-green)
![Platform](https://img.shields.io/badge/Platform-Streamlit-red)
![Data](https://img.shields.io/badge/Data-CMS-blue)

A streamlined **Facility Assessment Snapshot** tool , part of the INFINITE platform by MEDELITE. Retrieve CMS provider data by CCN, input manual facility metrics, and export branded PDF reports.

---

## Live App

**Deployed:** https://medelite-facility-snapshot-md5mg7eyuvarztgrtnapuj.streamlit.app

---

## Features

- **CCN Lookup** - Enter a CMS Certification Number (e.g., `686123`) to fetch live provider data from the [CMS Provider Data Catalog](https://data.cms.gov/provider-data/dataset/4pq5-n9py)
- **Facility Name Override** - Manually override the CMS facility name if needed
- **Manual Inputs** - Capture EMR System, Current Census, Type of Patient, and custom Notes
- **PDF Export** - Download a branded PDF snapshot report with facility data and manual inputs
- **Static Branding** - INFINITE - Managed by MEDELITE banner is always visible
- **Star Rating Cards** - Color-coded visual display of all four CMS star ratings
- **Word Doc Export** - Download an editable doc version of the same report
- **Advanced Error Handling** - CCN format validation, specific error messages, and a three-method API fallback chain to guarantee the correct facility is always returned
- **Hospitalization & ED Metrics** - State and national averages for all 12 STR/LT hospitalization and ED metrics sourced from the CMS State/US Averages dataset



---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Streamlit (Python) |
| Data API | CMS Provider Data Catalog (dataset `4pq5-n9py`, 'xcdc-v8bm') |
| PDF Export | ReportLab |
| HTTP Requests | requests |
| Deployment | Streamlit Cloud |
| Word Export | python-docx |

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

All provider data is fetched from the **CMS Provider Data Catalog** (`4pq5-n9py`)[^1] using the REST API with CCN conditions filter with 3-method fallback

[^1]: https://data.cms.gov/provider-data/dataset/4pq5-n9py

| App Field | CMS API Field (`4pq5-n9py`) |
|-----------|------------------------------|
| Facility Name | `provider_name` |
| Address | `provider_address` |
| City | `citytown` |
| State | `state` |
| ZIP | `zip_code` |
| Phone | `telephone_number` |
| Facility Type | `provider_type` |
| Avg Residents/Day | average_number_of_residents_per_day |
| Overall Rating | overall_rating |
| Ownership | `ownership_type` |
| Bed Count | `number_of_certified_beds` |
| Health Inspection | health_inspection_rating |
| Staffing | staffing_rating |
| Quality of Resident Care | qm_rating |
| CCN | cms_certification_number_ccn |

---
## State & National Averages - xcdc-v8bm

Hospitalization and ED averages are sourced from the CMS NH State & US Averages dataset, filtered by state_or_nation ("NATION" for national, state abbreviation for state).

| App Field | CMS API Field (`xcdc-v8bm`) |
|-----------|------------------------------|
| STR Hospitalization avg | percentage_of_short_stay_residents_who_were_rehospitalized__1d02 |
| STR ED Visit avg | percentage_of_short_stay_residents_who_had_an_outpatient_em_d911 |
| LT Hospitalization avg | number_of_hospitalizations_per_1000_longstay_resident_days |
| LT ED Visit avg | number_of_outpatient_emergency_department_visits_per_1000_l_de9d |

---

## Known Limitations

- **STR/LT Hospitalization Metrics (Facility Specific)** - Per-facility short-term and long-term hospitalization/ED scores are not exposed through any public CMS Provider Data Catalog API endpoint. The app currently displays state and national averages (sourced from the CMS State/US Averages dataset xcdc-v8bm), with facility-specific rows marked as "Not Reported" , consistent with how CMS Care Compare itself handles facilities without sufficient claims volume. A future enhancement could explore scraping the Care Compare web interface or requesting a bulk data export directly from CMS.

- **PDF Hyperlinks** -  The Medicare Care Compare link in the exported PDF is dynamically generated using the searched CCN (e.g., https://www.medicare.gov/care-compare/details/nursing-home/686123). Clicking it requires a PDF viewer that supports embedded hyperlinks (Adobe Acrobat, Chrome PDF viewer).

- **Star Rating Accuracy** - Ratings reflect live CMS data at the time of lookup. The reference PDF included in the project brief was generated from an earlier CMS data snapshot and may show different values for the same facility.

---

## License

Proprietary - INFINITE by MEDELITE. All rights reserved.
