# app/core/auth.py

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "users.db"


def get_db_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite users database with row_factory enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_user_db():
    """Initializes users table if not exists and seeds the default demo account."""
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
    finally:
        conn.close()

    create_demo_user_if_needed()


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
