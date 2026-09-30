# app/core/gdrive.py

import os
import re
import cgi
import logging
from pathlib import Path
from typing import Tuple, Optional
import requests

logger = logging.getLogger("docmind.gdrive")

MAX_DRIVE_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB cap


def parse_google_drive_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses a Google Drive or Google Docs URL and returns:
    (file_id, doc_type)
    doc_type can be 'file', 'document', 'spreadsheets', 'presentation', or None if invalid.
    """
    if not url or not isinstance(url, str):
        return None, None

    url = url.strip()

    # Google Docs
    doc_match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url)
    if doc_match:
        return doc_match.group(1), "document"

    # Google Sheets
    sheet_match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if sheet_match:
        return sheet_match.group(1), "spreadsheets"

    # Google Slides
    slides_match = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", url)
    if slides_match:
        return slides_match.group(1), "presentation"

    # Standard Google Drive File
    file_match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if file_match:
        return file_match.group(1), "file"

    # Google Drive Open ID / UC URL
    id_match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if id_match and "drive.google.com" in url:
        return id_match.group(1), "file"

    # Direct /d/ pattern
    direct_match = re.search(r"drive\.google\.com/.*?/([a-zA-Z0-9_-]{25,})", url)
    if direct_match:
        return direct_match.group(1), "file"

    return None, None


def _get_confirm_token(response: requests.Response) -> Optional[str]:
    """Extracts virus scan warning confirmation token for large Google Drive files."""
    try:
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                return value
    except Exception:
        pass

    # Check for confirmation token in HTML page
    resp_text = getattr(response, "text", "")
    if isinstance(resp_text, str) and resp_text:
        match = re.search(r'confirm=([0-9A-Za-z_]+)', resp_text)
        if match:
            return match.group(1)
    return None


def _extract_filename_from_headers(response: requests.Response, default_name: str) -> str:
    """Extracts clean filename from Content-Disposition header if available."""
    content_disp = response.headers.get("Content-Disposition", "")
    if content_disp:
        _, params = cgi.parse_header(content_disp)
        fname = params.get("filename*") or params.get("filename")
        if fname:
            if fname.lower().startswith("utf-8''"):
                fname = fname[7:]
            clean_fname = Path(fname).name
            clean_fname = re.sub(r'[\\/*?:"<>|]', "", clean_fname)
            if clean_fname:
                return clean_fname
    return default_name


def download_google_drive_file(url: str, output_dir: Path) -> Tuple[Path, str]:
    """
    Downloads a shared Google Drive file or Google Workspace document into output_dir.
    Returns (saved_file_path, original_filename).
    Raises ValueError on invalid URL, permission error, or file exceeding size limits.
    """
    file_id, doc_type = parse_google_drive_url(url)
    if not file_id:
        raise ValueError(
            "Invalid Google Drive link. Please provide a valid link from Google Drive or Google Docs "
            "(e.g., https://drive.google.com/file/d/... or https://docs.google.com/document/d/...)"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Attempt authenticated download via Google Drive OAuth/MCP if authenticated
    # This allows seamless downloading of private files from the user's connected Google Drive!
    try:
        from app.core.gdrive_mcp import is_authenticated, download_drive_file as download_drive_mcp
        if is_authenticated():
            try:
                logger.info(f"Attempting download via authenticated Google Drive OAuth API for file ID: {file_id}")
                return download_drive_mcp(file_id, output_dir)
            except Exception as oauth_err:
                logger.warning(f"OAuth Drive download attempt failed ({oauth_err}), falling back to public link...")
    except ImportError:
        pass

    # 2. Try gdown for public / shared links (handles warning screens, cookies, and tokens automatically)
    if doc_type == "file":
        try:
            import gdown
            clean_url = f"https://drive.google.com/uc?id={file_id}"
            temp_target = output_dir / f"gdown_{file_id}"
            out = gdown.download(clean_url, str(temp_target), quiet=True, fuzzy=True)
            if out and Path(out).exists() and Path(out).stat().st_size > 0:
                final_path = Path(out)
                file_size = final_path.stat().st_size
                if file_size <= MAX_DRIVE_DOWNLOAD_BYTES:
                    # Check if gdown accidentally downloaded HTML login page
                    try:
                        with open(final_path, "rb") as test_f:
                            header = test_f.read(1024)
                            if b"ServiceLogin" not in header and b"accounts.google.com" not in header:
                                logger.info(f"Successfully downloaded file via gdown: {final_path.name} ({file_size} bytes)")
                                return final_path, final_path.name
                    except Exception:
                        pass
                if final_path.exists():
                    try:
                        final_path.unlink()
                    except Exception:
                        pass
        except Exception as gdown_err:
            logger.warning(f"gdown attempt skipped ({gdown_err}), proceeding with direct stream...")

    # 3. Direct web download cascade for public files / shared links
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })

    # Prepare URL candidates based on doc_type
    if doc_type == "document":
        candidate_urls = [f"https://docs.google.com/document/d/{file_id}/export?format=pdf"]
        default_filename = f"google_doc_{file_id[:8]}.pdf"
    elif doc_type == "spreadsheets":
        candidate_urls = [f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"]
        default_filename = f"google_sheet_{file_id[:8]}.xlsx"
    elif doc_type == "presentation":
        candidate_urls = [f"https://docs.google.com/presentation/d/{file_id}/export?format=pdf"]
        default_filename = f"google_slides_{file_id[:8]}.pdf"
    else:
        # Standard Drive File: Try modern drive.usercontent.google.com CDN first, then uc fallback
        candidate_urls = [
            f"https://drive.usercontent.google.com/download?id={file_id}&export=download&authuser=0&confirm=t",
            f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t",
            f"https://drive.google.com/uc?export=download&id={file_id}",
        ]
        default_filename = f"drive_document_{file_id[:8]}.pdf"

    res = None
    last_error = None

    for download_url in candidate_urls:
        try:
            logger.info(f"Connecting to Google Drive download URL: {download_url}")
            res = session.get(download_url, stream=True, timeout=30, allow_redirects=True)

            # Check if an HTML confirmation page was returned for large files
            content_type = res.headers.get("Content-Type", "").lower() if hasattr(res, "headers") else ""
            if "text/html" in content_type:
                resp_text = getattr(res, "text", "") or ""

                # Check if Google returned a login redirect (Private file)
                if "ServiceLogin" in resp_text or "accounts.google.com" in resp_text:
                    logger.warning("Google Drive returned login page (file is private/restricted).")
                    break

                # Check for confirmation form
                # <form id="download-form" action="https://drive.usercontent.google.com/download" method="get">
                form_action_match = re.search(r'<form[^>]+action="([^"]+)"', resp_text)
                form_inputs = dict(re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', resp_text))

                if form_action_match and form_inputs:
                    action_url = form_action_match.group(1)
                    if not action_url.startswith("http"):
                        action_url = "https://drive.usercontent.google.com" + action_url
                    logger.info(f"Submitting Google Drive confirmation form to {action_url} with params {list(form_inputs.keys())}")
                    res = session.get(action_url, params=form_inputs, stream=True, timeout=60, allow_redirects=True)
                else:
                    # Token-based confirmation fallback
                    token = _get_confirm_token(res)
                    if token:
                        confirm_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm={token}&uuid="
                        res = session.get(confirm_url, stream=True, timeout=60, allow_redirects=True)

            if res.ok and "text/html" not in res.headers.get("Content-Type", "").lower():
                break
        except Exception as conn_err:
            logger.warning(f"Error querying {download_url}: {conn_err}")
            last_error = conn_err

    # 3. Check HTTP status and diagnose permission issues
    if res is None or not res.ok:
        status_code = res.status_code if res else "No response"
        if status_code == 404:
            raise ValueError("Google Drive file not found. Please verify the URL is correct.")

        raise ValueError(
            "Access denied to Google Drive file. Please ensure the link sharing is set to 'Anyone with the link can view'.\n\n"
            "If deploying on Render:\n"
            "• Option A: Right-click the file in Google Drive -> Share -> Change 'General access' to 'Anyone with the link can view' (Viewer).\n"
            "• Option B (Recommended): Connect your Google account on Render by adding the 'GDRIVE_TOKEN_JSON' environment variable "
            "in your Render Dashboard with the contents of your local 'credentials/token.json'."
        )

    content_type = res.headers.get("Content-Type", "").lower() if hasattr(res, "headers") else ""
    if "text/html" in content_type and doc_type == "file":
        resp_text = getattr(res, "text", "") or ""
        if "ServiceLogin" in resp_text or "accounts.google.com" in resp_text:
            raise ValueError(
                "Access denied to Google Drive file. This file is private and restricted.\n\n"
                "To access this file on Render:\n"
                "1. In Google Drive, click Share -> Change 'General access' to 'Anyone with the link can view' (Viewer).\n"
                "2. OR connect Google Drive on Render: In Render Dashboard > Environment, add the variable 'GDRIVE_TOKEN_JSON' "
                "with the JSON from your local 'credentials/token.json'. This enables direct Google Drive API access for private files."
            )

    filename = _extract_filename_from_headers(res, default_filename)
    dest_path = output_dir / f"gdrive_{file_id}_{filename}"

    # 4. Stream download to disk with 25 MB size enforcement
    downloaded_bytes = 0
    with open(dest_path, "wb") as f:
        for chunk in res.iter_content(chunk_size=64 * 1024):
            if chunk:
                downloaded_bytes += len(chunk)
                if downloaded_bytes > MAX_DRIVE_DOWNLOAD_BYTES:
                    f.close()
                    if dest_path.exists():
                        dest_path.unlink()
                    raise ValueError(
                        f"Google Drive file exceeds maximum allowed size of 25 MB ({downloaded_bytes / (1024 * 1024):.1f} MB)."
                    )
                f.write(chunk)

    if downloaded_bytes == 0:
        if dest_path.exists():
            dest_path.unlink()
        raise ValueError("Google Drive document appears to be empty (0 bytes received).")

    logger.info(f"Successfully downloaded Google Drive document '{filename}' ({downloaded_bytes / (1024*1024):.2f} MB)")
    return dest_path, filename
