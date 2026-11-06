import aiosqlite
import os
import datetime
from config import config

os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)

async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        # users
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access INTEGER DEFAULT 1,
                banned INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                deploy_count INTEGER DEFAULT 0,
                invites INTEGER DEFAULT 0
            )
        """)
        
        # user_containers
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                image TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        # sessions (للـ state)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                sso_url TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

# ─── USERS ───
async def register_user(user_id: int, username: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
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

async def update_points(user_id: int, amount: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET points = points + ? WHERE user_id=?", (amount, user_id))
        await db.commit()

async def increment_deploy(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE users SET deploy_count = deploy_count + 1 WHERE user_id=?", (user_id,))
        await db.commit()

# ─── CONTAINERS ───
async def add_container(user_id: int, name: str, image: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("INSERT INTO user_containers (user_id, name, image) VALUES (?, ?, ?)", (user_id, name, image))
        await db.commit()

async def get_user_containers(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM user_containers WHERE user_id=?", (user_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

async def delete_container(c_id: int, user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM user_containers WHERE id=? AND user_id=?", (c_id, user_id))
        await db.commit()

# ─── SESSIONS ───
async def set_session(user_id: int, state: str = None, sso_url: str = None):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM sessions WHERE user_id=?", (user_id,))
        if await cur.fetchone():
            await db.execute("UPDATE sessions SET state=?, sso_url=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (state, sso_url, user_id))
        else:
            await db.execute("INSERT INTO sessions (user_id, state, sso_url) VALUES (?, ?, ?)", (user_id, state, sso_url))
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
