# ============================================================
#  database.py  —  Async SQLite storage (multi-user support)
# ============================================================

import aiosqlite
from contextlib import asynccontextmanager

DB_PATH = "autoreply.db"

# ── Connection helper ─────────────────────────────────────
# WAL mode allows concurrent readers + one writer without
# blocking. timeout=30 makes writers wait up to 30 s before
# raising "database is locked" instead of failing instantly.

@asynccontextmanager
async def _db():
    async with aiosqlite.connect(DB_PATH, timeout=30) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = aiosqlite.Row
        yield conn

CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT    DEFAULT '',
    full_name   TEXT    DEFAULT '',
    phone       TEXT    DEFAULT '',
    enabled     INTEGER NOT NULL DEFAULT 0,
    message     TEXT    NOT NULL DEFAULT '',
    logged_in   INTEGER NOT NULL DEFAULT 0,
    joined_at   TEXT    DEFAULT (datetime('now'))
);
"""

CREATE_BROADCASTS = """
CREATE TABLE IF NOT EXISTS broadcasts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id    INTEGER,
    message     TEXT,
    sent_at     TEXT DEFAULT (datetime('now')),
    recipients  INTEGER DEFAULT 0
);
"""


async def init_db():
    async with _db() as db:
        await db.execute(CREATE_SETTINGS)
        await db.execute(CREATE_BROADCASTS)
        await db.commit()


# ── Settings CRUD ─────────────────────────────────────────

async def get_settings(user_id: int) -> dict:
    async with _db() as db:
        async with db.execute(
            "SELECT * FROM settings WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            return {
                "user_id": user_id, "username": "", "full_name": "",
                "phone": "", "enabled": 0, "message": "", "logged_in": 0,
                "joined_at": "",
            }


async def upsert_settings(user_id: int, **kwargs):
    settings = await get_settings(user_id)
    settings.update(kwargs)
    async with _db() as db:
        await db.execute(
            """
            INSERT INTO settings
                (user_id, username, full_name, phone, enabled, message, logged_in)
            VALUES
                (:user_id, :username, :full_name, :phone, :enabled, :message, :logged_in)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name,
                phone     = excluded.phone,
                enabled   = excluded.enabled,
                message   = excluded.message,
                logged_in = excluded.logged_in
            """,
            settings,
        )
        await db.commit()


async def set_enabled(user_id: int, value: bool):
    await upsert_settings(user_id, enabled=int(value))

async def set_message(user_id: int, message: str):
    await upsert_settings(user_id, message=message)

async def set_logged_in(user_id: int, value: bool):
    await upsert_settings(user_id, logged_in=int(value))

async def is_enabled(user_id: int) -> bool:
    return bool((await get_settings(user_id))["enabled"])

async def get_message(user_id: int) -> str:
    return (await get_settings(user_id))["message"]

async def is_logged_in(user_id: int) -> bool:
    return bool((await get_settings(user_id))["logged_in"])


# ── Admin queries ─────────────────────────────────────────

async def get_all_users() -> list:
    async with _db() as db:
        async with db.execute(
            "SELECT * FROM settings ORDER BY joined_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_logged_in_users() -> list:
    async with _db() as db:
        async with db.execute(
            "SELECT * FROM settings WHERE logged_in = 1 ORDER BY joined_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_all_user_ids() -> list:
    async with _db() as db:
        async with db.execute("SELECT user_id FROM settings") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def count_users() -> dict:
    async with _db() as db:
        async with db.execute("SELECT COUNT(*) FROM settings") as cur:
            total = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM settings WHERE logged_in = 1"
        ) as cur:
            active = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM settings WHERE enabled = 1"
        ) as cur:
            enabled = (await cur.fetchone())[0]
    return {"total": total, "active": active, "enabled": enabled}


async def log_broadcast(admin_id: int, message: str, recipients: int):
    async with _db() as db:
        await db.execute(
            "INSERT INTO broadcasts (admin_id, message, recipients) VALUES (?, ?, ?)",
            (admin_id, message, recipients),
        )
        await db.commit()


async def get_broadcast_history(limit: int = 5) -> list:
    async with _db() as db:
        async with db.execute(
            "SELECT * FROM broadcasts ORDER BY sent_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
