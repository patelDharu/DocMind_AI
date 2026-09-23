# frontend/streamlit_app.py

import base64
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Ensure project root is in sys.path so app.* modules are always importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import streamlit as st
import streamlit.components.v1 as components
import requests

from app.core.auth import (
    init_user_db,
    register_user,
    authenticate_user,
    get_user_chat_sessions,
    save_user_chat_session,
    delete_user_chat_session,
    clear_all_user_chat_sessions,
    get_or_create_demo_token,
    sanitize_chat_messages,
)

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
MAX_UPLOAD_SIZE_MB = 25
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


def get_current_user_email() -> str:
    """Returns the email address of the currently authenticated user."""
    if st.session_state.get("current_user"):
        return st.session_state.current_user.get("email", "").strip().lower()
    return ""


def get_api_headers() -> dict:
    """Returns HTTP Authorization headers for backend API requests."""
    token = st.session_state.get("auth_token")
    if not token and st.session_state.get("current_user"):
        token = st.session_state.current_user.get("token")
    if not token and st.session_state.get("authenticated"):
        token = get_or_create_demo_token()
        st.session_state.auth_token = token
    return {"Authorization": f"Bearer {token}"} if token else {}


chat_bar_path = str(ROOT_DIR / "frontend" / "components" / "chat_bar")
chat_bar_component = components.declare_component("chat_bar", path=chat_bar_path)

st.set_page_config(
    page_title="DocMind AI — Document Intelligence & Studio",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .source-card {
        background-color: #f8f9fa;
        border-left: 4px solid #4f46e5;
        padding: 10px 14px;
        margin-bottom: 8px;
        border-radius: 4px;
    }
    .badge-high { color: #15803d; font-weight: 600; }
    .badge-med { color: #b45309; font-weight: 600; }
    .badge-low { color: #b91c1c; font-weight: 600; }
    .chat-listen-btn { margin-top: 6px; }

    /* ChatGPT style session items */
    .chat-session-btn {
        text-align: left !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    /* Sidebar history rows: keep title and delete icon strictly side-by-side */
    div[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        align-items: center !important;
        gap: 4px !important;
    }
    div[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child {
        flex: 1 1 auto !important;
        min-width: 0 !important;
    }
    div[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {
        flex: 0 0 34px !important;
        min-width: 34px !important;
        max-width: 34px !important;
    }

    /* Sidebar delete chat button styling */
    div[data-testid="stSidebar"] div[data-testid="column"]:last-child button {
        padding: 0px !important;
        width: 32px !important;
        min-width: 32px !important;
        max-width: 32px !important;
        height: 36px !important;
        border-radius: 8px !important;
        border: 1px solid #fee2e2 !important;
        background-color: #fff1f2 !important;
        color: #ef4444 !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        line-height: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: all 0.15s ease !important;
    }
    div[data-testid="stSidebar"] div[data-testid="column"]:last-child button:hover {
        background-color: #fecaca !important;
        border-color: #ef4444 !important;
        color: #b91c1c !important;
        transform: scale(1.05) !important;
    }

    /* Remove Streamlit fixed white header blur/mask so text is never covered from above */
    header[data-testid="stHeader"] {
        background: transparent !important;
        background-color: transparent !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        box-shadow: none !important;
        border: none !important;
        height: 2.2rem !important;
        z-index: 50 !important;
    }

    /* Modern clean message card styling */
    div[data-testid="stChatMessage"] {
        background-color: #f8fafc !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 14px !important;
        padding: 1.1rem 1.3rem !important;
        margin-bottom: 0.9rem !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03) !important;
        color: #0f172a !important;
    }
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
        background-color: #eff6ff !important;
        border-color: #bfdbfe !important;
        color: #1e3a8a !important;
    }

    /* Fixed floating bottom search bar container (Tab 1 Chat only) */
    div[data-testid="stBottom"] {
        display: block !important;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 0.95) 30%, #ffffff 100%) !important;
        padding-top: 10px !important;
        padding-bottom: 8px !important;
        z-index: 9999 !important;
    }

    div[data-testid="stCustomComponentV1"]:has(iframe[title*="chat_bar"]) {
        min-height: 64px !important;
    }

    /* Auto-hide floating bottom chatbar when user is on Tab 2, 3, 4, or 5 */
    body:has(.stTabs [data-baseweb="tab-list"] button:not(:first-child)[aria-selected="true"]) div[data-testid="stBottom"],
    body:has(.stTabs [data-baseweb="tab-list"] [role="tab"]:not(:first-child)[aria-selected="true"]) div[data-testid="stBottom"],
    body:has(.stTabs [data-baseweb="tab-list"] button:not(:first-child)[aria-selected="true"]) div[data-testid="stCustomComponentV1"]:has(iframe[title*="chat_bar"]) {
        display: none !important;
        visibility: hidden !important;
        height: 0px !important;
        min-height: 0px !important;
        padding: 0px !important;
        margin: 0px !important;
        pointer-events: none !important;
    }
    body:has(.stTabs [data-baseweb="tab-list"] button:not(:first-child)[aria-selected="true"]) .block-container {
        padding-bottom: 2.5rem !important;
    }

    /* Modern clean file uploader dropzone */
    div[data-testid="stFileUploader"] {
        width: 100% !important;
    }
    div[data-testid="stFileUploader"] section {
        padding: 1.2rem 1.4rem !important;
        border-radius: 12px !important;
        border: 1.5px dashed #cbd5e1 !important;
        background-color: #f8fafc !important;
        min-height: 85px !important;
        transition: border-color 0.2s ease, background-color 0.2s ease !important;
    }
    div[data-testid="stFileUploader"] section:hover {
        border-color: #4f46e5 !important;
        background-color: #eff6ff !important;
    }

    /* Sticky Navigation Tabs acting as clean navbar without covering content */
    .stTabs [data-baseweb="tab-list"] {
        position: sticky !important;
        top: 0 !important;
        z-index: 100 !important;
        background: #ffffff !important;
        border-bottom: 1.5px solid #e2e8f0 !important;
        padding-top: 6px !important;
        padding-bottom: 6px !important;
        gap: 6px !important;
        display: flex !important;
        width: 100% !important;
        overflow-x: auto !important;
        white-space: nowrap !important;
        scrollbar-width: none !important;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
        display: none !important;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 7px 13px !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
        transition: all 0.15s ease !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #f1f5f9 !important;
        color: #2563eb !important;
    }

    /* Desktop & Laptop (> 1024px) */
    @media (min-width: 1025px) {
        .block-container {
            padding-top: 1.6rem !important;
            padding-bottom: 7.5rem !important;
            max-width: 96% !important;
            width: 96% !important;
            margin: 0 auto !important;
        }
        div[data-testid="stBottomBlockContainer"] {
            max-width: 96% !important;
            width: 96% !important;
            margin: 0 auto !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
    }

    /* Tablet (601px - 1024px) */
    @media (min-width: 601px) and (max-width: 1024px) {
        .block-container {
            padding-top: 1.2rem !important;
            padding-bottom: 6.5rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 98% !important;
            width: 98% !important;
        }
        div[data-testid="stBottomBlockContainer"] {
            max-width: 98% !important;
            width: 98% !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 6px 10px !important;
            font-size: 12px !important;
        }
        div[data-testid="stChatMessage"] {
            padding: 0.75rem 0.85rem !important;
        }
    }

    /* Universal Responsiveness & Mobile Enhancements */
    div[role="radiogroup"] {
        flex-wrap: wrap !important;
        gap: 8px !important;
    }
    div[data-testid="column"]:empty {
        display: none !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .stMarkdown table {
        display: block !important;
        width: 100% !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }
    .stMarkdown pre {
        max-width: 100% !important;
        overflow-x: auto !important;
        word-break: break-word !important;
        white-space: pre-wrap !important;
    }

    /* Mobile Phone (<= 600px) */
    @media (max-width: 600px) {
        .block-container {
            padding-top: 3.2rem !important;
            padding-bottom: 6.5rem !important;
            padding-left: 0.4rem !important;
            padding-right: 0.4rem !important;
            max-width: 100% !important;
            width: 100% !important;
        }
        div[data-testid="stBottom"] {
            padding-top: 4px !important;
            padding-bottom: 4px !important;
        }
        div[data-testid="stBottomBlockContainer"] {
            max-width: 100% !important;
            width: 100% !important;
            padding-left: 2px !important;
            padding-right: 2px !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px !important;
            padding-top: 2px !important;
            padding-bottom: 4px !important;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 5px 8px !important;
            font-size: 11.5px !important;
            border-radius: 5px !important;
        }
        div[data-testid="stChatMessage"] {
            padding: 0.5rem 0.6rem !important;
            margin-bottom: 0.5rem !important;
            font-size: 13.5px !important;
        }
        div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
        }
        div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            flex: 1 1 100% !important;
            min-width: 100% !important;
            margin-bottom: 0.5rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# CHAT SESSIONS & HISTORY PERSISTENCE (ChatGPT-STYLE)
# =========================================================

def clean_legacy_html(text: str) -> str:
    """Strip legacy HTML boxes, borders, and styled containers, converting them to clean markdown."""
    if not isinstance(text, str) or ("<div" not in text and "<span" not in text):
        return text
    import re
    t = text
    # Convert list items before stripping tags
    t = re.sub(r'<li[^>]*>', '• ', t)
    t = re.sub(r'</li>', '\n', t)
    # Convert strong tags to markdown bold
    t = re.sub(r'<strong[^>]*>', '**', t)
    t = re.sub(r'</strong>', '**', t)
    # Convert em tags to markdown italic
    t = re.sub(r'<em[^>]*>', '*', t)
    t = re.sub(r'</em>', '*', t)
    # Strip remaining HTML tags
    t = re.sub(r'</?(?:div|span|ul|ol|p|small|br|h\d)[^>]*>', '\n', t)
    # Collapse multiple consecutive newlines
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def load_chat_sessions():
    """Load all saved chat sessions strictly for the current user's email from database."""
    email = get_current_user_email()
    if not email:
        return []
    sessions = get_user_chat_sessions(email)
    for session in sessions:
        for m in session.get("messages", []):
            if "content" in m:
                m["content"] = clean_legacy_html(m["content"])
    return sessions


def save_chat_sessions(sessions):
    """Save chat sessions list to database for the current user's email."""
    email = get_current_user_email()
    if not email:
        return
    for s in sessions:
        save_user_chat_session(email, s)


def save_current_chat_session():
    """Persist current active session to database strictly under current user's email."""
    email = get_current_user_email()
    if not email or not st.session_state.get("messages"):
        return

    sess_id = st.session_state.get("current_session_id")
    if not sess_id:
        sess_id = str(uuid.uuid4())[:8]
        st.session_state.current_session_id = sess_id

    # Derive title from first user message
    first_q = next((m["content"] for m in st.session_state.messages if m["role"] == "user"), "New Conversation")
    clean_title = first_q.replace("🎤 ", "").strip()
    if len(clean_title) > 32:
        clean_title = clean_title[:32] + "..."

    now_str = datetime.now().strftime("%d %b, %H:%M")

    # Retain existing custom title if one was already set
    existing_sessions = get_user_chat_sessions(email)
    existing = next((s for s in existing_sessions if s.get("id") == sess_id), None)
    if existing and existing.get("title") and existing.get("title") != "New Conversation":
        clean_title = existing.get("title")

    safe_messages = sanitize_chat_messages(st.session_state.get("messages", []))
    session_data = {
        "id": sess_id,
        "title": clean_title,
        "updated_at": now_str,
        "selected_document_ids": st.session_state.get("selected_document_ids", []),
        "active_doc_id": st.session_state.get("active_doc_id"),
        "messages": safe_messages,
    }

    save_user_chat_session(email, session_data)


def start_new_chat():
    """Save current chat and initialize a clean new chat."""
    save_current_chat_session()
    st.session_state.current_session_id = str(uuid.uuid4())[:8]
    st.session_state.messages = []
    st.session_state.active_doc_id = None
    st.session_state.selected_document_ids = []
    st.session_state.audio_cache = {}
    st.session_state.last_chat_bar_msg_id = None


def clear_current_chat():
    """Completely clear current chat messages, active document targeting, and reset state."""
    email = get_current_user_email()
    sess_id = st.session_state.get("current_session_id")
    if email and sess_id:
        delete_user_chat_session(email, sess_id)
    st.session_state.messages = []
    st.session_state.active_doc_id = None
    st.session_state.selected_document_ids = []
    st.session_state.audio_cache = {}
    st.session_state.last_chat_bar_msg_id = None


def switch_to_chat_session(session_id: str):
    """Switch to an existing chat session from history."""
    save_current_chat_session()
    sessions = load_chat_sessions()
    target = next((s for s in sessions if s.get("id") == session_id), None)
    if target:
        st.session_state.current_session_id = target["id"]
        st.session_state.messages = target.get("messages", [])
        st.session_state.selected_document_ids = target.get("selected_document_ids", [])
        st.session_state.active_doc_id = target.get("active_doc_id")
        st.session_state.audio_cache = {}
        st.session_state.last_chat_bar_msg_id = None


def delete_chat_session(session_id: str):
    """Delete a chat session from history for the current user."""
    email = get_current_user_email()
    if email and session_id:
        delete_user_chat_session(email, session_id)
    if st.session_state.get("current_session_id") == session_id:
        start_new_chat()


# =========================================================
# SESSION STATE INITIALIZATION & AUTH DB
# =========================================================

init_user_db()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = str(uuid.uuid4())[:8]

if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_document_ids" not in st.session_state:
    st.session_state.selected_document_ids = []

if "active_doc_id" not in st.session_state:
    st.session_state.active_doc_id = None

if "audio_cache" not in st.session_state:
    st.session_state.audio_cache = {}

if "doc_action_alerts" not in st.session_state:
    st.session_state.doc_action_alerts = {}


# =========================================================
# API HELPER FUNCTIONS
# =========================================================

def fetch_documents():
    try:
        res = requests.get(f"{API_URL}/documents", headers=get_api_headers(), timeout=10)
        if res.ok:
            return res.json().get("documents", [])
    except Exception:
        pass
    return []


def delete_document(doc_id: str):
    try:
        res = requests.delete(f"{API_URL}/documents/{doc_id}", headers=get_api_headers(), timeout=15)
        return res.ok
    except Exception:
        return False


def synthesize_audio_api(text: str, lang: str = "en") -> bytes | None:
    try:
        payload = {"text": text[:1500], "language": lang}
        res = requests.post(f"{API_URL}/speak", json=payload, headers=get_api_headers(), timeout=30)
        if res.ok:
            data = res.json()
            fname = data.get("filename")
            # 1. Try reading directly from local output directory on server
            local_p = ROOT_DIR / "app" / "data" / "audio_out" / fname
            if local_p.exists():
                return local_p.read_bytes()
            # 2. Or fetch audio bytes via internal API call with auth headers
            aud_res = requests.get(f"{API_URL}/audio/{fname}", headers=get_api_headers(), timeout=20)
            if aud_res.ok:
                return aud_res.content
    except Exception as e:
        print(f"Audio synth error: {e}")
    return None


def format_action_alert_markdown(alert: dict) -> str:
    """Formats proactive action & deadline alert into clean, natural markdown without confusing boxes or excessive colors."""
    if not alert:
        return ""

    requires_action = alert.get("requires_action", False)
    doc_type = alert.get("document_type") or "Document"
    deadline = alert.get("deadline")
    summary = alert.get("action_summary", "")
    items = alert.get("action_items", [])
    consequences = alert.get("consequences")

    parts = []
    if requires_action:
        parts.append(f"### ⚠️ Action Required ({doc_type})")
        if summary:
            parts.append(f"**Action Summary:** {summary}")

        if deadline and str(deadline).lower() not in ["null", "none", ""]:
            parts.append(f"📅 **Due Date / Deadline:** {deadline}")

        if items and isinstance(items, list):
            item_bullets = "\n".join([f"• {it}" for it in items if it])
            parts.append(f"**What you need to do:**\n{item_bullets}")

        if consequences and str(consequences).lower() not in ["null", "none", ""]:
            parts.append(f"ℹ️ **Important Note:** {consequences}")
    else:
        parts.append(f"### 📄 {doc_type} (Informational)")
        if summary:
            parts.append(summary)

    return "\n\n".join(parts)


def ensure_uploaded_to_backend(uploaded_file, cache_prefix: str = "tab") -> str | None:
    """Uploads file to backend if not already uploaded, returning document_id with caching."""
    if not uploaded_file:
        return None

    file_bytes = uploaded_file.getvalue()

    # Pre-upload check: Enforce 25 MB limit
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        st.error(
            f"⚠️ File '{uploaded_file.name}' is {len(file_bytes) / (1024 * 1024):.1f} MB. "
            f"Maximum allowed file size is {MAX_UPLOAD_SIZE_MB} MB. Please upload a smaller file."
        )
        return None

    cache = st.session_state.setdefault("uploader_cache", {})
    file_sig = f"{uploaded_file.name}_{len(file_bytes)}"
    if cache_prefix in cache and cache[cache_prefix].get("sig") == file_sig:
        return cache[cache_prefix].get("doc_id")

    try:
        files = {"file": (uploaded_file.name, file_bytes)}
        res = requests.post(f"{API_URL}/upload", files=files, headers=get_api_headers(), timeout=120)
        if res.ok:
            data = res.json()
            doc_id = data["document_id"]
            if data.get("action_alert"):
                st.session_state.setdefault("doc_action_alerts", {})[doc_id] = data["action_alert"]
            cache[cache_prefix] = {"sig": file_sig, "doc_id": doc_id}
            return doc_id
        elif res.status_code == 413:
            st.error(f"⚠️ File '{uploaded_file.name}' exceeds the 25 MB limit. Please upload a file smaller than 25 MB.")
            return None
        elif res.status_code == 502:
            st.error(f"⚠️ 502 Bad Gateway: The cloud server was briefly busy or restarting. Please retry in a few moments.")
            return None
        else:
            err_msg = res.text
            try:
                err_msg = res.json().get("detail", res.text)
            except Exception:
                pass
            st.error(f"⚠️ Upload failed for {uploaded_file.name}: {err_msg}")
            return None
    except requests.exceptions.ConnectionError:
        st.error(f"⚠️ Connection Error: Unable to reach the backend server. If using cloud hosting, it may be waking up. Please retry in a moment.")
        return None
    except requests.exceptions.Timeout:
        st.error(f"⚠️ Upload timed out for {uploaded_file.name}. Please upload a smaller or simpler file.")
        return None
    except Exception as e:
        st.error(f"Error uploading {uploaded_file.name}: {e}")
        return None


# =========================================================
# AUTHENTICATION & LOGIN / SIGN UP PORTAL
# =========================================================

def render_auth_page():
    """Renders a responsive, modern, and high-contrast Sign In / Sign Up portal."""
    st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        .auth-brand-badge {
            width: 56px;
            height: 56px;
            border-radius: 14px;
            background: linear-gradient(135deg, #4f46e5, #7c3aed);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            margin: 0 auto 12px auto;
            box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
        }
        .auth-header-title {
            text-align: center;
            font-size: 26px;
            font-weight: 800;
            color: #0f172a;
            margin: 0;
            letter-spacing: -0.5px;
        }
        .auth-header-sub {
            text-align: center;
            font-size: 13.5px;
            color: #64748b;
            margin: 6px 0 18px 0;
        }
        /* Sign In button: Clean white background with border and dark text */
        div[data-testid="stForm"] button[kind="secondary"],
        div[data-testid="stForm"] button[data-testid="baseButton-secondary"] {
            background-color: #ffffff !important;
            color: #1e293b !important;
            border: 1.5px solid #cbd5e1 !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 15px !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
            transition: all 0.15s ease !important;
        }
        div[data-testid="stForm"] button[kind="secondary"]:hover,
        div[data-testid="stForm"] button[data-testid="baseButton-secondary"]:hover {
            background-color: #f8fafc !important;
            border-color: #94a3b8 !important;
            color: #0f172a !important;
        }

        /* Free Demo Sign In button: Bold Red background with white text */
        div[data-testid="stForm"] button[kind="primary"],
        div[data-testid="stForm"] button[data-testid="baseButton-primary"] {
            background-color: #ff4b4b !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 15px !important;
            box-shadow: 0 2px 6px rgba(255, 75, 75, 0.25) !important;
            transition: all 0.15s ease !important;
        }
        div[data-testid="stForm"] button[kind="primary"]:hover,
        div[data-testid="stForm"] button[data-testid="baseButton-primary"]:hover {
            background-color: #e63939 !important;
            box-shadow: 0 4px 12px rgba(255, 75, 75, 0.35) !important;
        }
        @media (max-width: 768px) {
            .auth-header-title {
                font-size: 22px;
            }
            .auth-header-sub {
                font-size: 12.5px;
                margin-bottom: 14px;
            }
            div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:first-child,
            div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:last-child {
                display: none !important;
            }
            div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-child(2) {
                flex: 1 1 100% !important;
                min-width: 100% !important;
                max-width: 100% !important;
            }
        }
    </style>
    """, unsafe_allow_html=True)

    _, col_center, _ = st.columns([1, 1.8, 1])
    with col_center:
        st.markdown("""
        <div class="auth-brand-badge">📚</div>
        <h1 class="auth-header-title">DocMind AI</h1>
        <p class="auth-header-sub">Trilingual Multi-Document Intelligence & Studio</p>
        """, unsafe_allow_html=True)

        tab_signin, tab_signup = st.tabs(["🔐 Sign In", "📝 Create Account"])

        with tab_signin:
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            with st.form("auth_signin_form", clear_on_submit=False):
                in_email = st.text_input("Email Address", placeholder="name@company.com", key="auth_signin_email")
                in_pwd = st.text_input("Password", type="password", placeholder="Enter your password", key="auth_signin_pwd")
                
                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                submitted_signin = st.form_submit_button("Sign In to DocMind", use_container_width=True, type="secondary")
                submitted_demo = st.form_submit_button("⚡ Free Demo Sign In", use_container_width=True, type="primary")

                if submitted_signin:
                    success, msg, user = authenticate_user(in_email, in_pwd)
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.current_user = user
                        st.session_state.auth_token = user.get("token")
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

                if submitted_demo:
                    success, msg, user = authenticate_user("demo@docmind.ai", "Demo@123")
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.current_user = user
                        st.session_state.auth_token = user.get("token") or get_or_create_demo_token()
                        st.rerun()
                    else:
                        st.error(msg)

        with tab_signup:
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            with st.form("auth_signup_form", clear_on_submit=False):
                up_name = st.text_input("Full Name", placeholder="e.g. Alex Morgan", key="auth_signup_name")
                up_email = st.text_input("Email Address", placeholder="name@company.com", key="auth_signup_email")
                up_pwd = st.text_input("Password (min 6 characters)", type="password", placeholder="Create a password", key="auth_signup_pwd")
                up_pwd_confirm = st.text_input("Confirm Password", type="password", placeholder="Re-enter your password", key="auth_signup_pwd_confirm")
                submitted_signup = st.form_submit_button("Create Account & Sign In", use_container_width=True, type="primary")

                if submitted_signup:
                    if not up_name.strip():
                        st.error("Please enter your full name.")
                    elif not up_email.strip():
                        st.error("Please enter a valid email address.")
                    elif up_pwd != up_pwd_confirm:
                        st.error("Passwords do not match. Please verify and try again.")
                    elif len(up_pwd) < 6:
                        st.error("Password must be at least 6 characters long.")
                    else:
                        success, msg, user = register_user(up_name, up_email, up_pwd)
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.current_user = user
                            st.session_state.auth_token = user.get("token")
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)


# =========================================================
# AUTHENTICATION GATEWAY
# =========================================================

if not st.session_state.get("authenticated", False):
    render_auth_page()
    st.stop()


# =========================================================
# SIDEBAR: USER PROFILE & DOCUMENT REPOSITORY
# =========================================================

curr_user = st.session_state.get("current_user") or {}
curr_email = curr_user.get("email", "").strip().lower()
u_name = curr_user.get("name", "DocMind User")
u_email = curr_user.get("email", "")
u_init = u_name[0].upper() if u_name else "U"

# Synchronize user chat state whenever user logs in or switches accounts
if st.session_state.get("active_email") != curr_email:
    st.session_state.active_email = curr_email
    user_sessions = load_chat_sessions()
    if user_sessions:
        latest = user_sessions[0]
        st.session_state.current_session_id = latest["id"]
        st.session_state.messages = latest.get("messages", [])
        st.session_state.selected_document_ids = latest.get("selected_document_ids", [])
        st.session_state.active_doc_id = latest.get("active_doc_id")
    else:
        st.session_state.current_session_id = str(uuid.uuid4())[:8]
        st.session_state.messages = []
        st.session_state.selected_document_ids = []
        st.session_state.active_doc_id = None

st.sidebar.markdown(f"""
<div style="display: flex; align-items: center; justify-content: space-between; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 10px 12px; margin-bottom: 12px;">
    <div style="display: flex; align-items: center; gap: 10px; overflow: hidden;">
        <div style="width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 15px; flex-shrink: 0; box-shadow: 0 2px 5px rgba(79,70,229,0.3);">
            {u_init}
        </div>
        <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            <div style="font-weight: 700; font-size: 13.5px; color: #0f172a; line-height: 1.25; overflow: hidden; text-overflow: ellipsis;">{u_name}</div>
            <div style="font-size: 11px; color: #64748b; line-height: 1.2; overflow: hidden; text-overflow: ellipsis;">{u_email}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

c_nav1, c_nav2 = st.sidebar.columns([1.4, 1])
with c_nav1:
    if st.button("➕ New Chat", key="top_new_chat_btn", use_container_width=True, type="primary"):
        start_new_chat()
        st.rerun()
with c_nav2:
    if st.button("🚪 Sign Out", key="sidebar_signout_btn", use_container_width=True, help="Sign out of your account"):
        save_current_chat_session()
        st.session_state.authenticated = False
        st.session_state.current_user = None
        st.session_state.active_email = None
        st.session_state.messages = []
        st.session_state.current_session_id = str(uuid.uuid4())[:8]
        st.rerun()

# ---------------------------------------------------------
# GPT-Style: Recent Chats / Conversation History
# ---------------------------------------------------------
st.sidebar.markdown("""
<div style="display: flex; align-items: center; justify-content: space-between; margin: 14px 0 8px 0;">
    <span style="font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.6px;">💬 Chat History</span>
</div>
""", unsafe_allow_html=True)

saved_sessions = load_chat_sessions()
if saved_sessions:
    for sess in saved_sessions[:25]:
        s_id = sess.get("id", "")
        is_active = (s_id == st.session_state.get("current_session_id"))
        s_title = sess.get("title", "New Conversation")
        if len(s_title) > 28:
            s_display_title = s_title[:28] + "..."
        else:
            s_display_title = s_title

        c_hist1, c_hist2 = st.sidebar.columns([5, 1])
        with c_hist1:
            icon = "🟢 " if is_active else "💬 "
            btn_type = "primary" if is_active else "secondary"
            if st.button(
                f"{icon}{s_display_title}",
                key=f"hist_btn_{s_id}",
                use_container_width=True,
                type=btn_type,
                help=f"{s_title}\nUpdated: {sess.get('updated_at', '')}",
            ):
                switch_to_chat_session(s_id)
                st.rerun()
        with c_hist2:
            if st.button("✕", key=f"del_btn_{s_id}", help=f"Delete '{s_title}'"):
                delete_chat_session(s_id)
                st.rerun()
else:
    st.sidebar.markdown("""
    <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 12px 10px; text-align: center; margin: 4px 0 12px 0;">
        <div style="font-size: 16px; margin-bottom: 2px;">💭</div>
        <div style="font-size: 12px; font-weight: 600; color: #475569;">No previous chats</div>
        <div style="font-size: 10.5px; color: #94a3b8; margin-top: 2px;">Your conversations will appear here.</div>
    </div>
    """, unsafe_allow_html=True)

st.sidebar.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown("---")

# 2. Document Search Scope Selection
documents = fetch_documents()

if documents:
    st.sidebar.subheader("🎯 Active Document Scope")
    scope_mode = st.sidebar.radio(
        "Search Mode",
        ["Single Document", "Multi-Document Scope"],
        horizontal=True,
    )

    doc_options = {d["document_id"]: f"📄 {d['filename']}" for d in documents}

    if scope_mode == "Single Document":
        choices = {"🌐 All Indexed Documents": None}
        for d in documents:
            choices[f"📄 {d['filename']}"] = d["document_id"]

        def_idx = 0
        if st.session_state.active_doc_id:
            for idx, (_, d_id) in enumerate(choices.items()):
                if d_id == st.session_state.active_doc_id:
                    def_idx = idx
                    break

        selected_label = st.sidebar.selectbox(
            "Select document to chat with:",
            list(choices.keys()),
            index=def_idx,
            key=f"doc_scope_selector_{st.session_state.get('active_doc_id')}",
        )
        selected_id = choices[selected_label]
        st.session_state.active_doc_id = selected_id
        st.session_state.selected_document_ids = [selected_id] if selected_id else []

        if selected_id:
            st.sidebar.info(f"Targeting: **{selected_label.replace('📄 ', '')}**")
        else:
            st.sidebar.warning("Searching across **ALL** documents.")

    else:
        selected_docs = st.sidebar.multiselect(
            "Select documents to query simultaneously:",
            options=list(doc_options.keys()),
            format_func=lambda x: doc_options.get(x, x),
            default=[d for d in st.session_state.selected_document_ids if d in doc_options],
        )
        st.session_state.selected_document_ids = selected_docs
        if selected_docs:
            st.sidebar.info(f"Targeting **{len(selected_docs)}** document(s).")
        else:
            st.sidebar.warning("Searching across **ALL** documents.")

else:
    st.sidebar.info("No documents indexed yet. Upload a document to get started.")

st.sidebar.markdown("---")
if st.sidebar.button("🧹 Clear Messages", use_container_width=True):
    clear_current_chat()
    st.rerun()


# =========================================================
# SYSTEM DIAGNOSTICS & HEALTH CHECK
# =========================================================

@st.cache_data(ttl=20)
def check_backend_alive():
    try:
        r = requests.get(f"{API_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

if not check_backend_alive():
    st.error(
        f"🚨 **Cannot connect to the FastAPI backend at `{API_URL}`**.\n\n"
        "File uploads and document queries require the backend server to be running.\n\n"
        "**How to fix on Render**:\n"
        "- Ensure your Web Service **Start Command** is `./start.sh` (or `bash start.sh`) so that both FastAPI and Streamlit are started together.\n"
        "- If you deployed FastAPI as a separate Web Service, set the `API_URL` environment variable to your FastAPI backend URL."
    )


# =========================================================
# MAIN CONTENT TABS
# =========================================================

tab_chat, tab_studio, tab_summarize, tab_compare, tab_extract = st.tabs([
    "💬 Chat & Q&A",
    "✍️ Document Studio",
    "📝 Summarizer",
    "⚖️ Comparison",
    "📊 Extract Data",
])


# =========================================================
# TAB 1: GPT-STYLE MASTER CHAT & Q&A
# =========================================================

with tab_chat:
    # Only show active document banner when conversation has messages and document(s) are actively targeted
    if st.session_state.messages and st.session_state.selected_document_ids:
        if len(st.session_state.selected_document_ids) == 1:
            cur_d_id = st.session_state.selected_document_ids[0]
            target_name = next(
                (d["filename"] for d in documents if d["document_id"] == cur_d_id),
                "Selected Document"
            )
            active_alert = st.session_state.get("doc_action_alerts", {}).get(cur_d_id)
            if active_alert:
                req_act = active_alert.get("requires_action", False)
                d_line = active_alert.get("deadline")
                if req_act:
                    badge = "⚠️ Action Required" + (f" (Due: {d_line})" if d_line and str(d_line).lower() not in ["null", "none", ""] else "")
                    st.caption(f"🎯 Actively querying: **{target_name}** &nbsp;·&nbsp; <span style='color:#dc2626; font-weight:600;'>{badge}</span>", unsafe_allow_html=True)
                else:
                    st.caption(f"🎯 Actively querying: **{target_name}** &nbsp;·&nbsp; <span style='color:#16a34a; font-weight:600;'>✅ Informational Document (No Action Needed)</span>", unsafe_allow_html=True)
            else:
                st.caption(f"🎯 Actively querying: **{target_name}**")
        elif len(st.session_state.selected_document_ids) > 1:
            st.caption(f"🎯 Actively querying **{len(st.session_state.selected_document_ids)}** selected documents.")

    # -------------------------------------------------------------
    # ChatGPT-Style Full-Height Natural Conversation Feed
    # -------------------------------------------------------------
    if not st.session_state.messages:
        st.markdown("""
        <div style="text-align: center; padding: 40px 16px 20px 16px; color: #64748b;">
            <div style="font-size: 38px; margin-bottom: 10px;">📄</div>
            <h3 style="color: #1e293b; margin-bottom: 8px; font-weight: 700; font-size: 22px;">DocMind AI Workspace</h3>
            <p style="font-size: 14.5px; max-width: 580px; margin: 0 auto 20px auto; color: #64748b; line-height: 1.5;">
                Upload contracts, reports, tax notices, or spreadsheets. Ask questions, compare documents, or get proactive deadline and action alerts.
            </p>
            <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                <span style="background: #f1f5f9; color: #334155; padding: 6px 14px; border-radius: 20px; font-size: 12.5px; font-weight: 500;">📎 Click <strong>(+)</strong> to Upload & Index</span>
                <span style="background: #f1f5f9; color: #334155; padding: 6px 14px; border-radius: 20px; font-size: 12.5px; font-weight: 500;">⚡ Proactive Action & Deadline Alerts</span>
                <span style="background: #f1f5f9; color: #334155; padding: 6px 14px; border-radius: 20px; font-size: 12.5px; font-weight: 500;">🎙️ Trilingual English / हिन्दी / ગુજરાતી</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.markdown(clean_legacy_html(msg["content"]), unsafe_allow_html=True)

                if msg["role"] == "assistant":
                    # Audio Playback (Kept purely in audio_cache without mutating msg with raw bytes)
                    if st.button("🔊 Listen", key=f"speak_btn_{idx}", help="Play answer audio"):
                        audio_data = st.session_state.audio_cache.get(idx)
                        if not audio_data:
                            audio_data = synthesize_audio_api(msg["content"], msg.get("detected_language", "en"))
                        if audio_data:
                            st.session_state.audio_cache[idx] = audio_data

                    if idx in st.session_state.audio_cache:
                        st.audio(st.session_state.audio_cache[idx], format="audio/mp3")

                    # References / Citations (Clean Markdown, no nested cards)
                    sources = msg.get("sources", [])
                    if sources:
                        with st.expander(f"📄 Referenced Sources ({len(sources)})", expanded=False):
                            for s in sources:
                                page_info = f" (Page {s['page']})" if s.get('page') else ""
                                snippet = f"\n> *\"{s['snippet']}\"*" if s.get('snippet') else ""
                                st.markdown(f"• **{s.get('source', 'Document')}**{page_info}{snippet}")

    # -------------------------------------------------------------
    # ChatGPT-Style Floating Bottom Docked Searchbar
    # -------------------------------------------------------------
    bottom_container = getattr(st, "bottom", getattr(st, "_bottom", None))
    if bottom_container:
        with bottom_container:
            chat_val = chat_bar_component(key="unified_chat_bar")
    else:
        chat_val = chat_bar_component(key="unified_chat_bar")

    if chat_val and chat_val.get("msg_id") != st.session_state.get("last_chat_bar_msg_id"):
        st.session_state.last_chat_bar_msg_id = chat_val.get("msg_id")

        # 1. File Upload with Optional Prompt (ChatGPT Searchbar Plus Button)
        if chat_val.get("type") == "file_and_prompt":
            fname = chat_val.get("filename", "document")
            raw_b64 = chat_val.get("file_base64", "")
            prompt = chat_val.get("content", "").strip()

            if raw_b64:
                file_bytes = base64.b64decode(raw_b64)
                if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
                    st.error(
                        f"⚠️ File '{fname}' is {len(file_bytes) / (1024 * 1024):.1f} MB. "
                        f"Maximum allowed file size is {MAX_UPLOAD_SIZE_MB} MB. Please upload a smaller file."
                    )
                else:
                    with st.spinner(f"Indexing {fname} & checking actions/deadlines with Gemini..."):
                        try:
                            files = {"file": (fname, file_bytes)}
                            res = requests.post(f"{API_URL}/upload", files=files, headers=get_api_headers(), timeout=120)
                            if res.ok:
                                data = res.json()
                                new_doc_id = data["document_id"]
                                action_alert = data.get("action_alert", {})
                                st.session_state.setdefault("doc_action_alerts", {})[new_doc_id] = action_alert
                                st.session_state.active_doc_id = new_doc_id
                                st.session_state.selected_document_ids = [new_doc_id]

                                alert_block = format_action_alert_markdown(action_alert)

                                if prompt:
                                    st.session_state.messages.append({
                                        "role": "user",
                                        "content": f"📄 **[{fname}]**\n\n{prompt}",
                                    })
                                    with st.spinner("Analyzing attached document with Master Model..."):
                                        try:
                                            history_payload = [
                                                {"role": m["role"], "content": m["content"]}
                                                for m in st.session_state.messages[:-1]
                                            ]
                                            payload = {
                                                "question": prompt,
                                                "document_ids": [new_doc_id],
                                                "history": history_payload,
                                                "top_k": 8,
                                            }
                                            ask_res = requests.post(f"{API_URL}/ask", json=payload, headers=get_api_headers(), timeout=120)
                                            if ask_res.ok:
                                                result = ask_res.json()
                                                answer_text = result.get("answer", "No answer returned.")
                                                full_reply = f"{alert_block}\n\n---\n\n{answer_text}" if alert_block else answer_text
                                                st.session_state.messages.append({
                                                    "role": "assistant",
                                                    "content": full_reply,
                                                    "confidence": result.get("confidence", "high"),
                                                    "sources": result.get("sources", []),
                                                    "rewritten_query": result.get("rewritten_query"),
                                                    "detected_language": result.get("detected_language", "en"),
                                                    "action_alert": action_alert,
                                                    "doc_id": new_doc_id,
                                                })
                                            else:
                                                st.session_state.messages.append({
                                                    "role": "assistant",
                                                    "content": f"{alert_block}\n\n⚠️ Could not generate answer ({ask_res.status_code}): {ask_res.text}",
                                                    "confidence": "low",
                                                    "sources": [],
                                                    "action_alert": action_alert,
                                                    "doc_id": new_doc_id,
                                                })
                                        except Exception as ask_err:
                                            st.session_state.messages.append({
                                                "role": "assistant",
                                                "content": f"{alert_block}\n\n⚠️ Connection error while answering: {ask_err}",
                                                "confidence": "low",
                                                "sources": [],
                                                "action_alert": action_alert,
                                                "doc_id": new_doc_id,
                                            })
                                else:
                                    st.session_state.messages.append({
                                        "role": "user",
                                        "content": f"📎 Attached document: **{fname}**",
                                    })
                                    welcome_parts = [f"📄 **{fname}** is ready."]
                                    if alert_block:
                                        welcome_parts.append(alert_block)
                                    welcome_parts.append("---\n*Ask any question about this document below, or choose an option from the tabs above.*")
                                    welcome_msg = "\n\n".join(welcome_parts)
                                    st.session_state.messages.append({
                                        "role": "assistant",
                                        "content": welcome_msg,
                                        "confidence": "high",
                                        "sources": [],
                                        "action_alert": action_alert,
                                        "doc_id": new_doc_id,
                                    })

                                save_current_chat_session()
                                st.rerun()
                            elif res.status_code == 413:
                                st.error(f"⚠️ File '{fname}' exceeds the 25 MB limit. Please upload a file smaller than 25 MB.")
                            elif res.status_code == 502:
                                st.error("⚠️ 502 Bad Gateway: The cloud server was briefly busy or restarting. Please retry in a moment.")
                            else:
                                err_msg = res.text
                                try:
                                    err_msg = res.json().get("detail", res.text)
                                except Exception:
                                    pass
                                st.error(f"⚠️ Upload failed: {err_msg}")
                        except requests.exceptions.ConnectionError:
                            st.error("⚠️ Connection Error: Unable to reach the backend server. If using cloud hosting, it may be waking up. Please retry in a moment.")
                        except requests.exceptions.Timeout:
                            st.error(f"⚠️ Upload timed out for {fname}. Please try again.")
                        except Exception as e:
                            st.error(f"Upload error: {e}")

        # 2. Text Query (Typed or Web Speech Recognition Transcribed)
        elif chat_val.get("type") == "text":
            prompt = chat_val.get("content", "").strip()
            if prompt:
                st.session_state.messages.append({"role": "user", "content": prompt})

                history_payload = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]

                with st.spinner("Analyzing context with Master Model..."):
                    try:
                        payload = {
                            "question": prompt,
                            "document_ids": st.session_state.selected_document_ids,
                            "history": history_payload,
                            "top_k": 8,
                        }
                        res = requests.post(f"{API_URL}/ask", json=payload, headers=get_api_headers(), timeout=120)

                        if res.ok:
                            result = res.json()
                            ans = result.get("answer", "No answer returned.")
                            conf = result.get("confidence", "medium")
                            sources = result.get("sources", [])
                            rewritten = result.get("rewritten_query")
                            det_lang = result.get("detected_language", "en")

                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": ans,
                                "confidence": conf,
                                "sources": sources,
                                "rewritten_query": rewritten,
                                "detected_language": det_lang,
                            })
                            save_current_chat_session()
                            st.rerun()
                        else:
                            st.error(f"Error ({res.status_code}): {res.text}")
                    except Exception as e:
                        st.error(f"Connection error: {e}")

        # 2. Audio Query Fallback (MediaRecorder recorded base64 audio)
        elif chat_val.get("type") == "audio_base64":
            raw_b64 = chat_val.get("audio", "")
            if raw_b64:
                audio_bytes = base64.b64decode(raw_b64)
                hist = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                with st.spinner("Transcribing and analyzing voice with Gemini 3.6 Flash..."):
                    try:
                        files = {"file": ("voice_q.webm", audio_bytes, "audio/webm")}
                        data = {
                            "document_ids": json.dumps(st.session_state.selected_document_ids),
                            "speak_reply": "true",
                            "history": json.dumps(hist),
                        }
                        res = requests.post(f"{API_URL}/ask-voice", files=files, data=data, headers=get_api_headers(), timeout=180)
                        if res.ok:
                            result = res.json()
                            user_text = result.get("transcribed_question", "Voice Query")
                            st.session_state.messages.append({
                                "role": "user",
                                "content": f"🎤 {user_text}",
                            })

                            audio_bytes = None
                            if result.get("audio_reply_path"):
                                fname = result["audio_reply_path"].replace("\\", "/").split("/")[-1]
                                local_p = Path("app/data/audio_out") / fname
                                if local_p.exists():
                                    audio_bytes = local_p.read_bytes()
                                else:
                                    try:
                                        r_aud = requests.get(f"{API_URL}/audio/{fname}", headers=get_api_headers(), timeout=15)
                                        if r_aud.ok:
                                            audio_bytes = r_aud.content
                                    except Exception:
                                        pass

                            msg_idx = len(st.session_state.messages)
                            if audio_bytes:
                                st.session_state.audio_cache[msg_idx] = audio_bytes

                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": result.get("answer", ""),
                                "confidence": result.get("confidence", "medium"),
                                "sources": result.get("sources", []),
                                "rewritten_query": result.get("rewritten_query"),
                                "detected_language": result.get("detected_language", "en"),
                            })
                            save_current_chat_session()
                            st.rerun()
                        else:
                            st.error(f"Voice error: {res.text}")
                    except Exception as e:
                        st.error(f"Connection error: {e}")


# =========================================================
# TAB 2: [NEW] DOCUMENT STUDIO (EDIT, AUGMENT & EXPORT)
# =========================================================

with tab_studio:
    st.markdown("### ✍️ Document Editor: Update or Add Content")
    st.caption("Easily add new clauses, payment terms, follow-ups, or edit existing sections in plain words, then download in Word or PDF.")

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # Step 1: Document Selection
    st.markdown("#### **Step 1: Choose your document**")
    st.caption("Upload the document you want to add content to or edit.")
    studio_file = st.file_uploader(
        "Upload document (PDF, Word, Excel, PowerPoint, or Text):",
        type=["pdf", "docx", "doc", "txt", "md", "csv", "xlsx", "pptx"],
        key="studio_direct_file_uploader",
        help="Drag and drop or browse the specific document you want to edit.",
    )
    use_active_doc = False
    if st.session_state.active_doc_id and not studio_file:
        active_name = next(
            (d["filename"] for d in documents if d["document_id"] == st.session_state.active_doc_id),
            "Active Document"
        )
        use_active_doc = st.checkbox(
            f"⚡ Or use current document from chat: **{active_name}**",
            value=True,
            key="studio_use_active_check",
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 2: Action / Mode Selection
    st.markdown("#### **Step 2: What would you like to do?**")
    st.caption("Choose whether you want to add new information at the end or edit existing text.")
    edit_mode_label = st.radio(
        "Select action:",
        [
            "➕ Add new content to the end of the document (Simple, Fast & Safe)",
            "✏️ Edit or rewrite text inside the document",
        ],
        key="studio_mode_radio",
    )
    selected_mode = "append" if "Add" in edit_mode_label else "revise"

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 3: Format Selection
    st.markdown("#### **Step 3: Choose download format**")
    st.caption("Select what type of file you want to download once the updates are completed.")
    export_format = st.radio(
        "Select format:",
        ["📄 Word Document (.docx)", "📑 PDF Document (.pdf)"],
        horizontal=True,
        key="studio_export_fmt",
    )
    fmt_ext = "docx" if "docx" in export_format.lower() else "pdf"

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 4: Instructions
    st.markdown("#### **Step 4: Tell the AI what changes to make**")
    st.caption("Describe what you want to add or change in plain everyday words.")
    prompt_instruction = st.text_area(
        "Your instructions:",
        placeholder="For example:\n• Add Payment Terms at the end: 50% advance and 50% upon delivery with 18% GST.\n• Add a new section on Patient Care Follow-up Instructions.\n• Add a Confidentiality and Non-Disclosure clause valid for 2 years.",
        height=120,
        key="studio_prompt_instruction",
    )

    st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
    auto_index_check = st.checkbox(
        "✅ Save this updated document to my library (so I can chat with it right away)",
        value=True,
        key="studio_auto_index_check",
    )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("✨ Update & Download Document", type="primary", use_container_width=True, key="studio_generate_btn"):
        target_doc_id = None
        target_filename = ""
        if studio_file:
            target_filename = studio_file.name
            with st.spinner(f"Preparing {target_filename}..."):
                target_doc_id = ensure_uploaded_to_backend(studio_file, cache_prefix="studio")
        elif use_active_doc and st.session_state.active_doc_id:
            target_doc_id = st.session_state.active_doc_id
            target_filename = active_name

        if not target_doc_id:
            st.warning("⚠️ Please upload a document above to begin modifying.")
        elif not prompt_instruction.strip():
            st.warning("⚠️ Please enter an update instruction.")
        else:
            with st.spinner(f"Drafting updates for {target_filename} with Gemini and compiling document..."):
                try:
                    payload = {
                        "document_id": target_doc_id,
                        "instruction": prompt_instruction,
                        "export_format": fmt_ext,
                        "auto_index": auto_index_check,
                        "edit_mode": selected_mode,
                    }
                    res = requests.post(f"{API_URL}/document/edit", json=payload, headers=get_api_headers(), timeout=180)
                    if res.ok:
                        data = res.json()
                        new_file_name = data["filename"]
                        download_url = f"{API_URL}{data['download_url']}"

                        st.success(f"🎉 Successfully created **{new_file_name}**!")

                        file_bytes = requests.get(download_url, headers=get_api_headers()).content
                        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if fmt_ext == "docx" else "application/pdf"

                        st.download_button(
                            label=f"📥 Download {new_file_name}",
                            data=file_bytes,
                            file_name=new_file_name,
                            mime=mime_type,
                            type="primary",
                            key="studio_download_btn",
                        )

                        if auto_index_check:
                            st.info(f"✅ Indexed {data.get('indexed_chunks', 0)} chunks into vector store. You can now chat with it in Tab 1!")

                        with st.expander("📄 Preview Generated Document Content", expanded=True):
                            st.markdown(data.get("updated_content", ""))
                    else:
                        try:
                            err_detail = res.json().get("detail", res.text)
                        except Exception:
                            err_detail = res.text
                        st.error(f"Studio error: {err_detail}")
                except Exception as e:
                    st.error(f"Connection error: {e}")


# =========================================================
# TAB 3: DOCUMENT SUMMARIZATION (Token-Budgeted)
# =========================================================

with tab_summarize:
    st.markdown("### 📝 Document Summarizer")
    st.caption("Get a clear, easy-to-read summary of any document in seconds.")

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # Step 1: Document Selection
    st.markdown("#### **Step 1: Choose your document**")
    st.caption("Upload the document you would like to summarize.")
    sum_file = st.file_uploader(
        "Upload document (PDF, Word, Excel, PowerPoint, or Text):",
        type=["pdf", "docx", "doc", "txt", "md", "csv", "tsv", "xlsx", "xls", "pptx", "html", "json"],
        key="sum_direct_file_uploader",
        help="Drag and drop or browse the specific document you want to summarize.",
    )
    use_active_doc_sum = False
    if st.session_state.active_doc_id and not sum_file:
        active_name = next(
            (d["filename"] for d in documents if d["document_id"] == st.session_state.active_doc_id),
            "Active Document"
        )
        use_active_doc_sum = st.checkbox(
            f"⚡ Or summarize current document from chat: **{active_name}**",
            value=True,
            key="sum_use_active_check",
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 2: Summary Format Selection
    st.markdown("#### **Step 2: What kind of summary do you need?**")
    st.caption("Select how you would like the summary presented.")
    sum_type_options = {
        "executive": "⚡ Quick Overview — Key takeaways in 1-2 minutes",
        "bullet_points": "📋 Bullet Points — Simple checklist of main highlights",
        "detailed": "📖 Full Detailed Summary — In-depth breakdown of every topic"
    }
    sum_type = st.radio(
        "Select summary style:",
        ["executive", "bullet_points", "detailed"],
        format_func=lambda k: sum_type_options[k],
        key="sum_format_radio",
    )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 3: Language Selection
    st.markdown("#### **Step 3: Choose summary language**")
    st.caption("Select your preferred language for reading the summary.")
    sum_lang_options = {
        "en": "🇬🇧 English",
        "hi": "🇮🇳 हिन्दी (Hindi)",
        "gu": "🇮🇳 ગુજરાતી (Gujarati)"
    }
    sum_lang = st.radio(
        "Select language:",
        ["en", "hi", "gu"],
        format_func=lambda k: sum_lang_options[k],
        horizontal=True,
        key="sum_lang_radio",
    )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("✨ Create Summary", type="primary", use_container_width=True, key="btn_gen_summary"):
        target_doc_id = None
        target_filename = ""
        if sum_file:
            target_filename = sum_file.name
            with st.spinner(f"Preparing {target_filename}..."):
                target_doc_id = ensure_uploaded_to_backend(sum_file, cache_prefix="summarize")
        elif use_active_doc_sum and st.session_state.active_doc_id:
            target_doc_id = st.session_state.active_doc_id
            target_filename = active_name

        if not target_doc_id:
            st.warning("⚠️ Please upload a document above to summarize.")
        else:
            with st.spinner(f"Reading {target_filename} and generating summary with Gemini..."):
                try:
                    payload = {
                        "document_id": target_doc_id,
                        "summary_type": sum_type,
                        "language": sum_lang,
                    }
                    res = requests.post(f"{API_URL}/summarize", json=payload, headers=get_api_headers(), timeout=120)
                    if res.ok:
                        data = res.json()
                        st.success(f"Summary for: **{data['filename']}**")
                        st.markdown(data.get("summary", ""))
                    else:
                        st.error(f"Summarization error: {res.text}")
                except Exception as e:
                    st.error(f"Failed to connect: {e}")


# =========================================================
# TAB 4: DOCUMENT COMPARISON (Token-Budgeted)
# =========================================================

with tab_compare:
    st.markdown("### ⚖️ Document Comparison")
    st.caption("Compare two documents side-by-side to find differences in prices, clauses, dates, and requirements.")

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # Step 1: First Document
    st.markdown("#### **Step 1: Choose the first document (Original / Version 1)**")
    st.caption("Upload the first document or baseline file.")
    file_a = st.file_uploader(
        "Upload First Document (PDF, Word, Excel, PPTX, TXT):",
        type=["pdf", "docx", "doc", "txt", "md", "csv", "tsv", "xlsx", "xls", "pptx", "html", "json"],
        key="comp_direct_file_a",
    )
    use_active_doc_a = False
    if st.session_state.active_doc_id and not file_a:
        active_name = next(
            (d["filename"] for d in documents if d["document_id"] == st.session_state.active_doc_id),
            "Active Document"
        )
        use_active_doc_a = st.checkbox(
            f"⚡ Use active chat document as First Document: **{active_name}**",
            value=False,
            key="comp_use_active_a_check",
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 2: Second Document
    st.markdown("#### **Step 2: Choose the second document (New / Version 2)**")
    st.caption("Upload the revised or second document you want to compare against.")
    file_b = st.file_uploader(
        "Upload Second Document (PDF, Word, Excel, PPTX, TXT):",
        type=["pdf", "docx", "doc", "txt", "md", "csv", "tsv", "xlsx", "xls", "pptx", "html", "json"],
        key="comp_direct_file_b",
    )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 3: Focus Areas
    st.markdown("#### **Step 3: What should the AI focus on? (Optional)**")
    st.caption("Mention specific areas of interest (e.g., pricing, deadlines, scope, penalty clauses).")
    focus = st.text_input(
        "Focus area:",
        value="Differences in budget, payment terms, deadlines, and deliverables",
        key="comp_focus_input",
    )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 4: Language Selection
    st.markdown("#### **Step 4: Choose comparison language**")
    st.caption("Select your preferred language for the comparison report.")
    comp_lang_options = {
        "en": "🇬🇧 English",
        "hi": "🇮🇳 हिन्दी (Hindi)",
        "gu": "🇮🇳 ગુજરાતી (Gujarati)"
    }
    comp_lang = st.radio(
        "Select language:",
        ["en", "hi", "gu"],
        format_func=lambda k: comp_lang_options[k],
        horizontal=True,
        key="comp_lang_radio",
    )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("⚖️ Compare Both Documents", type="primary", use_container_width=True, key="btn_compare_docs"):
        doc_a_id = None
        doc_b_id = None

        if file_a:
            with st.spinner(f"Preparing {file_a.name}..."):
                doc_a_id = ensure_uploaded_to_backend(file_a, cache_prefix="comp_a")
        elif use_active_doc_a and st.session_state.active_doc_id:
            doc_a_id = st.session_state.active_doc_id

        if file_b:
            with st.spinner(f"Preparing {file_b.name}..."):
                doc_b_id = ensure_uploaded_to_backend(file_b, cache_prefix="comp_b")

        if not doc_a_id or not doc_b_id:
            st.warning("⚠️ Please provide both Document A and Document B above to run the comparison.")
        elif doc_a_id == doc_b_id:
            st.warning("⚠️ Document A and Document B must be different files.")
        else:
            with st.spinner("Analyzing differences with Gemini..."):
                try:
                    payload = {
                        "document_ids": [doc_a_id, doc_b_id],
                        "focus_aspects": focus,
                        "language": comp_lang,
                    }
                    res = requests.post(f"{API_URL}/compare", json=payload, headers=get_api_headers(), timeout=180)
                    if res.ok:
                        data = res.json()
                        st.markdown(data.get("comparison", ""))
                    else:
                        st.error(f"Comparison error: {res.text}")
                except Exception as e:
                    st.error(f"Failed to connect: {e}")


# =========================================================
# TAB 5: STRUCTURED INFORMATION EXTRACTION (Token-Budgeted)
# =========================================================

with tab_extract:
    st.markdown("### 📊 Extract Key Information")
    st.caption("Quickly extract financial figures, due dates, milestones, and names from any document into clean tables.")

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # Step 1: Document Selection
    st.markdown("#### **Step 1: Choose your document**")
    st.caption("Upload the document you want to extract information from.")
    ext_file = st.file_uploader(
        "Upload document (PDF, Word, Excel, PowerPoint, or Text):",
        type=["pdf", "docx", "doc", "txt", "md", "csv", "tsv", "xlsx", "xls", "pptx", "html", "json"],
        key="extract_direct_file_uploader",
        help="Drag and drop or browse the specific document you want to extract data from.",
    )
    use_active_doc_ext = False
    if st.session_state.active_doc_id and not ext_file:
        active_name = next(
            (d["filename"] for d in documents if d["document_id"] == st.session_state.active_doc_id),
            "Active Document"
        )
        use_active_doc_ext = st.checkbox(
            f"⚡ Or extract from current document in chat: **{active_name}**",
            value=True,
            key="extract_use_active_check",
        )

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    st.markdown("---")

    # Step 2: Information Type Selection
    st.markdown("#### **Step 2: What information would you like to find?**")
    st.caption("Select what data the AI should focus on finding.")
    ext_type_options = {
        "full_schema": "📋 Complete Summary & Key Details — Everything important (Totals, dates, names)",
        "financials": "💰 Financial Numbers & Amounts — Invoices, prices, taxes, and totals",
        "dates_deadlines": "📅 Dates, Deadlines & Milestones — Due dates, renewal schedules, and terms",
        "key_entities": "🏢 Names, People & Organizations — Parties, companies, and roles",
    }
    ext_type = st.radio(
        "Select information to extract:",
        ["full_schema", "financials", "dates_deadlines", "key_entities"],
        format_func=lambda k: ext_type_options[k],
        key="extract_schema_radio",
    )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    if st.button("🔍 Find & Extract Information", type="primary", use_container_width=True, key="btn_extract_data"):
        target_doc_id = None
        target_filename = ""
        if ext_file:
            target_filename = ext_file.name
            with st.spinner(f"Preparing {target_filename}..."):
                target_doc_id = ensure_uploaded_to_backend(ext_file, cache_prefix="extract")
        elif use_active_doc_ext and st.session_state.active_doc_id:
            target_doc_id = st.session_state.active_doc_id
            target_filename = active_name

        if not target_doc_id:
            st.warning("⚠️ Please upload a document above for extraction.")
        else:
            with st.spinner(f"Extracting entities and attributes from {target_filename} with Gemini..."):
                try:
                    payload = {
                        "document_id": target_doc_id,
                        "extraction_type": ext_type,
                    }
                    res = requests.post(f"{API_URL}/extract", json=payload, headers=get_api_headers(), timeout=120)
                except Exception as conn_err:
                    st.error(f"Connection error: {conn_err}")
                    res = None

                if res is not None:
                    if res.ok:
                        data = res.json()

                        if data.get("summary_points"):
                            st.subheader("📌 Key Highlights")
                            for pt in data["summary_points"]:
                                st.write(f"- {pt}")

                        if data.get("extracted_items"):
                            st.subheader("📋 Extracted Attributes")
                            try:
                                st.dataframe(data["extracted_items"], use_container_width=True)
                            except Exception:
                                st.write(data["extracted_items"])

                        if data.get("tables_detected"):
                            st.subheader("📊 Detected Tables")
                            for tbl in data["tables_detected"]:
                                st.markdown(f"**{tbl.get('table_name', 'Table')}**")
                                headers = tbl.get("headers", [])
                                rows = tbl.get("rows", [])
                                if headers or rows:
                                    try:
                                        import pandas as pd
                                        clean_headers = [str(h).strip() if h is not None else "" for h in (headers or [])]
                                        clean_rows = []
                                        for r in (rows or []):
                                            if isinstance(r, list):
                                                clean_rows.append([str(c) if c is not None else "" for c in r])
                                            elif isinstance(r, dict):
                                                clean_rows.append([str(v) if v is not None else "" for v in r.values()])
                                            else:
                                                clean_rows.append([str(r)])

                                        max_cols = max(len(clean_headers), max((len(r) for r in clean_rows), default=0))
                                        if max_cols > 0:
                                            while len(clean_headers) < max_cols:
                                                clean_headers.append(f"Col {len(clean_headers) + 1}")
                                            clean_headers = clean_headers[:max_cols]

                                            seen = {}
                                            unique_headers = []
                                            for h in clean_headers:
                                                base = h if h else "Column"
                                                if base in seen:
                                                    seen[base] += 1
                                                    unique_headers.append(f"{base}_{seen[base]}")
                                                else:
                                                    seen[base] = 1
                                                    unique_headers.append(base)

                                            normalized_rows = []
                                            for r in clean_rows:
                                                if len(r) < max_cols:
                                                    r = r + [""] * (max_cols - len(r))
                                                normalized_rows.append(r[:max_cols])

                                            df = pd.DataFrame(normalized_rows, columns=unique_headers)
                                            st.dataframe(df, use_container_width=True)
                                    except Exception as tbl_err:
                                        st.caption(f"Could not render table as spreadsheet: {tbl_err}")
                                        if rows:
                                            st.write(rows)

                        with st.expander("📄 View Raw JSON Output"):
                            st.json(data)
                    else:
                        try:
                            err_msg = res.json().get("detail", res.text)
                        except Exception:
                            err_msg = res.text
                        st.error(f"Extraction error ({res.status_code}): {err_msg}")