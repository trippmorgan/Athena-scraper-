"""
Athena-Scraper Client Modules

Provides HTTP clients for sending data to external services.
"""

from .clinical_core_client import (
    ClinicalCoreClient,
    get_client,
    disable_client,
    enable_client
)

__all__ = [
    "ClinicalCoreClient",
    "get_client",
    "disable_client",
    "enable_client"
]
