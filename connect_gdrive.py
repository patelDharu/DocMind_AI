"""
DocMind AI — Interactive Google Drive Connector
Supports either:
1. Existing 'credentials/gcp-oauth.keys.json' file
2. Entering Client ID & Client Secret directly in the terminal
"""

import os
import sys
import json
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
KEY_FILE = CREDENTIALS_DIR / "gcp-oauth.keys.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"


def main():
    print("============================================================")
    print("       DocMind AI — Google Drive MCP Connection Setup       ")
    print("============================================================")

    # 1. Check if OAuth keys already exist
    if not KEY_FILE.is_file():
        # Check if user has any other json in credentials dir
        found = list(CREDENTIALS_DIR.glob("*.json"))
        found = [f for f in found if f.name != "token.json"]
        if found:
            print(f"\n[OK] Found credentials file: {found[0].name}")
            import shutil
            shutil.copyfile(found[0], KEY_FILE)
        else:
            print("\n[?] No 'gcp-oauth.keys.json' found.")
            print("You can either:")
            print("  A. Download the JSON from Google Cloud Console and save as:")
            print(f"     {KEY_FILE}")
            print("  B. Or enter your Google OAuth Client ID and Secret right now.")
            print("------------------------------------------------------------")
            choice = input("Would you like to enter Client ID and Secret now? (y/n): ").strip().lower()
            if choice == "y":
                client_id = input("\nEnter Google Client ID: ").strip()
                client_secret = input("Enter Google Client Secret: ").strip()
                if not client_id or not client_secret:
                    print("\n[ERROR] Client ID and Secret cannot be empty.")
                    sys.exit(1)

                data = {
                    "installed": {
                        "client_id": client_id,
                        "project_id": "docmind-ai-gdrive",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_secret": client_secret,
                        "redirect_uris": ["http://localhost"]
                    }
                }
                KEY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                print(f"[OK] Generated {KEY_FILE.name} successfully!")
            else:
                print(f"\nPlease place 'gcp-oauth.keys.json' in {CREDENTIALS_DIR} and re-run this script.")
                sys.exit(0)

    # 2. Run OAuth flow
    print("\n------------------------------------------------------------")
    print("Initiating Google Drive login...")
    print("A browser window will open. Please allow Google Drive access.")
    print("------------------------------------------------------------\n")

    try:
        from app.core.gdrive_mcp import get_gdrive_credentials, list_drive_files
        creds = get_gdrive_credentials()
        print("\n[SUCCESS] Connected to Google Drive successfully!")
        print(f"Token saved to: {TOKEN_FILE}")

        print("\nTesting file retrieval...")
        files = list_drive_files(page_size=5)
        if files:
            print(f"[OK] Successfully retrieved {len(files)} files from your Drive:")
            for idx, f in enumerate(files, 1):
                sz = f"{f['size'] / (1024*1024):.1f} MB" if f.get("size") else "Doc/Sheet"
                print(f"  {idx}. {f['name']} ({sz})")
        else:
            print("[OK] Connected to Google Drive (no documents found in root).")

        print("\n============================================================")
        print("  Google Drive MCP is fully configured and ready!           ")
        print("  You can now start DocMind by running: run_docmind.bat     ")
        print("============================================================")

    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
