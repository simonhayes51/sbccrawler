# db.py

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


# ------------------------- Connection Pool -------------------------

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


# ------------------------- Schema -------------------------

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
        # We need a CTE to count rows affected by UPDATE
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


# ------------------------- Upsert Set + Challenges -------------------------

async def upsert_set(payload: Dict[str, Any]) -> int:
    """Insert or update an SBC set and its challenges"""
    pool = await get_pool()

    rewards_text = ", ".join(
        [r.get("label") or r.get("reward") or r.get("type", "") for r in payload.get("rewards", [])]
    ) or None
    now = datetime.now(timezone.utc)

    async with pool.acquire() as con:
        # Upsert the main SBC set
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

        # Delete existing challenges for this set (clean slate)
        await con.execute("DELETE FROM sbc_challenges WHERE sbc_set_id = $1", set_id)

        # Insert challenges and requirements
        for idx, ch in enumerate(payload.get("sub_challenges", [])):
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

    print(
        f"✅ Upserted SBC set: {payload.get('name')} (ID: {set_id}) with {len(payload.get('sub_challenges', []))} challenges"
    )
    return set_id


# ------------------------- Player Table Discovery + Queries -------------------------

async def discover_player_table() -> Optional[str]:
    """Discover the player table name by heuristics on column names"""
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

            player_indicators = [
                "rating",
                "ovr",
                "overall",
                "position",
                "club",
                "league",
                "nation",
                "name",
            ]
            matches = sum(
                1 for indicator in player_indicators if any(indicator in col for col in column_names)
            )

            if matches >= 4:
                print(f"🎯 Found likely player table: {table_name}")

                detailed_columns = await con.fetch(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = $1
                    ORDER BY ordinal_position
                    """,
                    table_name,
                )
                print(f"  Columns: {', '.join([col['column_name'] for col in detailed_columns])}")

                sample = await con.fetchrow(f'SELECT * FROM "{table_name}" LIMIT 1')
                if sample:
                    print(f"  Sample: {dict(sample)}")

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
    """Get players from the database for building solutions"""
    try:
        player_table = await discover_player_table()
        if not player_table:
            print("⚠️ No player table found, returning empty result")
            return []

        pool = await get_pool()
        async with pool.acquire() as con:
            columns = await con.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                """,
                player_table,
            )
            column_names = [c["column_name"] for c in columns]
            lower_cols = [c.lower() for c in column_names]

            # Map common variations
            rating_col = None
            name_col = None
            position_col = None
            club_col = None
            league_col = None
            nation_col = None
            price_col = None

            for idx, col in enumerate(lower_cols):
                orig = column_names[idx]  # preserve case
                if rating_col is None and any(x in col for x in ["rating", "ovr", "overall"]):
                    rating_col = orig
                elif name_col is None and any(x in col for x in ["name", "player_name"]):
                    name_col = orig
                elif position_col is None and "position" in col:
                    position_col = orig
                elif club_col is None and any(x in col for x in ["club", "team"]):
                    club_col = orig
                elif league_col is None and "league" in col:
                    league_col = orig
                elif nation_col is None and any(x in col for x in ["nation", "country"]):
                    nation_col = orig
                elif price_col is None and any(x in col for x in ["price", "cost", "value"]):
                    price_col = orig

            select_cols: List[str] = []
            if name_col:
                select_cols.append(f'"{name_col}" AS name')
            if rating_col:
                select_cols.append(f'"{rating_col}" AS rating')
            if position_col:
                select_cols.append(f'"{position_col}" AS position')
            if club_col:
                select_cols.append(f'"{club_col}" AS club')
            if league_col:
                select_cols.append(f'"{league_col}" AS league')
            if nation_col:
                select_cols.append(f'"{nation_col}" AS nation')
            if price_col:
                select_cols.append(f'"{price_col}" AS price')
            else:
                select_cols.append("1000 AS price")

            if not select_cols:
                print("⚠️ No recognizable player columns found")
                return []

            where_conditions: List[str] = []
            params: List[Any] = []

            if rating_col and min_rating > 0:
                where_conditions.append(f'"{rating_col}" >= ${len(params) + 1}')
                params.append(min_rating)

            if rating_col and max_rating < 99:
                where_conditions.append(f'"{rating_col}" <= ${len(params) + 1}')
                params.append(max_rating)

            if league and league_col:
                where_conditions.append(f'"{league_col}" ILIKE ${len(params) + 1}')
                params.append(f"%{league}%")

            if club and club_col:
                where_conditions.append(f'"{club_col}" ILIKE ${len(params) + 1}')
                params.append(f"%{club}%")

            if nation and nation_col:
                where_conditions.append(f'"{nation_col}" ILIKE ${len(params) + 1}')
                params.append(f"%{nation}%")

            if position and position_col:
                where_conditions.append(f'"{position_col}" = ${len(params) + 1}')
                params.append(position.upper())

            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

            order_by = ""
            if price_col:
                order_by = f'ORDER BY "{price_col}"'
            elif rating_col:
                order_by = f'ORDER BY "{rating_col}"'

            params.append(limit)

            query = f'''
                SELECT {", ".join(select_cols)}
                FROM "{player_table}"
                {where_clause}
                {order_by}
                LIMIT ${len(params)}
            '''

            print(f"🔍 Query: {query}")
            print(f"📊 Parameters: {params}")

            rows = await con.fetch(query, *params)

            players: List[Dict[str, Any]] = []
            for row in rows:
                player = dict(row)
                player.setdefault("price", 1000)
                player.setdefault("rating", 75)
                player.setdefault("position", "CM")
                player.setdefault("name", "Unknown Player")
                player.setdefault("club", "Unknown Club")
                player.setdefault("league", "Unknown League")
                player.setdefault("nation", "Unknown Nation")
                players.append(player)

            print(f"✅ Found {len(players)} players matching criteria")
            return players

    except Exception as e:
        print(f"💥 Database player query failed: {e}")
        return []


# ------------------------- DB Stats -------------------------

async def get_database_stats() -> Dict[str, Any]:
    """Get comprehensive database statistics"""
    try:
        pool = await get_pool()
        async with pool.acquire() as con:
            sbc_stats = await con.fetchrow(
                """
                SELECT
                  COUNT(*) AS total_sets,
                  COUNT(*) FILTER (WHERE is_active = TRUE) AS active_sets
                FROM sbc_sets
                """
            )

            challenge_count = await con.fetchval(
                """
                SELECT COUNT(*)
                FROM sbc_challenges c
                JOIN sbc_sets s ON c.sbc_set_id = s.id
                WHERE s.is_active = TRUE
                """
            )

            player_table = await discover_player_table()
            player_count = 0
            if player_table:
                player_count = await con.fetchval(f'SELECT COUNT(*) FROM "{player_table}"')

            return {
                "sbc_sets": sbc_stats["total_sets"] if sbc_stats else 0,
                "active_sbc_sets": sbc_stats["active_sets"] if sbc_stats else 0,
                "sbc_challenges": challenge_count,
                "players_in_database": player_count,
                "player_table": player_table,
            }
    except Exception as e:
        print(f"💥 Database stats query failed: {e}")
        return {
            "sbc_sets": 0,
            "active_sbc_sets": 0,
            "sbc_challenges": 0,
            "players_in_database": 0,
            "player_table": None,
            "error": str(e),
        }
