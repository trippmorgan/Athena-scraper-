"""
Session Context: Browser-Captured Authentication State

This module captures the authentication context from the user's active
Athena browser session, enabling HTTP-first downloads without Selenium.

The Chrome extension extracts:
- Session cookies (auth tokens, CSRF tokens)
- Request headers (User-Agent, custom headers)
- Base URL for the Athena instance

SECURITY NOTES:
- Do NOT persist this long-term
- Prefer redacting/whitelisting headers in the extension before sending
- Session context expires when the user's browser session expires
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionContext:
    """
    Short-lived, session-derived auth context captured from the user's active Athena session.

    IMPORTANT:
    - Do NOT persist this long-term.
    - Prefer redacting/whitelisting headers in the extension before sending.

    Attributes:
        base_url: Base URL of the Athena instance (e.g., "https://athena.example.com")
        cookies: Dictionary of session cookies
        headers: Dictionary of request headers (include CSRF if needed)
        user_agent: Browser User-Agent string
        patient_hint: Current patient ID if known
        encounter_hint: Current encounter ID if known
    """
    base_url: str  # e.g. "https://athena.example.com"
    cookies: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    user_agent: Optional[str] = None

    patient_hint: Optional[str] = None
    encounter_hint: Optional[str] = None

    def cookie_header(self) -> str:
        """
        Format cookies as a Cookie header string.

        Returns:
            String formatted as "key1=value1; key2=value2"
        """
        return "; ".join([f"{k}={v}" for k, v in self.cookies.items() if v is not None])

    def with_patient(self, patient_id: str) -> "SessionContext":
        """
        Create a new SessionContext with patient hint set.

        Args:
            patient_id: The patient identifier

        Returns:
            New SessionContext with patient_hint populated
        """
        return SessionContext(
            base_url=self.base_url,
            cookies=self.cookies,
            headers=self.headers,
            user_agent=self.user_agent,
            patient_hint=patient_id,
            encounter_hint=self.encounter_hint,
        )

    def with_encounter(self, encounter_id: str) -> "SessionContext":
        """
        Create a new SessionContext with encounter hint set.

        Args:
            encounter_id: The encounter identifier

        Returns:
            New SessionContext with encounter_hint populated
        """
        return SessionContext(
            base_url=self.base_url,
            cookies=self.cookies,
            headers=self.headers,
            user_agent=self.user_agent,
            patient_hint=self.patient_hint,
            encounter_hint=encounter_id,
        )

    @staticmethod
    def from_extension_message(msg: Dict[str, Any]) -> "SessionContext":
        """
        Create SessionContext from Chrome extension message.

        Expected message format:
        {
            "type": "SESSION_CONTEXT",
            "baseUrl": "https://...",
            "cookies": {"name": "value", ...},
            "headers": {"Header-Name": "value", ...},
            "userAgent": "Mozilla/...",
            "patientId": "12345",
            "encounterId": "67890"
        }

        Args:
            msg: Dictionary from extension message

        Returns:
            SessionContext populated from the message
        """
        return SessionContext(
            base_url=msg.get("baseUrl", msg.get("base_url", "")),
            cookies=msg.get("cookies", {}),
            headers=msg.get("headers", {}),
            user_agent=msg.get("userAgent", msg.get("user_agent")),
            patient_hint=msg.get("patientId", msg.get("patient_id")),
            encounter_hint=msg.get("encounterId", msg.get("encounter_id")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "base_url": self.base_url,
            "cookies": self.cookies,
            "headers": self.headers,
            "user_agent": self.user_agent,
            "patient_hint": self.patient_hint,
            "encounter_hint": self.encounter_hint,
        }

    def is_valid(self) -> bool:
        """
        Check if this session context has minimum required data.

        Returns:
            True if base_url and at least one cookie are present
        """
        return bool(self.base_url) and bool(self.cookies)

    def __repr__(self) -> str:
        cookie_count = len(self.cookies)
        header_count = len(self.headers)
        return (
            f"SessionContext(base_url='{self.base_url}', "
            f"cookies={cookie_count}, headers={header_count}, "
            f"patient={self.patient_hint}, encounter={self.encounter_hint})"
        )


# Global session context storage (in-memory, short-lived)
_current_session: Optional[SessionContext] = None


def set_session_context(ctx: SessionContext) -> None:
    """Set the current session context (called when extension sends session data)."""
    global _current_session
    _current_session = ctx
    logger.info(f"[SESSION] Updated: {ctx}")


def get_session_context() -> Optional[SessionContext]:
    """Get the current session context if available."""
    return _current_session


def clear_session_context() -> None:
    """Clear the current session context (on logout or expiry)."""
    global _current_session
    _current_session = None
    logger.info("[SESSION] Cleared")
