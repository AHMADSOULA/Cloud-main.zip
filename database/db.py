import aiosqlite
import os
import datetime
from config import config

os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)

async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sso_url TEXT NOT NULL,
                status TEXT DEFAULT 'done',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def register_user(user_id: int, username: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users ORDER BY user_id")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

async def add_job(user_id: int, sso_url: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("INSERT INTO jobs (user_id, sso_url) VALUES (?, ?)", (user_id, sso_url))
        await db.commit()

async def count_jobs():
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM jobs")
        row = await cur.fetchone()
        return row[0] if row else 0
