import aiosqlite
from typing import Optional

DB_PATH = "bot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_premium INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                article INTEGER NOT NULL,
                name TEXT,
                target_price INTEGER,
                last_price INTEGER,
                wb_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, article)
            )
        """)
        await db.commit()


async def get_or_create_user(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            return dict(await cursor.fetchone())


async def count_user_items(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tracked_items WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]


async def add_item(user_id: int, article: int, name: str, price: Optional[int], wb_url: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO tracked_items (user_id, article, name, last_price, wb_url)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, article, name, price, wb_url),
            )
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def remove_item(user_id: int, article: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tracked_items WHERE user_id = ? AND article = ?",
            (user_id, article),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_user_items(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tracked_items WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_all_items() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tracked_items") as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def update_price(item_id: int, new_price: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracked_items SET last_price = ? WHERE id = ?",
            (new_price, item_id),
        )
        await db.commit()


async def set_premium(user_id: int, value: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, is_premium) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET is_premium = excluded.is_premium",
            (user_id, int(value)),
        )
        await db.commit()
