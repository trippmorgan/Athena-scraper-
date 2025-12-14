"""
Download Manager: HTTP-First with Selenium Fallback

This module orchestrates document downloads using a tiered strategy:

1. HTTP-FIRST (Preferred)
   - Uses session cookies/headers captured from browser
   - Fast, lightweight, no browser overhead
   - Works for most direct download links

2. SELENIUM FALLBACK (Quarantined)
   - Only invoked when HTTP fails
   - Uses isolated Selenium service (separate container/process)
   - Required for JavaScript-rendered download links
   - Credentials passed via secrets manager (never hardcoded)

Every downloaded artifact gets full provenance tracking.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import logging
import os

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from provenance import Provenance, sha256_bytes
from .session_context import SessionContext
from .http_fetcher import fetch_bytes, HttpFetchResult
from .artifact_store import ArtifactStore, StoredArtifact, DiskArtifactStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadOutcome:
    """
    Result of a download attempt.

    Attributes:
        ok: True if download succeeded
        artifact: StoredArtifact if successful
        error: Error message if failed
        tried_http: Whether HTTP was attempted
        tried_selenium: Whether Selenium fallback was attempted
        http_status: HTTP status code from first attempt
    """
    ok: bool
    artifact: Optional[StoredArtifact] = None
    error: Optional[str] = None
    tried_http: bool = False
    tried_selenium: bool = False
    http_status: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ok": self.ok,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "error": self.error,
            "tried_http": self.tried_http,
            "tried_selenium": self.tried_selenium,
            "http_status": self.http_status,
        }


class DownloadManager:
    """
    Orchestrates document downloads with HTTP-first strategy.

    Usage:
        store = DiskArtifactStore("/data/artifacts")
        dm = DownloadManager(store=store)

        # Download with session context
        ctx = SessionContext(base_url="https://athena.example.com", cookies={...})
        outcome = dm.download(ctx=ctx, url="https://.../download/123", filename_hint="report.pdf")

        if outcome.ok:
            print(f"Downloaded: {outcome.artifact.artifact_id}")
        else:
            print(f"Failed: {outcome.error}")
    """

    def __init__(
        self,
        *,
        store: ArtifactStore,
        selenium_service_url: Optional[str] = None
    ):
        """
        Initialize download manager.

        Args:
            store: ArtifactStore implementation for persisting downloads
            selenium_service_url: Optional URL of Selenium fallback service
                                  (e.g., http://selenium-fallback:8080)
        """
        self.store = store
        self.selenium_service_url = selenium_service_url or os.environ.get("SELENIUM_SERVICE_URL")

        logger.info(
            f"[DOWNLOAD] Initialized (selenium_fallback={'enabled' if self.selenium_service_url else 'disabled'})"
        )

    def download(
        self,
        *,
        ctx: SessionContext,
        url: str,
        filename_hint: str = "artifact.bin",
        skip_selenium: bool = False
    ) -> DownloadOutcome:
        """
        Download a file using HTTP-first strategy.

        Args:
            ctx: SessionContext with authentication credentials
            url: URL to download from
            filename_hint: Suggested filename for storage
            skip_selenium: If True, don't attempt Selenium fallback

        Returns:
            DownloadOutcome with result details
        """
        logger.info(f"[DOWNLOAD] Starting: {url}")

        # 1) HTTP-first attempt
        http_result = fetch_bytes(ctx, url)

        if http_result.ok and http_result.content:
            # Success! Store the artifact
            prov = Provenance.now(
                source_url=url,
                http_method="GET",
                status=http_result.status,
                artifact_hash=sha256_bytes(http_result.content),
                patient_hint=ctx.patient_hint,
                encounter_hint=ctx.encounter_hint,
                meta={"download_path": "http_first"}
            )

            # Use filename from Content-Disposition if available
            actual_filename = http_result.filename_from_header or filename_hint

            artifact = self.store.put(
                bytes_data=http_result.content,
                filename=actual_filename,
                mime_type=http_result.content_type,
                provenance=prov
            )

            logger.info(f"[DOWNLOAD] Success (HTTP): {artifact.artifact_id}")
            return DownloadOutcome(
                ok=True,
                artifact=artifact,
                tried_http=True,
                http_status=http_result.status
            )

        # HTTP failed - log the reason
        logger.warning(f"[DOWNLOAD] HTTP failed: {http_result.error}")

        # 2) Selenium fallback (if enabled and not skipped)
        if skip_selenium or not self.selenium_service_url:
            return DownloadOutcome(
                ok=False,
                error=http_result.error or "HTTP fetch failed",
                tried_http=True,
                tried_selenium=False,
                http_status=http_result.status
            )

        logger.info("[DOWNLOAD] Attempting Selenium fallback...")
        return self._selenium_fallback(ctx, url, filename_hint, http_result.status)

    def _selenium_fallback(
        self,
        ctx: SessionContext,
        url: str,
        filename_hint: str,
        http_status: Optional[int]
    ) -> DownloadOutcome:
        """
        Attempt download via Selenium fallback service.

        Args:
            ctx: SessionContext (for patient/encounter hints)
            url: URL to download
            filename_hint: Suggested filename
            http_status: HTTP status from failed first attempt

        Returns:
            DownloadOutcome with result details
        """
        if requests is None:
            return DownloadOutcome(
                ok=False,
                error="requests library not installed",
                tried_http=True,
                tried_selenium=True,
                http_status=http_status
            )

        try:
            # Get credentials from environment (NEVER hardcode)
            username = os.environ.get("ATHENA_USERNAME", "")
            password = os.environ.get("ATHENA_PASSWORD", "")

            if not username or not password:
                logger.error("[DOWNLOAD] Selenium fallback requires ATHENA_USERNAME and ATHENA_PASSWORD env vars")
                return DownloadOutcome(
                    ok=False,
                    error="Selenium credentials not configured",
                    tried_http=True,
                    tried_selenium=True,
                    http_status=http_status
                )

            r = requests.post(
                f"{self.selenium_service_url.rstrip('/')}/download",
                json={
                    "target_url": url,
                    "username": username,
                    "password": password,
                    "headless": True,
                },
                timeout=120,
            )
            r.raise_for_status()

            payload = r.json()
            if not payload.get("ok") or not payload.get("content_b64"):
                error = payload.get("error") or "Selenium fallback failed"
                logger.error(f"[DOWNLOAD] Selenium failed: {error}")
                return DownloadOutcome(
                    ok=False,
                    error=error,
                    tried_http=True,
                    tried_selenium=True,
                    http_status=http_status
                )

            # Decode and store
            data = base64.b64decode(payload["content_b64"].encode("ascii"))
            fname = payload.get("filename") or filename_hint

            prov = Provenance.now(
                source_url=url,
                http_method="GET",
                status=200,
                artifact_hash=sha256_bytes(data),
                patient_hint=ctx.patient_hint,
                encounter_hint=ctx.encounter_hint,
                meta={"download_path": "selenium_fallback"}
            )

            artifact = self.store.put(
                bytes_data=data,
                filename=fname,
                mime_type=None,
                provenance=prov
            )

            logger.info(f"[DOWNLOAD] Success (Selenium): {artifact.artifact_id}")
            return DownloadOutcome(
                ok=True,
                artifact=artifact,
                tried_http=True,
                tried_selenium=True,
                http_status=http_status
            )

        except requests.exceptions.Timeout:
            return DownloadOutcome(
                ok=False,
                error="Selenium fallback timed out",
                tried_http=True,
                tried_selenium=True,
                http_status=http_status
            )
        except Exception as e:
            logger.error(f"[DOWNLOAD] Selenium error: {e}")
            return DownloadOutcome(
                ok=False,
                error=str(e),
                tried_http=True,
                tried_selenium=True,
                http_status=http_status
            )

    def batch_download(
        self,
        *,
        ctx: SessionContext,
        urls: List[Dict[str, str]],
        skip_selenium: bool = False
    ) -> List[DownloadOutcome]:
        """
        Download multiple files.

        Args:
            ctx: SessionContext with authentication
            urls: List of dicts with "url" and optional "filename" keys
            skip_selenium: If True, don't attempt Selenium fallback

        Returns:
            List of DownloadOutcome objects
        """
        outcomes = []
        for item in urls:
            url = item.get("url")
            if not url:
                continue
            filename = item.get("filename", "artifact.bin")
            outcome = self.download(ctx=ctx, url=url, filename_hint=filename, skip_selenium=skip_selenium)
            outcomes.append(outcome)
        return outcomes


# Global download manager instance
_manager: Optional[DownloadManager] = None


def get_download_manager(
    store_path: str = "data/artifacts",
    selenium_url: Optional[str] = None
) -> DownloadManager:
    """
    Get or create the global download manager instance.

    Args:
        store_path: Path for artifact storage
        selenium_url: Optional Selenium fallback service URL

    Returns:
        DownloadManager instance
    """
    global _manager
    if _manager is None:
        store = DiskArtifactStore(store_path)
        _manager = DownloadManager(store=store, selenium_service_url=selenium_url)
    return _manager
