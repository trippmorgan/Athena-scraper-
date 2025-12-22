"""
Shadow EHR Backend: FastAPI WebSocket Server

This is the Normalization Engine (Tier 2) that:
1. Accepts WebSocket connections from Chrome extension (/ws/chrome)
2. Accepts WebSocket connections from React frontend (/ws/frontend)
3. Converts AthenaNet JSON to FHIR R4 resources
4. Relays processed data to the frontend
"""

# Load environment variables FIRST before any other imports
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (parent of backend/)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

import asyncio
import json
import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pythonjsonlogger import jsonlogger
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import asynccontextmanager
from active_routes import router as active_router, set_main_cache
from event_store import EventStore
from event_indexer import EventIndexer, create_indexer, INDEXER_VERSION
from narrative_engine import get_narrative_engine, NarrativeRequest
from clinical_interpreters import (
    get_registry, interpret_event, get_interpreter_versions,
    InterpreterRegistry
)
from ai_summarizer import (
    get_summarizer, generate_context, generate_briefing,
    generate_med_alert, ClinicalSummarizer, SummaryType
)
from provenance import Provenance, sha256_json
from files import (
    SessionContext, get_session_context, set_session_context,
    DownloadManager, get_download_manager, DiskArtifactStore, get_artifact_store
)
from artifacts import (
    extract_document_refs, get_artifact_detector, get_artifact_index,
    DocumentRef, MissingDocument
)
from vascular_extractors import (
    get_vascular_extractor, extract_vascular_assessment,
    VascularAssessment, PADExtractor, CarotidExtractor, AAAExtractor,
    AntithromboticBridgingCalculator, ANTITHROMBOTIC_DATABASE
)
from vascular_parser import build_vascular_profile

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from vision_discovery import router as discovery_router

from schemas import (
    AthenaPayload, Patient, LogEntry, WebSocketMessage, ScraperMode
)
from fhir_converter import (
    convert_to_fhir, extract_patient_id, create_log_entry,
    build_patient_from_aggregated_data
)

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

# Create custom formatter with colors for terminal
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    BOLD = '\033[1m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{self.BOLD}{record.levelname}{self.RESET}"
        record.msg = f"{color}{record.msg}{self.RESET}"
        # Make sure standard formatter runs on a string
        if hasattr(record, 'msg') and not isinstance(record.msg, str):
            record.msg = str(record.msg)
        return super().format(record)

# Configure root logger
def setup_logging():
    """Setup comprehensive logging for the application."""

    # Create logger
    logger = logging.getLogger("shadow-ehr")
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers = []

    # Console handler with colors for readability during development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO) # Keep console less verbose
    console_formatter = ColoredFormatter(
        '%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Rotating file handler for persistent, structured JSON logs
    # Rotates daily, keeps 7 days of logs.
    log_file = "shadow_ehr.log"
    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=7, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG) # Full verbosity for file logs

    # Use a custom format for the JSON logs
    # Including standard log attributes and allowing for extra context
    json_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s %(lineno)d %(funcName)s',
        rename_fields={'levelname': 'level', 'asctime': 'timestamp'}
    )
    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)

    # Add a handler for a separate, non-JSON error log if needed
    error_handler = logging.FileHandler('shadow_ehr.error.log', mode='a')
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    error_handler.setFormatter(error_formatter)
    logger.addHandler(error_handler)

    return logger

logger = setup_logging()

# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections for Chrome extension and Frontend clients."""

    def __init__(self, event_store: EventStore, event_indexer: EventIndexer):
        # Active connections
        self.chrome_connections: List[WebSocket] = []
        self.frontend_connections: List[WebSocket] = []

        # Current scraper mode
        self.mode: ScraperMode = ScraperMode.PASSIVE

        # Patient data cache (in-memory, keyed by patient_id)
        self.patient_cache: Dict[str, Dict[str, Any]] = {}

        # Current patient context (for associating data without patient ID in URL)
        self.current_patient_id: Optional[str] = None

        # Statistics
        self.stats = {
            'payloads_received': 0,
            'payloads_processed': 0,
            'errors': 0,
            'patients_cached': 0,
            'events_indexed': 0
        }

        # Event store for raw and interpreted records
        self.event_store = event_store

        # Event indexer (Layer 2) for classification
        self.event_indexer = event_indexer

        # Clinical interpreters (Layer 3) for extraction
        self.interpreter_registry = get_registry()

        # Interpreted clinical records cache (patient_id -> category -> records)
        self.clinical_cache: Dict[str, Dict[str, List]] = {}

        # Endpoint tracking for discovery analysis
        self.endpoint_history: Dict[str, Dict] = {}  # URL pattern -> {count, methods, sizes, record_type}

        logger.info("ConnectionManager initialized")
        logger.info(f"  Event Indexer: v{INDEXER_VERSION}")
        logger.info(f"  Clinical Interpreters: {list(self.interpreter_registry.get_versions().keys())}")

    async def connect_chrome(self, websocket: WebSocket):
        """Accept and register a Chrome extension connection."""
        await websocket.accept()
        self.chrome_connections.append(websocket)

        logger.info("=" * 60)
        logger.info("CHROME EXTENSION CONNECTED")
        logger.info(f"  Remote: {websocket.client}")
        logger.info(f"  Total Chrome connections: {len(self.chrome_connections)}")
        logger.info("=" * 60)

        # Notify frontend about Chrome connection
        await self.broadcast_to_frontend({
            "type": "STATUS_UPDATE",
            "data": "CONNECTED"
        })

    async def connect_frontend(self, websocket: WebSocket):
        """Accept and register a frontend connection."""
        await websocket.accept()
        self.frontend_connections.append(websocket)

        logger.info("=" * 60)
        logger.info("FRONTEND CLIENT CONNECTED")
        logger.info(f"  Remote: {websocket.client}")
        logger.info(f"  Total frontend connections: {len(self.frontend_connections)}")
        logger.info("=" * 60)

    def disconnect_chrome(self, websocket: WebSocket):
        """Remove a Chrome extension connection."""
        if websocket in self.chrome_connections:
            self.chrome_connections.remove(websocket)

        logger.warning("=" * 60)
        logger.warning("CHROME EXTENSION DISCONNECTED")
        logger.warning(f"  Remaining connections: {len(self.chrome_connections)}")
        logger.warning("=" * 60)

    def disconnect_frontend(self, websocket: WebSocket):
        """Remove a frontend connection."""
        if websocket in self.frontend_connections:
            self.frontend_connections.remove(websocket)

        logger.warning("FRONTEND CLIENT DISCONNECTED")
        logger.warning(f"  Remaining connections: {len(self.frontend_connections)}")

    async def broadcast_to_frontend(self, message: dict):
        """Send a message to all connected frontend clients."""
        if not self.frontend_connections:
            logger.debug("No frontend clients to broadcast to")
            return

        message_str = json.dumps(message)
        msg_type = message.get('type', 'UNKNOWN')
        msg_size = len(message_str)

        logger.debug(f"Broadcasting to {len(self.frontend_connections)} frontend(s): {msg_type} ({msg_size} bytes)")

        disconnected = []
        success_count = 0

        for connection in self.frontend_connections:
            try:
                await connection.send_text(message_str)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send to frontend: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect_frontend(conn)

        if success_count > 0:
            logger.debug(f"Broadcast complete: {success_count}/{len(self.frontend_connections)} successful")

    async def process_athena_payload(self, data: dict):
        """
        Process incoming AthenaNet payload from Chrome extension.
        """
        self.stats['payloads_received'] += 1

        try:
            endpoint = data.get('endpoint', '')
            method = data.get('method', 'GET')
            payload = data.get('payload')
            payload_size = len(json.dumps(payload)) if payload else 0
            status = data.get('status')
            raw_timestamp = data.get('timestamp') or datetime.utcnow().isoformat()
            source = data.get('source', 'chrome_interceptor')

            # Extract patient ID from multiple locations (active fetch includes it in _meta or raw wrapper)
            raw_patient = data.get('patientId')
            if not raw_patient and isinstance(payload, dict):
                raw_patient = payload.get('patientId')
                # Check inside 'raw' wrapper (compound payloads from active fetch)
                if not raw_patient and 'raw' in payload and isinstance(payload.get('raw'), dict):
                    raw_patient = payload['raw'].get('patientId')
                    if not raw_patient and '_meta' in payload['raw']:
                        raw_patient = payload['raw'].get('_meta', {}).get('chartId')
                if not raw_patient and '_meta' in payload:
                    raw_patient = payload.get('_meta', {}).get('chartId')

            logger.info("-" * 60)
            logger.info("INCOMING ATHENA PAYLOAD")
            logger.info(f"  Method: {method}")
            logger.info(f"  Endpoint: {endpoint[:80]}{'...' if len(endpoint) > 80 else ''}")
            logger.info(f"  Patient ID (from payload): {raw_patient or 'none'}")
            logger.info(f"  Payload size: {payload_size} bytes")
            logger.debug(f"  Raw payload preview: {str(payload)[:200]}...")

            # Persist the raw payload before any transformation
            raw_event = await self.event_store.append_raw_event({
                'timestamp': raw_timestamp,
                'endpoint': endpoint,
                'method': method,
                'status': status,
                'patient_id': raw_patient,
                'payload_size': payload_size,
                'payload': payload,
                'source': source,
            })
            logger.info(f"Raw event stored: {raw_event['id']}")

            # Convert to FHIR
            logger.info("Converting to FHIR R4...")
            record_type, fhir_resource = convert_to_fhir(endpoint, method, payload)
            logger.info(f"  🏷️  RECORD TYPE DETECTED: {record_type.upper()}")
            if record_type == 'unknown':
                logger.warning(f"  ⚠️  UNKNOWN record type - data may not be categorized correctly!")
                logger.warning(f"  ⚠️  URL: {endpoint[:100]}")

            # Create log entry for frontend
            log_entry = create_log_entry(endpoint, method, payload, fhir_resource)
            logger.debug(f"  Log entry created: {log_entry.id}")

            # Send log entry to frontend
            await self.broadcast_to_frontend({
                "type": "LOG_ENTRY",
                "data": log_entry.model_dump()
            })
            logger.info("LOG_ENTRY sent to frontend")

            # Extract patient ID and update cache
            patient_id = raw_patient or extract_patient_id(endpoint)
            is_active_fetch = 'active-fetch' in endpoint

            logger.info(f"Processing payload. Patient ID: {patient_id}, Is Active Fetch: {is_active_fetch}, Current Context: {self.current_patient_id}")
            logger.info(f"Cache state BEFORE update: {list(self.patient_cache.keys())}")


            if patient_id:
                # If a patient ID is present in the payload, it's the source of truth.
                if is_active_fetch and self.current_patient_id != patient_id:
                    logger.warning(f"  New active fetch detected. Changing patient context from '{self.current_patient_id}' to '{patient_id}'.")
                
                self.current_patient_id = patient_id
                await self.update_patient_cache(patient_id, record_type, fhir_resource)
            
            elif self.current_patient_id and not is_active_fetch and record_type != 'unknown':
                # For passive events WITHOUT an ID, use the last known patient context.
                logger.info(f"  No patient ID in passive event. Using current patient context: {self.current_patient_id}")
                await self.update_patient_cache(self.current_patient_id, record_type, fhir_resource)
            
            else:
                # Discard if we have no context, or if it's an active fetch without an ID (which is an error state).
                logger.warning(f"  Could not determine patient context for this event. Discarding.")
                logger.warning(f"    - Endpoint: {endpoint}")
                logger.warning(f"    - Is Active Fetch: {is_active_fetch}")
                logger.warning(f"    - Current Context: {self.current_patient_id}")

            # Index event using Layer 2 Event Indexer (replaces simple append_index_entry)
            # The indexer provides:
            #   - More accurate clinical category classification
            #   - Extraction hints for downstream interpreters
            #   - Confidence scores for classification quality
            #   - Source type detection (passive vs active fetch)
            index_entry = await self.event_indexer.index_event({
                'id': raw_event['id'],
                'endpoint': endpoint,
                'payload': payload,
                'timestamp': raw_event['timestamp'],
                'patient_id': patient_id or self.current_patient_id,
            })
            self.stats['events_indexed'] += 1
            logger.debug(f"  Indexed as: {index_entry.category}/{index_entry.subcategory or '-'} (conf={index_entry.confidence:.2f})")

            # Layer 3: Clinical Interpretation
            # Run interpreters on indexed events to extract clinical meaning
            interpretation_results = self.interpreter_registry.interpret_event(
                raw_event={'id': raw_event['id'], 'payload': payload, 'endpoint': endpoint},
                index_entry=index_entry.to_dict()
            )

            # Cache interpreted results by patient and category
            if interpretation_results and (patient_id or self.current_patient_id):
                pid = patient_id or self.current_patient_id
                if pid not in self.clinical_cache:
                    self.clinical_cache[pid] = {'medication': [], 'problem': [], 'vital': [], 'allergy': []}

                for result in interpretation_results:
                    category = result.category
                    if category in self.clinical_cache[pid]:
                        self.clinical_cache[pid][category].extend(result.records)
                        logger.info(f"  🔬 Interpreted {len(result.records)} {category}(s) for patient {pid}")

                        # Broadcast clinical update to frontend
                        await self.broadcast_to_frontend({
                            "type": "CLINICAL_UPDATE",
                            "data": {
                                "patient_id": pid,
                                "category": category,
                                "records": result.records,
                                "interpreter_version": result.interpreter_version,
                                "confidence": result.confidence
                            }
                        })

            # Track endpoint for discovery analysis
            import re
            normalized_endpoint = re.sub(r'/\d+(?=/|$|\?)', '/{id}', endpoint)
            if normalized_endpoint not in self.endpoint_history:
                self.endpoint_history[normalized_endpoint] = {
                    'count': 0, 'methods': set(), 'sizes': [], 'record_type': record_type
                }
            self.endpoint_history[normalized_endpoint]['count'] += 1
            self.endpoint_history[normalized_endpoint]['methods'].add(method)
            self.endpoint_history[normalized_endpoint]['sizes'].append(payload_size)

            self.stats['payloads_processed'] += 1
            logger.info(f"Payload processed successfully (Total: {self.stats['payloads_processed']})")

        except Exception as e:
            self.stats['errors'] += 1
            logger.error("=" * 60)
            logger.error("ERROR PROCESSING PAYLOAD")
            logger.error(f"  Error: {str(e)}")
            logger.error(f"  Total errors: {self.stats['errors']}")
            logger.exception("Full traceback:")
            logger.error("=" * 60)

    async def update_patient_cache(self, patient_id: str, record_type: str, fhir_resource: Any):
        """Update the patient cache with new data and emit patient update."""

        logger.info(f"Updating cache for patient {patient_id} with record type {record_type}.")
        is_new_patient = patient_id not in self.patient_cache

        if is_new_patient:
            self.patient_cache[patient_id] = {
                'patient': None,
                'vitals': None,
                'medications': [],
                'problems': [],
                'labs': [],
                'allergies': [],
                'allergy': [],
                'documents': [],
                'notes': [],
                'note': [],
                'procedures': [],
                'imaging': [],
                'unknown': [],  # Store unclassified data for debugging
                'last_update': None
            }
            self.stats['patients_cached'] += 1
            logger.info(f"NEW PATIENT ADDED TO CACHE: {patient_id}")
            logger.info(f"Cache state AFTER adding new patient: {list(self.patient_cache.keys())}")

        cache = self.patient_cache[patient_id]

        # Update appropriate section
        logger.debug(f"Updating cache section: {record_type}")

        if record_type == 'patient':
            if hasattr(fhir_resource, 'dict'):
                cache['patient'] = fhir_resource.model_dump()
            else:
                cache['patient'] = fhir_resource
            logger.info(f"  Patient demographics updated")

        elif record_type == 'vital':
            if hasattr(fhir_resource, 'dict'):
                cache['vitals'] = fhir_resource.model_dump()
            else:
                cache['vitals'] = fhir_resource
            logger.info(f"  Vitals updated")

        elif record_type == 'medication':
            logger.info(f"  💊 MEDICATION DATA RECEIVED - Type: {type(fhir_resource).__name__}")
            if isinstance(fhir_resource, dict):
                logger.info(f"  💊 MEDICATION KEYS: {list(fhir_resource.keys())[:10]}")
                if 'medications' in fhir_resource:
                    meds = fhir_resource['medications']
                    if meds:
                        cache['medications'].extend(meds) if isinstance(meds, list) else cache['medications'].append(meds)
                        logger.info(f"  ✅ Medications updated ({len(cache['medications'])} total meds)")
                    else:
                        logger.warning(f"  ⚠️ Empty medications list in response")
                else:
                    # Try to extract from other keys
                    logger.warning(f"  ⚠️ No 'medications' key - raw keys: {list(fhir_resource.keys())}")
                    # Store raw for debugging
                    cache['medications'].append(fhir_resource)
            elif isinstance(fhir_resource, list):
                cache['medications'].extend(fhir_resource)
                logger.info(f"  ✅ Medications list stored ({len(fhir_resource)} items)")
            else:
                logger.warning(f"  ⚠️ Unexpected medication format: {type(fhir_resource)}")

        elif record_type == 'problem':
            if isinstance(fhir_resource, dict) and 'conditions' in fhir_resource:
                cache['problems'] = fhir_resource['conditions']
                logger.info(f"  Problems updated ({len(cache['problems'])} conditions)")

        elif record_type == 'lab':
            # Store lab results
            if isinstance(fhir_resource, list):
                cache['labs'].extend(fhir_resource)
            else:
                cache['labs'].append(fhir_resource)
            logger.info(f"  Labs updated ({len(cache['labs'])} results)")

        elif record_type == 'allergy':
            # Store allergies
            if isinstance(fhir_resource, list):
                cache['allergies'].extend(fhir_resource)
                cache['allergy'].extend(fhir_resource)
            else:
                cache['allergies'].append(fhir_resource)
                cache['allergy'].append(fhir_resource)
            logger.info(f"  Allergies updated ({len(cache['allergies'])} allergies)")

        elif record_type == 'note':
            # Store notes
            if isinstance(fhir_resource, list):
                cache['notes'].extend(fhir_resource)
                cache['note'].extend(fhir_resource)
            else:
                cache['notes'].append(fhir_resource)
                cache['note'].append(fhir_resource)
            logger.info(f"  Notes updated ({len(cache['notes'])} notes)")

        elif record_type == 'imaging':
            # Store imaging
            if isinstance(fhir_resource, list):
                cache['imaging'].extend(fhir_resource)
            else:
                cache['imaging'].append(fhir_resource)
            logger.info(f"  Imaging updated ({len(cache['imaging'])} studies)")

        elif record_type == 'compound':
            # COMPOUND PAYLOAD: Contains multiple data types (medications, vitals, labs, etc.)
            logger.info(f"  🔀 COMPOUND PAYLOAD PROCESSING")
            if isinstance(fhir_resource, dict):
                # Extract medications
                if 'medications' in fhir_resource and fhir_resource['medications']:
                    meds = fhir_resource['medications']
                    if isinstance(meds, list):
                        cache['medications'].extend(meds)
                    else:
                        cache['medications'].append(meds)
                    logger.info(f"  💊 Extracted {len(meds) if isinstance(meds, list) else 1} medications from compound")

                # Extract vitals
                if 'vitals' in fhir_resource and fhir_resource['vitals']:
                    vitals = fhir_resource['vitals']
                    if hasattr(vitals, 'dict'):
                        cache['vitals'] = vitals.model_dump()
                    else:
                        cache['vitals'] = vitals
                    logger.info(f"  📊 Extracted vitals from compound")

                # Extract labs
                if 'labs' in fhir_resource and fhir_resource['labs']:
                    labs = fhir_resource['labs']
                    if isinstance(labs, list):
                        cache['labs'].extend(labs)
                    else:
                        cache['labs'].append(labs)
                    logger.info(f"  🧪 Extracted {len(labs) if isinstance(labs, list) else 1} labs from compound")

                # Extract conditions/problems
                if 'conditions' in fhir_resource and fhir_resource['conditions']:
                    conditions = fhir_resource['conditions']
                    if isinstance(conditions, list):
                        cache['problems'].extend(conditions)
                    else:
                        cache['problems'].append(conditions)
                    logger.info(f"  🩺 Extracted {len(conditions) if isinstance(conditions, list) else 1} conditions from compound")

                # Extract allergies
                if 'allergies' in fhir_resource and fhir_resource['allergies']:
                    allergies = fhir_resource['allergies']
                    if isinstance(allergies, list):
                        cache['allergies'].extend(allergies)
                        cache['allergy'].extend(allergies)
                    else:
                        cache['allergies'].append(allergies)
                        cache['allergy'].append(allergies)
                    logger.info(f"  ⚠️ Extracted {len(allergies) if isinstance(allergies, list) else 1} allergies from compound")

                logger.info(f"  ✅ COMPOUND PAYLOAD PROCESSED SUCCESSFULLY")

        else:
            # Store unknown types for debugging
            cache['unknown'].append({'type': record_type, 'data': fhir_resource})
            logger.debug(f"  Unknown record type '{record_type}' stored")

            # POST-PROCESS: Extract patient data from unknown items if cache['patient'] is empty
            if isinstance(fhir_resource, dict):
                # Check if this unknown item contains patient demographics
                patient_data = fhir_resource.get('patient')
                if patient_data and isinstance(patient_data, dict) and not cache.get('patient'):
                    # Found patient data in unknown - extract it!
                    logger.info(f"  🔍 RECOVERED patient data from unknown: {patient_data.get('LastName', 'Unknown')}")
                    cache['patient'] = patient_data

        cache['last_update'] = datetime.now().isoformat()

        # FINAL RECOVERY: If cache['patient'] still empty, scan all unknown items
        if not cache.get('patient'):
            for item in cache.get('unknown', []):
                if isinstance(item, dict):
                    data = item.get('data', {})
                    if isinstance(data, dict) and 'patient' in data:
                        patient_info = data['patient']
                        if isinstance(patient_info, dict) and patient_info.get('LastName'):
                            logger.info(f"  🔍 RECOVERED patient from unknown scan: {patient_info.get('LastName')}")
                            cache['patient'] = patient_info
                            break

        # Build and emit patient update
        patient = build_patient_from_aggregated_data(
            patient_id=patient_id,
            patient_data=cache.get('patient'),
            vitals_data=cache.get('vitals'),
            medications_data=cache.get('medications'),
            problems_data=cache.get('problems')
        )

        logger.info("=" * 60)
        logger.info("EMITTING PATIENT UPDATE TO FRONTEND")
        logger.info(f"  Patient ID: {patient_id}")
        logger.info(f"  Name: {patient.name}")
        logger.info(f"  MRN: {patient.mrn}")
        logger.info(f"  Conditions: {len(patient.conditions)}")
        logger.info(f"  Medications: {len(patient.medications)}")
        logger.info(f"  Vitals: BP={patient.vitals.bp}, HR={patient.vitals.hr}")
        logger.info("=" * 60)

        await self.broadcast_to_frontend({
            "type": "PATIENT_UPDATE",
            "data": patient.model_dump()
        })

    def set_mode(self, mode: str):
        """Set the scraper mode."""
        try:
            old_mode = self.mode.value
            self.mode = ScraperMode(mode)
            logger.info(f"SCRAPER MODE CHANGED: {old_mode} -> {self.mode.value}")
        except ValueError:
            logger.warning(f"Invalid mode requested: {mode}")

    def get_stats(self) -> dict:
        """Get current statistics."""
        return {
            **self.stats,
            'chrome_connections': len(self.chrome_connections),
            'frontend_connections': len(self.frontend_connections),
            'mode': self.mode.value
        }


# Event store for raw and interpreted payloads (Layer 1)
event_store = EventStore()

# Event indexer for classification (Layer 2)
event_indexer = create_indexer("data")

# Global connection manager
manager = ConnectionManager(event_store, event_indexer)

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("=" * 60)
    logger.info("  SHADOW EHR BACKEND STARTING")
    logger.info("=" * 60)
    logger.info("WebSocket Endpoints:")
    logger.info("  Chrome Extension: ws://localhost:8000/ws/chrome")
    logger.info("  React Frontend:   ws://localhost:8000/ws/frontend")
    logger.info("")
    logger.info("REST Endpoints:")
    logger.info("  Health Check:     http://localhost:8000/health")
    logger.info("  Status:           http://localhost:8000/")
    logger.info("  Patients:         http://localhost:8000/patients")
    logger.info("  Stats:            http://localhost:8000/stats")
    logger.info("=" * 60)
    logger.info("Waiting for connections...")
    logger.info("")
    yield
    logger.info("=" * 60)
    logger.info("  SHADOW EHR BACKEND SHUTTING DOWN")
    logger.info("=" * 60)


# Create FastAPI app
app = FastAPI(
    title="Shadow EHR Backend",
    description="Normalization Engine for AthenaNet data interception",
    version="0.9.2",
    lifespan=lifespan
)

# CORS middleware for REST endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include active fetch routes
app.include_router(active_router)
app.include_router(discovery_router)

# Share the patient cache with active routes
set_main_cache(manager.patient_cache)


@app.get("/")
async def root():
    """Health check and status endpoint."""
    logger.debug("Root endpoint accessed")
    return {
        "service": "Shadow EHR Backend",
        "status": "running",
        "version": "0.9.2",
        "connections": {
            "chrome": len(manager.chrome_connections),
            "frontend": len(manager.frontend_connections)
        },
        "mode": manager.mode.value
    }


@app.get("/health")
async def health():
    """Simple health check endpoint."""
    logger.debug("Health check")
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/stats")
async def stats():
    """Get backend statistics."""
    stats = manager.get_stats()
    logger.info(f"Stats requested: {stats}")
    return stats


@app.get("/events/raw")
async def raw_events(patient_id: Optional[str] = None, limit: int = 50):
    """Return recent raw intercepted events for debugging and replay."""
    return {
        "patient_id": patient_id,
        "limit": limit,
        "events": event_store.get_raw_events(patient_id=patient_id, limit=limit),
    }


@app.get("/events/index")
async def indexed_events(patient_id: Optional[str] = None, limit: int = 50):
    """Return interpreter index entries linked to raw events (legacy endpoint)."""
    return {
        "patient_id": patient_id,
        "limit": limit,
        "events": event_store.get_index(patient_id=patient_id, limit=limit),
    }
# ... inside the FastAPI app ...

@app.post("/ai/narrative/{patient_id}")
async def generate_patient_narrative(patient_id: str, request: NarrativeRequest):
    """
    Generates a concise clinical narrative.
    The engine now handles the 'Sorting' (VascularProfile creation) internally
    to ensure the LLM only sees clean data.
    """
    logger.info("=" * 60)
    logger.info(f"[NARRATIVE API] Processing for: {patient_id}")

    # 1. ABSORB: Get Raw Data from Cache
    if patient_id not in manager.patient_cache:
        return {"error": "Patient data not found in RAM. Navigate to chart first."}

    raw_cache = manager.patient_cache[patient_id]
    
    # Optional: Merge Interpreted Data (Layer 3) into Raw Cache before sending
    if patient_id in manager.clinical_cache:
        interp = manager.clinical_cache[patient_id]
        if 'problem' in interp:
            # We prefer interpreted problems if available
            raw_cache['problems'] = interp['problem']
        if 'medication' in interp:
            raw_cache['medications'] = interp['medication']

    # 2. SORT & SYNTHESIZE (Handled by Engine)
    engine = get_narrative_engine()
    try:
        result = await engine.generate_narrative(patient_id, raw_cache, request.include_vision)
        return result
    except Exception as e:
        logger.error(f"[NARRATIVE API] Failed: {e}")
        return {"error": str(e)}

# ============================================================================
# EVENT INDEXER ENDPOINTS (Layer 2)
# ============================================================================

@app.get("/index/query")
async def query_index(
    patient_id: Optional[str] = None,
    category: Optional[str] = None,
    source_type: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 100
):
    """
    Query the Event Index with filters.

    Filters:
    - patient_id: Filter by patient
    - category: medication, problem, vital, lab, allergy, compound, etc.
    - source_type: passive_intercept, active_fetch
    - min_confidence: Minimum classification confidence (0.0-1.0)
    """
    entries = event_indexer.query(
        patient_id=patient_id,
        category=category,
        source_type=source_type,
        min_confidence=min_confidence,
        limit=limit
    )
    return {
        "count": len(entries),
        "filters": {
            "patient_id": patient_id,
            "category": category,
            "source_type": source_type,
            "min_confidence": min_confidence
        },
        "entries": entries
    }


@app.get("/index/stats")
async def index_stats():
    """
    Get Event Indexer statistics by category.

    Returns count of indexed events per clinical category,
    useful for understanding data distribution.
    """
    category_stats = event_indexer.get_category_stats()
    return {
        "indexer_version": INDEXER_VERSION,
        "total_indexed": sum(category_stats.values()),
        "by_category": category_stats,
        "events_indexed_this_session": manager.stats.get('events_indexed', 0)
    }


@app.post("/index/reindex")
async def reindex_events(force: bool = False):
    """
    Reindex all raw events (batch reprocessing).

    Use force=True to reindex events that already have entries
    from the current indexer version.

    This enables retrospective analysis when classification logic improves.
    """
    raw_path = Path("data/raw_events.jsonl")
    stats = await event_indexer.reindex_all(raw_path, force=force)
    return {
        "status": "complete",
        "indexer_version": INDEXER_VERSION,
        "stats": stats
    }


# ============================================================================
# CLINICAL INTERPRETER ENDPOINTS (Layer 3)
# ============================================================================

@app.get("/clinical/interpreters")
async def list_interpreters():
    """
    List all registered clinical interpreters and their versions.
    """
    return {
        "interpreters": get_interpreter_versions(),
        "categories": list(get_interpreter_versions().keys())
    }


@app.get("/clinical/{patient_id}")
async def get_clinical_data(patient_id: str, category: Optional[str] = None):
    """
    Get interpreted clinical data for a patient.

    Args:
        patient_id: Patient identifier
        category: Optional filter by category (medication, problem, etc.)
    """
    if patient_id not in manager.clinical_cache:
        return {
            "patient_id": patient_id,
            "error": "No clinical data found",
            "available_patients": list(manager.clinical_cache.keys())
        }

    cache = manager.clinical_cache[patient_id]

    if category:
        if category not in cache:
            return {
                "patient_id": patient_id,
                "category": category,
                "error": f"No {category} data found",
                "available_categories": list(cache.keys())
            }
        return {
            "patient_id": patient_id,
            "category": category,
            "count": len(cache[category]),
            "records": cache[category]
        }

    # Return all categories
    return {
        "patient_id": patient_id,
        "categories": {
            cat: {
                "count": len(records),
                "records": records
            }
            for cat, records in cache.items()
        }
    }


@app.get("/clinical/{patient_id}/medications")
async def get_medications(patient_id: str, antithrombotic_only: bool = False):
    """
    Get interpreted medications for a patient.

    For vascular surgery workflow, use antithrombotic_only=true to filter
    to critical perioperative medications.
    """
    if patient_id not in manager.clinical_cache:
        return {"patient_id": patient_id, "error": "No clinical data found"}

    meds = manager.clinical_cache[patient_id].get('medication', [])

    if antithrombotic_only:
        meds = [m for m in meds if m.get('is_antithrombotic', False)]

    return {
        "patient_id": patient_id,
        "count": len(meds),
        "antithrombotic_filter": antithrombotic_only,
        "medications": meds
    }


@app.get("/clinical/{patient_id}/problems")
async def get_problems(patient_id: str, vascular_only: bool = False):
    """
    Get interpreted problems/diagnoses for a patient.

    For vascular surgery workflow, use vascular_only=true to filter
    to vascular-relevant conditions.
    """
    if patient_id not in manager.clinical_cache:
        return {"patient_id": patient_id, "error": "No clinical data found"}

    problems = manager.clinical_cache[patient_id].get('problem', [])

    if vascular_only:
        problems = [p for p in problems if p.get('is_vascular', False) or p.get('is_cardiovascular_risk', False)]

    return {
        "patient_id": patient_id,
        "count": len(problems),
        "vascular_filter": vascular_only,
        "problems": problems
    }


@app.get("/clinical/{patient_id}/summary")
async def get_clinical_summary(patient_id: str):
    """
    Get a clinical summary for vascular surgery decision support.

    Provides:
    - Antithrombotic medications (critical for perioperative management)
    - Vascular diagnoses
    - Cardiovascular risk factors
    """
    if patient_id not in manager.clinical_cache:
        return {"patient_id": patient_id, "error": "No clinical data found"}

    cache = manager.clinical_cache[patient_id]
    meds = cache.get('medication', [])
    problems = cache.get('problem', [])

    # Extract critical data for vascular surgery
    antithrombotics = [m for m in meds if m.get('is_antithrombotic', False)]
    vascular_dx = [p for p in problems if p.get('is_vascular', False)]
    cv_risk_factors = [p for p in problems if p.get('is_cardiovascular_risk', False)]

    return {
        "patient_id": patient_id,
        "summary": {
            "antithrombotic_medications": {
                "count": len(antithrombotics),
                "items": [{"name": m['name'], "status": m.get('status', 'active')} for m in antithrombotics]
            },
            "vascular_diagnoses": {
                "count": len(vascular_dx),
                "items": [{"name": p['display_name'], "icd10": p.get('icd10_code')} for p in vascular_dx]
            },
            "cardiovascular_risk_factors": {
                "count": len(cv_risk_factors),
                "items": [{"name": p['display_name'], "icd10": p.get('icd10_code')} for p in cv_risk_factors]
            }
        },
        "total_medications": len(meds),
        "total_problems": len(problems)
    }


# ============================================================================
# AI SUMMARIZER ENDPOINTS (Layer 4 - Clinical Intelligence)
# ============================================================================

@app.get("/ai/briefing/{patient_id}")
async def get_surgical_briefing(patient_id: str):
    """
    Generate an AI-powered surgical briefing for the patient.

    Provides:
    - Antithrombotic status and management considerations
    - Vascular diagnoses summary
    - Cardiovascular risk assessment (RCRI-like)
    - Critical alerts (CLI, high-risk conditions)
    """
    if patient_id not in manager.clinical_cache:
        return {"patient_id": patient_id, "error": "No clinical data found"}

    cache = manager.clinical_cache[patient_id]
    meds = cache.get('medication', [])
    problems = cache.get('problem', [])

    # Generate clinical context
    context = generate_context(patient_id, meds, problems)

    # Generate briefing
    briefing = generate_briefing(context)

    return {
        "patient_id": patient_id,
        "briefing": briefing,
        "context": context.to_dict(),
        "generated_at": context.generated_at
    }


@app.get("/ai/med-alert/{patient_id}")
async def get_medication_alert(patient_id: str):
    """
    Generate medication management alerts for surgical planning.

    Focuses on antithrombotic management:
    - Anticoagulants requiring hold periods
    - Antiplatelets with specific recommendations
    - Bridging considerations
    """
    if patient_id not in manager.clinical_cache:
        return {"patient_id": patient_id, "error": "No clinical data found"}

    cache = manager.clinical_cache[patient_id]
    meds = cache.get('medication', [])
    problems = cache.get('problem', [])

    context = generate_context(patient_id, meds, problems)
    alert = generate_med_alert(context)

    return {
        "patient_id": patient_id,
        "alert": alert,
        "antithrombotic_count": len(context.antithrombotics),
        "anticoagulants": [m['name'] for m in context.anticoagulants],
        "antiplatelets": [m['name'] for m in context.antiplatelets]
    }


@app.get("/ai/context/{patient_id}")
async def get_clinical_context(patient_id: str, format: str = "json"):
    """
    Generate structured clinical context for LLM integration.

    Args:
        patient_id: Patient identifier
        format: Output format - "json" or "prompt"

    The "prompt" format returns text ready to paste into Claude/GPT.
    """
    if patient_id not in manager.clinical_cache:
        return {"patient_id": patient_id, "error": "No clinical data found"}

    cache = manager.clinical_cache[patient_id]
    meds = cache.get('medication', [])
    problems = cache.get('problem', [])

    context = generate_context(patient_id, meds, problems)

    if format == "prompt":
        return {
            "patient_id": patient_id,
            "prompt": context.to_prompt(),
            "format": "prompt"
        }

    return {
        "patient_id": patient_id,
        "context": context.to_dict(),
        "format": "json"
    }


@app.get("/ai/risk/{patient_id}")
async def get_risk_assessment(patient_id: str):
    """
    Generate cardiovascular risk assessment for surgical planning.

    Based on RCRI-like criteria:
    - High-risk surgery
    - Ischemic heart disease
    - Heart failure
    - Cerebrovascular disease
    - Diabetes
    - Renal insufficiency
    """
    if patient_id not in manager.clinical_cache:
        return {"patient_id": patient_id, "error": "No clinical data found"}

    cache = manager.clinical_cache[patient_id]
    meds = cache.get('medication', [])
    problems = cache.get('problem', [])

    context = generate_context(patient_id, meds, problems)

    # Calculate risk score
    risk_factors = []
    if context.has_cad:
        risk_factors.append({"factor": "Coronary Artery Disease", "present": True})
    if context.has_chf:
        risk_factors.append({"factor": "Heart Failure", "present": True})
    if context.has_stroke_history:
        risk_factors.append({"factor": "Cerebrovascular Disease", "present": True})
    if context.has_diabetes:
        risk_factors.append({"factor": "Diabetes", "present": True})
    if context.has_ckd:
        risk_factors.append({"factor": "Renal Insufficiency", "present": True})

    risk_count = len(risk_factors)
    risk_level = "HIGH" if risk_count >= 3 else "MODERATE" if risk_count >= 1 else "LOW"

    return {
        "patient_id": patient_id,
        "risk_level": risk_level,
        "risk_score": risk_count,
        "max_score": 5,
        "risk_factors": risk_factors,
        "vascular_status": {
            "pad": context.pad_present,
            "claudication": context.claudication,
            "critical_limb_ischemia": context.critical_limb_ischemia
        }
    }


@app.get("/debug/cache/{patient_id}")
async def debug_patient_cache(patient_id: str):
    """
    Debug endpoint: Get raw cache data for a patient.
    Helps identify data structure issues.
    """
    if patient_id not in manager.patient_cache:
        return {"error": "Patient not found", "available": list(manager.patient_cache.keys())}

    cache = manager.patient_cache[patient_id]
    return {
        "patient_id": patient_id,
        "cache_keys": list(cache.keys()),
        "medications_count": len(cache.get('medications', [])),
        "medications_sample": cache.get('medications', [])[:3],  # First 3 for debug
        "problems_count": len(cache.get('problems', [])),
        "labs_count": len(cache.get('labs', [])),
        "allergies_count": len(cache.get('allergies', [])),
        "raw_cache": cache
    }


@app.get("/captured-endpoints")
async def get_captured_endpoints():
    """
    Get all captured endpoint patterns for discovery analysis.
    Returns data in format compatible with /discovery/analyze-traffic.
    """
    endpoints = []
    for pattern, data in manager.endpoint_history.items():
        avg_size = sum(data['sizes']) / len(data['sizes']) if data['sizes'] else 0
        endpoints.append({
            "path": pattern,
            "count": data['count'],
            "methods": list(data['methods']),
            "avgSize": int(avg_size),
            "detected_type": data['record_type']
        })

    # Sort by count descending
    endpoints.sort(key=lambda x: x['count'], reverse=True)

    return {
        "endpoints": endpoints,
        "total_unique": len(endpoints),
        "total_requests": sum(e['count'] for e in endpoints)
    }


# ============================================================================
# HTTP INGEST ENDPOINT (Alternative to WebSocket)
# ============================================================================

from fastapi import Request, Header
from typing import Optional

@app.post("/ingest")
async def ingest_payload(request: Request, x_source: Optional[str] = Header(None)):
    """
    HTTP POST endpoint for receiving captured API data from Chrome extension.
    This is an alternative to the WebSocket approach, with offline queue support.
    """
    try:
        body = await request.json()

        logger.info("=" * 60)
        logger.info("🔥 HTTP INGEST RECEIVED")
        logger.info(f"  Source Header: {x_source or 'none'}")

        # Extract fields from the new payload format
        url = body.get('url', '')
        method = body.get('method', 'GET')
        data = body.get('data', {})
        source = body.get('source', 'unknown')
        timestamp = body.get('timestamp', datetime.now().isoformat())
        size = body.get('size', 0)

        # Extract patient ID from multiple possible locations
        # Priority: body.patientId > data.patientId > data.raw.patientId > data._meta.chartId > data.raw._meta.chartId
        patient_id = body.get('patientId')
        if not patient_id and isinstance(data, dict):
            patient_id = data.get('patientId')
            if not patient_id and 'raw' in data and isinstance(data.get('raw'), dict):
                patient_id = data['raw'].get('patientId')
                if not patient_id and '_meta' in data['raw']:
                    patient_id = data['raw'].get('_meta', {}).get('chartId')
            if not patient_id and '_meta' in data:
                patient_id = data.get('_meta', {}).get('chartId')

        logger.info(f"  Method: {method}")
        logger.info(f"  URL: {url[:100]}{'...' if len(url) > 100 else ''}")
        logger.info(f"  Source: {source}")
        logger.info(f"  Patient ID extracted: {patient_id or 'none'}")
        logger.info(f"  Size: {size} bytes")
        logger.info(f"  Data type: {type(data).__name__}")
        if isinstance(data, dict):
            keys = list(data.keys())[:15]
            logger.info(f"  Data keys: {keys}")
            # Log nested keys for Athena compound payloads
            for key in ['active_medications', 'allergies', 'active_problems', 'measurements', 'demographics']:
                if key in data:
                    nested = data[key]
                    if isinstance(nested, dict):
                        logger.info(f"  📦 {key} keys: {list(nested.keys())[:5]}")
                    elif isinstance(nested, list):
                        logger.info(f"  📦 {key}: list with {len(nested)} items")
        logger.info(f"  Frontend connections: {len(manager.frontend_connections)}")
        logger.info(f"  Current patients cached: {len(manager.patient_cache)}")

        # Convert to internal format for processing
        internal_payload = {
            'endpoint': url,
            'method': method,
            'payload': data,
            'patientId': patient_id  # Include extracted patient ID
        }

        # Process through the same pipeline as WebSocket
        await manager.process_athena_payload(internal_payload)

        # If we have a patient ID from active fetch, set it as current context
        if patient_id and source == 'active-fetch':
            manager.current_patient_id = patient_id
            logger.info(f"  Set current patient context to: {patient_id}")

        # Notify frontend that Chrome is active
        await manager.broadcast_to_frontend({
            "type": "STATUS_UPDATE",
            "data": "CONNECTED"
        })

        logger.success = lambda msg: logger.info(f"✅ {msg}")
        logger.info("✅ Ingest successful")
        logger.info("=" * 60)

        return {
            "status": "ok",
            "processed": True,
            "timestamp": datetime.now().isoformat(),
            "patientId": patient_id
        }

    except Exception as e:
        logger.error(f"Ingest error: {e}")
        logger.exception("Full traceback:")
        return {
            "status": "error",
            "message": str(e)
        }


@app.websocket("/ws/chrome")
async def chrome_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Chrome extension.
    Receives intercepted AthenaNet API payloads.

    Includes heartbeat mechanism to keep connection alive.
    """
    logger.info(f"Chrome WebSocket connection attempt from {websocket.client}")
    await manager.connect_chrome(websocket)

    # Heartbeat task to keep connection alive
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(30)  # Send ping every 30 seconds
                try:
                    await websocket.send_json({"type": "PING", "timestamp": datetime.now().isoformat()})
                    logger.debug("Heartbeat PING sent to Chrome")
                except Exception:
                    break  # Connection closed, exit heartbeat
        except asyncio.CancelledError:
            pass  # Task cancelled, clean exit

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            # Receive data from Chrome extension with timeout
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=120.0)
            except asyncio.TimeoutError:
                # No message in 120 seconds - send ping to check if connection is alive
                try:
                    await websocket.send_json({"type": "PING", "timestamp": datetime.now().isoformat()})
                    continue
                except Exception:
                    logger.warning("Chrome connection stale - no response to ping")
                    break

            logger.debug(f"Raw data received from Chrome ({len(data)} bytes)")

            try:
                payload = json.loads(data)
                # Handle PONG responses
                if payload.get('type') == 'PONG':
                    logger.debug("Heartbeat PONG received from Chrome")
                    continue
                logger.debug("JSON parsed successfully")
                # Process the AthenaNet payload
                await manager.process_athena_payload(payload)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from Chrome: {e}")
                logger.error(f"Raw data: {data[:500]}...")
            except Exception as e:
                logger.error(f"Error processing Chrome data: {e}")
                logger.exception("Full traceback:")

    except WebSocketDisconnect:
        pass  # Normal disconnect
    except Exception as e:
        logger.error(f"Chrome WebSocket error: {e}")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect_chrome(websocket)
        # Notify frontend about Chrome disconnection
        await manager.broadcast_to_frontend({
            "type": "STATUS_UPDATE",
            "data": "DISCONNECTED"
        })


@app.websocket("/ws/frontend")
async def frontend_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for React frontend.
    Sends processed data and receives mode change commands.

    Includes heartbeat mechanism to keep connection alive through proxies.
    """
    logger.info(f"Frontend WebSocket connection attempt from {websocket.client}")
    await manager.connect_frontend(websocket)

    # Heartbeat task to keep connection alive
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(30)  # Send ping every 30 seconds
                try:
                    await websocket.send_json({"type": "PING", "timestamp": datetime.now().isoformat()})
                    logger.debug("Heartbeat PING sent to frontend")
                except Exception:
                    break  # Connection closed, exit heartbeat
        except asyncio.CancelledError:
            pass  # Task cancelled, clean exit

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            # Receive commands from frontend with timeout
            try:
                # Use wait_for with timeout to detect stale connections
                data = await asyncio.wait_for(websocket.receive_text(), timeout=120.0)
            except asyncio.TimeoutError:
                # No message in 120 seconds - send ping to check if connection is alive
                try:
                    await websocket.send_json({"type": "PING", "timestamp": datetime.now().isoformat()})
                    continue
                except Exception:
                    logger.warning("Frontend connection stale - no response to ping")
                    break

            logger.debug(f"Message from frontend: {data}")

            try:
                message = json.loads(data)
                action = message.get('action', '')

                # Handle PONG responses (heartbeat acknowledgment)
                if action == 'PONG':
                    logger.debug("Heartbeat PONG received from frontend")
                    continue

                logger.info(f"Frontend action received: {action}")

                if action == 'SET_MODE':
                    mode = message.get('mode', 'PASSIVE')
                    manager.set_mode(mode)

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from frontend: {data}")
            except Exception as e:
                logger.error(f"Error processing frontend message: {e}")

    except WebSocketDisconnect:
        pass  # Normal disconnect
    except Exception as e:
        logger.error(f"Frontend WebSocket error: {e}")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect_frontend(websocket)


@app.get("/patient/{patient_id}")
async def get_patient(patient_id: str):
    """Get aggregated patient data from cache."""
    logger.info(f"Patient requested: {patient_id}")

    if patient_id in manager.patient_cache:
        cache = manager.patient_cache[patient_id]
        patient = build_patient_from_aggregated_data(
            patient_id=patient_id,
            patient_data=cache.get('patient'),
            vitals_data=cache.get('vitals'),
            medications_data=cache.get('medications'),
            problems_data=cache.get('problems')
        )
        logger.info(f"Patient found: {patient.name}")
        return {"patient": patient.model_dump()}

    logger.warning(f"Patient not found: {patient_id}")
    return {"error": "Patient not found", "patient_id": patient_id}


@app.get("/patients")
async def list_patients():
    """List all patients in cache."""
    logger.info(f"Listing all patients ({len(manager.patient_cache)} in cache)")

    patients = []
    for patient_id, cache in manager.patient_cache.items():
        patient = build_patient_from_aggregated_data(
            patient_id=patient_id,
            patient_data=cache.get('patient'),
            vitals_data=cache.get('vitals'),
            medications_data=cache.get('medications'),
            problems_data=cache.get('problems')
        )
        patients.append(patient.model_dump())

    return {"patients": patients, "count": len(patients)}


@app.delete("/cache")
async def clear_cache():
    """Clear the patient cache."""
    count = len(manager.patient_cache)
    manager.patient_cache.clear()
    logger.warning(f"Patient cache cleared ({count} patients removed)")
    return {"status": "cleared", "patients_removed": count}


# ==============================================================================
# LAYER 5: ARTIFACT & DOCUMENT DOWNLOAD ENDPOINTS
# ==============================================================================

@app.post("/session/context")
async def update_session_context(ctx_data: dict):
    """
    Update session context from Chrome extension.

    The extension should send cookies and headers captured from the active
    Athena session to enable HTTP-first document downloads.
    """
    try:
        ctx = SessionContext.from_extension_message(ctx_data)
        set_session_context(ctx)
        logger.info(f"[SESSION] Context updated: {ctx}")
        return {
            "status": "ok",
            "base_url": ctx.base_url,
            "cookies_count": len(ctx.cookies),
            "headers_count": len(ctx.headers),
            "patient_hint": ctx.patient_hint,
        }
    except Exception as e:
        logger.error(f"[SESSION] Failed to update context: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/session/context")
async def get_current_session():
    """Get the current session context status."""
    ctx = get_session_context()
    if ctx:
        return {
            "status": "active",
            "base_url": ctx.base_url,
            "cookies_count": len(ctx.cookies),
            "headers_count": len(ctx.headers),
            "patient_hint": ctx.patient_hint,
            "encounter_hint": ctx.encounter_hint,
        }
    return {"status": "no_session", "message": "No session context available"}


@app.get("/artifacts")
async def list_artifacts(patient_id: Optional[str] = None, limit: int = 50):
    """
    List stored artifacts.

    Args:
        patient_id: Optional filter by patient
        limit: Maximum number of artifacts to return
    """
    store = get_artifact_store()

    if patient_id:
        artifacts = store.list_by_patient(patient_id)
    else:
        artifacts = store.list_all(limit=limit)

    return {
        "artifacts": [a.to_dict() for a in artifacts],
        "count": len(artifacts),
    }


@app.get("/artifacts/stats")
async def artifact_stats():
    """Get artifact storage statistics."""
    store = get_artifact_store()
    return store.stats()


@app.get("/artifacts/{artifact_id}")
async def get_artifact_metadata(artifact_id: str):
    """Get metadata for a specific artifact."""
    store = get_artifact_store()
    meta = store.get_metadata(artifact_id)
    if meta:
        return meta.to_dict()
    return {"error": "Artifact not found", "artifact_id": artifact_id}


@app.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str):
    """Download artifact bytes (returns base64 for JSON compatibility)."""
    import base64
    store = get_artifact_store()
    data = store.get(artifact_id)
    if data:
        meta = store.get_metadata(artifact_id)
        return {
            "artifact_id": artifact_id,
            "filename": meta.original_filename if meta else None,
            "mime_type": meta.mime_type if meta else None,
            "size_bytes": len(data),
            "content_b64": base64.b64encode(data).decode("ascii"),
        }
    return {"error": "Artifact not found", "artifact_id": artifact_id}


@app.post("/artifacts/detect-missing")
async def detect_missing_artifacts(payload: dict):
    """
    Detect missing documents from an Athena payload.

    Pass in a raw Athena payload and get back a list of documents
    that are referenced but not yet downloaded.
    """
    patient_id = payload.get("patient_id")
    encounter_id = payload.get("encounter_id")
    data = payload.get("data", payload)

    # Extract document refs from payload
    refs = extract_document_refs(data, patient_id, encounter_id)

    # Find missing
    detector = get_artifact_detector()
    missing = detector.find_missing(refs)

    return {
        "total_refs": len(refs),
        "missing_count": len(missing),
        "missing": [m.to_dict() for m in missing],
        "downloadable": [m.to_dict() for m in missing if m.reason == "not_in_store"],
    }


@app.post("/artifacts/download")
async def download_document(request: dict):
    """
    Download a document using HTTP-first strategy.

    Args (in request body):
        url: URL to download
        filename: Suggested filename
        patient_id: Optional patient ID for provenance
        encounter_id: Optional encounter ID for provenance
        skip_selenium: If true, don't attempt Selenium fallback
    """
    url = request.get("url")
    if not url:
        return {"error": "url is required"}

    filename = request.get("filename", "document.pdf")
    patient_id = request.get("patient_id")
    encounter_id = request.get("encounter_id")
    skip_selenium = request.get("skip_selenium", True)  # Default to HTTP-only

    # Get session context
    ctx = get_session_context()
    if not ctx:
        return {
            "error": "No session context available",
            "hint": "Extension must send session context first via POST /session/context"
        }

    # Add patient/encounter hints
    if patient_id:
        ctx = ctx.with_patient(patient_id)
    if encounter_id:
        ctx = ctx.with_encounter(encounter_id)

    # Download
    dm = get_download_manager()
    outcome = dm.download(ctx=ctx, url=url, filename_hint=filename, skip_selenium=skip_selenium)

    # Update artifact index if successful
    if outcome.ok and outcome.artifact:
        index = get_artifact_index()
        index.add_doc(outcome.artifact.artifact_id)

    return outcome.to_dict()


@app.post("/artifacts/batch-download")
async def batch_download_documents(request: dict):
    """
    Download multiple documents.

    Args (in request body):
        documents: List of {url, filename} objects
        patient_id: Optional patient ID for all documents
        skip_selenium: If true, don't attempt Selenium fallback
    """
    documents = request.get("documents", [])
    if not documents:
        return {"error": "documents list is required"}

    patient_id = request.get("patient_id")
    skip_selenium = request.get("skip_selenium", True)

    ctx = get_session_context()
    if not ctx:
        return {"error": "No session context available"}

    if patient_id:
        ctx = ctx.with_patient(patient_id)

    dm = get_download_manager()
    index = get_artifact_index()

    results = []
    success_count = 0

    for doc in documents:
        url = doc.get("url")
        if not url:
            continue

        filename = doc.get("filename", "document.pdf")
        outcome = dm.download(ctx=ctx, url=url, filename_hint=filename, skip_selenium=skip_selenium)

        if outcome.ok and outcome.artifact:
            index.add_doc(outcome.artifact.artifact_id)
            success_count += 1

        results.append({
            "url": url,
            "outcome": outcome.to_dict()
        })

    return {
        "total": len(documents),
        "success": success_count,
        "failed": len(documents) - success_count,
        "results": results,
    }


@app.get("/artifacts/index/stats")
async def artifact_index_stats():
    """Get artifact index statistics."""
    index = get_artifact_index()
    return {
        "indexed_count": index.count(),
    }


# ==============================================================================
# LAYER 6: VASCULAR SURGERY EXTRACTORS (PREOP PLANNING)
# ==============================================================================

@app.get("/vascular/{patient_id}")
async def get_vascular_assessment(patient_id: str, surgery_type: str = "vascular"):
    """
    Get complete vascular surgery preoperative assessment.

    Returns PAD, Carotid, AAA assessments plus antithrombotic bridging plan.
    """
    # Gather clinical data from cache
    cache = manager.patient_cache.get(patient_id, {})

    clinical_data = {
        'medications': cache.get('medications', []),
        'problems': cache.get('problems', []),
        'vitals': cache.get('vitals', []),
        'notes': cache.get('notes', []),
        'imaging': cache.get('imaging', []),
        'results': cache.get('results', []),
        'surgical_history': cache.get('surgical_history', []),
    }

    # Also check clinical_cache from interpreters
    if patient_id in manager.clinical_cache:
        interp_data = manager.clinical_cache[patient_id]
        if 'medication' in interp_data:
            clinical_data['medications'].extend(interp_data['medication'])
        if 'problem' in interp_data:
            clinical_data['problems'].extend(interp_data['problem'])

    assessment = extract_vascular_assessment(patient_id, clinical_data, surgery_type)

    return {
        "patient_id": patient_id,
        "assessment": assessment.to_dict(),
        "preop_summary": assessment.generate_preop_summary(),
    }


@app.get("/vascular/{patient_id}/pad")
async def get_pad_assessment(patient_id: str):
    """
    Get PAD (Peripheral Arterial Disease) assessment.

    Includes: ABI/TBI, Rutherford classification, CLI status, amputation risk.
    """
    cache = manager.patient_cache.get(patient_id, {})
    clinical_data = {
        'medications': cache.get('medications', []),
        'problems': cache.get('problems', []),
        'vitals': cache.get('vitals', []),
        'notes': cache.get('notes', []),
        'surgical_history': cache.get('surgical_history', []),
    }

    extractor = PADExtractor()
    assessment = extractor.extract(patient_id, clinical_data)

    return {
        "patient_id": patient_id,
        "pad_assessment": assessment.to_dict(),
    }


@app.get("/vascular/{patient_id}/carotid")
async def get_carotid_assessment(patient_id: str):
    """
    Get carotid disease assessment.

    Includes: Stenosis %, symptom status, intervention recommendation.
    """
    cache = manager.patient_cache.get(patient_id, {})
    clinical_data = {
        'problems': cache.get('problems', []),
        'results': cache.get('results', []),
        'imaging': cache.get('imaging', []),
        'notes': cache.get('notes', []),
        'surgical_history': cache.get('surgical_history', []),
    }

    extractor = CarotidExtractor()
    assessment = extractor.extract(patient_id, clinical_data)

    return {
        "patient_id": patient_id,
        "carotid_assessment": assessment.to_dict(),
    }


@app.get("/vascular/{patient_id}/aaa")
async def get_aaa_assessment(patient_id: str):
    """
    Get AAA (Abdominal Aortic Aneurysm) assessment.

    Includes: Diameter, growth rate, rupture risk, EVAR suitability.
    """
    cache = manager.patient_cache.get(patient_id, {})
    clinical_data = {
        'problems': cache.get('problems', []),
        'results': cache.get('results', []),
        'imaging': cache.get('imaging', []),
        'notes': cache.get('notes', []),
        'surgical_history': cache.get('surgical_history', []),
    }

    extractor = AAAExtractor()
    assessment = extractor.extract(patient_id, clinical_data)

    return {
        "patient_id": patient_id,
        "aaa_assessment": assessment.to_dict(),
    }


@app.get("/vascular/{patient_id}/bridging")
async def get_bridging_plan(patient_id: str, surgery_type: str = "vascular", surgery_date: Optional[str] = None):
    """
    Get antithrombotic bridging plan for perioperative management.

    Includes: Hold recommendations, restart timing, bridging needs.
    """
    cache = manager.patient_cache.get(patient_id, {})
    medications = cache.get('medications', [])
    problems = cache.get('problems', [])

    # Also include interpreted medications
    if patient_id in manager.clinical_cache:
        interp_data = manager.clinical_cache[patient_id]
        if 'medication' in interp_data:
            medications.extend(interp_data['medication'])
        if 'problem' in interp_data:
            problems.extend(interp_data['problem'])

    calculator = AntithromboticBridgingCalculator()
    plan = calculator.calculate_bridging_plan(
        patient_id=patient_id,
        medications=medications,
        problems=problems,
        surgery_type=surgery_type,
        surgery_date=surgery_date
    )

    return {
        "patient_id": patient_id,
        "bridging_plan": plan.to_dict(),
    }


@app.get("/vascular/antithrombotics/database")
async def get_antithrombotic_database():
    """
    Get the antithrombotic medication database with bridging parameters.

    Reference for hold times, restart timing, and reversal agents.
    """
    return {
        "medications": {k: v.to_dict() for k, v in ANTITHROMBOTIC_DATABASE.items()},
        "count": len(ANTITHROMBOTIC_DATABASE),
    }


@app.post("/vascular/preop-summary")
async def generate_preop_summary(request: dict):
    """
    Generate complete preoperative summary for surgical planning.

    Pass clinical data directly for patients not in cache.
    """
    patient_id = request.get("patient_id", "unknown")
    clinical_data = request.get("clinical_data", {})
    surgery_type = request.get("surgery_type", "vascular")

    assessment = extract_vascular_assessment(patient_id, clinical_data, surgery_type)

    return {
        "patient_id": patient_id,
        "assessment": assessment.to_dict(),
        "preop_summary": assessment.generate_preop_summary(),
    }


# ==============================================================================
# VASCULAR PROFILE ENDPOINT (for SurgicalDashboard UI)
# ==============================================================================

@app.get("/active/profile/{patient_id}")
async def get_vascular_profile(patient_id: str):
    """
    Get VascularProfile for the SurgicalDashboard UI.

    Uses the Data Separation Layer to build a clean, typed profile
    from raw cache data.
    """
    logger.info(f"[PROFILE] Fetching VascularProfile for patient {patient_id}")

    # Get raw cache data
    cache = manager.patient_cache.get(patient_id)
    if not cache:
        logger.warning(f"[PROFILE] No cache found for patient {patient_id}")
        return {"success": False, "error": "Patient not in cache. Use /active/profile endpoint instead.", "profile": None}

    logger.info(f"[PROFILE] Cache keys: {list(cache.keys())}")

    # Transform cache to parser input format
    parser_input = {
        "demographics": {"data": cache.get("patient") or {}},
        "patient": cache.get("patient") or {},
        "medications": {"data": cache.get("medications") or []},
        "problems": {"data": cache.get("problems") or []},
        "labs": {"data": cache.get("labs") or []},
        "notes": {"data": cache.get("notes") or []},
        "procedures": {"data": cache.get("surgical_history") or []},
        "allergies": {"data": cache.get("allergies") or []},
        "documents": {"data": cache.get("documents") or []},
        "unknown": cache.get("unknown") or [],
    }

    # Also merge interpreted data if available
    if patient_id in manager.clinical_cache:
        interp_data = manager.clinical_cache[patient_id]
        if 'medication' in interp_data:
            existing_meds = parser_input["medications"]["data"] or []
            if isinstance(existing_meds, list):
                parser_input["medications"]["data"] = existing_meds + interp_data['medication']
        if 'problem' in interp_data:
            existing_probs = parser_input["problems"]["data"] or []
            if isinstance(existing_probs, list):
                parser_input["problems"]["data"] = existing_probs + interp_data['problem']

    logger.info(f"[PROFILE] Parser input prepared with {len(parser_input.get('unknown', []))} unknown items")

    try:
        # Build the VascularProfile using the Data Separation Layer
        profile = build_vascular_profile(patient_id, parser_input)

        # Convert to dict for JSON serialization
        profile_dict = profile.model_dump()

        logger.info(f"[PROFILE] VascularProfile built: name={profile.name}, "
                   f"diagnoses={len(profile.diagnoses)}, "
                   f"antithrombotics={len(profile.antithrombotics)}, "
                   f"documents={len(profile.documents)}")

        return {
            "success": True,
            "profile": profile_dict
        }
    except Exception as e:
        logger.error(f"[PROFILE] Failed to build VascularProfile: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e), "profile": None}


@app.get("/active/preop-checklist/{patient_id}")
async def get_preop_checklist(patient_id: str):
    """
    Get pre-op surgical checklist for the SurgicalDashboard UI.
    """
    logger.info(f"[CHECKLIST] Fetching preop checklist for patient {patient_id}")

    # Get the profile first
    cache = manager.patient_cache.get(patient_id)
    if not cache:
        return {"error": "Patient not in cache"}

    # Transform cache to parser input format
    parser_input = {
        "demographics": {"data": cache.get("patient") or {}},
        "patient": cache.get("patient") or {},
        "medications": {"data": cache.get("medications") or []},
        "problems": {"data": cache.get("problems") or []},
        "labs": {"data": cache.get("labs") or []},
        "allergies": {"data": cache.get("allergies") or []},
        "unknown": cache.get("unknown") or [],
    }

    try:
        profile = build_vascular_profile(patient_id, parser_input)

        # Build checklist from profile
        blocking_issues = []

        # Check antithrombotics
        anticoag_held = True
        anticoag_details = "No anticoagulants on record"
        bridging_required = False

        for med in profile.antithrombotics:
            if med.category in ['vka', 'doac']:
                anticoag_details = f"{med.name} - Hold {med.hold_days_preop} days pre-op"
                if med.bridging_required:
                    bridging_required = True
                    blocking_issues.append(f"Bridging required for {med.name}")

        # Check renal function
        renal_ok = True
        renal_details = "No recent labs"
        if profile.renal_function:
            if profile.renal_function.contrast_risk in ['high', 'contraindicated']:
                renal_ok = False
                blocking_issues.append(f"Contrast risk: {profile.renal_function.contrast_risk}")
            renal_details = f"Cr: {profile.renal_function.creatinine or 'N/A'}, eGFR: {profile.renal_function.egfr or 'N/A'}"

        # Check coagulation
        coag_ok = True
        coag_details = "No coag panel"
        if profile.coagulation:
            if profile.coagulation.reversal_needed:
                coag_ok = False
                blocking_issues.append("INR elevated - reversal may be needed")
            coag_details = f"INR: {profile.coagulation.inr or 'N/A'}"

        # Check cardiac
        cardiac_cleared = profile.cardiac_risk == 'cleared'
        cardiac_details = f"Cardiac risk: {profile.cardiac_risk}"
        if profile.cardiac_risk == 'high':
            blocking_issues.append("High cardiac risk - consider cardiology clearance")

        # Check allergies
        contrast_allergy = any('contrast' in a.allergen.lower() for a in profile.critical_allergies)
        allergy_alerts = [a.allergen for a in profile.critical_allergies]
        if contrast_allergy:
            blocking_issues.append("Contrast allergy - pre-medicate or use alternative")

        ready = len(blocking_issues) == 0

        return {
            "patient_id": patient_id,
            "mrn": profile.mrn,
            "name": profile.name,
            "antithrombotics_held": anticoag_held,
            "anticoagulant_details": anticoag_details,
            "bridging_required": bridging_required,
            "renal_function_ok": renal_ok,
            "renal_details": renal_details,
            "coagulation_ok": coag_ok,
            "coagulation_details": coag_details,
            "cardiac_cleared": cardiac_cleared,
            "cardiac_details": cardiac_details,
            "contrast_allergy": contrast_allergy,
            "allergy_alerts": allergy_alerts,
            "ready_for_surgery": ready,
            "blocking_issues": blocking_issues,
        }
    except Exception as e:
        logger.error(f"[CHECKLIST] Failed: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
