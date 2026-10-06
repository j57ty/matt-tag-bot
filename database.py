import os
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize SQLite database tables and indices, and preload seed members if present."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                x_handle TEXT PRIMARY KEY COLLATE NOCASE,
                tg_username TEXT COLLATE NOCASE,
                user_id INTEGER,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_members_tg_username ON members(tg_username);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_members_user_id ON members(user_id);
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users_cache (
                user_id INTEGER PRIMARY KEY,
                tg_username TEXT COLLATE NOCASE,
                first_name TEXT,
                last_name TEXT,
                last_seen TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cache_username ON users_cache(tg_username);
            """
        )
        conn.commit()

        # Seed initial members from seed_members.json if file exists
        seed_path = Path(__file__).resolve().parent / "seed_members.json"
        if seed_path.exists():
            try:
                with open(seed_path, "r", encoding="utf-8") as f:
                    seed_data = json.load(f)
                now = datetime.utcnow().isoformat()
                for item in seed_data:
                    clean_tag = normalize_handle(item.get("tag", ""))
                    clean_tg = normalize_handle(item.get("tg_username", ""))
                    if clean_tag and clean_tg:
                        cursor.execute(
                            """
                            INSERT INTO members (x_handle, tg_username, user_id, first_name, last_name, created_at, updated_at)
                            VALUES (?, ?, NULL, NULL, NULL, ?, ?)
                            ON CONFLICT(x_handle) DO UPDATE SET
                                tg_username = excluded.tg_username;
                            """,
                            (clean_tag, clean_tg, now, now)
                        )
                conn.commit()
            except Exception as e:
                print(f"Error loading seed_members.json: {e}")


def normalize_handle(handle: str) -> str:
    """Strips leading '@' and whitespace, and converts to lowercase."""
    if not handle:
        return ""
    return handle.strip().lstrip("@").lower()


def cache_user(user_id: int, tg_username: Optional[str], first_name: Optional[str], last_name: Optional[str]):
    """Records or updates user profile in cache and links known tg_username in members."""
    now = datetime.utcnow().isoformat()
    clean_username = normalize_handle(tg_username) if tg_username else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users_cache (user_id, tg_username, first_name, last_name, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                tg_username = excluded.tg_username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen = excluded.last_seen;
            """,
            (user_id, clean_username, first_name, last_name, now)
        )
        # Also auto-update user_id and names in members if this username is registered
        if clean_username:
            cursor.execute(
                """
                UPDATE members
                SET user_id = ?, first_name = COALESCE(?, first_name), last_name = COALESCE(?, last_name), updated_at = ?
                WHERE tg_username = ? COLLATE NOCASE;
                """,
                (user_id, first_name, last_name, now, clean_username)
            )
        conn.commit()


def find_cached_user_by_username(tg_username: str) -> Optional[Dict[str, Any]]:
    clean_username = normalize_handle(tg_username)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users_cache WHERE tg_username = ? COLLATE NOCASE LIMIT 1;",
            (clean_username,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def find_cached_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users_cache WHERE user_id = ? LIMIT 1;",
            (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_member(
    x_handle: str,
    tg_username: Optional[str] = None,
    user_id: Optional[int] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> Dict[str, Any]:
    """Links or updates a Telegram user with a tag."""
    clean_x = normalize_handle(x_handle)
    clean_tg_user = normalize_handle(tg_username) if tg_username else None
    now = datetime.utcnow().isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO members (x_handle, tg_username, user_id, first_name, last_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(x_handle) DO UPDATE SET
                tg_username = COALESCE(excluded.tg_username, members.tg_username),
                user_id = COALESCE(excluded.user_id, members.user_id),
                first_name = COALESCE(excluded.first_name, members.first_name),
                last_name = COALESCE(excluded.last_name, members.last_name),
                updated_at = excluded.updated_at;
            """,
            (clean_x, clean_tg_user, user_id, first_name, last_name, now, now)
        )
        conn.commit()

        cursor.execute("SELECT * FROM members WHERE x_handle = ? COLLATE NOCASE;", (clean_x,))
        return dict(cursor.fetchone())


def get_member_by_x_handle(x_handle: str) -> Optional[Dict[str, Any]]:
    clean_x = normalize_handle(x_handle)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM members WHERE x_handle = ? COLLATE NOCASE LIMIT 1;",
            (clean_x,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_member_by_user_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM members WHERE user_id = ? LIMIT 1;",
            (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_member_by_tg_username(tg_username: str) -> Optional[Dict[str, Any]]:
    clean_username = normalize_handle(tg_username)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM members WHERE tg_username = ? COLLATE NOCASE LIMIT 1;",
            (clean_username,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def remove_member(identifier: str) -> bool:
    """Removes a member link by tag, @telegram_username, or telegram user_id."""
    clean_id = normalize_handle(identifier)
    with get_connection() as conn:
        cursor = conn.cursor()
        if clean_id.isdigit():
            cursor.execute("DELETE FROM members WHERE user_id = ?;", (int(clean_id),))
        else:
            cursor.execute(
                "DELETE FROM members WHERE x_handle = ? COLLATE NOCASE OR tg_username = ? COLLATE NOCASE;",
                (clean_id, clean_id)
            )
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted


def list_all_members() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members ORDER BY updated_at DESC;")
        return [dict(row) for row in cursor.fetchall()]


def count_members() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM members;")
        row = cursor.fetchone()
        return row["cnt"] if row else 0
