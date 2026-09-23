# test_gdrive_integration.py
"""
Automated unit and integration test suite for Google Drive document connection.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.core.gdrive import parse_google_drive_url, download_google_drive_file


def test_url_parsing():
    print("\n--- Test 1: Google Drive URL Parsing ---")

    # 1. Standard file link
    url1 = "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view?usp=sharing"
    fid, dtype = parse_google_drive_url(url1)
    assert fid == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", f"Expected file ID, got {fid}"
    assert dtype == "file", f"Expected 'file', got {dtype}"
    print("  [OK] Standard drive.google.com/file/d/ link parsed correctly.")

    # 2. Open ID link
    url2 = "https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz_12345"
    fid, dtype = parse_google_drive_url(url2)
    assert fid == "1AbCdEfGhIjKlMnOpQrStUvWxYz_12345"
    assert dtype == "file"
    print("  [OK] Open ID drive.google.com/open?id= link parsed correctly.")

    # 3. Google Docs link
    url3 = "https://docs.google.com/document/d/1t_2e3S4T5_u6R7l8/edit?usp=drivesdk"
    fid, dtype = parse_google_drive_url(url3)
    assert fid == "1t_2e3S4T5_u6R7l8"
    assert dtype == "document"
    print("  [OK] docs.google.com/document/d/ link parsed as 'document'.")

    # 4. Google Sheets link
    url4 = "https://docs.google.com/spreadsheets/d/1sheetId_987654321/edit#gid=0"
    fid, dtype = parse_google_drive_url(url4)
    assert fid == "1sheetId_987654321"
    assert dtype == "spreadsheets"
    print("  [OK] docs.google.com/spreadsheets/d/ link parsed as 'spreadsheets'.")

    # 5. Google Slides link
    url5 = "https://docs.google.com/presentation/d/1slides_pres_12345/edit"
    fid, dtype = parse_google_drive_url(url5)
    assert fid == "1slides_pres_12345"
    assert dtype == "presentation"
    print("  [OK] docs.google.com/presentation/d/ link parsed as 'presentation'.")

    # 6. Invalid link
    fid, dtype = parse_google_drive_url("https://example.com/not-drive")
    assert fid is None and dtype is None
    print("  [OK] Non-Drive URL correctly rejected.")


def test_download_mock():
    print("\n--- Test 2: Mocked Google Drive File Download ---")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Disposition": 'attachment; filename="annual_report_2025.pdf"'}
    mock_resp.iter_content = MagicMock(return_value=[b"%PDF-1.4 Mock PDF Content with financial terms"])
    mock_resp.cookies = {}

    out_dir = Path("app/data/uploads/test_drive")
    with patch("requests.Session.get", return_value=mock_resp):
        saved_path, fname = download_google_drive_file(
            "https://drive.google.com/file/d/1mockFileId12345/view",
            out_dir,
        )
        assert saved_path.exists(), "Downloaded file should exist"
        assert fname == "annual_report_2025.pdf", f"Expected 'annual_report_2025.pdf', got '{fname}'"
        print(f"  [OK] Mocked download succeeded: {fname} ({saved_path.stat().st_size} bytes)")

        # Cleanup
        if saved_path.exists():
            saved_path.unlink()
    if out_dir.exists():
        try:
            out_dir.rmdir()
        except Exception:
            pass


def main():
    print("=" * 60)
    print("  DocMind AI Google Drive Connection Verification Suite")
    print("=" * 60)
    test_url_parsing()
    test_download_mock()
    print("\n" + "=" * 60)
    print("  ALL GOOGLE DRIVE TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    main()
