import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize SQLite database tables and indices."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                user_id INTEGER PRIMARY KEY,
                x_handle TEXT NOT NULL UNIQUE COLLATE NOCASE,
                tg_username TEXT COLLATE NOCASE,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_members_x_handle ON members(x_handle);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_members_tg_username ON members(tg_username);
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


def normalize_handle(handle: str) -> str:
    """Strips leading '@' and whitespace, and converts to lowercase."""
    if not handle:
        return ""
    return handle.strip().lstrip("@").lower()


def cache_user(user_id: int, tg_username: Optional[str], first_name: Optional[str], last_name: Optional[str]):
    """Records or updates user profile in cache when they interact in chat."""
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
        # Also update members table if user is registered to keep their names/usernames current
        cursor.execute(
            """
            UPDATE members
            SET tg_username = ?, first_name = ?, last_name = ?, updated_at = ?
            WHERE user_id = ?;
            """,
            (clean_username, first_name, last_name, now, user_id)
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
    user_id: int,
    x_handle: str,
    tg_username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
) -> Dict[str, Any]:
    """Links or updates a Telegram user with an X handle."""
    clean_x = normalize_handle(x_handle)
    clean_tg_user = normalize_handle(tg_username) if tg_username else None
    now = datetime.utcnow().isoformat()

    with get_connection() as conn:
        cursor = conn.cursor()

        # Check if this X handle is already linked to another user ID
        cursor.execute(
            "SELECT user_id FROM members WHERE x_handle = ? COLLATE NOCASE;",
            (clean_x,)
        )
        existing = cursor.fetchone()
        if existing and existing["user_id"] != user_id:
            # Reassign from previous user to this user
            cursor.execute("DELETE FROM members WHERE user_id = ?;", (existing["user_id"],))

        cursor.execute(
            """
            INSERT INTO members (user_id, x_handle, tg_username, first_name, last_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                x_handle = excluded.x_handle,
                tg_username = COALESCE(excluded.tg_username, members.tg_username),
                first_name = COALESCE(excluded.first_name, members.first_name),
                last_name = COALESCE(excluded.last_name, members.last_name),
                updated_at = excluded.updated_at;
            """,
            (user_id, clean_x, clean_tg_user, first_name, last_name, now, now)
        )
        conn.commit()

        cursor.execute("SELECT * FROM members WHERE user_id = ?;", (user_id,))
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
    """Removes a member link by X handle, @telegram_username, or telegram user_id."""
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
