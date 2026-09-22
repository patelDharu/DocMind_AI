# test_api_endpoints.py
import sys
import os
import io

WORKSPACE_ROOT = r"D:\docmind-ai"
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(WORKSPACE_ROOT, ".env"))

from fastapi.testclient import TestClient
from app.api.main import app
from app.core.auth import generate_session_token, get_or_create_demo_token

client = TestClient(app)

def test_endpoints():
    print("Testing FastAPI Route Authentication & Protection...")

    # 1. Public endpoints
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    res = client.get("/health")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    print("  [OK] Public endpoints (/, /health) accessible")

    # 2. Unauthenticated calls to protected routes should return 401
    res = client.get("/documents")
    assert res.status_code == 401, f"Expected 401 for unauthenticated /documents, got {res.status_code}"
    print("  [OK] Unauthenticated GET /documents returns 401 Unauthorized")

    res = client.post("/ask", json={"question": "What is in the document?"})
    assert res.status_code == 401, f"Expected 401 for unauthenticated /ask, got {res.status_code}"
    print("  [OK] Unauthenticated POST /ask returns 401 Unauthorized")

    res = client.post("/upload", files={"file": ("test.txt", b"content", "text/plain")})
    assert res.status_code == 401, f"Expected 401 for unauthenticated /upload, got {res.status_code}"
    print("  [OK] Unauthenticated POST /upload returns 401 Unauthorized")

    # 3. Authenticated calls with Bearer token
    token = get_or_create_demo_token()
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200, f"Expected 200 for authenticated /auth/me, got {res.status_code}"
    user_data = res.json().get("user")
    assert user_data["email"] == "demo@docmind.ai", f"Expected demo user, got {user_data}"
    print(f"  [OK] Authenticated GET /auth/me works for: {user_data['email']}")

    res = client.get("/documents", headers=headers)
    assert res.status_code == 200, f"Expected 200 for authenticated /documents, got {res.status_code}"
    print("  [OK] Authenticated GET /documents returns 200 OK")

    # 4. Voice cap test (>15 MB file rejected with 413)
    oversized_audio = io.BytesIO(b"0" * (16 * 1024 * 1024))  # 16 MB
    res = client.post(
        "/ask-voice",
        files={"file": ("large_voice.wav", oversized_audio, "audio/wav")},
        headers=headers,
    )
    assert res.status_code == 413, f"Expected 413 for >15MB voice recording, got {res.status_code}"
    print("  [OK] POST /ask-voice strictly rejects files >15MB with HTTP 413")

    # 5. Document upload test with authentication
    sample_file = io.BytesIO(b"DocMind Enterprise AI test content for automated verification.")
    res = client.post(
        "/upload",
        files={"file": ("api_test_doc.txt", sample_file, "text/plain")},
        headers=headers,
    )
    assert res.status_code == 200, f"Expected 200 for authenticated upload, got {res.status_code}: {res.text}"
    uploaded_doc_id = res.json()["document_id"]
    print(f"  [OK] Authenticated POST /upload succeeded: {uploaded_doc_id}")

    # Clean up test document
    del_res = client.delete(f"/documents/{uploaded_doc_id}", headers=headers)
    assert del_res.status_code == 200, f"Expected 200 for delete, got {del_res.status_code}"
    print(f"  [OK] Authenticated DELETE /documents/{uploaded_doc_id} succeeded")

    print("\nALL FASTAPI ROUTE AUTH & SIZE LIMIT TESTS PASSED!")

if __name__ == "__main__":
    test_endpoints()
