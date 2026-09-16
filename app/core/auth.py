# app/core/auth.py

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "users.db"


def get_db_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite users database with row_factory enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_user_db():
    """Initializes users and chat_sessions tables if not exists and seeds the default demo account."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL COLLATE NOCASE,
                    title TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    selected_document_ids TEXT,
                    active_doc_id TEXT,
                    messages TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_email ON chat_sessions(user_email);
            """)
    finally:
        conn.close()

    create_demo_user_if_needed()
    migrate_legacy_json_sessions_if_needed()


def hash_password(password: str, salt_hex: str) -> str:
    """Hashes password with PBKDF2-HMAC-SHA256 (100,000 iterations)."""
    salt = bytes.fromhex(salt_hex)
    pwd_bytes = password.encode("utf-8")
    derived = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt, 100_000)
    return derived.hex()


def is_valid_email(email: str) -> bool:
    """Basic RFC 5322 compliant regex check for email validity."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email.strip()))


def register_user(name: str, email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Registers a new user with secure salted password hashing.
    Returns: (success, message, user_dict)
    """
    clean_name = name.strip()
    clean_email = email.strip().lower()

    if not clean_name:
        return False, "Please enter your full name.", None

    if not clean_email or not is_valid_email(clean_email):
        return False, "Please provide a valid email address.", None

    if len(password) < 6:
        return False, "Password must be at least 6 characters long.", None

    init_user_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
        if cursor.fetchone():
            return False, "An account with this email address already exists.", None

        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        salt_hex = secrets.token_hex(16)
        pwd_hash = hash_password(password, salt_hex)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with conn:
            conn.execute(
                """
                INSERT INTO users (user_id, name, email, password_hash, salt, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, clean_name, clean_email, pwd_hash, salt_hex, now_str, now_str),
            )

        user_dict = {
            "user_id": user_id,
            "name": clean_name,
            "email": clean_email,
            "created_at": now_str,
        }
        return True, "Account created successfully!", user_dict
    except Exception as e:
        return False, f"Registration error: {e}", None
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validates user credentials and updates last login timestamp.
    Returns: (success, message, user_dict)
    """
    clean_email = email.strip().lower()
    if not clean_email or not password:
        return False, "Email and password are required.", None

    init_user_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
        row = cursor.fetchone()

        if not row:
            return False, "Invalid email or password.", None

        salt_hex = row["salt"]
        stored_hash = row["password_hash"]
        attempt_hash = hash_password(password, salt_hex)

        # Constant-time comparison prevents timing attacks
        if not hmac.compare_digest(stored_hash, attempt_hash):
            return False, "Invalid email or password.", None

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with conn:
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_str, row["id"]))

        user_dict = {
            "user_id": row["user_id"],
            "name": row["name"],
            "email": row["email"],
            "created_at": row["created_at"],
            "last_login": now_str,
        }
        return True, f"Welcome back, {row['name']}!", user_dict
    except Exception as e:
        return False, f"Authentication error: {e}", None
    finally:
        conn.close()


def create_demo_user_if_needed():
    """Seeds a ready-to-test demo account: demo@docmind.ai / Demo@123."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = 'demo@docmind.ai'")
        if not cursor.fetchone():
            salt_hex = secrets.token_hex(16)
            pwd_hash = hash_password("Demo@123", salt_hex)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with conn:
                conn.execute(
                    """
                    INSERT INTO users (user_id, name, email, password_hash, salt, created_at, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("usr_demo001", "Demo User", "demo@docmind.ai", pwd_hash, salt_hex, now_str, now_str),
                )
    except Exception as e:
        print(f"Warning initializing demo user: {e}")
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile by user_id."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, email, created_at, last_login FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


# =========================================================
# CHAT SESSIONS PERSISTENCE (Strict Email-Wise Isolation)
# =========================================================

def get_user_chat_sessions(email: str) -> List[Dict[str, Any]]:
    """
    Retrieves all chat sessions strictly belonging to the specified email address,
    ordered newest first.
    """
    clean_email = email.strip().lower() if email else ""
    if not clean_email:
        return []

    init_user_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_email, title, updated_at, selected_document_ids, active_doc_id, messages
            FROM chat_sessions
            WHERE user_email = ?
            ORDER BY rowid DESC
            """,
            (clean_email,)
        )
        rows = cursor.fetchall()
        sessions = []
        for r in rows:
            try:
                msgs = json.loads(r["messages"]) if r["messages"] else []
            except Exception:
                msgs = []
            try:
                doc_ids = json.loads(r["selected_document_ids"]) if r["selected_document_ids"] else []
            except Exception:
                doc_ids = []
            sessions.append({
                "id": r["id"],
                "user_email": r["user_email"],
                "title": r["title"],
                "updated_at": r["updated_at"],
                "selected_document_ids": doc_ids,
                "active_doc_id": r["active_doc_id"],
                "messages": msgs,
            })
        return sessions
    finally:
        conn.close()


def save_user_chat_session(email: str, session: Dict[str, Any]):
    """
    Saves or updates a chat session strictly belonging to the specified email address.
    """
    clean_email = email.strip().lower() if email else ""
    if not clean_email or not session or not session.get("id"):
        return

    init_user_db()
    conn = get_db_connection()
    try:
        sess_id = session["id"]
        title = session.get("title", "New Conversation")
        updated_at = session.get("updated_at") or datetime.now().strftime("%d %b, %H:%M")
        doc_ids_json = json.dumps(session.get("selected_document_ids", []))
        active_doc_id = session.get("active_doc_id")
        messages_json = json.dumps(session.get("messages", []), ensure_ascii=False)

        with conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (id, user_email, title, updated_at, selected_document_ids, active_doc_id, messages)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_email = excluded.user_email,
                    title = excluded.title,
                    updated_at = excluded.updated_at,
                    selected_document_ids = excluded.selected_document_ids,
                    active_doc_id = excluded.active_doc_id,
                    messages = excluded.messages
                """,
                (sess_id, clean_email, title, updated_at, doc_ids_json, active_doc_id, messages_json),
            )
    finally:
        conn.close()


def delete_user_chat_session(email: str, session_id: str):
    """
    Deletes a specific chat session for the specified email address.
    """
    clean_email = email.strip().lower() if email else ""
    if not clean_email or not session_id:
        return

    init_user_db()
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM chat_sessions WHERE id = ? AND user_email = ?",
                (session_id, clean_email),
            )
    finally:
        conn.close()


def clear_all_user_chat_sessions(email: str):
    """
    Deletes all chat sessions for the specified email address.
    """
    clean_email = email.strip().lower() if email else ""
    if not clean_email:
        return

    init_user_db()
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                "DELETE FROM chat_sessions WHERE user_email = ?",
                (clean_email,),
            )
    finally:
        conn.close()


def migrate_legacy_json_sessions_if_needed():
    """
    Automatically migrates any existing JSON session files into SQLite chat_sessions table.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chat_sessions")
        count = cursor.fetchone()[0]
        if count > 0:
            return  # Already migrated

        cursor.execute("SELECT user_id, email FROM users")
        user_map = {row["user_id"]: row["email"] for row in cursor.fetchall()}
        user_map["default"] = "demo@docmind.ai"

        data_dir = DB_PATH.parent
        if not data_dir.exists():
            return

        for f in data_dir.glob("chat_sessions*.json"):
            target_email = "demo@docmind.ai"
            if "_" in f.stem:
                parts = f.stem.split("_")
                u_id = "_".join(parts[2:]) if len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
                target_email = user_map.get(u_id, user_map.get(f.stem.replace("chat_sessions_", ""), "demo@docmind.ai"))

            try:
                with open(f, "r", encoding="utf-8") as fp:
                    sessions = json.load(fp)
                    if isinstance(sessions, list):
                        for s in sessions:
                            if s.get("id") and s.get("messages"):
                                save_user_chat_session(target_email, s)
            except Exception:
                pass
    except Exception as e:
        print(f"Warning during legacy session migration: {e}")
    finally:
        conn.close()

