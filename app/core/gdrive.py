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
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # 1. Google Workspace Documents (Docs, Sheets, Slides) -> Export formatted files
    if doc_type == "document":
        download_url = f"https://docs.google.com/document/d/{file_id}/export?format=pdf"
        default_filename = f"google_doc_{file_id[:8]}.pdf"
    elif doc_type == "spreadsheets":
        download_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
        default_filename = f"google_sheet_{file_id[:8]}.xlsx"
    elif doc_type == "presentation":
        download_url = f"https://docs.google.com/presentation/d/{file_id}/export?format=pdf"
        default_filename = f"google_slides_{file_id[:8]}.pdf"
    else:
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        default_filename = f"drive_document_{file_id[:8]}.pdf"

    logger.info(f"Connecting to Google Drive URL: {download_url}")
    res = session.get(download_url, stream=True, timeout=30)

    # 2. Check for virus warning confirmation token for large shared files (>10MB)
    token = _get_confirm_token(res)
    if token:
        confirm_url = f"https://drive.google.com/uc?export=download&confirm={token}&id={file_id}"
        logger.info(f"Following Google Drive large file confirmation: {confirm_url}")
        res = session.get(confirm_url, stream=True, timeout=60)

    # 3. Check HTTP status
    if res.status_code == 404:
        raise ValueError("Google Drive file not found. Please verify the link is correct.")
    if res.status_code in [401, 403]:
        raise ValueError(
            "Access denied to Google Drive file. Please ensure the link sharing is set to 'Anyone with the link can view'."
        )
    if not res.ok:
        raise ValueError(f"Failed to download Google Drive document (HTTP {res.status_code}).")

    content_type = res.headers.get("Content-Type", "").lower() if hasattr(res, "headers") else ""
    if "text/html" in content_type and doc_type == "file":
        resp_text = getattr(res, "text", "") or ""
        if isinstance(resp_text, str) and ("ServiceLogin" in resp_text or "accounts.google.com" in resp_text):
            raise ValueError(
                "This Google Drive file is private. Please update Google Drive sharing settings to "
                "'Anyone with the link can view' and try again."
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
