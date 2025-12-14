"""
HTTP Fetcher: HTTP-First Download Using Session Credentials

This module provides HTTP-based file downloading using cookies and headers
captured from the user's active browser session.

This is the preferred method because:
1. Fast - No browser overhead
2. Lightweight - Just HTTP requests
3. Reliable - Standard HTTP semantics

Use Selenium fallback only when HTTP fetch fails (e.g., JavaScript-rendered download links).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import logging

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from .session_context import SessionContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpFetchResult:
    """
    Result of an HTTP fetch operation.

    Attributes:
        ok: True if the request succeeded (2xx status)
        status: HTTP status code
        headers: Response headers
        content: Response body as bytes
        error: Error message if request failed
        final_url: Final URL after redirects
    """
    ok: bool
    status: int
    headers: Dict[str, str]
    content: bytes
    error: Optional[str] = None
    final_url: Optional[str] = None

    @property
    def content_type(self) -> Optional[str]:
        """Get the Content-Type header if present."""
        return self.headers.get("Content-Type") or self.headers.get("content-type")

    @property
    def content_length(self) -> int:
        """Get the content length."""
        return len(self.content)

    @property
    def filename_from_header(self) -> Optional[str]:
        """
        Extract filename from Content-Disposition header if present.

        Examples:
            Content-Disposition: attachment; filename="report.pdf"
            Content-Disposition: attachment; filename*=UTF-8''report%20name.pdf
        """
        cd = self.headers.get("Content-Disposition") or self.headers.get("content-disposition")
        if not cd:
            return None

        # Simple parsing - handle filename="..." or filename=...
        import re
        match = re.search(r'filename[*]?=["\']?([^"\';\s]+)["\']?', cd)
        if match:
            return match.group(1)
        return None


def fetch_bytes(
    ctx: SessionContext,
    url: str,
    timeout_s: int = 30,
    allow_redirects: bool = True,
    verify_ssl: bool = True
) -> HttpFetchResult:
    """
    HTTP-first fetch using session cookies/headers captured from the active browser session.

    Args:
        ctx: SessionContext with cookies and headers from browser
        url: URL to fetch
        timeout_s: Request timeout in seconds
        allow_redirects: Whether to follow redirects
        verify_ssl: Whether to verify SSL certificates

    Returns:
        HttpFetchResult with response data or error information
    """
    if requests is None:
        return HttpFetchResult(
            ok=False,
            status=0,
            headers={},
            content=b"",
            error="requests library not installed"
        )

    # Build headers
    hdrs = dict(ctx.headers or {})
    if ctx.user_agent and "user-agent" not in {k.lower() for k in hdrs.keys()}:
        hdrs["User-Agent"] = ctx.user_agent

    # Pass cookies both ways: requests cookie-jar + explicit header
    # This improves compatibility with odd server setups
    cookies = ctx.cookies or {}
    if cookies and "cookie" not in {k.lower() for k in hdrs.keys()}:
        hdrs["Cookie"] = ctx.cookie_header()

    logger.info(f"[HTTP] Fetching: {url}")
    logger.debug(f"[HTTP] Cookies: {len(cookies)} items")
    logger.debug(f"[HTTP] Headers: {list(hdrs.keys())}")

    try:
        r = requests.get(
            url,
            headers=hdrs,
            cookies=cookies,
            timeout=timeout_s,
            allow_redirects=allow_redirects,
            verify=verify_ssl,
            stream=False  # Load full content
        )

        result = HttpFetchResult(
            ok=bool(r.ok),
            status=int(r.status_code),
            headers={k: v for k, v in r.headers.items()},
            content=r.content or b"",
            error=None if r.ok else f"HTTP {r.status_code}",
            final_url=r.url if r.url != url else None
        )

        if result.ok:
            logger.info(f"[HTTP] Success: {result.status}, {result.content_length} bytes")
        else:
            logger.warning(f"[HTTP] Failed: {result.status} - {url}")

        return result

    except requests.exceptions.Timeout:
        logger.error(f"[HTTP] Timeout after {timeout_s}s: {url}")
        return HttpFetchResult(
            ok=False,
            status=0,
            headers={},
            content=b"",
            error=f"Timeout after {timeout_s}s"
        )
    except requests.exceptions.SSLError as e:
        logger.error(f"[HTTP] SSL Error: {e}")
        return HttpFetchResult(
            ok=False,
            status=0,
            headers={},
            content=b"",
            error=f"SSL Error: {e}"
        )
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[HTTP] Connection Error: {e}")
        return HttpFetchResult(
            ok=False,
            status=0,
            headers={},
            content=b"",
            error=f"Connection Error: {e}"
        )
    except Exception as e:
        logger.error(f"[HTTP] Unexpected error: {e}")
        return HttpFetchResult(
            ok=False,
            status=0,
            headers={},
            content=b"",
            error=str(e)
        )


def fetch_json(
    ctx: SessionContext,
    url: str,
    timeout_s: int = 30
) -> tuple[bool, Optional[Dict], Optional[str]]:
    """
    Fetch JSON data using session context.

    Args:
        ctx: SessionContext with cookies and headers
        url: URL to fetch
        timeout_s: Request timeout in seconds

    Returns:
        Tuple of (success, json_data, error_message)
    """
    result = fetch_bytes(ctx, url, timeout_s)
    if not result.ok:
        return False, None, result.error

    try:
        import json
        data = json.loads(result.content.decode("utf-8"))
        return True, data, None
    except Exception as e:
        return False, None, f"JSON parse error: {e}"


def head_request(
    ctx: SessionContext,
    url: str,
    timeout_s: int = 10
) -> HttpFetchResult:
    """
    Perform HEAD request to check URL availability without downloading content.

    Args:
        ctx: SessionContext with cookies and headers
        url: URL to check
        timeout_s: Request timeout in seconds

    Returns:
        HttpFetchResult (content will be empty)
    """
    if requests is None:
        return HttpFetchResult(
            ok=False,
            status=0,
            headers={},
            content=b"",
            error="requests library not installed"
        )

    hdrs = dict(ctx.headers or {})
    if ctx.user_agent:
        hdrs["User-Agent"] = ctx.user_agent
    if ctx.cookies:
        hdrs["Cookie"] = ctx.cookie_header()

    try:
        r = requests.head(
            url,
            headers=hdrs,
            cookies=ctx.cookies,
            timeout=timeout_s,
            allow_redirects=True
        )
        return HttpFetchResult(
            ok=bool(r.ok),
            status=int(r.status_code),
            headers={k: v for k, v in r.headers.items()},
            content=b"",
            error=None if r.ok else f"HTTP {r.status_code}",
            final_url=r.url if r.url != url else None
        )
    except Exception as e:
        return HttpFetchResult(
            ok=False,
            status=0,
            headers={},
            content=b"",
            error=str(e)
        )
