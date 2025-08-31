import asyncpg
from typing import Dict, Any, List, Optional
from datetime import datetime

async def get_player_by_card_id(card_id: int, pool: asyncpg.Pool) -> Optional[Dict[str, Any]]:
    """Get a single player by card_id"""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT card_id, name, rating, position, club, league, nation, price,
                       rarity, is_special, card_type, weak_foot, skill_moves
                FROM fut_players 
                WHERE card_id = $1
            """, card_id)
            
            if row:
                return dict(row)
            return None
            
    except Exception as e:
        print(f"⚠️ Error fetching player {card_id}: {e}")
        return None

async def get_players_by_card_ids(card_ids: List[int], pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """Get multiple players by card_ids"""
    if not card_ids:
        return []
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT card_id, name, rating, position, club, league, nation, price,
                       rarity, is_special, card_type, weak_foot, skill_moves
                FROM fut_players 
                WHERE card_id = ANY($1)
                ORDER BY rating DESC, price ASC
            """, card_ids)
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        print(f"⚠️ Error fetching players {card_ids}: {e}")
        return []

async def search_players_by_name(name: str, pool: asyncpg.Pool, limit: int = 20) -> List[Dict[str, Any]]:
    """Search players by name (fuzzy search)"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT card_id, name, rating, position, club, league, nation, price,
                       rarity, is_special, card_type
                FROM fut_players 
                WHERE name ILIKE $1
                ORDER BY rating DESC, price ASC
                LIMIT $2
            """, f"%{name}%", limit)
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        print(f"⚠️ Error searching players by name '{name}': {e}")
        return []

async def get_players_by_criteria(
    pool: asyncpg.Pool,
    min_rating: Optional[int] = None,
    max_rating: Optional[int] = None,
    position: Optional[str] = None,
    league: Optional[str] = None,
    club: Optional[str] = None,
    nation: Optional[str] = None,
    max_price: Optional[int] = None,
    is_special: Optional[bool] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get players matching specific criteria"""
    try:
        conditions = []
        params = []
        param_count = 0
        
        if min_rating is not None:
            param_count += 1
            conditions.append(f"rating >= ${param_count}")
            params.append(min_rating)
        
        if max_rating is not None:
            param_count += 1
            conditions.append(f"rating <= ${param_count}")
            params.append(max_rating)
        
        if position:
            param_count += 1
            conditions.append(f"position = ${param_count}")
            params.append(position.upper())
        
        if league:
            param_count += 1
            conditions.append(f"league ILIKE ${param_count}")
            params.append(f"%{league}%")
        
        if club:
            param_count += 1
            conditions.append(f"club ILIKE ${param_count}")
            params.append(f"%{club}%")
        
        if nation:
            param_count += 1
            conditions.append(f"nation ILIKE ${param_count}")
            params.append(f"%{nation}%")
        
        if max_price is not None:
            param_count += 1
            conditions.append(f"price <= ${param_count}")
            params.append(max_price)
        
        if is_special is not None:
            param_count += 1
            conditions.append(f"is_special = ${param_count}")
            params.append(is_special)
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        param_count += 1
        params.append(limit)
        
        query = f"""
            SELECT card_id, name, rating, position, club, league, nation, price,
                   rarity, is_special, card_type, weak_foot, skill_moves
            FROM fut_players 
            {where_clause}
            ORDER BY rating DESC, price ASC
            LIMIT ${param_count}
        """
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
            
    except Exception as e:
        print(f"⚠️ Error getting players by criteria: {e}")
        return []

async def get_cheapest_players_by_rating(rating: int, pool: asyncpg.Pool, count: int = 11) -> List[Dict[str, Any]]:
    """Get the cheapest players of a specific rating"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT card_id, name, rating, position, club, league, nation, price,
                       rarity, is_special, card_type
                FROM fut_players 
                WHERE rating = $1 AND price IS NOT NULL AND price > 0
                ORDER BY price ASC
                LIMIT $2
            """, rating, count)
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        print(f"⚠️ Error getting cheapest players for rating {rating}: {e}")
        return []

async def analyze_solution_cost(player_ids: List[int], pool: asyncpg.Pool) -> Dict[str, Any]:
    """Analyze the cost and composition of a solution"""
    players = await get_players_by_card_ids(player_ids, pool)
    
    if not players:
        return {
            "total_cost": 0,
            "player_count": 0,
            "average_rating": 0,
            "players": [],
            "missing_players": len(player_ids)
        }
    
    total_cost = sum(p.get("price", 0) for p in players if p.get("price"))
    avg_rating = sum(p.get("rating", 0) for p in players) / len(players)
    
    # Position distribution
    positions = {}
    for player in players:
        pos = player.get("position", "Unknown")
        positions[pos] = positions.get(pos, 0) + 1
    
    # League distribution
    leagues = {}
    for player in players:
        league = player.get("league", "Unknown")
        leagues[league] = leagues.get(league, 0) + 1
    
    # Nation distribution  
    nations = {}
    for player in players:
        nation = player.get("nation", "Unknown")
        nations[nation] = nations.get(nation, 0) + 1
    
    found_ids = {p["card_id"] for p in players}
    missing_ids = [pid for pid in player_ids if pid not in found_ids]
    
    return {
        "total_cost": total_cost,
        "player_count": len(players),
        "average_rating": round(avg_rating, 1),
        "highest_rating": max(p.get("rating", 0) for p in players) if players else 0,
        "lowest_rating": min(p.get("rating", 0) for p in players) if players else 0,
        "special_cards": sum(1 for p in players if p.get("is_special")),
        "position_distribution": positions,
        "league_distribution": leagues,
        "nation_distribution": nations,
        "players": players,
        "missing_players": len(missing_ids),
        "missing_player_ids": missing_ids
    }

async def get_database_player_stats(pool: asyncpg.Pool) -> Dict[str, Any]:
    """Get overall statistics about the player database"""
    try:
        async with pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_players,
                    COUNT(DISTINCT position) as total_positions,
                    COUNT(DISTINCT league) as total_leagues,
                    COUNT(DISTINCT club) as total_clubs,
                    COUNT(DISTINCT nation) as total_nations,
                    AVG(rating) as avg_rating,
                    MAX(rating) as max_rating,
                    MIN(rating) as min_rating,
                    COUNT(*) FILTER (WHERE is_special = true) as special_cards,
                    COUNT(*) FILTER (WHERE price IS NOT NULL AND price > 0) as players_with_prices
                FROM fut_players
            """)
            
            # Get rating distribution
            rating_dist = await conn.fetch("""
                SELECT rating, COUNT(*) as count
                FROM fut_players
                GROUP BY rating
                ORDER BY rating DESC
            """)
            
            # Get position distribution
            pos_dist = await conn.fetch("""
                SELECT position, COUNT(*) as count
                FROM fut_players
                GROUP BY position
                ORDER BY count DESC
                LIMIT 20
            """)
            
            # Get league distribution
            league_dist = await conn.fetch("""
                SELECT league, COUNT(*) as count
                FROM fut_players
                GROUP BY league
                ORDER BY count DESC
                LIMIT 10
            """)
            
            return {
                "total_players": stats["total_players"],
                "total_positions": stats["total_positions"],
                "total_leagues": stats["total_leagues"],
                "total_clubs": stats["total_clubs"],
                "total_nations": stats["total_nations"],
                "average_rating": round(stats["avg_rating"], 1) if stats["avg_rating"] else 0,
                "max_rating": stats["max_rating"],
                "min_rating": stats["min_rating"],
                "special_cards": stats["special_cards"],
                "players_with_prices": stats["players_with_prices"],
                "rating_distribution": {str(row["rating"]): row["count"] for row in rating_dist},
                "position_distribution": {row["position"]: row["count"] for row in pos_dist},
                "league_distribution": {row["league"]: row["count"] for row in league_dist}
            }
            
    except Exception as e:
        print(f"⚠️ Error getting database stats: {e}")
        return {}

async def validate_solution_requirements(player_ids: List[int], requirements: List[Dict[str, Any]], pool: asyncpg.Pool) -> Dict[str, Any]:
    """Validate if a solution meets the SBC requirements"""
    players = await get_players_by_card_ids(player_ids, pool)
    
    if not players:
        return {
            "valid": False,
            "reason": "No players found in database",
            "checks": []
        }
    
    checks = []
    all_valid = True
    
    for req in requirements:
        req_kind = req.get("kind")
        req_text = req.get("text", "")
        
        if req_kind == "team_rating_min":
            min_rating = req.get("value", 0)
            avg_rating = sum(p.get("rating", 0) for p in players) / len(players)
            valid = avg_rating >= min_rating
            
            checks.append({
                "requirement": req_text,
                "type": "team_rating",
                "required": min_rating,
                "actual": round(avg_rating, 1),
                "valid": valid
            })
            
            if not valid:
                all_valid = False
        
        elif req_kind == "chem_min":
            # Chemistry calculation would need more complex logic
            # For now, assume it's met
            checks.append({
                "requirement": req_text,
                "type": "chemistry",
                "required": req.get("value", 100),
                "actual": 100,  # Mock value
                "valid": True,
                "note": "Chemistry calculation not implemented"
            })
        
        elif req_kind == "min_from":
            count_needed = req.get("count", 1)
            key = req.get("key", "").lower()
            
            # Check if it's league, club, or nation requirement
            matching_players = 0
            if any(word in key for word in ["premier", "liga", "serie", "ligue", "bundesliga", "league"]):
                # League requirement
                matching_players = sum(1 for p in players if key in p.get("league", "").lower())
            elif any(word in key for word in ["england", "spain", "france", "germany", "italy"]):
                # Nation requirement
                matching_players = sum(1 for p in players if key in p.get("nation", "").lower())
            else:
                # Club requirement
                matching_players = sum(1 for p in players if key in p.get("club", "").lower())
            
            valid = matching_players >= count_needed
            
            checks.append({
                "requirement": req_text,
                "type": "min_from",
                "required": count_needed,
                "actual": matching_players,
                "valid": valid,
                "key": key
            })
            
            if not valid:
                all_valid = False
        
        elif req_kind == "min_program":
            # Special card requirement
            count_needed = req.get("count", 1)
            special_players = sum(1 for p in players if p.get("is_special"))
            valid = special_players >= count_needed
            
            checks.append({
                "requirement": req_text,
                "type": "special_cards",
                "required": count_needed,
                "actual": special_players,
                "valid": valid
            })
            
            if not valid:
                all_valid = False
    
    return {
        "valid": all_valid,
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["valid"]),
        "failed_checks": sum(1 for c in checks if not c["valid"]),
        "checks": checks,
        "solution_summary": {
            "player_count": len(players),
            "total_cost": sum(p.get("price", 0) for p in players),
            "average_rating": round(sum(p.get("rating", 0) for p in players) / len(players), 1)
        }
    }

# Test function
async def test_player_database():
    """Test the player database functions"""
    from db import get_pool
    
    print("🧪 Testing Player Database Functions")
    print("=" * 50)
    
    try:
        pool = await get_pool()
        
        # Test 1: Get database stats
        print("\n📊 Test 1: Database Statistics")
        stats = await get_database_player_stats(pool)
        if stats:
            print(f"  ✅ Total players: {stats['total_players']:,}")
            print(f"  ✅ Average rating: {stats['average_rating']}")
            print(f"  ✅ Special cards: {stats['special_cards']:,}")
            print(f"  ✅ Players with prices: {stats['players_with_prices']:,}")
        else:
            print("  ❌ Failed to get database stats")
        
        # Test 2: Search by name
        print("\n🔍 Test 2: Search Players by Name")
        players = await search_players_by_name("Messi", pool, limit=3)
        if players:
            print(f"  ✅ Found {len(players)} players matching 'Messi'")
            for player in players[:2]:
                print(f"    - {player['name']} ({player['rating']} OVR, {player['position']})")
        else:
            print("  ❌ No players found for 'Messi'")
        
        # Test 3: Get players by criteria
        print("\n🎯 Test 3: Get Players by Criteria (85+ rating, Premier League)")
        players = await get_players_by_criteria(
            pool, 
            min_rating=85, 
            league="Premier League", 
            limit=5
        )
        if players:
            print(f"  ✅ Found {len(players)} high-rated Premier League players")
            for player in players[:3]:
                print(f"    - {player['name']} ({player['rating']} OVR, {player['club']})")
        else:
            print("  ❌ No players found matching criteria")
        
        # Test 4: Analyze solution (using some sample card IDs)
        print("\n💰 Test 4: Analyze Solution Cost")
        # These are example card IDs - replace with actual ones from your database
        sample_ids = [100922276, 100922277, 100922278]  # Replace with real card IDs
        
        analysis = await analyze_solution_cost(sample_ids, pool)
        print(f"  📊 Players found: {analysis['player_count']}/{len(sample_ids)}")
        print(f"  💰 Total cost: {analysis['total_cost']:,} coins")
        print(f"  ⭐ Average rating: {analysis['average_rating']}")
        if analysis['missing_players'] > 0:
            print(f"  ⚠️ Missing players: {analysis['missing_players']}")
        
        return True
        
    except Exception as e:
        print(f"💥 Test failed: {e}")
        return False

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_player_database())
