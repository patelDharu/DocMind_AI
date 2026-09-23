# app/core/auth.py

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger("docmind.auth")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "users.db"


def get_database_url() -> Optional[str]:
    """Returns normalized DATABASE_URL if set (converts postgres:// to postgresql://)."""
    raw_url = (os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        return None
    # Fix Render/Heroku legacy postgres:// schema for psycopg2
    if raw_url.startswith("postgres://"):
        raw_url = "postgresql://" + raw_url[len("postgres://"):]
    return raw_url


def is_postgres() -> bool:
    """Returns True if a PostgreSQL connection string is configured."""
    return bool(get_database_url())


def get_database_status_info() -> Dict[str, Any]:
    """Returns current active database type and connection info for diagnostics."""
    if is_postgres():
        url = get_database_url() or ""
        host = url.split("@")[-1].split("/")[0] if "@" in url else "remote"
        return {
            "type": "postgresql",
            "label": "PostgreSQL (Persistent Cloud)",
            "host": host,
            "persistent": True,
        }
    return {
        "type": "sqlite",
        "label": "Local SQLite (Ephemeral on Render)",
        "path": str(DB_PATH),
        "persistent": False,
    }


def get_raw_connection():
    """Returns a raw database connection (psycopg2 for PostgreSQL, sqlite3 for local)."""
    db_url = get_database_url()
    if db_url:
        try:
            import psycopg2
            return psycopg2.connect(db_url)
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL via DATABASE_URL ({e}). Falling back to SQLite...")
    
    # SQLite fallback
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def execute_db(
    query: str,
    params: tuple = (),
    fetchone: bool = False,
    fetchall: bool = False,
    commit: bool = False,
) -> Any:
    """
    Executes a SQL query universally across both SQLite and PostgreSQL.
    Automatically handles parameter placeholders (? -> %s for Postgres)
    and returns dictionary-like rows.
    """
    conn = get_raw_connection()
    use_pg = is_postgres() and not isinstance(conn, sqlite3.Connection)
    
    try:
        if use_pg:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            pg_query = query.replace("?", "%s")
            cursor.execute(pg_query, params)
        else:
            cursor = conn.cursor()
            cursor.execute(query, params)

        result = None
        if fetchone:
            row = cursor.fetchone()
            result = dict(row) if row else None
        elif fetchall:
            rows = cursor.fetchall()
            result = [dict(r) for r in rows] if rows else []

        if commit:
            conn.commit()

        return result
    except Exception as e:
        if commit and conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise e
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_user_db():
    """
    Initializes users, chat_sessions, and user_sessions tables
    in either PostgreSQL or SQLite, then seeds the default demo user.
    """
    conn = get_raw_connection()
    use_pg = is_postgres() and not isinstance(conn, sqlite3.Connection)

    try:
        cursor = conn.cursor()
        if use_pg:
            # PostgreSQL Schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    title TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    selected_document_ids TEXT,
                    active_doc_id TEXT,
                    messages TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_email ON chat_sessions(user_email);
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_sessions_email ON user_sessions(user_email);
            """)
            conn.commit()
        else:
            # SQLite Schema
            cursor.execute("""
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
            cursor.execute("""
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
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_email ON chat_sessions(user_email);
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL COLLATE NOCASE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_sessions_email ON user_sessions(user_email);
            """)
            conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

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
    try:
        existing = execute_db(
            "SELECT id FROM users WHERE LOWER(email) = LOWER(?)",
            (clean_email,),
            fetchone=True,
        )
        if existing:
            return False, "An account with this email address already exists.", None

        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        salt_hex = secrets.token_hex(16)
        pwd_hash = hash_password(password, salt_hex)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        execute_db(
            """
            INSERT INTO users (user_id, name, email, password_hash, salt, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, clean_name, clean_email, pwd_hash, salt_hex, now_str, now_str),
            commit=True,
        )

        user_dict = {
            "user_id": user_id,
            "name": clean_name,
            "email": clean_email,
            "created_at": now_str,
        }
        token = generate_session_token(clean_email)
        user_dict["token"] = token
        return True, "Account created successfully!", user_dict
    except Exception as e:
        logger.error(f"Registration exception: {e}")
        return False, f"Registration error: {e}", None


def authenticate_user(email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validates user credentials and updates last login timestamp.
    Returns clear, user-friendly messages distinguishing between missing user vs wrong password.
    Returns: (success, message, user_dict)
    """
    clean_email = email.strip().lower()
    if not clean_email or not password:
        return False, "Email and password are required.", None

    init_user_db()
    try:
        row = execute_db(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
            (clean_email,),
            fetchone=True,
        )

        if not row:
            if is_postgres():
                return False, "No account found with this email. Please check your spelling or create an account.", None
            else:
                return (
                    False,
                    "No account found with this email. Note: If running on Render free tier, server restarts wipe local storage. "
                    "Please create an account or connect a PostgreSQL database.",
                    None,
                )

        salt_hex = row["salt"]
        stored_hash = row["password_hash"]
        attempt_hash = hash_password(password, salt_hex)

        # Constant-time comparison prevents timing attacks
        if not hmac.compare_digest(stored_hash, attempt_hash):
            return False, "Incorrect password. Please verify and try again.", None

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        execute_db(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (now_str, row["id"]),
            commit=True,
        )

        user_dict = {
            "user_id": row["user_id"],
            "name": row["name"],
            "email": row["email"],
            "created_at": row["created_at"],
            "last_login": now_str,
        }
        token = generate_session_token(clean_email)
        user_dict["token"] = token
        return True, f"Welcome back, {row['name']}!", user_dict
    except Exception as e:
        logger.error(f"Authentication exception: {e}")
        return False, f"Authentication error: {e}", None


def generate_session_token(email: str, duration_days: int = 30) -> str:
    """Generates and persists a secure session token for the user."""
    clean_email = email.strip().lower()
    token = f"dmtk_{secrets.token_urlsafe(32)}"
    now = datetime.now()
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (now + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")

    init_user_db()
    try:
        execute_db(
            """
            INSERT INTO user_sessions (token, user_email, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, clean_email, created_at, expires_at),
            commit=True,
        )
        return token
    except Exception as e:
        logger.warning(f"Failed to persist session token: {e}")
        return token


def validate_session_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validates a session token or static API key.
    Returns user dict if valid, None otherwise.
    """
    if not token or not isinstance(token, str):
        return None

    clean_token = token.strip()
    if clean_token.startswith("Bearer "):
        clean_token = clean_token[7:].strip()

    # 1. Master API key check
    master_key = os.getenv("DOCMIND_API_KEY")
    if master_key and clean_token == master_key.strip():
        return {
            "user_id": "usr_system",
            "name": "System Administrator",
            "email": "admin@docmind.ai",
            "is_admin": True,
            "token": clean_token,
        }

    # 2. Database session check
    init_user_db()
    try:
        row = execute_db(
            "SELECT user_email, expires_at FROM user_sessions WHERE token = ?",
            (clean_token,),
            fetchone=True,
        )
        if not row:
            return None

        expires_at_str = row.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > expires_at:
                    return None
            except Exception:
                pass

        email = row["user_email"]
        user_row = execute_db(
            "SELECT user_id, name, email, created_at, last_login FROM users WHERE LOWER(email) = LOWER(?)",
            (email,),
            fetchone=True,
        )
        if user_row:
            u_dict = dict(user_row)
            u_dict["token"] = clean_token
            return u_dict

        return {
            "user_id": f"usr_{uuid.uuid4().hex[:12]}",
            "name": email.split("@")[0].capitalize(),
            "email": email,
            "token": clean_token,
        }
    except Exception as e:
        logger.warning(f"Token validation error: {e}")
        return None


def revoke_session_token(token: str) -> bool:
    """Revokes / deletes a session token."""
    if not token:
        return False
    clean_token = token.replace("Bearer ", "").strip()
    init_user_db()
    try:
        execute_db("DELETE FROM user_sessions WHERE token = ?", (clean_token,), commit=True)
        return True
    except Exception:
        return False


def get_or_create_demo_token() -> str:
    """Returns an active session token for demo@docmind.ai."""
    create_demo_user_if_needed()
    return generate_session_token("demo@docmind.ai")


def sanitize_chat_messages(messages: Any) -> list:
    """
    Recursively cleans message payloads to ensure all bytes or non-serializable objects
    are safely stripped or converted before JSON persistence.
    """
    if not isinstance(messages, list):
        return []

    clean_list = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        clean_msg = {}
        for k, v in msg.items():
            if isinstance(v, bytes):
                continue
            elif isinstance(v, dict):
                clean_msg[k] = {
                    sub_k: (str(sub_v) if isinstance(sub_v, bytes) else sub_v)
                    for sub_k, sub_v in v.items()
                    if not isinstance(sub_v, bytes)
                }
            elif isinstance(v, list):
                clean_msg[k] = [
                    (str(x) if isinstance(x, bytes) else x)
                    for x in v
                    if not isinstance(x, bytes)
                ]
            else:
                clean_msg[k] = v
        clean_list.append(clean_msg)
    return clean_list


def create_demo_user_if_needed():
    """Seeds a ready-to-test demo account: demo@docmind.ai / Demo@123."""
    try:
        row = execute_db(
            "SELECT id FROM users WHERE LOWER(email) = 'demo@docmind.ai'",
            fetchone=True,
        )
        if not row:
            salt_hex = secrets.token_hex(16)
            pwd_hash = hash_password("Demo@123", salt_hex)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            execute_db(
                """
                INSERT INTO users (user_id, name, email, password_hash, salt, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("usr_demo001", "Demo User", "demo@docmind.ai", pwd_hash, salt_hex, now_str, now_str),
                commit=True,
            )
    except Exception as e:
        logger.warning(f"Warning initializing demo user: {e}")


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves user profile by user_id."""
    try:
        return execute_db(
            "SELECT user_id, name, email, created_at, last_login FROM users WHERE user_id = ?",
            (user_id,),
            fetchone=True,
        )
    except Exception:
        return None


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
    try:
        rows = execute_db(
            """
            SELECT id, user_email, title, updated_at, selected_document_ids, active_doc_id, messages
            FROM chat_sessions
            WHERE LOWER(user_email) = LOWER(?)
            ORDER BY updated_at DESC
            """,
            (clean_email,),
            fetchall=True,
        )
        sessions = []
        for r in rows:
            try:
                msgs = json.loads(r["messages"]) if r.get("messages") else []
            except Exception:
                msgs = []
            try:
                doc_ids = json.loads(r["selected_document_ids"]) if r.get("selected_document_ids") else []
            except Exception:
                doc_ids = []
            sessions.append({
                "id": r["id"],
                "user_email": r["user_email"],
                "title": r["title"],
                "updated_at": r["updated_at"],
                "selected_document_ids": doc_ids,
                "active_doc_id": r.get("active_doc_id"),
                "messages": msgs,
            })
        return sessions
    except Exception as e:
        logger.warning(f"Error getting chat sessions: {e}")
        return []


def save_user_chat_session(email: str, session: Dict[str, Any]):
    """
    Saves or updates a chat session strictly belonging to the specified email address.
    """
    clean_email = email.strip().lower() if email else ""
    if not clean_email or not session or not session.get("id"):
        return

    init_user_db()
    try:
        sess_id = session["id"]
        title = session.get("title", "New Conversation")
        updated_at = session.get("updated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        doc_ids_json = json.dumps(session.get("selected_document_ids", []), default=str)
        active_doc_id = session.get("active_doc_id")
        raw_msgs = session.get("messages", [])
        safe_msgs = sanitize_chat_messages(raw_msgs)
        messages_json = json.dumps(safe_msgs, ensure_ascii=False, default=str)

        execute_db(
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
            commit=True,
        )
    except Exception as e:
        logger.warning(f"Error saving chat session: {e}")


def delete_user_chat_session(email: str, session_id: str):
    """
    Deletes a specific chat session for the specified email address.
    """
    clean_email = email.strip().lower() if email else ""
    if not clean_email or not session_id:
        return

    init_user_db()
    try:
        execute_db(
            "DELETE FROM chat_sessions WHERE id = ? AND LOWER(user_email) = LOWER(?)",
            (session_id, clean_email),
            commit=True,
        )
    except Exception as e:
        logger.warning(f"Error deleting chat session: {e}")


def clear_all_user_chat_sessions(email: str):
    """
    Deletes all chat sessions for the specified email address.
    """
    clean_email = email.strip().lower() if email else ""
    if not clean_email:
        return

    init_user_db()
    try:
        execute_db(
            "DELETE FROM chat_sessions WHERE LOWER(user_email) = LOWER(?)",
            (clean_email,),
            commit=True,
        )
    except Exception as e:
        logger.warning(f"Error clearing chat sessions: {e}")


def migrate_legacy_json_sessions_if_needed():
    """
    Automatically migrates any existing JSON session files into SQLite/Postgres chat_sessions table.
    """
    try:
        row = execute_db("SELECT COUNT(*) as cnt FROM chat_sessions", fetchone=True)
        count = row["cnt"] if row and "cnt" in row else (list(row.values())[0] if row else 0)
        if count > 0:
            return  # Already migrated

        user_rows = execute_db("SELECT user_id, email FROM users", fetchall=True) or []
        user_map = {r["user_id"]: r["email"] for r in user_rows}
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
        logger.warning(f"Warning during legacy session migration: {e}")
