# Athena EHR Schema Analysis

## Analysis Date: 2024-12-13
## Data Source: 812 captured events from real AthenaNet traffic

---

## Executive Summary

This document provides the empirical schema analysis for AthenaNet's internal API structures,
derived from actual intercepted traffic. This serves as the canonical reference for building
clinical data interpreters.

**Key Findings:**
1. Data is deeply nested (3-4 levels) with Athena-specific class markers (`__CLASS__`)
2. Clinical data requires navigating through `Events[].Instance` structures
3. ICD-10 and SNOMED codes are available but in different sub-objects
4. Medication names are in `DisplayName`, not `MedicationName`

---

## 1. Medications Schema

### Endpoint Pattern
```
/{practice}/{dept}/ax/data?sources=active_medications&...
```

### JSON Path to Drug Name
```
payload
  └── active_medications
        └── Medications[]                          ← Array of medication objects
              └── Events[]                         ← Array of medication events
                    └── Instance                   ← The actual medication data
                          ├── DisplayName          ← "testosterone cypionate" ✓
                          ├── UnstructuredSig      ← "TAKE ONE TABLET BY MOUTH ONCE DAILY" ✓
                          ├── Medication           ← Nested drug metadata
                          │     ├── ProductName
                          │     └── TherapeuticClass ← Drug classification
                          ├── QuantityValue        ← 30
                          ├── RefillsAllowed       ← 3
                          ├── PrescriberName       ← "Dr. Smith"
                          └── PharmacyName         ← "CVS Pharmacy"
```

### Critical Fields for Vascular Surgery
| Field Path | Example Value | Clinical Use |
|------------|---------------|--------------|
| `Events[0].Instance.DisplayName` | "clopidogrel" | Antithrombotic identification |
| `Events[0].Instance.UnstructuredSig` | "TAKE ONE TABLET..." | Dosing instructions |
| `Events[0].Instance.Medication.TherapeuticClass` | "ANTIPLATELET" | Drug classification |

### Sample Raw Structure
```json
{
  "active_medications": {
    "Medications": [
      {
        "__CLASS__": "Athena::Chart::Entity::Medication",
        "Events": [
          {
            "__CLASS__": "Athena::Chart::Entity::MedicationEvent",
            "Type": "ENTER",
            "Instance": {
              "__CLASS__": "Athena::Chart::Entity::MedicationInstance",
              "DisplayName": "pantoprazole",
              "UnstructuredSig": "TAKE ONE TABLET BY MOUTH ONCE DAILY",
              "QuantityValue": 30,
              "Medication": {
                "ProductName": "PROTONIX",
                "TherapeuticClass": "PROTON PUMP INHIBITOR"
              }
            }
          }
        ]
      }
    ]
  }
}
```

---

## 2. Problems/Diagnoses Schema

### Endpoint Pattern
```
/{practice}/{dept}/ax/data?sources=active_problems&...
```

### JSON Path to Diagnosis
```
payload
  └── active_problems
        └── Problems[]                             ← Array of problem objects
              ├── Name                             ← "intermittent claudication..." ✓
              ├── Code                             ← SNOMED code object
              │     ├── Code                       ← "12236951000119108" (SNOMED)
              │     ├── Description                ← Full clinical description
              │     └── CodeSet                    ← "SNOMED"
              ├── PatientSnomedICD10s[]            ← ICD-10 mappings
              │     ├── DIAGNOSISCODE              ← "I70213" ✓
              │     ├── FULLDESCRIPTION            ← "Athscl native arteries..."
              │     └── SNOMEDCODE                 ← Cross-reference
              ├── Status                           ← Active/Resolved
              └── Primary                          ← Boolean
```

### Critical Fields for Vascular Surgery
| Field Path | Example Value | Clinical Use |
|------------|---------------|--------------|
| `Problems[].Name` | "intermittent claudication..." | Primary display |
| `Problems[].Code.Code` | "12236951000119108" | SNOMED for analytics |
| `Problems[].PatientSnomedICD10s[].DIAGNOSISCODE` | "I70.213" | Billing/risk stratification |

### Vascular-Relevant ICD-10 Codes Found
```
I70.213 - Atherosclerosis of native arteries of extremities with intermittent claudication, bilateral legs
K21.9   - Gastroesophageal reflux disease (anesthesia risk)
N40.1   - Benign prostatic hyperplasia (catheter considerations)
E78.2   - Mixed hyperlipidemia (cardiovascular risk)
R06.02  - Shortness of breath (cardiopulmonary risk)
```

---

## 3. Allergies Schema

### Endpoint Pattern
```
/{practice}/{dept}/ax/data?sources=allergies&...
```

### Structure (Needs Verification)
```
payload
  └── allergies
        └── (TBD - No allergy events in current sample)
```

**Note:** No allergy-specific events captured. The `allergies` key appears in active-fetch
compound payloads but those contain error responses, not actual allergy data.

**Action Required:** Navigate to a patient's allergy tab to capture this structure.

---

## 4. Vitals Schema

### Endpoint Pattern
```
/{practice}/{dept}/ax/data?sources=measurements&...
```

### Structure (Needs Verification)
```
payload
  └── measurements
        └── (TBD - Structure pending capture)
```

---

## 5. Active Fetch Compound Payload Structure

When using the active fetcher, the payload structure changes:

```
{
  "patientId": "35212677",
  "_meta": {
    "chartId": "35212677",
    "timestamp": "2024-12-13T..."
  },
  "medications": {
    "success": true,
    "data": [...],               ← Normalized medication array
    "endpoint": "https://..."
  },
  "problems": {
    "success": true,
    "data": [...],               ← Normalized problem array
    "endpoint": "https://..."
  },
  "vitals": {
    "success": false,
    "error": "HTTP 500..."       ← Failed fetch
  }
}
```

---

## 6. Interpreter Implementation Guide

### Medication Interpreter - Correct Path
```python
def extract_medications(payload: dict) -> list:
    """
    Extract medications from Athena active_medications payload.

    CRITICAL: Drug names are at Events[].Instance.DisplayName,
    NOT at the top level of the medication object.
    """
    results = []

    # Navigate to medications array
    am = payload.get('active_medications', {})
    medications = am.get('Medications', [])

    for med in medications:
        events = med.get('Events', [])

        for event in events:
            instance = event.get('Instance', {})

            if instance:
                results.append({
                    'name': instance.get('DisplayName', ''),
                    'sig': instance.get('UnstructuredSig', ''),
                    'quantity': instance.get('QuantityValue'),
                    'refills': instance.get('RefillsAllowed'),
                    'prescriber': instance.get('PrescriberName', ''),
                    'pharmacy': instance.get('PharmacyName', ''),
                    'therapeutic_class': instance.get('Medication', {}).get('TherapeuticClass', '')
                })
                break  # Only need first event per medication

    return results
```

### Problem Interpreter - Correct Path
```python
def extract_problems(payload: dict) -> list:
    """
    Extract problems from Athena active_problems payload.
    """
    results = []

    ap = payload.get('active_problems', {})
    problems = ap.get('Problems', [])

    for prob in problems:
        icd_codes = []
        for mapping in prob.get('PatientSnomedICD10s', []):
            icd_codes.append({
                'code': mapping.get('DIAGNOSISCODE', ''),
                'description': mapping.get('FULLDESCRIPTION', '')
            })

        results.append({
            'name': prob.get('Name', ''),
            'snomed_code': prob.get('Code', {}).get('Code', ''),
            'snomed_desc': prob.get('Code', {}).get('Description', ''),
            'icd10_codes': icd_codes,
            'is_primary': prob.get('Primary', False),
            'status': prob.get('Status')
        })

    return results
```

---

## 7. Endpoint Priority for Capture

| Priority | Endpoint Pattern | Clinical Value | Capture Status |
|----------|-----------------|----------------|----------------|
| 1 | `sources=active_medications` | Antithrombotic monitoring | ✓ 8 events |
| 2 | `sources=active_problems` | Disease burden, risk | ✓ 4 events |
| 3 | `sources=allergies` | Contrast/drug allergies | ⚠ 0 events |
| 4 | `sources=measurements` | Vitals/hemodynamics | ⚠ Low yield |
| 5 | `sources=historical_problems` | Surgical history | ✓ 3 events |

---

## 8. Known Issues

1. **HTTP 500 Errors**: Active fetch gets rate-limited, resulting in empty data
2. **Allergy Capture**: Not triggering from passive intercepts - need tab navigation
3. **Lab Results**: Endpoint structure unknown - needs separate capture session
4. **Vital Signs**: Low yield from current capture - may need encounter context

---

## Appendix: Raw Event Counts by Category

```
active_fetch:     332 (40.9%)  ← Synthetic markers
athena_data:      139 (17.1%)  ← Generic ax/data calls
encounter:        115 (14.2%)  ← Visit/session data
document:          55 (6.8%)   ← Clinical documents
lab:               55 (6.8%)   ← Lab-related
medication:        25 (3.1%)   ← Drug data
demographic:       23 (2.8%)   ← Patient info
vital:             20 (2.5%)   ← Measurements
problem:           18 (2.2%)   ← Diagnoses
allergy:            8 (1.0%)   ← Allergies
```
