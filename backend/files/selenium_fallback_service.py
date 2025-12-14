"""
Selenium Fallback Service: Isolated Browser Automation for Auth-Required Downloads

DESIGN GOALS:
- Quarantine Selenium + credentials in a separate service/container
- Never run by default (only when HTTP-first fails)
- Use environment variables or secrets manager (NOT config.yaml with passwords)
- Provide a narrow API: "download this URL within the logged-in session"

This is a standalone FastAPI service that:
1. Launches a browser (optional headless)
2. Logs in to Athena (tenant-specific selectors)
3. Downloads a given URL to a temp dir
4. Returns the bytes (base64) or writes to shared storage

SECURITY NOTES:
- Run this in a separate container/process
- Credentials should come from env vars or secrets manager
- Limit network access (only allow connections from main backend)
- Consider using Selenium Grid for scalability

CUSTOMIZATION:
- You MUST customize perform_login() for your Athena tenant
- Update selectors for username, password, submit button, and post-login indicator

USAGE:
    # Start as standalone service:
    uvicorn backend.files.selenium_fallback_service:app --host 0.0.0.0 --port 8081

    # Or via Docker:
    docker run -p 8081:8081 -e ATHENA_LOGIN_URL=https://... selenium-fallback

    # Call from main backend:
    POST http://selenium-fallback:8081/download
    {
        "target_url": "https://.../download/123",
        "username": "...",
        "password": "...",
        "headless": true
    }
"""

from __future__ import annotations

import base64
import os
import time
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Conditional import - Selenium may not be installed
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("[SELENIUM] selenium package not installed - fallback service disabled")


# FastAPI app
app = FastAPI(
    title="Athena Selenium Fallback Service",
    description="Isolated browser automation for auth-required downloads",
    version="1.0.0"
)


class DownloadRequest(BaseModel):
    """Request model for download endpoint."""
    target_url: str
    username: str
    password: str
    headless: bool = True
    timeout_s: int = 90


class DownloadResponse(BaseModel):
    """Response model for download endpoint."""
    ok: bool
    filename: Optional[str] = None
    content_b64: Optional[str] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Response model for health endpoint."""
    status: str
    selenium_available: bool
    login_url_configured: bool


def make_driver(download_dir: str, headless: bool) -> "webdriver.Chrome":
    """
    Create a Chrome WebDriver configured for downloads.

    Args:
        download_dir: Directory where downloads will be saved
        headless: Whether to run in headless mode

    Returns:
        Configured Chrome WebDriver instance
    """
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium not installed")

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")

    # Configure download behavior
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True,  # Download PDFs instead of opening
    }
    opts.add_experimental_option("prefs", prefs)

    return webdriver.Chrome(options=opts)


def perform_login(driver: "webdriver.Chrome", username: str, password: str) -> None:
    """
    Perform login to Athena EHR.

    TENANT-SPECIFIC: You MUST customize this function for your Athena instance.
    Update the selectors and login URL as needed.

    Args:
        driver: Chrome WebDriver instance
        username: Athena username
        password: Athena password

    Raises:
        RuntimeError: If login URL not configured or login fails
    """
    login_url = os.environ.get("ATHENA_LOGIN_URL")
    if not login_url:
        raise RuntimeError("ATHENA_LOGIN_URL environment variable not set")

    logger.info(f"[SELENIUM] Navigating to login: {login_url}")
    driver.get(login_url)

    # Wait for page to load
    wait = WebDriverWait(driver, 30)

    # =========================================================================
    # CUSTOMIZE THESE SELECTORS FOR YOUR ATHENA TENANT
    # =========================================================================

    # Username field - try multiple selectors
    username_selectors = [
        (By.ID, "username"),
        (By.ID, "login-username"),
        (By.NAME, "username"),
        (By.CSS_SELECTOR, "input[type='text']"),
        (By.CSS_SELECTOR, "input[name='username']"),
        (By.CSS_SELECTOR, "input[autocomplete='username']"),
    ]

    user_el = None
    for by, selector in username_selectors:
        try:
            user_el = wait.until(EC.presence_of_element_located((by, selector)))
            logger.info(f"[SELENIUM] Found username field: {selector}")
            break
        except Exception:
            continue

    if not user_el:
        raise RuntimeError("Could not find username field")

    # Password field - try multiple selectors
    password_selectors = [
        (By.ID, "password"),
        (By.ID, "login-password"),
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.CSS_SELECTOR, "input[name='password']"),
    ]

    pass_el = None
    for by, selector in password_selectors:
        try:
            pass_el = wait.until(EC.presence_of_element_located((by, selector)))
            logger.info(f"[SELENIUM] Found password field: {selector}")
            break
        except Exception:
            continue

    if not pass_el:
        raise RuntimeError("Could not find password field")

    # Fill credentials
    logger.info("[SELENIUM] Entering credentials...")
    user_el.clear()
    user_el.send_keys(username)
    pass_el.clear()
    pass_el.send_keys(password)

    # Submit - try multiple methods
    submitted = False

    # Try submit button
    submit_selectors = [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
        (By.ID, "login-button"),
        (By.ID, "submit"),
        (By.CSS_SELECTOR, "button.login-button"),
    ]

    for by, selector in submit_selectors:
        try:
            submit_btn = driver.find_element(by, selector)
            submit_btn.click()
            submitted = True
            logger.info(f"[SELENIUM] Clicked submit: {selector}")
            break
        except Exception:
            continue

    # Fallback: submit via password field
    if not submitted:
        logger.info("[SELENIUM] Submitting via password field...")
        pass_el.submit()

    # Wait for post-login indicator (customize for your tenant)
    logger.info("[SELENIUM] Waiting for login to complete...")
    time.sleep(3)  # Initial wait

    # Check for successful login indicators
    post_login_indicators = [
        (By.CSS_SELECTOR, ".dashboard"),
        (By.CSS_SELECTOR, ".patient-search"),
        (By.CSS_SELECTOR, ".main-content"),
        (By.CSS_SELECTOR, "[data-test='logged-in']"),
    ]

    logged_in = False
    for by, selector in post_login_indicators:
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((by, selector)))
            logged_in = True
            logger.info(f"[SELENIUM] Login confirmed: {selector}")
            break
        except Exception:
            continue

    if not logged_in:
        # Check for error messages
        error_selectors = [".error", ".alert-danger", ".login-error"]
        for selector in error_selectors:
            try:
                error_el = driver.find_element(By.CSS_SELECTOR, selector)
                if error_el.text:
                    raise RuntimeError(f"Login failed: {error_el.text}")
            except Exception:
                continue

        # Assume success if no errors found
        logger.warning("[SELENIUM] Could not confirm login, proceeding anyway...")


def wait_for_download(download_dir: Path, timeout_s: int = 60) -> Path:
    """
    Wait for a file download to complete.

    Args:
        download_dir: Directory to monitor for downloads
        timeout_s: Maximum time to wait in seconds

    Returns:
        Path to the downloaded file

    Raises:
        TimeoutError: If download doesn't complete within timeout
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        files = list(download_dir.glob("*"))
        # Filter out incomplete downloads (.crdownload, .tmp, .part)
        complete = [p for p in files if not any(
            p.name.endswith(ext) for ext in [".crdownload", ".tmp", ".part"]
        )]
        if complete:
            # Return most recently modified file
            return max(complete, key=lambda p: p.stat().st_mtime)
        time.sleep(0.5)

    raise TimeoutError(f"Download did not complete within {timeout_s} seconds")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if SELENIUM_AVAILABLE else "degraded",
        selenium_available=SELENIUM_AVAILABLE,
        login_url_configured=bool(os.environ.get("ATHENA_LOGIN_URL"))
    )


@app.post("/download", response_model=DownloadResponse)
async def download(req: DownloadRequest) -> DownloadResponse:
    """
    Download a file from an authenticated Athena session.

    This endpoint:
    1. Launches a browser
    2. Logs in to Athena
    3. Navigates to the target URL (triggering download)
    4. Returns the downloaded file as base64

    Args:
        req: Download request with URL and credentials

    Returns:
        DownloadResponse with base64-encoded file content
    """
    if not SELENIUM_AVAILABLE:
        return DownloadResponse(
            ok=False,
            error="Selenium not installed. Run: pip install selenium"
        )

    # Create temporary download directory
    tmp = Path("/tmp/athena_selenium_downloads")
    tmp.mkdir(parents=True, exist_ok=True)
    job_dir = tmp / str(int(time.time() * 1000))
    job_dir.mkdir(parents=True, exist_ok=True)

    driver = None
    try:
        logger.info(f"[SELENIUM] Starting download: {req.target_url}")

        # Launch browser
        driver = make_driver(str(job_dir), headless=req.headless)

        # Perform login
        perform_login(driver, req.username, req.password)

        # Navigate to target URL (should trigger download)
        logger.info(f"[SELENIUM] Navigating to target: {req.target_url}")
        driver.get(req.target_url)

        # Wait for download to complete
        fpath = wait_for_download(job_dir, timeout_s=req.timeout_s)
        logger.info(f"[SELENIUM] Download complete: {fpath.name}")

        # Read and encode file
        data = fpath.read_bytes()

        return DownloadResponse(
            ok=True,
            filename=fpath.name,
            content_b64=base64.b64encode(data).decode("ascii"),
            size_bytes=len(data)
        )

    except Exception as e:
        logger.error(f"[SELENIUM] Download failed: {e}")
        return DownloadResponse(ok=False, error=str(e))

    finally:
        # Clean up
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

        # Clean up download directory
        try:
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass


@app.post("/check-login")
async def check_login(username: str, password: str):
    """
    Test login credentials without downloading anything.

    Useful for verifying credentials are correct before using them.
    """
    if not SELENIUM_AVAILABLE:
        raise HTTPException(503, "Selenium not installed")

    driver = None
    try:
        driver = make_driver("/tmp", headless=True)
        perform_login(driver, username, password)
        return {"ok": True, "message": "Login successful"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# Run with: uvicorn backend.files.selenium_fallback_service:app --host 0.0.0.0 --port 8081
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SELENIUM_SERVICE_PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
