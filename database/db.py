import aiosqlite
import os
import datetime
from config import config

os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)


async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        # jobs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sso_url TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # users
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                expire_at TIMESTAMP NULL
            )
        """)

        # sessions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id INTEGER PRIMARY KEY,
                job_id INTEGER,
                sso_url TEXT,
                state TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # requests
        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        """)

        # settings (global state)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_global_stop', '0')"
        )

        await db.commit()


# ═══════════════════════════════════════════
# JOBS
# ═══════════════════════════════════════════

async def add_job(user_id: int, sso_url: str) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO jobs (user_id, sso_url) VALUES (?, ?)",
            (user_id, sso_url)
        )
        await db.commit()
        return cur.lastrowid


async def update_job(job_id: int, status: str, result: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status=?, result=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, result, job_id)
        )
        await db.commit()


async def get_user_jobs(user_id: int, limit: int = 10):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, status, created_at FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        return await cur.fetchall()


async def count_jobs():
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM jobs")
        row = await cur.fetchone()
        return row[0] if row else 0


# ═══════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════

async def register_user(user_id: int, username: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        access = 1 if user_id == config.ADMIN_ID else 0
        priority = 100 if user_id == config.ADMIN_ID else 0

        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, username, access, priority)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, access, priority))
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_all_users():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY user_id")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def has_access(user_id: int) -> bool:
    if user_id == config.ADMIN_ID:
        return True
    user = await get_user(user_id)
    if not user:
        return False
    if user.get("banned"):
        return False
    if not user.get("access"):
        return False
    exp = user.get("expire_at")
    if exp:
        try:
            exp_dt = datetime.datetime.fromisoformat(exp)
            if datetime.datetime.utcnow() > exp_dt:
                return False
        except Exception:
            pass
    return True


async def is_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return bool(user and user.get("banned"))


async def set_access(user_id: int, access: int, expire_at: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        if expire_at:
            await db.execute(
                "UPDATE users SET access=?, expire_at=?, banned=0 WHERE user_id=?",
                (access, expire_at, user_id)
            )
        else:
            await db.execute(
                "UPDATE users SET access=?, expire_at=NULL, banned=0 WHERE user_id=?",
                (access, user_id)
            )
        await db.commit()


async def set_ban(user_id: int, banned: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET banned=? WHERE user_id=?", (banned, user_id))
        await db.commit()


async def set_priority(user_id: int, priority: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET priority=? WHERE user_id=?", (priority, user_id))
        await db.commit()


async def get_active_users():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE access=1 AND banned=0")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_banned_users():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE banned=1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════
# REQUESTS
# ═══════════════════════════════════════════

async def add_request(user_id: int, username: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO requests (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await db.commit()


async def get_requests(status: str = "pending"):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM requests WHERE status=? ORDER BY id DESC",
            (status,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def update_request(req_id: int, status: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE requests SET status=? WHERE id=?", (status, req_id))
        await db.commit()


# ═══════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════

async def set_session(user_id: int, job_id: int = None, sso_url: str = None, state: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM sessions WHERE user_id=?", (user_id,))
        exists = await cur.fetchone()
        if exists:
            updates, params = [], []
            for field, val in [("job_id", job_id), ("sso_url", sso_url), ("state", state)]:
                if val is not None:
                    updates.append(f"{field}=?")
                    params.append(val)
            if updates:
                params.append(user_id)
                await db.execute(
                    f"UPDATE sessions SET {', '.join(updates)}, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                    params
                )
        else:
            await db.execute(
                "INSERT INTO sessions (user_id, job_id, sso_url, state) VALUES (?, ?, ?, ?)",
                (user_id, job_id, sso_url, state)
            )
        await db.commit()


async def get_session(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM sessions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def clear_session(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        await db.commit()


# ═══════════════════════════════════════════
# SETTINGS (Global State)
# ═══════════════════════════════════════════

async def init_global_state():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_global_stop', '0')"
        )
        await db.commit()


async def get_setting(key: str, default: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await db.commit()


async def is_globally_stopped() -> bool:
    val = await get_setting("bot_global_stop", "0")
    return val == "1"


async def set_global_stop(stop: bool):
    await set_setting("bot_global_stop", "1" if stop else "0")
