# db.py

import os
import asyncpg
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

POOL: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    global POOL
    if POOL is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL not set")
        try:
            POOL = await asyncpg.create_pool(url, min_size=1, max_size=10)
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Postgres: {e}")
    return POOL

# SBC Tables Schema

SBC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sbc_sets (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT,
    repeatable_text TEXT,
    expires_at TIMESTAMPTZ,
    site_cost INTEGER,
    reward_summary TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sbc_challenges (
    id BIGSERIAL PRIMARY KEY,
    sbc_set_id BIGINT REFERENCES sbc_sets(id) ON DELETE CASCADE,
    name TEXT,
    site_cost INTEGER,
    reward_text TEXT,
    order_index INTEGER,
    UNIQUE (sbc_set_id, name)
);

CREATE TABLE IF NOT EXISTS sbc_requirements (
    id BIGSERIAL PRIMARY KEY,
    challenge_id BIGINT REFERENCES sbc_challenges(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    key TEXT,
    op TEXT,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_sets_active ON sbc_sets(is_active);
CREATE INDEX IF NOT EXISTS idx_sets_slug ON sbc_sets(slug);
CREATE INDEX IF NOT EXISTS idx_challenges_set ON sbc_challenges(sbc_set_id);
CREATE INDEX IF NOT EXISTS idx_requirements_challenge ON sbc_requirements(challenge_id);
"""

async def init_db():
    """Initialize database with SBC tables"""
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(SBC_SCHEMA_SQL)
    print("✅ SBC database schema initialized")

async def mark_all_inactive_before(ts: datetime):
    """Mark SBC sets as inactive before a given timestamp"""
    pool = await get_pool()
    async with pool.acquire() as con:
        count = await con.fetchval(
            "UPDATE sbc_sets SET is_active = FALSE WHERE last_seen_at < $1 RETURNING COUNT(*)",
            ts
        )
    print(f"📊 Marked {count} SBC sets as inactive")

# … keep the rest of your functions, just make sure all quotes are " not “ ” and docstrings are ''' or """
