# frontend/streamlit_app.py

import base64
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import requests

API_URL = "http://127.0.0.1:8000"
CHAT_SESSIONS_FILE = Path("app/data/chat_sessions.json")
chat_bar_component = components.declare_component("chat_bar", path="frontend/components/chat_bar")

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

    /* Fixed floating bottom search bar container */
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

    /* Sticky Navigation Tabs acting as clean navbar without covering content */
    .stTabs [data-baseweb="tab-list"] {
        position: sticky !important;
        top: 0 !important;
        z-index: 100 !important;
        background: #ffffff !important;
        border-bottom: 1.5px solid #e2e8f0 !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
        gap: 6px;
        overflow-x: auto;
        white-space: nowrap;
        flex-wrap: nowrap;
        -webkit-overflow-scrolling: touch;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 7px 14px;
        font-size: 13.5px;
        font-weight: 500;
        border-radius: 6px;
        white-space: nowrap;
        flex-shrink: 0;
    }

    /* Desktop & Laptop (> 1024px) */
    @media (min-width: 1025px) {
        .block-container {
            padding-top: 4.5rem !important;
            padding-bottom: 7.5rem !important;
            max-width: 94% !important;
            width: 94% !important;
            margin: 0 auto !important;
        }
        div[data-testid="stBottomBlockContainer"] {
            max-width: 94% !important;
            width: 94% !important;
            margin: 0 auto !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
    }

    /* Tablet (601px - 1024px) */
    @media (min-width: 601px) and (max-width: 1024px) {
        .block-container {
            padding-top: 3.8rem !important;
            padding-bottom: 7rem !important;
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
            padding: 6px 11px !important;
            font-size: 12.5px !important;
        }
        div[data-testid="stChatMessage"] {
            padding: 0.75rem 0.85rem !important;
        }
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

def load_chat_sessions():
    """Load all saved chat sessions from disk, sorted newest first."""
    if not CHAT_SESSIONS_FILE.exists():
        return []
    try:
        with open(CHAT_SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def save_chat_sessions(sessions):
    """Save chat sessions list to disk."""
    try:
        CHAT_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHAT_SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving chat sessions: {e}")


def save_current_chat_session():
    """Persist current active session to disk if it has messages."""
    if not st.session_state.get("messages"):
        return

    sessions = load_chat_sessions()
    sess_id = st.session_state.get("current_session_id")
    if not sess_id:
        sess_id = str(uuid.uuid4())[:8]
        st.session_state.current_session_id = sess_id

    # Derive title from first user message
    first_q = next((m["content"] for m in st.session_state.messages if m["role"] == "user"), "New Conversation")
    clean_title = first_q.replace("🎤 ", "").strip()
    if len(clean_title) > 30:
        clean_title = clean_title[:30] + "..."

    now_str = datetime.now().strftime("%d %b, %H:%M")

    existing_idx = next((i for i, s in enumerate(sessions) if s.get("id") == sess_id), None)
    session_data = {
        "id": sess_id,
        "title": clean_title,
        "updated_at": now_str,
        "selected_document_ids": st.session_state.get("selected_document_ids", []),
        "active_doc_id": st.session_state.get("active_doc_id"),
        "messages": st.session_state.get("messages", []),
    }

    if existing_idx is not None:
        orig_title = sessions[existing_idx].get("title")
        if orig_title and orig_title != "New Conversation":
            session_data["title"] = orig_title
        sessions[existing_idx] = session_data
        # Keep most recently updated session at top
        sessions.insert(0, sessions.pop(existing_idx))
    else:
        sessions.insert(0, session_data)

    sessions = sessions[:30]
    save_chat_sessions(sessions)


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
    st.session_state.messages = []
    st.session_state.active_doc_id = None
    st.session_state.selected_document_ids = []
    st.session_state.audio_cache = {}
    st.session_state.last_chat_bar_msg_id = None
    sess_id = st.session_state.get("current_session_id")
    if sess_id:
        sessions = load_chat_sessions()
        for s in sessions:
            if s.get("id") == sess_id:
                s["messages"] = []
                s["active_doc_id"] = None
                s["selected_document_ids"] = []
                s["title"] = "New Conversation"
                s["updated_at"] = datetime.now().strftime("%d %b, %H:%M")
                break
        save_chat_sessions(sessions)


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
    """Delete a chat session from history."""
    sessions = load_chat_sessions()
    sessions = [s for s in sessions if s.get("id") != session_id]
    save_chat_sessions(sessions)
    if st.session_state.get("current_session_id") == session_id:
        start_new_chat()


# =========================================================
# SESSION STATE INITIALIZATION
# =========================================================

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
        res = requests.get(f"{API_URL}/documents", timeout=10)
        if res.ok:
            return res.json().get("documents", [])
    except Exception:
        pass
    return []


def delete_document(doc_id: str):
    try:
        res = requests.delete(f"{API_URL}/documents/{doc_id}", timeout=15)
        return res.ok
    except Exception:
        return False


def synthesize_audio_api(text: str, lang: str = "en") -> bytes | None:
    try:
        payload = {"text": text[:1500], "language": lang}
        res = requests.post(f"{API_URL}/speak", json=payload, timeout=30)
        if res.ok:
            data = res.json()
            fname = data.get("filename")
            # 1. Try reading directly from local output directory on server
            local_p = Path("app/data/audio_out") / fname
            if local_p.exists():
                return local_p.read_bytes()
            # 2. Or fetch audio bytes via container internal API call
            aud_res = requests.get(f"{API_URL}/audio/{fname}", timeout=20)
            if aud_res.ok:
                return aud_res.content
    except Exception as e:
        print(f"Audio synth error: {e}")
    return None


def format_action_alert_markdown(alert: dict) -> str:
    """Formats proactive action & deadline alert into a modern, high-contrast, structured card."""
    if not alert:
        return ""

    requires_action = alert.get("requires_action", False)
    urgency = (alert.get("urgency") or "none").lower()
    doc_type = alert.get("document_type") or "Document"
    deadline = alert.get("deadline")
    summary = alert.get("action_summary", "")
    items = alert.get("action_items", [])
    consequences = alert.get("consequences")

    if requires_action:
        urgency_color = "#dc2626" if urgency == "high" else ("#d97706" if urgency == "medium" else "#2563eb")
        urgency_bg = "#fef2f2" if urgency == "high" else ("#fffbeb" if urgency == "medium" else "#eff6ff")
        urgency_border = "#fca5a5" if urgency == "high" else ("#fde68a" if urgency == "medium" else "#bfdbfe")
        urgency_text = "🔴 HIGH URGENCY — ACTION REQUIRED" if urgency == "high" else ("🟡 MEDIUM URGENCY — ACTION REQUIRED" if urgency == "medium" else "🔵 LOW URGENCY — ACTION RECOMMENDED")

        items_html = ""
        if items and isinstance(items, list):
            items_li = "".join([f"<li style='margin-bottom: 5px;'>{it}</li>" for it in items if it])
            items_html = f"""
            <div style="margin-top: 10px; font-weight: 600; color: #1e293b; font-size: 14px;">📋 What You Need To Do:</div>
            <ul style="margin: 4px 0 10px 20px; padding: 0; color: #334155; font-size: 13.5px; line-height: 1.5;">
                {items_li}
            </ul>
            """

        deadline_html = ""
        if deadline and str(deadline).lower() not in ["null", "none", ""]:
            deadline_html = f"""
            <div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 8px 14px; border-radius: 6px; margin: 10px 0; color: #991b1b; font-weight: 600; font-size: 14px;">
                📅 <strong>Deadline / Due Date</strong>: {deadline}
            </div>
            """

        consequences_html = ""
        if consequences and str(consequences).lower() not in ["null", "none", ""]:
            consequences_html = f"""
            <div style="background: #fffbeb; border-left: 4px solid #f59e0b; padding: 8px 14px; border-radius: 6px; margin: 10px 0; color: #92400e; font-size: 13.5px; line-height: 1.45;">
                ⚠️ <strong>Consequences If Missed</strong>: {consequences}
            </div>
            """

        card_html = f"""
<div style="background: #ffffff; border: 1.5px solid {urgency_border}; border-left: 6px solid {urgency_color}; border-radius: 12px; padding: 16px 20px; margin: 8px 0 14px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">
        <span style="background: {urgency_bg}; color: {urgency_color}; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 12.5px; border: 1px solid {urgency_border};">
            {urgency_text}
        </span>
        <span style="color: #64748b; font-size: 13px; font-weight: 500;">
            📋 Document Classification: <strong style="color: #334155;">{doc_type}</strong>
        </span>
    </div>
    <div style="font-size: 16px; font-weight: 700; color: #0f172a; margin-bottom: 6px;">
        ⚠️ Proactive Alert: Action Required
    </div>
    <div style="font-size: 14px; color: #334155; line-height: 1.6;">
        <strong>🎯 Action Summary</strong>: {summary}
    </div>
    {deadline_html}
    {items_html}
    {consequences_html}
</div>
"""
        return card_html.strip()
    else:
        card_html = f"""
<div style="background: #ffffff; border: 1.5px solid #bbf7d0; border-left: 6px solid #16a34a; border-radius: 12px; padding: 16px 20px; margin: 8px 0 14px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">
        <span style="background: #f0fdf4; color: #15803d; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 12.5px; border: 1px solid #bbf7d0;">
            ✅ INFORMATIONAL DOCUMENT (NO ACTION NEEDED)
        </span>
        <span style="color: #64748b; font-size: 13px; font-weight: 500;">
            📋 Document Classification: <strong style="color: #334155;">{doc_type}</strong>
        </span>
    </div>
    <div style="font-size: 16px; font-weight: 700; color: #0f172a; margin-bottom: 6px;">
        ℹ️ Proactive Alert: Informational Status
    </div>
    <div style="font-size: 14px; color: #334155; line-height: 1.6;">
        {summary}
    </div>
    <div style="font-size: 12.5px; color: #64748b; margin-top: 6px; font-style: italic;">
        *This document has been reviewed. No pending obligations, payments, or upcoming deadlines were detected.*
    </div>
</div>
"""
        return card_html.strip()


def ensure_uploaded_to_backend(uploaded_file, cache_prefix: str = "tab") -> str | None:
    """Uploads file to backend if not already uploaded, returning document_id with caching."""
    if not uploaded_file:
        return None
    cache = st.session_state.setdefault("uploader_cache", {})
    file_bytes = uploaded_file.getvalue()
    file_sig = f"{uploaded_file.name}_{len(file_bytes)}"
    if cache_prefix in cache and cache[cache_prefix].get("sig") == file_sig:
        return cache[cache_prefix].get("doc_id")

    try:
        files = {"file": (uploaded_file.name, file_bytes)}
        res = requests.post(f"{API_URL}/upload", files=files, timeout=300)
        if res.ok:
            data = res.json()
            doc_id = data["document_id"]
            if data.get("action_alert"):
                st.session_state.setdefault("doc_action_alerts", {})[doc_id] = data["action_alert"]
            cache[cache_prefix] = {"sig": file_sig, "doc_id": doc_id}
            return doc_id
        else:
            st.error(f"Upload failed for {uploaded_file.name}: {res.text}")
            return None
    except Exception as e:
        st.error(f"Error uploading {uploaded_file.name}: {e}")
        return None


# =========================================================
# SIDEBAR: DOCUMENT REPOSITORY & SELECTION
# =========================================================

st.sidebar.title("📚 DocMind AI")
st.sidebar.caption("Trilingual RAG & Document Studio")

# ---------------------------------------------------------
# ChatGPT-Style: Primary ➕ New Chat Action
# ---------------------------------------------------------
if st.sidebar.button("➕ New Chat", key="top_new_chat_btn", use_container_width=True, type="primary"):
    start_new_chat()
    st.rerun()

# ---------------------------------------------------------
# ChatGPT-Style: Recent Chats / Conversation History
# ---------------------------------------------------------
saved_sessions = load_chat_sessions()
if saved_sessions:
    with st.sidebar.expander(f"💬 Recent Chats ({len(saved_sessions)})", expanded=True):
        for sess in saved_sessions:
            s_id = sess.get("id", "")
            is_active = (s_id == st.session_state.get("current_session_id"))
            s_title = sess.get("title", "Conversation")

            c_hist1, c_hist2 = st.columns([5, 1])
            with c_hist1:
                icon = "🟢 " if is_active else "💬 "
                if st.button(f"{icon}{s_title}", key=f"hist_btn_{s_id}", use_container_width=True, help=f"Updated: {sess.get('updated_at', '')}"):
                    switch_to_chat_session(s_id)
                    st.rerun()
            with c_hist2:
                if st.button("✕", key=f"del_btn_{s_id}", help="Delete this chat"):
                    delete_chat_session(s_id)
                    st.rerun()

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
# MAIN CONTENT TABS
# =========================================================

tab_chat, tab_studio, tab_summarize, tab_compare, tab_extract = st.tabs([
    "💬 ChatGPT-Style Chat & Q&A",
    "✍️ Document Studio (Edit & Export)",
    "📝 Document Summarization",
    "⚖️ Document Comparison",
    "📊 Structured Extraction",
])


# =========================================================
# TAB 1: CHATGPT-STYLE MASTER CHAT & Q&A
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
                st.markdown(msg["content"], unsafe_allow_html=True)

                if msg["role"] == "assistant":
                    col_m1, col_m2 = st.columns([4, 1])
                    with col_m1:
                        conf = msg.get("confidence")
                        if conf == "high":
                            st.markdown('<span class="badge-high">🟢 High Confidence</span>', unsafe_allow_html=True)
                        elif conf == "medium":
                            st.markdown('<span class="badge-med">🟡 Medium Confidence</span>', unsafe_allow_html=True)
                        elif conf == "low":
                            st.markdown('<span class="badge-low">🔴 Low Confidence / Grounding Guardrail</span>', unsafe_allow_html=True)

                        if msg.get("rewritten_query"):
                            st.caption(f"🔍 *Decontextualized search query:* `{msg['rewritten_query']}`")

                    with col_m2:
                        # 🔊 Speaker / Listen Button (ChatGPT-Style Audio Playback)
                        if st.button("🔊 Listen", key=f"speak_btn_{idx}", help="Play answer audio"):
                            audio_data = msg.get("audio_bytes")
                            if not audio_data:
                                audio_data = synthesize_audio_api(msg["content"], msg.get("detected_language", "en"))
                                msg["audio_bytes"] = audio_data
                            if audio_data:
                                st.session_state.audio_cache[idx] = audio_data

                    if idx in st.session_state.audio_cache:
                        st.audio(st.session_state.audio_cache[idx], format="audio/mp3")

                    # 🔔 Proactive Action & Deadline Controls (Trilingual Switcher & Voice)
                    alert_info = msg.get("action_alert")
                    doc_id_ref = msg.get("doc_id") or st.session_state.active_doc_id
                    if alert_info:
                        with st.expander("🔔 Action Alert: Translate & 🔊 Read Aloud", expanded=False):
                            ca1, ca2 = st.columns([3, 2])
                            with ca1:
                                cur_l = alert_info.get("language", "en")
                                opts_l = ["en", "hi", "gu"]
                                def_idx = opts_l.index(cur_l) if cur_l in opts_l else 0
                                new_l = st.radio(
                                    "Alert Language:",
                                    opts_l,
                                    index=def_idx,
                                    format_func=lambda x: {"en": "🇬🇧 English", "hi": "🇮🇳 हिन्दी (Hindi)", "gu": "🇮🇳 ગુજરાતી (Gujarati)"}[x],
                                    horizontal=True,
                                    key=f"alert_lang_radio_{idx}",
                                )
                                if new_l != cur_l and doc_id_ref:
                                    try:
                                        r_al = requests.get(f"{API_URL}/document/{doc_id_ref}/action-alert", params={"language": new_l}, timeout=30)
                                        if r_al.ok:
                                            new_alert_data = r_al.json().get("action_alert", {})
                                            old_md = format_action_alert_markdown(alert_info)
                                            new_md = format_action_alert_markdown(new_alert_data)
                                            msg["action_alert"] = new_alert_data
                                            if old_md in msg["content"]:
                                                msg["content"] = msg["content"].replace(old_md, new_md)
                                            st.session_state.setdefault("doc_action_alerts", {})[doc_id_ref] = new_alert_data
                                            st.rerun()
                                    except Exception as err:
                                        st.error(f"Translation failed: {err}")

                            with ca2:
                                if st.button("🔊 Listen to Alert", key=f"listen_alert_btn_{idx}", help="Read alert aloud in selected language"):
                                    speak_text = alert_info.get("action_summary", "") or alert_info.get("alert_markdown", "")
                                    aud_bytes = synthesize_audio_api(speak_text, alert_info.get("language", "en"))
                                    if aud_bytes:
                                        st.session_state.audio_cache[f"alert_audio_{idx}"] = aud_bytes

                            if f"alert_audio_{idx}" in st.session_state.audio_cache:
                                st.audio(st.session_state.audio_cache[f"alert_audio_{idx}"], format="audio/mp3")

                    # Source Citations
                    sources = msg.get("sources", [])
                    if sources:
                        with st.expander(f"📖 Sources & Evidence ({len(sources)} citations)", expanded=False):
                            for s in sources:
                                st.markdown(f"""
                                <div class="source-card">
                                    <strong>📄 {s['source']}</strong> — Page {s['page']} &nbsp;·&nbsp; <em>Relevance: {s['score']}</em><br/>
                                    <small style="color:#555;">"{s.get('snippet', '')}"</small>
                                </div>
                                """, unsafe_allow_html=True)

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
                with st.spinner(f"Indexing {fname} & checking actions/deadlines with Gemini..."):
                    try:
                        files = {"file": (fname, file_bytes)}
                        res = requests.post(f"{API_URL}/upload", files=files, timeout=300)
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
                                        ask_res = requests.post(f"{API_URL}/ask", json=payload, timeout=120)
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
                                welcome_msg = f"✅ Successfully indexed **{fname}** ({data.get('chunks_indexed', 0)} chunks).\n\n{alert_block}\n\nAsk me any question about this document, request a summary, or open Document Studio to modify it!"
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
                        else:
                            st.error(f"Upload failed: {res.text}")
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
                        res = requests.post(f"{API_URL}/ask", json=payload, timeout=120)

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
                        res = requests.post(f"{API_URL}/ask-voice", files=files, data=data, timeout=180)
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
                                        r_aud = requests.get(f"{API_URL}/audio/{fname}", timeout=15)
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
                                "audio_bytes": audio_bytes,
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
    st.markdown("### ✍️ Document Studio: Prompt-Based Augmenter & Exporter")
    st.caption("Upload a document directly to add new sections, appendices, payment terms, or update clauses via AI prompt, then export to PDF or DOCX.")

    col_upload, col_opts = st.columns([3, 2])
    with col_upload:
        studio_file = st.file_uploader(
            "📁 Upload Document to Modify & Export (PDF, Word, TXT, Excel, etc.):",
            type=["pdf", "docx", "doc", "txt", "md", "csv", "xlsx", "pptx"],
            key="studio_direct_file_uploader",
            help="Drag and drop or browse the specific document you want to edit with Document Studio.",
        )
        use_active_doc = False
        if st.session_state.active_doc_id and not studio_file:
            active_name = next(
                (d["filename"] for d in documents if d["document_id"] == st.session_state.active_doc_id),
                "Active Document"
            )
            use_active_doc = st.checkbox(
                f"⚡ Or use currently active chat document: **{active_name}**",
                value=False,
                key="studio_use_active_check",
            )

    with col_opts:
        export_format = st.radio(
            "Export Format",
            ["DOCX (.docx)", "PDF (.pdf)"],
            horizontal=True,
            key="studio_export_fmt",
        )
        fmt_ext = "docx" if "docx" in export_format.lower() else "pdf"

        edit_mode_label = st.radio(
            "Modification Mode",
            [
                "➕ Append New Section / Appendix (Fast & Safe)",
                "✏️ Revise / Edit Existing Sections",
            ],
            help="Append mode drafts only the new content using minimal tokens, completely avoiding 429 quota limits, and appends it to your full document.",
            key="studio_mode_radio",
        )
        selected_mode = "append" if "Append" in edit_mode_label else "revise"

    prompt_instruction = st.text_area(
        "Enter your update instruction (e.g. Add sections, clauses, or appendices):",
        placeholder="e.g., Add Section 6: Payment Terms & Milestones (40% advance, 60% upon delivery with 30-day net credit). Include an SLA clause guaranteeing 99.9% uptime with 5% monthly penalty for breaches.",
        height=110,
        key="studio_prompt_instruction",
    )

    auto_index_check = st.checkbox(
        "Auto-index updated document into DocMind (so you can immediately chat with the updated version)",
        value=True,
        key="studio_auto_index_check",
    )

    if st.button("✨ Generate & Export Updated Document", type="primary", key="studio_generate_btn"):
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
                    res = requests.post(f"{API_URL}/document/edit", json=payload, timeout=180)
                    if res.ok:
                        data = res.json()
                        new_file_name = data["filename"]
                        download_url = f"{API_URL}{data['download_url']}"

                        st.success(f"🎉 Successfully created **{new_file_name}**!")

                        file_bytes = requests.get(download_url).content
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
                        st.error(f"Studio error: {res.text}")
                except Exception as e:
                    st.error(f"Connection error: {e}")


# =========================================================
# TAB 3: DOCUMENT SUMMARIZATION (Token-Budgeted)
# =========================================================

with tab_summarize:
    st.markdown("### 📝 Intelligent Document Summarization")
    st.caption("Upload a document directly to generate executive, detailed, or action-oriented summaries in English, Hindi, or Gujarati.")

    col_sum_up, col_sum_opt = st.columns([3, 2])
    with col_sum_up:
        sum_file = st.file_uploader(
            "📁 Upload Document to Summarize (PDF, Word, Excel, CSV, PPTX, TXT):",
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
                f"⚡ Or summarize currently active chat document: **{active_name}**",
                value=False,
                key="sum_use_active_check",
            )

    with col_sum_opt:
        sum_type = st.selectbox(
            "Summary Format",
            ["executive", "detailed", "bullet_points"],
            format_func=lambda x: x.replace("_", " ").title(),
            key="sum_format_select",
        )
        sum_lang = st.selectbox(
            "Output Language",
            ["en", "hi", "gu"],
            format_func=lambda x: {"en": "English", "hi": "हिन्दी (Hindi)", "gu": "ગુજરાતી (Gujarati)"}[x],
            key="sum_lang_select",
        )

    if st.button("✨ Generate Summary", type="primary", key="btn_gen_summary"):
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
                    res = requests.post(f"{API_URL}/summarize", json=payload, timeout=120)
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
    st.markdown("### ⚖️ Cross-Document Comparison")
    st.caption("Upload two documents directly to compare requirements, terms, budgets, and key differences.")

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("#### 📄 Document A (Base Document)")
        file_a = st.file_uploader(
            "Upload Document A (PDF, Word, Excel, PPTX, TXT):",
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
                f"⚡ Use active chat document as Doc A: **{active_name}**",
                value=False,
                key="comp_use_active_a_check",
            )

    with col_c2:
        st.markdown("#### 📄 Document B (Comparison Target)")
        file_b = st.file_uploader(
            "Upload Document B (PDF, Word, Excel, PPTX, TXT):",
            type=["pdf", "docx", "doc", "txt", "md", "csv", "tsv", "xlsx", "xls", "pptx", "html", "json"],
            key="comp_direct_file_b",
        )

    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        focus = st.text_input(
            "Specific Focus Area (Optional)",
            value="Differences in budget, requirements, deadlines, and deliverables",
            key="comp_focus_input",
        )
    with col_f2:
        comp_lang = st.selectbox(
            "Comparison Language",
            ["en", "hi", "gu"],
            format_func=lambda x: {"en": "English", "hi": "हिन्दी (Hindi)", "gu": "ગુજરાતી (Gujarati)"}[x],
            key="comp_lang_select",
        )

    if st.button("⚖️ Compare Documents", type="primary", key="btn_compare_docs"):
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
                    res = requests.post(f"{API_URL}/compare", json=payload, timeout=180)
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
    st.markdown("### 📊 Structured Information Extraction")
    st.caption("Upload a document directly to extract key entities, financial numbers, milestone deadlines, and tables into structured JSON.")

    col_ext_up, col_ext_opt = st.columns([3, 2])
    with col_ext_up:
        ext_file = st.file_uploader(
            "📁 Upload Document for Structured Extraction (PDF, Word, Excel, CSV, PPTX, TXT):",
            type=["pdf", "docx", "doc", "txt", "md", "csv", "tsv", "xlsx", "xls", "pptx", "html", "json"],
            key="extract_direct_file_uploader",
            help="Drag and drop or browse the specific document you want to extract structured data from.",
        )
        use_active_doc_ext = False
        if st.session_state.active_doc_id and not ext_file:
            active_name = next(
                (d["filename"] for d in documents if d["document_id"] == st.session_state.active_doc_id),
                "Active Document"
            )
            use_active_doc_ext = st.checkbox(
                f"⚡ Or extract from currently active chat document: **{active_name}**",
                value=False,
                key="extract_use_active_check",
            )

    with col_ext_opt:
        ext_type = st.selectbox(
            "Extraction Schema",
            ["full_schema", "financials", "dates_deadlines", "key_entities"],
            format_func=lambda x: x.replace("_", " ").title(),
            key="extract_schema_select",
        )

    if st.button("🔍 Extract Structured Data", type="primary", key="btn_extract_data"):
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
                    res = requests.post(f"{API_URL}/extract", json=payload, timeout=120)
                    if res.ok:
                        data = res.json()

                        if data.get("summary_points"):
                            st.subheader("📌 Key Highlights")
                            for pt in data["summary_points"]:
                                st.write(f"- {pt}")

                        if data.get("extracted_items"):
                            st.subheader("📋 Extracted Attributes")
                            st.dataframe(data["extracted_items"], use_container_width=True)

                        if data.get("tables_detected"):
                            st.subheader("📊 Detected Tables")
                            for tbl in data["tables_detected"]:
                                st.markdown(f"**{tbl.get('table_name', 'Table')}**")
                                headers = tbl.get("headers", [])
                                rows = tbl.get("rows", [])
                                if headers and rows:
                                    import pandas as pd
                                    df = pd.DataFrame(rows, columns=headers)
                                    st.dataframe(df, use_container_width=True)

                        with st.expander("📄 View Raw JSON Output"):
                            st.json(data)
                    else:
                        st.error(f"Extraction error: {res.text}")
                except Exception as e:
                    st.error(f"Failed to connect: {e}")