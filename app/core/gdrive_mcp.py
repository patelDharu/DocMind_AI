# app/core/gdrive_mcp.py
"""
Google Drive MCP Core Service for DocMind AI.
Handles OAuth2 authentication, file searching, metadata retrieval,
and document downloading/exporting via the official Google Drive API v3.
"""

import os
import io
import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("docmind.gdrive_mcp")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"
DEFAULT_CLIENT_SECRETS = [
    CREDENTIALS_DIR / "gcp-oauth.keys.json",
    CREDENTIALS_DIR / "credentials.json",
    CREDENTIALS_DIR / "client_secret.json",
]

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

MIME_EXPORTS = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


def get_client_secrets_path() -> Optional[Path]:
    """Finds the Google Cloud OAuth client secrets JSON file."""
    custom_path = os.getenv("GDRIVE_OAUTH_PATH")
    if custom_path and Path(custom_path).is_file():
        return Path(custom_path)

    for p in DEFAULT_CLIENT_SECRETS:
        if p.is_file():
            return p

    # Check for any client_secret*.json in credentials dir
    if CREDENTIALS_DIR.is_dir():
        for p in CREDENTIALS_DIR.glob("*.json"):
            if p.name != "token.json":
                return p
    return None


def is_gdrive_configured() -> bool:
    """Checks if client secrets JSON is present."""
    return get_client_secrets_path() is not None


def is_authenticated() -> bool:
    """Checks if a valid, non-expired (or refreshable) token exists."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not TOKEN_PATH.is_file():
        return False

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.valid:
            return True
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            return True
    except Exception as e:
        logger.warning(f"Error checking token validity: {e}")
    return False


def get_gdrive_credentials():
    """Returns valid google.oauth2.credentials.Credentials or raises ValueError."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    creds = None

    if TOKEN_PATH.is_file():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as e:
            logger.warning(f"Could not load token.json: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
                return creds
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}")

        # Need initial authentication flow
        secrets_path = get_client_secrets_path()
        if not secrets_path:
            raise FileNotFoundError(
                f"Google OAuth credentials not found. Please place your downloaded OAuth JSON "
                f"file in '{CREDENTIALS_DIR}\\gcp-oauth.keys.json' or set GDRIVE_OAUTH_PATH."
            )

        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Successfully generated new Google Drive OAuth token.")

    return creds


def get_drive_service():
    """Builds and returns the Google Drive API v3 resource service."""
    from googleapiclient.discovery import build

    creds = get_gdrive_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_drive_files(
    query: Optional[str] = None,
    page_size: int = 15,
) -> List[Dict[str, Any]]:
    """
    Lists or searches files from the authenticated user's Google Drive.
    """
    service = get_drive_service()

    # Exclude trashed files and folders by default
    q_parts = ["trashed = false", "mimeType != 'application/vnd.google-apps.folder'"]
    if query:
        sanitized = query.replace("'", "\\'")
        q_parts.append(f"(name contains '{sanitized}' or fullText contains '{sanitized}')")

    final_q = " and ".join(q_parts)

    response = service.files().list(
        q=final_q,
        pageSize=page_size,
        fields="files(id, name, mimeType, modifiedTime, size, webViewLink, iconLink)",
        orderBy="modifiedTime desc",
    ).execute()

    files = response.get("files", [])
    results = []
    for f in files:
        results.append({
            "id": f.get("id"),
            "name": f.get("name"),
            "mime_type": f.get("mimeType"),
            "modified_time": f.get("modifiedTime"),
            "size": int(f.get("size", 0)) if f.get("size") else None,
            "link": f.get("webViewLink"),
            "icon": f.get("iconLink"),
        })
    return results


def download_drive_file(file_id: str, output_dir: Path) -> Tuple[Path, str]:
    """
    Downloads or exports a Google Drive file to output_dir.
    Returns (saved_path, filename).
    """
    from googleapiclient.http import MediaIoBaseDownload

    service = get_drive_service()
    meta = service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
    file_name = meta.get("name", f"gdrive_doc_{file_id}")
    mime_type = meta.get("mimeType", "")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize file name for Windows/filesystem safety
    safe_file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
    if not safe_file_name:
        safe_file_name = f"gdrive_doc_{file_id}"
    dest_path = output_dir / f"mcp_gdrive_{file_id}_{safe_file_name}"

    # If it's a native Google Doc, Sheet, or Presentation, export it
    if mime_type in MIME_EXPORTS:
        export_mime, ext = MIME_EXPORTS[mime_type]
        if not file_name.endswith(ext):
            file_name += ext
        if not safe_file_name.endswith(ext):
            safe_file_name += ext
            dest_path = output_dir / f"mcp_gdrive_{file_id}_{safe_file_name}"
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_id)

    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.info(f"Download {int(status.progress() * 100)}% for {file_name}")

    logger.info(f"Successfully downloaded Drive file: {dest_path.name}")
    return dest_path, file_name


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("============================================================")
    print("  DocMind AI - Google Drive MCP Authentication & Test CLI   ")
    print("============================================================")

    if not is_gdrive_configured():
        print("\n[!] Google Cloud OAuth credentials file not found.")
        print(f"Please place your 'gcp-oauth.keys.json' in:")
        print(f"  {CREDENTIALS_DIR}\\gcp-oauth.keys.json\n")
        print("See credentials/README.md for step-by-step instructions.")
        sys.exit(1)

    print(f"\nFound credentials: {get_client_secrets_path().name}")
    print("Authenticating with Google Drive...")
    try:
        creds = get_gdrive_credentials()
        print("[OK] Authentication successful! Token saved to credentials/token.json")
        print("\nFetching recent files from your Google Drive...")
        files = list_drive_files(page_size=5)
        if files:
            print(f"Successfully connected to Google Drive! Found {len(files)} files:")
            for idx, f in enumerate(files, 1):
                print(f"  {idx}. {f['name']} (ID: {f['id']})")
        else:
            print("Connected to Google Drive! (No files found or empty Drive)")
    except Exception as e:
        print(f"\n[ERROR] Authentication failed: {e}")
        sys.exit(1)
