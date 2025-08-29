import os
import asyncpg
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

__all__ = [
    "get_pool",
    "init_db",
    "mark_all_inactive_before",
    "upsert_set",
    "discover_player_table",
    "get_players_for_solution",
    "get_database_stats",
]

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
    pool = await get_pool()
    async with pool.acquire() as con:
        await con.execute(SBC_SCHEMA_SQL)
    print("✅ SBC database schema initialized")

async def mark_all_inactive_before(ts: datetime):
    pool = await get_pool()
    async with pool.acquire() as con:
        count = await con.fetchval(
            """
            WITH updated AS (
                UPDATE sbc_sets
                SET is_active = FALSE
                WHERE last_seen_at < $1
                RETURNING 1
            )
            SELECT COUNT(*) FROM updated
            """,
            ts,
        )
    print(f"📊 Marked {count} SBC sets as inactive")

async def upsert_set(payload: Dict[str, Any]) -> int:
    """Insert or update an SBC set and, if present, its challenges."""
    pool = await get_pool()

    rewards_text = ", ".join(
        [r.get("label") or r.get("reward") or r.get("type", "") for r in payload.get("rewards", [])]
    ) or None
    now = datetime.now(timezone.utc)

    async with pool.acquire() as con:
        set_id = await con.fetchval(
            """
            INSERT INTO sbc_sets (
                slug, name, repeatable_text, expires_at, site_cost, reward_summary, last_seen_at, is_active
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
            ON CONFLICT (slug) DO UPDATE SET
              name = EXCLUDED.name,
              repeatable_text = EXCLUDED.repeatable_text,
              expires_at = EXCLUDED.expires_at,
              site_cost = EXCLUDED.site_cost,
              reward_summary = EXCLUDED.reward_summary,
              last_seen_at = EXCLUDED.last_seen_at,
              is_active = TRUE
            RETURNING id
            """,
            payload["slug"],
            payload.get("name"),
            payload.get("repeatable"),
            payload.get("expires_at"),
            payload.get("cost"),
            rewards_text,
            now,
        )

        incoming = payload.get("sub_challenges", []) or []

        if incoming:
            # Clear existing only if we have new to write
            await con.execute("DELETE FROM sbc_challenges WHERE sbc_set_id = $1", set_id)

            for idx, ch in enumerate(incoming):
                ch_id = await con.fetchval(
                    """
                    INSERT INTO sbc_challenges (sbc_set_id, name, site_cost, reward_text, order_index)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    set_id,
                    ch.get("name"),
                    ch.get("cost"),
                    ch.get("reward"),
                    idx,
                )

                for req in ch.get("requirements", []):
                    await con.execute(
                        "INSERT INTO sbc_requirements (challenge_id, kind, key, op, value) VALUES ($1, $2, $3, $4, $5)",
                        ch_id,
                        req.get("kind", "raw"),
                        req.get("key"),
                        req.get("op"),
                        str(req.get("value") if req.get("value") is not None else req.get("text")),
                    )
        else:
            # No challenges parsed this run; keep existing ones (only the set row updated)
            pass

    print(
        f"✅ Upserted SBC set: {payload.get('name')} (ID: {set_id}) with {len(incoming)} challenges"
    )
    return set_id

async def discover_player_table() -> Optional[str]:
    pool = await get_pool()
    async with pool.acquire() as con:
        tables = await con.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND (table_name ILIKE '%player%' OR table_name ILIKE '%card%' OR table_name ILIKE '%fut%')
            ORDER BY table_name
            """
        )
        for table in tables:
            table_name = table["table_name"]
            columns = await con.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                """,
                table_name,
            )
            column_names = [c["column_name"].lower() for c in columns]
            indicators = ["rating", "ovr", "overall", "position", "club", "league", "nation", "name"]
            matches = sum(1 for ind in indicators if any(ind in col for col in column_names))
            if matches >= 4:
                print(f"🎯 Found likely player table: {table_name}")
                return table_name
        print("⚠️ No player table found automatically")
        return None

async def get_players_for_solution(
    min_rating: int = 0,
    max_rating: int = 99,
    league: Optional[str] = None,
    club: Optional[str] = None,
    nation: Optional[str] = None,
    position: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    try:
        player_table = await discover_player_table()
        if not player_table:
            return []
        pool = await get_pool()
        async with pool.acquire() as con:
            cols = await con.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                """,
                player_table,
            )
            column_names = [c["column_name"] for c in cols]
            lower = [c.lower() for c in column_names]

            def pick(names, want):
                for i, c in enumerate(lower):
                    if any(w in c for w in want):
                        return column_names[i]
                return None

            rating_col = pick(lower, ["rating", "ovr", "overall"])
            name_col = pick(lower, ["name", "player_name"])
            position_col = pick(lower, ["position"])
            club_col = pick(lower, ["club", "team"])
            league_col = pick(lower, ["league"])
            nation_col = pick(lower, ["nation", "country"])
            price_col = pick(lower, ["price", "cost", "value"])

            select_cols = []
            if name_col: select_cols.append(f'"{name_col}" AS name')
            if rating_col: select_cols.append(f'"{rating_col}" AS rating')
            if position_col: select_cols.append(f'"{position_col}" AS position')
            if club_col: select_cols.append(f'"{club_col}" AS club')
            if league_col: select_cols.append(f'"{league_col}" AS league')
            if nation_col: select_cols.append(f'"{nation_col}" AS nation')
            if price_col: select_cols.append(f'"{price_col}" AS price')
            else: select_cols.append("1000 AS price")

            if not select_cols:
                return []

            where, params = [], []
            if rating_col and min_rating > 0:
                where.append(f'"{rating_col}" >= ${len(params)+1}'); params.append(min_rating)
            if rating_col and max_rating < 99:
                where.append(f'"{rating_col}" <= ${len(params)+1}'); params.append(max_rating)
            if league and league_col:
                where.append(f'"{league_col}" ILIKE ${len(params)+1}'); params.append(f"%{league}%")
            if club and club_col:
                where.append(f'"{club_col}" ILIKE ${len(params)+1}'); params.append(f"%{club}%")
            if nation and nation_col:
                where.append(f'"{nation_col}" ILIKE ${len(params)+1}'); params.append(f"%{nation}%")
            if position and position_col:
                where.append(f'"{position_col}" = ${len(params)+1}'); params.append(position.upper())

            where_clause = "WHERE " + " AND ".join(where) if where else ""
            order_by = f'ORDER BY "{price_col}"' if price_col else (f'ORDER BY "{rating_col}"' if rating_col else "")

            params.append(limit)
            query = f'''
                SELECT {", ".join(select_cols)}
                FROM "{player_table}"
                {where_clause}
                {order_by}
                LIMIT ${len(params)}
            '''
            rows = await con.fetch(query, *params)
            out: List[Dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d.setdefault("price", 1000)
                d.setdefault("rating", 75)
                d.setdefault("position", "CM")
                d.setdefault("name", "Unknown Player")
                d.setdefault("club", "Unknown Club")
                d.setdefault("league", "Unknown League")
                d.setdefault("nation", "Unknown Nation")
                out.append(d)
            return out
    except Exception as e:
        print(f"💥 Database player query failed: {e}")
        return []

async def get_database_stats() -> Dict[str, Any]:
    try:
        pool = await get_pool()
        async with pool.acquire() as con:
            sbc_stats = await con.fetchrow("""
                SELECT COUNT(*) AS total_sets,
                       COUNT(*) FILTER (WHERE is_active = TRUE) AS active_sets
                FROM sbc_sets
            """)
            challenge_count = await con.fetchval("""
                SELECT COUNT(*) FROM sbc_challenges c
                JOIN sbc_sets s ON c.sbc_set_id = s.id
                WHERE s.is_active = TRUE
            """)
            player_count = 0
            pt = await discover_player_table()
            if pt:
                player_count = await con.fetchval(f'SELECT COUNT(*) FROM "{pt}"')
            return {
                "sbc_sets": sbc_stats["total_sets"] if sbc_stats else 0,
                "active_sbc_sets": sbc_stats["active_sets"] if sbc_stats else 0,
                "sbc_challenges": challenge_count,
                "players_in_database": player_count,
                "player_table": pt,
            }
    except Exception as e:
        print(f"💥 Database stats query failed: {e}")
        return {"sbc_sets": 0, "active_sbc_sets": 0, "sbc_challenges": 0, "players_in_database": 0, "player_table": None, "error": str(e)}
