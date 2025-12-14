"""
Files Module: Document and Artifact Download System

This module provides HTTP-first file downloading with Selenium fallback
for authenticated Athena EHR document retrieval.

Components:
- SessionContext: Captures browser session auth (cookies, headers)
- HttpFetcher: HTTP-first download using session credentials
- ArtifactStore: Persists downloaded files with provenance
- DownloadManager: Orchestrates HTTP + Selenium fallback
- SeleniumFallbackService: Isolated Selenium service for auth-required downloads

Design Philosophy:
1. HTTP-first: Use captured session cookies whenever possible (fast, no browser)
2. Selenium fallback: Only when HTTP fails (quarantined, never default)
3. Provenance: Every artifact gets immutable traceability
"""

from .session_context import SessionContext, get_session_context, set_session_context
from .http_fetcher import fetch_bytes, HttpFetchResult
from .artifact_store import ArtifactStore, DiskArtifactStore, StoredArtifact, get_artifact_store
from .download_manager import DownloadManager, DownloadOutcome, get_download_manager

__all__ = [
    "SessionContext",
    "get_session_context",
    "set_session_context",
    "fetch_bytes",
    "HttpFetchResult",
    "ArtifactStore",
    "DiskArtifactStore",
    "StoredArtifact",
    "get_artifact_store",
    "DownloadManager",
    "DownloadOutcome",
    "get_download_manager",
]
