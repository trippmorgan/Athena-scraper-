"""
Shadow EHR Backend: FastAPI WebSocket Server

This is the Normalization Engine (Tier 2) that:
1. Accepts WebSocket connections from Chrome extension (/ws/chrome)
2. Accepts WebSocket connections from React frontend (/ws/frontend)
3. Converts AthenaNet JSON to FHIR R4 resources
4. Relays processed data to the frontend
"""

import asyncio
import json
import logging
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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
        return super().format(record)

# Configure root logger
def setup_logging():
    """Setup comprehensive logging for the application."""

    # Create logger
    logger = logging.getLogger("shadow-ehr")
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers = []

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = ColoredFormatter(
        '%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler for persistent logs
    file_handler = logging.FileHandler('shadow_ehr.log', mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logging()

# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections for Chrome extension and Frontend clients."""

    def __init__(self):
        # Active connections
        self.chrome_connections: List[WebSocket] = []
        self.frontend_connections: List[WebSocket] = []

        # Current scraper mode
        self.mode: ScraperMode = ScraperMode.PASSIVE

        # Patient data cache (in-memory, keyed by patient_id)
        self.patient_cache: Dict[str, Dict[str, Any]] = {}

        # Statistics
        self.stats = {
            'payloads_received': 0,
            'payloads_processed': 0,
            'errors': 0,
            'patients_cached': 0
        }

        logger.info("ConnectionManager initialized")

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

            logger.info("-" * 60)
            logger.info("INCOMING ATHENA PAYLOAD")
            logger.info(f"  Method: {method}")
            logger.info(f"  Endpoint: {endpoint[:80]}{'...' if len(endpoint) > 80 else ''}")
            logger.info(f"  Payload size: {payload_size} bytes")
            logger.debug(f"  Raw payload preview: {str(payload)[:200]}...")

            # Convert to FHIR
            logger.info("Converting to FHIR R4...")
            record_type, fhir_resource = convert_to_fhir(endpoint, method, payload)
            logger.info(f"  Record type detected: {record_type}")

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
            patient_id = extract_patient_id(endpoint)
            if patient_id:
                logger.info(f"  Patient ID extracted: {patient_id}")
                await self.update_patient_cache(patient_id, record_type, fhir_resource)
            else:
                logger.debug("  No patient ID in endpoint")

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

        is_new_patient = patient_id not in self.patient_cache

        if is_new_patient:
            self.patient_cache[patient_id] = {
                'patient': None,
                'vitals': None,
                'medications': [],
                'problems': [],
                'last_update': None
            }
            self.stats['patients_cached'] += 1
            logger.info(f"NEW PATIENT ADDED TO CACHE: {patient_id}")

        cache = self.patient_cache[patient_id]

        # Update appropriate section
        logger.debug(f"Updating cache section: {record_type}")

        if record_type == 'patient':
            if hasattr(fhir_resource, 'model_dump'):
                cache['patient'] = fhir_resource.model_dump()
            else:
                cache['patient'] = fhir_resource
            logger.info(f"  Patient demographics updated")

        elif record_type == 'vital':
            if hasattr(fhir_resource, 'model_dump'):
                cache['vitals'] = fhir_resource.model_dump()
            else:
                cache['vitals'] = fhir_resource
            logger.info(f"  Vitals updated")

        elif record_type == 'medication':
            if isinstance(fhir_resource, dict) and 'medications' in fhir_resource:
                cache['medications'] = fhir_resource['medications']
                logger.info(f"  Medications updated ({len(cache['medications'])} meds)")

        elif record_type == 'problem':
            if isinstance(fhir_resource, dict) and 'conditions' in fhir_resource:
                cache['problems'] = fhir_resource['conditions']
                logger.info(f"  Problems updated ({len(cache['problems'])} conditions)")

        cache['last_update'] = datetime.now().isoformat()

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


# Global connection manager
manager = ConnectionManager()

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
        logger.info("HTTP INGEST RECEIVED")
        logger.info(f"  Source Header: {x_source or 'none'}")

        # Extract fields from the new payload format
        url = body.get('url', '')
        method = body.get('method', 'GET')
        data = body.get('data', {})
        patient_id = body.get('patientId')
        source = body.get('source', 'unknown')
        timestamp = body.get('timestamp', datetime.now().isoformat())
        size = body.get('size', 0)

        logger.info(f"  Method: {method}")
        logger.info(f"  URL: {url[:80]}{'...' if len(url) > 80 else ''}")
        logger.info(f"  Source: {source}")
        logger.info(f"  Patient ID: {patient_id or 'none'}")
        logger.info(f"  Size: {size} bytes")

        # Convert to internal format for processing
        internal_payload = {
            'endpoint': url,
            'method': method,
            'payload': data
        }

        # Process through the same pipeline as WebSocket
        await manager.process_athena_payload(internal_payload)

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
    """
    logger.info(f"Chrome WebSocket connection attempt from {websocket.client}")
    await manager.connect_chrome(websocket)

    try:
        while True:
            # Receive data from Chrome extension
            data = await websocket.receive_text()
            logger.debug(f"Raw data received from Chrome ({len(data)} bytes)")

            try:
                payload = json.loads(data)
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
    """
    logger.info(f"Frontend WebSocket connection attempt from {websocket.client}")
    await manager.connect_frontend(websocket)

    try:
        while True:
            # Receive commands from frontend
            data = await websocket.receive_text()
            logger.debug(f"Message from frontend: {data}")

            try:
                message = json.loads(data)
                action = message.get('action', '')

                logger.info(f"Frontend action received: {action}")

                if action == 'SET_MODE':
                    mode = message.get('mode', 'PASSIVE')
                    manager.set_mode(mode)

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from frontend: {data}")
            except Exception as e:
                logger.error(f"Error processing frontend message: {e}")

    except WebSocketDisconnect:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")
