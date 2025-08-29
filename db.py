# db.py

import os
import asyncpg
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

POOL: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
global POOL
if POOL is None:
url = os.getenv(“DATABASE_URL”)
if not url:
raise RuntimeError(“DATABASE_URL not set”)
try:
POOL = await asyncpg.create_pool(url, min_size=1, max_size=10)
except Exception as e:
raise RuntimeError(f”Failed to connect to Postgres: {e}”)
return POOL

# SBC Tables Schema

SBC_SCHEMA_SQL = “””
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
“””

async def init_db():
“”“Initialize database with SBC tables”””
pool = await get_pool()
async with pool.acquire() as con:
await con.execute(SBC_SCHEMA_SQL)
print(“✅ SBC database schema initialized”)

async def mark_all_inactive_before(ts: datetime):
“”“Mark SBC sets as inactive before a given timestamp”””
pool = await get_pool()
async with pool.acquire() as con:
count = await con.fetchval(
“UPDATE sbc_sets SET is_active = FALSE WHERE last_seen_at < $1 RETURNING COUNT(*)”,
ts
)
print(f”📊 Marked {count} SBC sets as inactive”)

async def upsert_set(payload: Dict[str, Any]) -> int:
“”“Insert or update an SBC set and its challenges”””
pool = await get_pool()
rewards_text = “, “.join([r.get(“label”) or r.get(“reward”) or r.get(“type”,””) for r in payload.get(“rewards”, [])]) or None
now = datetime.now(timezone.utc)

```
async with pool.acquire() as con:
    # Upsert the main SBC set
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
    
    # Delete existing challenges for this set to avoid orphaned data
    await con.execute("DELETE FROM sbc_challenges WHERE sbc_set_id = $1", set_id)
    
    # Insert challenges and requirements
    for idx, ch in enumerate(payload.get("sub_challenges", [])):
        ch_id = await con.fetchval(
            """
            INSERT INTO sbc_challenges (sbc_set_id,name,site_cost,reward_text,order_index)
            VALUES ($1,$2,$3,$4,$5)
            RETURNING id
            """,
            set_id, ch.get("name"), ch.get("cost"), ch.get("reward"), idx
        )
        
        # Insert requirements for this challenge
        for req in ch.get("requirements", []):
            await con.execute(
                "INSERT INTO sbc_requirements (challenge_id,kind,key,op,value) VALUES ($1,$2,$3,$4,$5)",
                ch_id,
                req.get("kind","raw"),
                req.get("key"),
                req.get("op"),
                str(req.get("value") if req.get("value") is not None else req.get("text"))
            )

print(f"✅ Upserted SBC set: {payload.get('name')} (ID: {set_id}) with {len(payload.get('sub_challenges', []))} challenges")
return set_id
```

# ==================== PLAYER DATABASE QUERIES ====================

async def discover_player_table() -> str:
“”“Discover the player table name and structure”””
pool = await get_pool()
async with pool.acquire() as con:
# Look for tables that might contain player data
tables = await con.fetch(”””
SELECT table_name
FROM information_schema.tables
WHERE table_schema = ‘public’
AND (table_name ILIKE ‘%player%’ OR table_name ILIKE ‘%card%’ OR table_name ILIKE ‘%fut%’)
ORDER BY table_name
“””)

```
    for table in tables:
        table_name = table['table_name']
        
        # Check if this table has player-like columns
        columns = await con.fetch("""
            SELECT column_name 
            FROM information_schema.columns
            WHERE table_name = $1
        """, table_name)
        
        column_names = [col['column_name'].lower() for col in columns]
        
        # Look for typical player data columns
        player_indicators = ['rating', 'ovr', 'overall', 'position', 'club', 'league', 'nation', 'name']
        matches = sum(1 for indicator in player_indicators if any(indicator in col for col in column_names))
        
        if matches >= 4:  # If it has at least 4 player-like columns
            print(f"🎯 Found likely player table: {table_name}")
            
            # Show column structure
            detailed_columns = await con.fetch("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = $1
                ORDER BY ordinal_position
            """, table_name)
            
            print(f"  Columns: {', '.join([col['column_name'] for col in detailed_columns])}")
            
            # Show sample data
            sample = await con.fetchrow(f"SELECT * FROM {table_name} LIMIT 1")
            if sample:
                print(f"  Sample: {dict(sample)}")
            
            return table_name
    
    print("⚠️ No player table found automatically")
    return None
```

async def get_players_for_solution(
min_rating: int = 0,
max_rating: int = 99,
league: str = None,
club: str = None,
nation: str = None,
position: str = None,
limit: int = 100
) -> List[Dict[str, Any]]:
“”“Get players from the database for building solutions”””

```
try:
    # Discover player table if not known
    player_table = await discover_player_table()
    if not player_table:
        print("⚠️ No player table found, using mock data")
        return []
    
    pool = await get_pool()
    async with pool.acquire() as con:
        # Build dynamic query based on available columns
        columns = await con.fetch("""
            SELECT column_name 
            FROM information_schema.columns
            WHERE table_name = $1
        """, player_table)
        
        column_names = [col['column_name'].lower() for col in columns]
        
        # Map common column variations
        rating_col = None
        name_col = None
        position_col = None
        club_col = None
        league_col = None
        nation_col = None
        price_col = None
        
        for col in column_names:
            if any(x in col for x in ['rating', 'ovr', 'overall']):
                rating_col = col
            elif any(x in col for x in ['name', 'player_name']):
                name_col = col
            elif 'position' in col:
                position_col = col
            elif any(x in col for x in ['club', 'team']):
                club_col = col
            elif 'league' in col:
                league_col = col
            elif any(x in col for x in ['nation', 'country']):
                nation_col = col
            elif any(x in col for x in ['price', 'cost', 'value']):
                price_col = col
        
        # Build SELECT clause
        select_cols = []
        if name_col: select_cols.append(f"{name_col} as name")
        if rating_col: select_cols.append(f"{rating_col} as rating")
        if position_col: select_cols.append(f"{position_col} as position")
        if club_col: select_cols.append(f"{club_col} as club")
        if league_col: select_cols.append(f"{league_col} as league")
        if nation_col: select_cols.append(f"{nation_col} as nation")
        if price_col: select_cols.append(f"{price_col} as price")
        else: select_cols.append("1000 as price")  # Default price if no price column
        
        if not select_cols:
            print("⚠️ No recognizable player columns found")
            return []
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        if rating_col and min_rating > 0:
            where_conditions.append(f"{rating_col} >= ${len(params) + 1}")
            params.append(min_rating)
        
        if rating_col and max_rating < 99:
            where_conditions.append(f"{rating_col} <= ${len(params) + 1}")
            params.append(max_rating)
        
        if league and league_col:
            where_conditions.append(f"{league_col} ILIKE ${len(params) + 1}")
            params.append(f"%{league}%")
        
        if club and club_col:
            where_conditions.append(f"{club_col} ILIKE ${len(params) + 1}")
            params.append(f"%{club}%")
        
        if nation and nation_col:
            where_conditions.append(f"{nation_col} ILIKE ${len(params) + 1}")
            params.append(f"%{nation}%")
        
        if position and position_col:
            where_conditions.append(f"{position_col} = ${len(params) + 1}")
            params.append(position.upper())
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Add ORDER BY price if available, otherwise by rating
        order_col = price_col if price_col else rating_col
        order_by = f"ORDER BY {order_col}" if order_col else ""
        
        params.append(limit)
        
        query = f"""
            SELECT {', '.join(select_cols)}
            FROM {player_table}
            {where_clause}
            {order_by}
            LIMIT ${len(params)}
        """
        
        print(f"🔍 Query: {query}")
        print(f"📊 Parameters: {params}")
        
        rows = await con.fetch(query, *params)
        
        players = []
        for row in rows:
            player = dict(row)
            # Ensure all required fields exist
            player.setdefault('price', 1000)
            player.setdefault('rating', 75)
            player.setdefault('position', 'CM')
            player.setdefault('name', 'Unknown Player')
            player.setdefault('club', 'Unknown Club')
            player.setdefault('league', 'Unknown League')
            player.setdefault('nation', 'Unknown Nation')
            players.append(player)
        
        print(f"✅ Found {len(players)} players matching criteria")
        return players
        
except Exception as e:
    print(f"💥 Database player query failed: {e}")
    return []
```

async def get_database_stats():
“”“Get comprehensive database statistics”””
try:
pool = await get_pool()
async with pool.acquire() as con:
# Get SBC stats
sbc_stats = await con.fetchrow(”””
SELECT
COUNT(*) as total_sets,
COUNT(*) FILTER (WHERE is_active = TRUE) as active_sets
FROM sbc_sets
“””)

```
        challenge_count = await con.fetchval("""
            SELECT COUNT(*) 
            FROM sbc_challenges c 
            JOIN sbc_sets s ON c.sbc_set_id = s.id 
            WHERE s.is_active = TRUE
        """)
        
        # Try to get player stats from discovered table
        player_table = await discover_player_table()
        player_count = 0
        if player_table:
            player_count = await con.fetchval(f"SELECT COUNT(*) FROM {player_table}")
        
        return {
            "sbc_sets": sbc_stats['total_sets'] if sbc_stats else 0,
            "active_sbc_sets": sbc_stats['active_sets'] if sbc_stats else 0,
            "sbc_challenges": challenge_count,
            "players_in_database": player_count,
            "player_table": player_table
        }
except Exception as e:
    print(f"💥 Database stats query failed: {e}")
    return {
        "sbc_sets": 0,
        "active_sbc_sets": 0,
        "sbc_challenges": 0,
        "players_in_database": 0,
        "player_table": None,
        "error": str(e)
    }
```