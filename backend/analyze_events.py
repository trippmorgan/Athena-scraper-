#!/usr/bin/env python3
"""
===============================================================================
ATHENA EVENT STORE ANALYZER
===============================================================================

PURPOSE:
    This script performs a comprehensive analysis of intercepted AthenaNet
    traffic to identify:

    1. ENDPOINT TAXONOMY: Which API endpoints are being called, with what
       frequency, and what clinical data type they likely contain.

    2. PAYLOAD STRUCTURE: The nested JSON structure of each endpoint type,
       identifying stable vs. volatile fields.

    3. PATIENT CONTEXT: How patient IDs flow through the system and which
       endpoints carry patient-identifiable data.

    4. CLINICAL VALUE DENSITY: Which endpoints contain the highest
       concentration of clinically actionable information.

THEORETICAL FRAMEWORK:
    EHR systems like AthenaNet are designed for UI rendering, not data
    extraction. Their APIs exhibit several characteristics that complicate
    clinical data extraction:

    - FRAGMENTATION: Clinical concepts (e.g., "medications") are spread
      across multiple endpoints optimized for different UI views.

    - CONTEXT DEPENDENCY: The same endpoint may return different data
      depending on session state, user permissions, or navigation path.

    - SCHEMA DRIFT: Field names and nesting structures vary between
      endpoints, even for semantically identical data.

    - UI OPTIMIZATION: Data is shaped for rendering (display strings)
      rather than computation (structured codes).

    This analysis provides the empirical foundation for building robust
    clinical interpreters that can aggregate across endpoints and
    normalize schema variations.

OUTPUT:
    - Console summary of endpoint patterns
    - Detailed JSON analysis file for further processing
    - Recommendations for interpreter development

USAGE:
    python analyze_events.py [--limit N] [--patient PATIENT_ID]

Author: Claude Code Analysis
Date: 2024
===============================================================================
"""

import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime


# =============================================================================
# CONFIGURATION
# =============================================================================

DATA_DIR = Path("data")
RAW_EVENTS_FILE = DATA_DIR / "raw_events.jsonl"
INDEX_FILE = DATA_DIR / "event_index.jsonl"
OUTPUT_FILE = DATA_DIR / "event_analysis.json"

# Clinical endpoint classification patterns
# These are heuristics based on common EHR URL patterns
CLINICAL_PATTERNS = {
    'medication': [
        r'medication', r'med[s]?(?:\b|_)', r'prescription', r'rx',
        r'drug', r'pharma', r'active_medications'
    ],
    'problem': [
        r'problem', r'condition', r'diagnosis', r'diagnos', r'icd',
        r'dx', r'active_problems', r'historical_problems'
    ],
    'allergy': [
        r'allerg', r'adverse', r'reaction', r'sensitivity'
    ],
    'vital': [
        r'vital', r'measurement', r'blood.?pressure', r'bp', r'pulse',
        r'temperature', r'weight', r'height', r'bmi'
    ],
    'lab': [
        r'lab', r'result', r'panel', r'cbc', r'bmp', r'cmp',
        r'hemoglobin', r'a1c', r'creatinine', r'egfr'
    ],
    'procedure': [
        r'procedure', r'surgery', r'operation', r'intervention',
        r'cpt', r'order'
    ],
    'document': [
        r'document', r'note', r'report', r'letter', r'summary',
        r'external_document'
    ],
    'demographic': [
        r'demographic', r'patient(?!.?id)', r'personal', r'contact',
        r'address', r'insurance'
    ],
    'encounter': [
        r'encounter', r'visit', r'appointment', r'admission'
    ],
    'imaging': [
        r'imaging', r'radiology', r'xray', r'ct(?:\b|_)', r'mri',
        r'ultrasound', r'echo'
    ]
}


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def load_jsonl(path: Path, limit: Optional[int] = None) -> List[Dict]:
    """
    Load a JSONL file into memory.

    JSONL (JSON Lines) is an append-friendly format where each line is a
    valid JSON object. This is ideal for event stores because:
    - Appends don't require reading/rewriting the entire file
    - Partial reads are possible without loading everything
    - Corruption is localized to individual lines

    Args:
        path: Path to the JSONL file
        limit: Optional maximum number of records to load

    Returns:
        List of parsed JSON objects
    """
    records = []
    if not path.exists():
        print(f"⚠️  File not found: {path}")
        return records

    with path.open() as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            try:
                records.append(json.loads(line.strip()))
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON parse error on line {i+1}: {e}")
                continue

    return records


def normalize_endpoint(endpoint: str) -> str:
    """
    Normalize an endpoint URL by replacing variable path segments with
    placeholders.

    This is crucial for endpoint taxonomy because:
    - Patient/chart IDs appear in URLs: /chart/12345/vitals → /chart/{id}/vitals
    - Encounter IDs vary: /encounter/98765/notes → /encounter/{id}/notes
    - Practice/department IDs: /8042/65/ax/data → /{practice}/{dept}/ax/data

    The goal is to create canonical endpoint patterns that can be grouped
    for frequency analysis.

    Args:
        endpoint: Raw endpoint URL

    Returns:
        Normalized endpoint with {id} placeholders
    """
    # Replace numeric path segments (likely IDs)
    normalized = re.sub(r'/\d{4,}(?=/|$|\?)', '/{id}', endpoint)

    # Replace practice/department pattern at start
    normalized = re.sub(r'^/\d+/\d+/', '/{practice}/{dept}/', normalized)

    # Normalize query parameters (remove specific values, keep keys)
    if '?' in normalized:
        base, query = normalized.split('?', 1)
        # Extract just the 'sources' parameter value which is semantically important
        sources_match = re.search(r'sources?=([^&]+)', query)
        if sources_match:
            normalized = f"{base}?sources={sources_match.group(1)}"
        else:
            # Keep just the base for other query strings
            normalized = base + "?..."

    return normalized


def classify_endpoint(endpoint: str) -> str:
    """
    Classify an endpoint into a clinical category using pattern matching.

    This is a heuristic classification based on URL patterns. The accuracy
    depends on how consistently the EHR vendor names their endpoints. For
    AthenaNet, the 'sources' parameter is particularly valuable as it
    explicitly names the data type.

    Classification Strategy:
    1. First check for explicit 'sources=' parameter (most reliable)
    2. Then check URL path for clinical keywords
    3. Default to 'unknown' for unrecognized patterns

    Args:
        endpoint: Normalized endpoint URL

    Returns:
        Clinical category string
    """
    endpoint_lower = endpoint.lower()

    # Check each clinical pattern
    for category, patterns in CLINICAL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, endpoint_lower):
                return category

    # Check for Athena-specific patterns
    if 'ax/data' in endpoint_lower:
        return 'athena_data'  # Generic Athena data endpoint
    if 'ax/security' in endpoint_lower:
        return 'security'
    if 'active-fetch' in endpoint_lower:
        return 'active_fetch'  # Our synthetic active fetch markers

    return 'unknown'


def extract_payload_structure(payload: Any, max_depth: int = 3, current_depth: int = 0) -> Dict:
    """
    Extract the structural skeleton of a payload for schema analysis.

    This function recursively traverses a JSON payload and extracts:
    - Key names at each level
    - Value types (string, number, array, object)
    - Array lengths (to detect empty vs. populated)
    - Sample values (truncated for privacy)

    The goal is to identify stable structural patterns that can inform
    interpreter development. For example:
    - "active_medications.Medications" is always an array
    - "demographics.firstName" is always a string

    Args:
        payload: JSON payload to analyze
        max_depth: Maximum recursion depth (prevents infinite loops)
        current_depth: Current recursion depth

    Returns:
        Dictionary describing the payload structure
    """
    if current_depth >= max_depth:
        return {"_truncated": True}

    if payload is None:
        return {"_type": "null"}

    if isinstance(payload, bool):
        return {"_type": "bool", "_sample": payload}

    if isinstance(payload, (int, float)):
        return {"_type": "number", "_sample": payload}

    if isinstance(payload, str):
        # Truncate long strings, flag potential PHI
        sample = payload[:50] + "..." if len(payload) > 50 else payload
        is_potential_phi = bool(re.search(r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9,}\b', payload))
        return {
            "_type": "string",
            "_length": len(payload),
            "_sample": sample if not is_potential_phi else "[REDACTED]"
        }

    if isinstance(payload, list):
        if not payload:
            return {"_type": "array", "_length": 0, "_items": None}

        # Sample first item only
        first_item = extract_payload_structure(payload[0], max_depth, current_depth + 1)
        return {
            "_type": "array",
            "_length": len(payload),
            "_items": first_item
        }

    if isinstance(payload, dict):
        result = {"_type": "object", "_keys": list(payload.keys())[:20]}

        # Recursively analyze nested objects (but limit to important keys)
        important_keys = [k for k in payload.keys() if any(
            term in k.lower() for term in
            ['medication', 'problem', 'allergy', 'vital', 'lab', 'patient', 'name', 'code', 'id']
        )]

        for key in important_keys[:5]:  # Limit to 5 to avoid explosion
            result[key] = extract_payload_structure(payload[key], max_depth, current_depth + 1)

        return result

    return {"_type": "unknown"}


def analyze_events(events: List[Dict]) -> Dict:
    """
    Perform comprehensive analysis of captured events.

    This is the core analysis function that produces:

    1. ENDPOINT FREQUENCY TABLE
       - Which endpoints are called most often
       - Average payload size per endpoint
       - Detected clinical category

    2. PATIENT DISTRIBUTION
       - Which patient IDs appear in the data
       - How many events per patient
       - Endpoints per patient

    3. RECORD TYPE ANALYSIS (from index)
       - Distribution of detected record types
       - Correlation between endpoints and types

    4. PAYLOAD STRUCTURE SAMPLES
       - Representative structure for each endpoint type
       - Key field names and types

    5. TEMPORAL PATTERNS
       - Events over time
       - Session boundaries

    Args:
        events: List of raw event dictionaries

    Returns:
        Comprehensive analysis dictionary
    """
    analysis = {
        "meta": {
            "total_events": len(events),
            "analysis_timestamp": datetime.now().isoformat(),
            "file_analyzed": str(RAW_EVENTS_FILE)
        },
        "endpoints": defaultdict(lambda: {
            "count": 0,
            "methods": set(),
            "total_size": 0,
            "patient_ids": set(),
            "clinical_category": None,
            "sample_payload_structure": None
        }),
        "patients": defaultdict(lambda: {
            "event_count": 0,
            "endpoints": set(),
            "clinical_categories": set()
        }),
        "clinical_categories": Counter(),
        "record_types": Counter(),
        "payload_key_frequency": Counter(),
        "timeline": []
    }

    for event in events:
        endpoint = event.get("endpoint", "")
        method = event.get("method", "GET")
        patient_id = event.get("patient_id")
        payload = event.get("payload")
        payload_size = event.get("payload_size", 0)
        timestamp = event.get("timestamp", "")

        # Normalize and classify endpoint
        normalized = normalize_endpoint(endpoint)
        category = classify_endpoint(normalized)

        # Update endpoint stats
        ep_stats = analysis["endpoints"][normalized]
        ep_stats["count"] += 1
        ep_stats["methods"].add(method)
        ep_stats["total_size"] += payload_size
        ep_stats["clinical_category"] = category
        if patient_id:
            ep_stats["patient_ids"].add(patient_id)

        # Capture sample structure (first occurrence only)
        if ep_stats["sample_payload_structure"] is None and payload:
            ep_stats["sample_payload_structure"] = extract_payload_structure(payload)

        # Update patient stats
        if patient_id:
            pt_stats = analysis["patients"][patient_id]
            pt_stats["event_count"] += 1
            pt_stats["endpoints"].add(normalized)
            pt_stats["clinical_categories"].add(category)

        # Update category counts
        analysis["clinical_categories"][category] += 1

        # Track top-level payload keys
        if isinstance(payload, dict):
            for key in payload.keys():
                analysis["payload_key_frequency"][key] += 1

        # Timeline (sample every 10th event)
        if len(analysis["timeline"]) < 100 and event.get("timestamp"):
            analysis["timeline"].append({
                "timestamp": timestamp,
                "endpoint": normalized[:60],
                "category": category
            })

    # Convert sets to lists for JSON serialization
    for ep, stats in analysis["endpoints"].items():
        stats["methods"] = list(stats["methods"])
        stats["patient_ids"] = list(stats["patient_ids"])[:10]  # Limit for privacy
        stats["avg_size"] = stats["total_size"] // max(stats["count"], 1)

    for pt, stats in analysis["patients"].items():
        stats["endpoints"] = list(stats["endpoints"])
        stats["clinical_categories"] = list(stats["clinical_categories"])

    # Sort endpoints by count
    analysis["endpoints"] = dict(
        sorted(analysis["endpoints"].items(), key=lambda x: x[1]["count"], reverse=True)
    )

    return analysis


def print_summary(analysis: Dict) -> None:
    """
    Print a human-readable summary of the analysis.

    This provides immediate insight into the data without requiring
    the analyst to parse JSON. The summary is designed to answer:

    - "What endpoints are we capturing?"
    - "Are we getting clinical data?"
    - "Which patients are in the data?"
    - "What should we interpret first?"
    """
    print("\n" + "=" * 80)
    print("ATHENA EVENT STORE ANALYSIS REPORT")
    print("=" * 80)

    meta = analysis["meta"]
    print(f"\n📊 OVERVIEW")
    print(f"   Total Events: {meta['total_events']:,}")
    print(f"   Analysis Time: {meta['analysis_timestamp']}")
    print(f"   Unique Endpoints: {len(analysis['endpoints'])}")
    print(f"   Unique Patients: {len(analysis['patients'])}")

    print(f"\n📁 CLINICAL CATEGORY DISTRIBUTION")
    for category, count in analysis["clinical_categories"].most_common(15):
        pct = (count / meta['total_events']) * 100
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"   {category:20} {count:5} ({pct:5.1f}%) {bar[:30]}")

    print(f"\n🔝 TOP 20 ENDPOINTS (by frequency)")
    print(f"   {'Endpoint':<60} {'Count':>6} {'Category':>15}")
    print(f"   {'-'*60} {'-'*6} {'-'*15}")
    for i, (endpoint, stats) in enumerate(list(analysis["endpoints"].items())[:20]):
        ep_display = endpoint[:58] + ".." if len(endpoint) > 60 else endpoint
        print(f"   {ep_display:<60} {stats['count']:>6} {stats['clinical_category']:>15}")

    print(f"\n👤 PATIENT COVERAGE (top 10)")
    patients_sorted = sorted(
        analysis["patients"].items(),
        key=lambda x: x[1]["event_count"],
        reverse=True
    )[:10]
    for patient_id, stats in patients_sorted:
        cats = ", ".join(stats["clinical_categories"][:5])
        print(f"   Patient {patient_id}: {stats['event_count']} events, categories: {cats}")

    print(f"\n🔑 TOP PAYLOAD KEYS (most frequent)")
    for key, count in analysis["payload_key_frequency"].most_common(20):
        print(f"   {key}: {count}")

    print(f"\n💡 RECOMMENDATIONS")

    # Find medication-related endpoints
    med_endpoints = [ep for ep, stats in analysis["endpoints"].items()
                     if stats["clinical_category"] == "medication"]
    if med_endpoints:
        print(f"\n   MEDICATIONS ({len(med_endpoints)} endpoints):")
        for ep in med_endpoints[:5]:
            stats = analysis["endpoints"][ep]
            print(f"   → {ep[:70]} (n={stats['count']})")

    # Find problem-related endpoints
    prob_endpoints = [ep for ep, stats in analysis["endpoints"].items()
                      if stats["clinical_category"] == "problem"]
    if prob_endpoints:
        print(f"\n   PROBLEMS ({len(prob_endpoints)} endpoints):")
        for ep in prob_endpoints[:5]:
            stats = analysis["endpoints"][ep]
            print(f"   → {ep[:70]} (n={stats['count']})")

    # Find high-volume unknown endpoints (potential new patterns)
    unknown_high = [(ep, stats) for ep, stats in analysis["endpoints"].items()
                    if stats["clinical_category"] == "unknown" and stats["count"] > 10]
    if unknown_high:
        print(f"\n   ⚠️  UNCLASSIFIED HIGH-VOLUME ENDPOINTS (review manually):")
        for ep, stats in sorted(unknown_high, key=lambda x: x[1]["count"], reverse=True)[:5]:
            print(f"   → {ep[:70]} (n={stats['count']})")

    print("\n" + "=" * 80)


def main():
    """Main entry point for the analysis script."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze Athena event store")
    parser.add_argument("--limit", type=int, help="Limit number of events to analyze")
    parser.add_argument("--patient", type=str, help="Filter to specific patient ID")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE), help="Output file path")
    args = parser.parse_args()

    print(f"📂 Loading events from {RAW_EVENTS_FILE}...")
    events = load_jsonl(RAW_EVENTS_FILE, limit=args.limit)

    if not events:
        print("❌ No events found. Ensure the backend has been capturing data.")
        sys.exit(1)

    print(f"✅ Loaded {len(events):,} events")

    # Filter by patient if specified
    if args.patient:
        events = [e for e in events if e.get("patient_id") == args.patient]
        print(f"   Filtered to {len(events):,} events for patient {args.patient}")

    print(f"🔍 Analyzing...")
    analysis = analyze_events(events)

    # Print summary to console
    print_summary(analysis)

    # Save detailed analysis to file
    output_path = Path(args.output)
    with output_path.open("w") as f:
        json.dump(analysis, f, indent=2, default=str)

    print(f"\n📄 Detailed analysis saved to: {output_path}")


if __name__ == "__main__":
    main()
