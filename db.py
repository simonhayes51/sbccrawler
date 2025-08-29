# db.py
import asyncpg
import os
import json

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None

async def get_pool():
    global _pool
    if not _pool:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool

async def save_set(slug, url, name, expires_at, repeatable, rewards, challenges):
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO sbc_sets (slug, url, name, expires_at, repeatable, rewards, challenges, active)
            VALUES ($1,$2,$3,$4,$5,$6,$7,true)
            ON CONFLICT (slug) DO UPDATE SET
                url=EXCLUDED.url,
                name=EXCLUDED.name,
                expires_at=EXCLUDED.expires_at,
                repeatable=EXCLUDED.repeatable,
                rewards=EXCLUDED.rewards,
                challenges=EXCLUDED.challenges,
                active=true
            """,
            slug, url, name, expires_at, repeatable,
            json.dumps(rewards), json.dumps(challenges)
        )

async def mark_all_inactive_before(timestamp):
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(
            "UPDATE sbc_sets SET active=false WHERE updated_at < $1",
            timestamp,
        )

async def get_all_sets():
    pool = await get_pool()
    async with pool.acquire() as con:
        rows = await con.fetch("SELECT * FROM sbc_sets WHERE active=true ORDER BY name")
        return [dict(r) for r in rows]
