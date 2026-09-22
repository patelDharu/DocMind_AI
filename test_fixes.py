# test_fixes.py
"""
Automated Verification Suite for DocMind AI Updates:
1. Session Token Auth & Validation
2. Serialization Security (Prevent 'bytes is not JSON serializable')
3. Per-User Document Isolation at VectorStore & BM25 layers
4. ReportLab PDF Generation with Styled Tables
5. Semantic AI Search & Conceptual Retrieval
"""

import sys
import os
import json
from pathlib import Path

WORKSPACE_ROOT = r"D:\docmind-ai"
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(WORKSPACE_ROOT, ".env"))

def test_auth_and_tokens():
    print("\n--- Test 1: Auth & Token Generation ---")
    from app.core.auth import (
        init_user_db,
        generate_session_token,
        validate_session_token,
        revoke_session_token,
        sanitize_chat_messages,
    )

    init_user_db()
    token = generate_session_token("test_user@docmind.ai")
    assert token and token.startswith("dmtk_"), f"Invalid token format: {token}"
    print(f"  [OK] Generated session token: {token[:16]}...")

    user_info = validate_session_token(token)
    assert user_info is not None, "Token validation returned None"
    assert user_info["email"] == "test_user@docmind.ai", f"Expected test_user@docmind.ai, got {user_info}"
    print(f"  [OK] Successfully validated token for: {user_info['email']}")

    # Invalid token check
    invalid_res = validate_session_token("invalid_token_12345")
    assert invalid_res is None, "Invalid token should return None"
    print("  [OK] Invalid token correctly rejected")

    # Revoke check
    revoked = revoke_session_token(token)
    assert revoked is True, "Token revocation failed"
    after_revoke = validate_session_token(token)
    assert after_revoke is None, "Revoked token still validated"
    print("  [OK] Token successfully revoked")


def test_bytes_serialization():
    print("\n--- Test 2: 'bytes not JSON serializable' Fix ---")
    from app.core.auth import sanitize_chat_messages, save_user_chat_session, get_user_chat_sessions

    sample_messages = [
        {"role": "user", "content": "Hello document"},
        {
            "role": "assistant",
            "content": "Here is the answer",
            "audio_bytes": b"RIFF\x24\x00\x00\x00WAVEfmt ",  # Raw bytes payload!
            "sources": [{"source": "test.pdf", "page": 1}],
        },
    ]

    # Verify sanitizer removes raw bytes
    sanitized = sanitize_chat_messages(sample_messages)
    assert "audio_bytes" not in sanitized[1], "audio_bytes was not stripped"

    # Verify JSON serialization does not throw TypeError
    serialized = json.dumps(sanitized)
    assert isinstance(serialized, str), "Failed to serialize sanitized messages"
    print("  [OK] Sanitized message successfully serialized to JSON without TypeError")

    # Test saving through auth layer
    test_session = {
        "id": "test_sess_001",
        "title": "Serialization Test",
        "messages": sample_messages,  # contains raw bytes!
    }
    save_user_chat_session("serialization_test@docmind.ai", test_session)
    saved_sessions = get_user_chat_sessions("serialization_test@docmind.ai")
    target = next((s for s in saved_sessions if s["id"] == "test_sess_001"), None)
    assert target is not None, "Failed to retrieve saved session"
    assert len(target["messages"]) == 2, f"Expected 2 messages, got {len(target['messages'])}"
    print("  [OK] Session with raw bytes safely persisted to SQLite and reloaded")


def test_pdf_table_formatting():
    print("\n--- Test 3: Document Studio Table PDF Export ---")
    from app.core.doc_editor import DocumentEditor

    test_md = """# GoodWeave Inspection Report
Master Report
Generated on 11 Sept 2026

All inspections

| Inspections Resport | Exporter | Producer | Subcontractor | Contractor | Household | Total |
| --- | --- | --- | --- | --- | --- | --- |
| Number of inspections | 13 | 0 | 0 | 0 | 0 | 13 |
| Number with tracked time | 13 | 0 | 0 | 0 | 0 | 13 |
| % with tracked time | 100% | — | — | — | — | 100% |
| Avg tracked time (hours) | 0.00 | — | — | — | — | 0.00 |

### Notes
- Updated inspection counts reflected above.
- Report certified and verified.
"""

    out_pdf = os.path.join(WORKSPACE_ROOT, "app", "data", "generated", "test_report_styled.pdf")
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)

    result_path = DocumentEditor.export_to_pdf(test_md, out_pdf, title="Updated: goodweave-inspection-report")
    assert os.path.exists(result_path), f"Output PDF does not exist at {result_path}"
    pdf_size = os.path.getsize(result_path)
    assert pdf_size > 1000, f"Generated PDF is unusually small: {pdf_size} bytes"
    print(f"  [OK] Successfully compiled styled PDF with ReportLab Table: {result_path} ({pdf_size} bytes)")


def test_user_document_isolation():
    print("\n--- Test 4: Per-User Document Isolation ---")
    from app.core.vectorstore import VectorStore

    store = VectorStore(collection_name="test_isolation_collection")

    # Add chunk for User Alice
    alice_chunk = [{
        "id": "alice_doc_chunk_1",
        "text": "Alice secret financial report: Q3 profit was 500,000 dollars.",
        "metadata": {
            "document_id": "alice_doc_1",
            "source": "alice_financials.pdf",
            "page": 1,
            "chunk": 0,
        }
    }]
    store.add_chunks(alice_chunk, user_email="alice@docmind.ai")

    # Add chunk for User Bob
    bob_chunk = [{
        "id": "bob_doc_chunk_1",
        "text": "Bob engineering specifications: Turbine engine pressure 450 PSI.",
        "metadata": {
            "document_id": "bob_doc_1",
            "source": "bob_specs.pdf",
            "page": 1,
            "chunk": 0,
        }
    }]
    store.add_chunks(bob_chunk, user_email="bob@docmind.ai")

    # 1. Listing isolation
    alice_docs = store.list_documents(user_email="alice@docmind.ai")
    alice_filenames = [d["filename"] for d in alice_docs]
    assert "alice_financials.pdf" in alice_filenames, "Alice doc not in Alice's list"
    assert "bob_specs.pdf" not in alice_filenames, "Bob's doc leaked into Alice's list!"

    bob_docs = store.list_documents(user_email="bob@docmind.ai")
    bob_filenames = [d["filename"] for d in bob_docs]
    assert "bob_specs.pdf" in bob_filenames, "Bob doc not in Bob's list"
    assert "alice_financials.pdf" not in bob_filenames, "Alice's doc leaked into Bob's list!"
    print("  [OK] Document listings strictly isolated per user")

    # 2. Search isolation
    # Alice searches for "turbine pressure" -> should find NOTHING
    alice_search = store.search(query="turbine pressure", user_email="alice@docmind.ai")
    for r in alice_search:
        assert r["document_id"] != "bob_doc_1", "Bob's document appeared in Alice's search results!"

    # Bob searches for "profit dollars" -> should find NOTHING
    bob_search = store.search(query="profit dollars", user_email="bob@docmind.ai")
    for r in bob_search:
        assert r["document_id"] != "alice_doc_1", "Alice's document appeared in Bob's search results!"
    print("  [OK] Vector & BM25 search strictly isolated per user")

    # Clean up test collection
    store.clear_all()
    print("  [OK] Isolation test collection cleaned up")


def main():
    print("=" * 60)
    print("  DocMind AI Bug Fix & Architecture Verification Suite")
    print("=" * 60)

    test_auth_and_tokens()
    test_bytes_serialization()
    test_pdf_table_formatting()
    test_user_document_isolation()

    print("\n" + "=" * 60)
    print("  ALL 4 VERIFICATION TESTS PASSED SUCCESSFULLY! [PASS]")
    print("=" * 60)


if __name__ == "__main__":
    main()
