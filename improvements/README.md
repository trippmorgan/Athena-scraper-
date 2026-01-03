# Self-Improving Feedback Loop

The EHR Bridge AI Team includes a feedback loop that learns from observed traffic and generates code improvements automatically.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    FEEDBACK LOOP                                │
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │ OBSERVE  │───▶│ ANALYZE  │───▶│ GENERATE │───▶│  APPLY   │ │
│   │          │    │          │    │          │    │          │ │
│   │ Traffic  │    │ Patterns │    │ Code     │    │ Review   │ │
│   │ Errors   │    │ Schemas  │    │ Fixes    │    │ Approve  │ │
│   │ Failures │    │ Changes  │    │ Parsers  │    │ Apply    │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│        │                                               │       │
│        └───────────────── LEARN ───────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

## Improvement Types

### 1. Endpoint Discovery
When new API patterns are detected in Athena traffic:

```json
{
  "type": "new_endpoint",
  "pattern": "/api/chart/{patientId}/vitals",
  "discovered_at": "2024-01-15T10:30:00Z",
  "sample_response": { "vitals": [...] }
}
```

**Generated:** New fetch function + parser

### 2. Schema Changes
When response structure changes:

```json
{
  "type": "schema_change",
  "endpoint": "/api/chart/{id}/medications",
  "old_field": "dosage",
  "new_field": "dose_quantity",
  "detected_at": "2024-01-15T11:00:00Z"
}
```

**Generated:** Updated parser with field mapping

### 3. Error Fixes
When parsing fails:

```json
{
  "type": "parse_error",
  "file": "vascular_parser.py",
  "line": 142,
  "error": "KeyError: 'medication_name'",
  "context": { "actual_key": "med_name" }
}
```

**Generated:** Fixed parser with null checks

### 4. Optimizations
When performance issues detected:

```json
{
  "type": "optimization",
  "issue": "N+1 query pattern",
  "file": "active_routes.py",
  "suggestion": "Batch fetch medications"
}
```

**Generated:** Optimized code with batching

## Directory Structure

```
.improvements/
├── pending/           # Awaiting review
│   ├── 001_new_vitals_endpoint.md
│   └── 002_fix_medication_parser.md
├── applied/           # Accepted and applied
│   └── 001_new_vitals_endpoint.md
└── rejected/          # Declined
    └── 002_fix_medication_parser.md
```

## Improvement File Format

Each improvement is a markdown file:

```markdown
# Improvement: New Vitals Endpoint

**Type:** new_endpoint
**Priority:** medium
**Generated:** 2024-01-15T10:30:00Z
**Agent:** Codex (Principal Engineer)

## Analysis

Discovered new endpoint pattern during observation:
- URL: `/api/chart/12345/vitals`
- Method: GET
- Response contains: BP, HR, RR, SpO2, Temp

## Proposed Changes

### File: extension/activeFetcher.js

```javascript
// Add after line 45
async function fetchVitals(patientId) {
  return await fetchWithSession(`/api/chart/${patientId}/vitals`);
}
```

### File: backend/vascular_parser.py

```python
# Add after line 120
def parse_vitals(data: dict) -> VitalsRecord:
    return VitalsRecord(
        bp_systolic=data.get('bp', {}).get('systolic'),
        bp_diastolic=data.get('bp', {}).get('diastolic'),
        heart_rate=data.get('hr'),
        resp_rate=data.get('rr'),
        spo2=data.get('spo2'),
        temperature=data.get('temp')
    )
```

## Actions

- [ ] Review changes
- [ ] Apply to codebase
- [ ] Test with sample data
```

## Using the Feedback Loop

### CLI Commands

```bash
# List pending improvements
python -m backend.improvement_engine list

# View specific improvement
python -m backend.improvement_engine show 001

# Apply improvement
python -m backend.improvement_engine apply 001

# Reject improvement
python -m backend.improvement_engine reject 001 --reason "Not needed"
```

### VS Code Extension

1. Open Command Palette (Cmd+Shift+P)
2. Type "EHR Bridge: Review Improvements"
3. Browse pending improvements
4. Click "Apply" or "Reject" for each

### API Endpoints

```bash
# List pending
GET /ai/improvements/pending

# Get improvement details
GET /ai/improvements/001

# Apply improvement
POST /ai/improvements/001/apply

# Reject improvement
POST /ai/improvements/001/reject
```

## Configuration

In `backend/improvement_engine.py`:

```python
IMPROVEMENT_CONFIG = {
    "auto_apply": False,           # Require manual review
    "min_confidence": 0.8,         # Only suggest high-confidence changes
    "max_pending": 20,             # Limit pending queue
    "notify_on_critical": True,    # Alert for critical fixes
    "allowed_file_types": [        # Files that can be modified
        ".py", ".js", ".ts", ".tsx"
    ]
}
```

## Security

- Improvements NEVER auto-apply (require human review)
- Changes are sandboxed and reversible
- All modifications logged for audit trail
- No PHI included in improvement files
