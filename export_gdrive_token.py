# export_gdrive_token.py
"""
Utility script to display the Google Drive OAuth token for Render deployment.
Copy and paste this environment variable into your Render Dashboard under the 'Environment' tab.
"""

import sys
import json
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent
TOKEN_PATH = WORKSPACE_ROOT / "credentials" / "token.json"


def main():
    print("=" * 65)
    print("   DocMind AI — Google Drive Token Exporter for Render       ")
    print("=" * 65)

    if not TOKEN_PATH.is_file():
        print(f"\n[!] Token file not found at: {TOKEN_PATH}")
        print("Please authenticate locally first by running:")
        print("    python connect_gdrive.py")
        sys.exit(1)

    try:
        raw_content = TOKEN_PATH.read_text(encoding="utf-8").strip()
        # Validate that it is valid JSON
        token_data = json.loads(raw_content)
        # Compact single-line JSON string suitable for Render environment variables
        compact_json = json.dumps(token_data, separators=(",", ":"))

        print("\n[SUCCESS] Google Drive token found!")
        print("\nTo enable Google Drive imports on Render:")
        print("1. Open your Render Dashboard -> Your Web Service -> 'Environment' tab.")
        print("2. Add a new Environment Variable with:")
        print("-" * 65)
        print("Key:")
        print("GDRIVE_TOKEN_JSON")
        print("\nValue (Copy the entire line below):")
        print(compact_json)
        print("-" * 65)
        print("\n3. Click 'Save Changes'. Render will automatically redeploy.")
        print("   All Google Drive imports (both private and public) will work seamlessly!\n")

    except Exception as e:
        print(f"\n[ERROR] Failed to read token file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
