# db.py
import os
import json
import asyncpg
from typing import Any, Dict, List, Optional

DATABASE_URL = os.getenv("DATABASE_URL")
_POOL: Optional[asyncpg.pool.Pool] = None

async def get_pool():
    global _POOL
    if _POOL is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _POOL = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _POOL

async def init_db():
    """
    Create/alter the sbc_sets table so required columns exist.
    Safe to call on every startup.
    """
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute("""
        CREATE TABLE IF NOT EXISTS sbc_sets (
            slug         text PRIMARY KEY,
            url          text,
            name         text,
            expires_at   timestamptz,
            repeatable   boolean DEFAULT false,
            rewards      jsonb    NOT NULL DEFAULT '[]'::jsonb,
            challenges   jsonb    NOT NULL DEFAULT '[]'::jsonb,
            active       boolean  NOT NULL DEFAULT true,
            updated_at   timestamptz NOT NULL DEFAULT now()
        );
        """)
        # Ensure columns exist (if upgrading from older schema)
        for col, ddl in [
            ("url",        "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS url text"),
            ("name",       "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS name text"),
            ("expires_at", "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS expires_at timestamptz"),
            ("repeatable", "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS repeatable boolean"),
            ("rewards",    "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS rewards jsonb"),
            ("challenges", "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS challenges jsonb"),
            ("active",     "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS active boolean"),
            ("updated_at", "ALTER TABLE sbc_sets ADD COLUMN IF NOT EXISTS updated_at timestamptz"),
        ]:
            await con.execute(ddl)

        # Ensure updated_at auto-updates
        await con.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS trigger AS $$
        BEGIN
          NEW.updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
        await con.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sbc_sets_updated_at'
          ) THEN
            CREATE TRIGGER trg_sbc_sets_updated_at
            BEFORE INSERT OR UPDATE ON sbc_sets
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
          END IF;
        END$$;
        """)

async def save_set(*, slug, url, name, expires_at, repeatable, rewards, challenges):
    if not slug:
        # Ignore rows without a stable slug
        return
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO sbc_sets
              (slug, url, name, expires_at, repeatable, rewards, challenges, active)
            VALUES ($1,  $2,  $3,   $4,         $5,        $6,      $7,         true)
            ON CONFLICT (slug) DO UPDATE SET
              url        = EXCLUDED.url,
              name       = EXCLUDED.name,
              expires_at = EXCLUDED.expires_at,
              repeatable = EXCLUDED.repeatable,
              rewards    = EXCLUDED.rewards,
              challenges = EXCLUDED.challenges,
              active     = true
            """,
            slug, url, name, expires_at, repeatable,
            json.dumps(rewards or []), json.dumps(challenges or []),
        )

async def mark_all_inactive_before(ts):
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(
            "UPDATE sbc_sets SET active=false WHERE updated_at < $1",
            ts,
        )

async def get_all_sets() -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT slug, url, name, expires_at, repeatable, rewards, challenges, active, updated_at
            FROM sbc_sets
            WHERE active = true
            ORDER BY COALESCE(expires_at, 'infinity') ASC, name ASC
            """
        )
        return [dict(r) for r in rows]

async def get_set_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT slug, url, name, expires_at, repeatable, rewards, challenges, active, updated_at
            FROM sbc_sets
            WHERE slug = $1
            """,
            slug,
        )
        return dict(row) if row else None
