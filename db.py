import os
import asyncpg
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

POOL: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    global POOL
    if POOL is None:
        POOL = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=5)
    return POOL

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sbc_sets (
  id BIGSERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT,
  repeatable_text TEXT,
  refresh_text TEXT,
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
"""

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(SCHEMA_SQL)

async def mark_all_inactive_before(ts: datetime):
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(
            "UPDATE sbc_sets SET is_active = FALSE WHERE last_seen_at < $1",
            ts
        )

async def upsert_set(payload: Dict[str, Any]) -> int:
    """
    payload: {
      'slug','name','repeatable','expires_at','site_cost','rewards'(list text),
      'sub_challenges': [ { 'name','site_cost','reward','requirements':[ dicts ] } ]
    }
    """
    pool = await get_pool()
    rewards_text = ", ".join([r.get("label") or r.get("reward") or r.get("type","") for r in payload.get("rewards", [])]) or None
    now = datetime.now(timezone.utc)
    async with pool.acquire() as con:
        set_id = await con.fetchval(
            """
            INSERT INTO sbc_sets (slug,name,repeatable_text,expires_at,site_cost,reward_summary,last_seen_at,is_active)
            VALUES ($1,$2,$3,$4,$5,$6,$7,TRUE)
            ON CONFLICT (slug) DO UPDATE SET
              name=EXCLUDED.name,
              repeatable_text=EXCLUDED.repeatable_text,
              expires_at=EXCLUDED.expires_at,
              site_cost=EXCLUDED.site_cost,
              reward_summary=EXCLUDED.reward_summary,
              last_seen_at=EXCLUDED.last_seen_at,
              is_active=TRUE
            RETURNING id
            """,
            payload["slug"],
            payload.get("name"),
            payload.get("repeatable"),
            payload.get("expires_at"),
            payload.get("cost"),
            rewards_text,
            now
        )
        # challenges
        for idx, ch in enumerate(payload.get("sub_challenges", [])):
            ch_id = await con.fetchval(
                """
                INSERT INTO sbc_challenges (sbc_set_id,name,site_cost,reward_text,order_index)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (sbc_set_id,name) DO UPDATE SET
                  site_cost=EXCLUDED.site_cost,
                  reward_text=EXCLUDED.reward_text,
                  order_index=EXCLUDED.order_index
                RETURNING id
                """,
                set_id, ch.get("name"), ch.get("cost"), ch.get("reward"), idx
            )
            # replace requirements
            await con.execute("DELETE FROM sbc_requirements WHERE challenge_id=$1", ch_id)
            for req in ch.get("requirements", []):
                await con.execute(
                    "INSERT INTO sbc_requirements (challenge_id,kind,key,op,value) VALUES ($1,$2,$3,$4,$5)",
                    ch_id,
                    req.get("kind","raw"),
                    req.get("key"),
                    req.get("op"),
                    str(req.get("value") if req.get("value") is not None else req.get("text"))
                )
    return set_id
