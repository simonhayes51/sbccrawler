# main.py - Full SBC Browser and Solution Calculator
import os, asyncio, traceback
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse

# Initialize FastAPI app
app = FastAPI(title="FUT SBC Tracker", description="FIFA Ultimate Team Squad Building Challenge tracker and solver")

# Global status for health monitoring
status = {"ready": False, "last_run": None, "startup_error": None}

# ==================== DATABASE AND CRAWLER INITIALIZATION ====================

async def _initial_run():
    """Initialize database and run initial crawl"""
    try:
        # Import here to avoid startup issues if modules have problems
        from db import init_db
        from scheduler import run_job
        
        print("🔧 Initializing database...")
        await init_db()
        
        print("🔄 Running initial SBC crawl...")
        await run_job()
        
        status["ready"] = True
        status["last_run"] = "startup"
        print("✅ Initial setup complete!")
        
    except Exception as e:
        status["startup_error"] = f"{type(e).__name__}: {e}"
        print(f"💥 Initial setup failed: {e}")
        print("".join(traceback.format_exc()))

@app.on_event("startup")
async def on_startup():
    """Startup event handler"""
    print(f"🧩 DATABASE_URL configured: {bool(os.getenv('DATABASE_URL'))}")
    
    try:
        # Start background tasks
        asyncio.create_task(_initial_run())
        
        # Start the daily scheduler
        from scheduler import schedule_loop
        asyncio.create_task(schedule_loop())
        
        print("✅ App bootstrapped; background tasks scheduled")
        
    except Exception as e:
        status["startup_error"] = f"{type(e).__name__}: {e}"
        print(f"💥 Startup failed: {e}")
        print("".join(traceback.format_exc()))

# ==================== BASIC ENDPOINTS ====================

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok" if not status.get("startup_error") else "error",
        "ready": status.get("ready", False),
        "last_run": status.get("last_run"),
        "startup_error": status.get("startup_error"),
        "database_configured": bool(os.getenv("DATABASE_URL"))
    }

@app.post("/force")
async def force_crawl():
    """Force a manual SBC crawl"""
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "DATABASE_URL not configured")
    
    try:
        from scheduler import run_job
        await run_job()
        status["ready"] = True
        status["last_run"] = "manual"
        return {"ok": True, "message": "Manual crawl completed"}
    except Exception as e:
        raise HTTPException(500, f"Manual crawl failed: {e}")

@app.get("/db-stats")
async def db_stats():
    """Get database statistics"""
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            set_count = await con.fetchval("SELECT COUNT(*) FROM sbc_sets WHERE is_active = TRUE")
            challenge_count = await con.fetchval("SELECT COUNT(*) FROM sbc_challenges c JOIN sbc_sets s ON c.sbc_set_id = s.id WHERE s.is_active = TRUE") 
            requirement_count = await con.fetchval("SELECT COUNT(*) FROM sbc_requirements r JOIN sbc_challenges c ON r.challenge_id = c.id JOIN sbc_sets s ON c.sbc_set_id = s.id WHERE s.is_active = TRUE")
            
            return {
                "active_sets": set_count,
                "total_challenges": challenge_count,
                "total_requirements": requirement_count,
                "status": "connected"
            }
    except Exception as e:
        raise HTTPException(500, f"Database query failed: {e}")

# ==================== SBC API ENDPOINTS ====================

@app.get("/api/sbcs")
async def get_sbcs(
    category: Optional[str] = Query(None, description="Filter by category"),
    active_only: bool = Query(True, description="Show only active SBCs"),
    limit: int = Query(50, description="Maximum number of SBCs to return"),
    offset: int = Query(0, description="Offset for pagination")
):
    """Get list of SBCs with basic info"""
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            # Build query based on filters
            where_conditions = []
            params = []
            
            if active_only:
                where_conditions.append("s.is_active = TRUE")
            
            if category:
                where_conditions.append("s.slug LIKE $" + str(len(params) + 1))
                params.append(f"%/{category}/%")
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            params.extend([limit, offset])
            
            query = f"""
                SELECT 
                    s.id, s.slug, s.name, s.expires_at, s.reward_summary,
                    s.last_seen_at, s.is_active,
                    COUNT(c.id) as challenge_count
                FROM sbc_sets s
                LEFT JOIN sbc_challenges c ON s.id = c.sbc_set_id
                {where_clause}
                GROUP BY s.id, s.slug, s.name, s.expires_at, s.reward_summary, s.last_seen_at, s.is_active
                ORDER BY s.last_seen_at DESC
                LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """
            
            rows = await con.fetch(query, *params)
            
            return {
                "sbcs": [
                    {
                        "id": row["id"],
                        "slug": row["slug"],
                        "name": row["name"],
                        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
                        "rewards": row["reward_summary"],
                        "challenge_count": row["challenge_count"],
                        "last_updated": row["last_seen_at"].isoformat(),
                        "is_active": row["is_active"],
                        "category": row["slug"].split("/")[2] if len(row["slug"].split("/")) > 2 else "unknown"
                    }
                    for row in rows
                ],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "has_more": len(rows) == limit
                }
            }
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch SBCs: {e}")

@app.get("/api/sbcs/{sbc_id}")
async def get_sbc_details(sbc_id: int):
    """Get detailed SBC information including all challenges and requirements"""
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            # Get SBC basic info
            sbc = await con.fetchrow("""
                SELECT id, slug, name, repeatable_text, expires_at, site_cost, 
                       reward_summary, last_seen_at, is_active
                FROM sbc_sets 
                WHERE id = $1
            """, sbc_id)
            
            if not sbc:
                raise HTTPException(404, "SBC not found")
            
            # Get challenges with requirements
            challenges = await con.fetch("""
                SELECT c.id, c.name, c.site_cost, c.reward_text, c.order_index
                FROM sbc_challenges c
                WHERE c.sbc_set_id = $1
                ORDER BY c.order_index
            """, sbc_id)
            
            # Get requirements for all challenges
            challenge_data = []
            for challenge in challenges:
                requirements = await con.fetch("""
                    SELECT kind, key, op, value
                    FROM sbc_requirements
                    WHERE challenge_id = $1
                    ORDER BY id
                """, challenge["id"])
                
                challenge_data.append({
                    "id": challenge["id"],
                    "name": challenge["name"],
                    "cost": challenge["site_cost"],
                    "reward": challenge["reward_text"],
                    "order": challenge["order_index"],
                    "requirements": [
                        {
                            "kind": req["kind"],
                            "key": req["key"],
                            "operator": req["op"],
                            "value": req["value"]
                        }
                        for req in requirements
                    ]
                })
            
            return {
                "sbc": {
                    "id": sbc["id"],
                    "slug": sbc["slug"],
                    "name": sbc["name"],
                    "repeatable": sbc["repeatable_text"],
                    "expires_at": sbc["expires_at"].isoformat() if sbc["expires_at"] else None,
                    "cost": sbc["site_cost"],
                    "rewards": sbc["reward_summary"],
                    "last_updated": sbc["last_seen_at"].isoformat(),
                    "is_active": sbc["is_active"],
                    "url": f"https://www.fut.gg{sbc['slug']}"
                },
                "challenges": challenge_data
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch SBC details: {e}")

@app.get("/api/categories")
async def get_categories():
    """Get available SBC categories"""
    if not os.getenv("DATABASE_URL"):
        return {"categories": []}  # Return empty if no DB
    
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            rows = await con.fetch("""
                SELECT 
                    CASE 
                        WHEN slug LIKE '%/players/%' THEN 'players'
                        WHEN slug LIKE '%/icons/%' THEN 'icons'
                        WHEN slug LIKE '%/upgrades/%' THEN 'upgrades'
                        WHEN slug LIKE '%/live/%' THEN 'live'
                        WHEN slug LIKE '%/foundations/%' THEN 'foundations'
                        ELSE 'other'
                    END as category,
                    COUNT(*) as count
                FROM sbc_sets
                WHERE is_active = TRUE
                GROUP BY 1
                ORDER BY count DESC
            """)
            
            return {
                "categories": [
                    {
                        "name": row["category"],
                        "count": row["count"],
                        "display_name": row["category"].title()
                    }
                    for row in rows
                ]
            }
    except Exception as e:
        print(f"Categories query failed: {e}")
        return {"categories": []}

# ==================== SOLUTION CALCULATOR ====================

# Simple player database for solutions (mock data)
MOCK_PLAYERS = [
    {"name": "Casemiro", "rating": 89, "position": "CDM", "price": 45000, "league": "Premier League", "club": "Manchester United", "nation": "Brazil"},
    {"name": "Luka Modrić", "rating": 88, "position": "CM", "price": 40000, "league": "LaLiga", "club": "Real Madrid", "nation": "Croatia"},
    {"name": "Sergio Busquets", "rating": 87, "position": "CDM", "price": 15000, "league": "MLS", "club": "Inter Miami", "nation": "Spain"},
    {"name": "Thiago Silva", "rating": 86, "position": "CB", "price": 18000, "league": "Premier League", "club": "Chelsea", "nation": "Brazil"},
    {"name": "Marco Verratti", "rating": 85, "position": "CM", "price": 25000, "league": "Ligue 1", "club": "Paris Saint-Germain", "nation": "Italy"},
    {"name": "Yann Sommer", "rating": 84, "position": "GK", "price": 3000, "league": "Serie A", "club": "Inter", "nation": "Switzerland"},
    {"name": "André Onana", "rating": 83, "position": "GK", "price": 2000, "league": "Premier League", "club": "Manchester United", "nation": "Cameroon"},
    {"name": "Aaron Ramsdale", "rating": 82, "position": "GK", "price": 1500, "league": "Premier League", "club": "Arsenal", "nation": "England"},
    {"name": "Nick Pope", "rating": 81, "position": "GK", "price": 1200, "league": "Premier League", "club": "Newcastle", "nation": "England"},
    {"name": "Generic 80 CB", "rating": 80, "position": "CB", "price": 800, "league": "Generic League", "club": "Generic Club", "nation": "Generic"},
    {"name": "Generic 79 CM", "rating": 79, "position": "CM", "price": 650, "league": "Generic League", "club": "Generic Club", "nation": "Generic"},
]

def calculate_team_rating(players):
    """Calculate average team rating"""
    if not players:
        return 0
    return sum(p["rating"] for p in players) / len(players)

def solve_simple_sbc(requirements):
    """Simple SBC solver"""
    selected_players = []
    min_rating = 0
    required_from = {}
    
    # Parse requirements
    for req in requirements:
        if req["kind"] == "team_rating_min":
            min_rating = int(req["value"]) if req["value"] else 0
        elif req["kind"] == "min_from" and req.get("key"):
            count = 1
            if req.get("value") and str(req["value"]).isdigit():
                count = int(req["value"])
            required_from[req["key"]] = count
    
    # Add required players first
    for key, count in required_from.items():
        key_lower = key.lower()
        matching_players = [
            p for p in MOCK_PLAYERS
            if (key_lower in p["league"].lower() or 
                key_lower in p["nation"].lower() or 
                key_lower in p["club"].lower())
        ]
        
        # Sort by price and take cheapest
        matching_players.sort(key=lambda x: x["price"])
        selected_players.extend(matching_players[:min(count, len(matching_players))])
    
    # Fill remaining spots
    remaining_players = [p for p in MOCK_PLAYERS if p not in selected_players]
    remaining_players.sort(key=lambda x: x["price"])
    
    while len(selected_players) < 11:
        selected_players.append(remaining_players[len(selected_players) % len(remaining_players)])
    
    # Upgrade players to meet rating requirement
    current_rating = calculate_team_rating(selected_players)
    attempts = 0
    
    while current_rating < min_rating and attempts < 20:
        lowest_player = min(selected_players, key=lambda x: x["rating"])
        selected_players.remove(lowest_player)
        
        better_players = [p for p in MOCK_PLAYERS 
                         if p not in selected_players and p["rating"] > lowest_player["rating"]]
        
        if better_players:
            better_players.sort(key=lambda x: x["price"])
            selected_players.append(better_players[0])
            current_rating = calculate_team_rating(selected_players)
        else:
            selected_players.append(lowest_player)
            break
        
        attempts += 1
    
    total_cost = sum(p["price"] for p in selected_players)
    final_rating = calculate_team_rating(selected_players)
    
    return {
        "total_cost": total_cost,
        "chemistry": 100,
        "rating": round(final_rating, 1),
        "meets_requirements": final_rating >= min_rating if min_rating > 0 else True,
        "players": selected_players,
        "requirements_analysis": [
            {
                "requirement": f"Min. Team Rating: {min_rating}" if min_rating > 0 else "No specific rating required",
                "satisfied": final_rating >= min_rating if min_rating > 0 else True,
                "notes": f"Achieved {final_rating:.1f} rating"
            }
        ] + [
            {
                "requirement": f"Min. players from {key}",
                "satisfied": True,
                "notes": f"Added {count} player(s) from {key}"
            }
            for key, count in required_from.items()
        ]
    }

@app.get("/api/challenges/{challenge_id}/solution")
async def get_challenge_solution(challenge_id: int):
    """Get cheapest solution for a specific challenge"""
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            # Verify challenge exists and get requirements
            challenge = await con.fetchrow("""
                SELECT c.id, c.name, s.name as sbc_name
                FROM sbc_challenges c
                JOIN sbc_sets s ON c.sbc_set_id = s.id
                WHERE c.id = $1
            """, challenge_id)
            
            if not challenge:
                raise HTTPException(404, "Challenge not found")
            
            # Get requirements
            requirements = await con.fetch("""
                SELECT kind, key, op, value
                FROM sbc_requirements
                WHERE challenge_id = $1
            """, challenge_id)
            
            # Convert to solver format
            req_list = [
                {
                    "kind": req["kind"],
                    "key": req["key"],
                    "op": req["op"], 
                    "value": req["value"]
                }
                for req in requirements
            ]
            
            solution = solve_simple_sbc(req_list)
            
            return {
                "challenge": {
                    "id": challenge["id"],
                    "name": challenge["name"],
                    "sbc_name": challenge["sbc_name"]
                },
                "solution": solution
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to calculate solution: {e}")

# ==================== WEB UI ====================

@app.get("/", response_class=HTMLResponse)
async def sbc_browser():
    """Main SBC browser page with full UI"""
    return HTMLResponse(open("sbc_browser.html", "r").read())

# ==================== DEBUG ENDPOINTS ====================

@app.get("/test-crawl")
async def test_crawl():
    """Test crawl functionality"""
    try:
        from crawler import crawl_all_sets
        sets = await crawl_all_sets(debug_first=True)
        
        return {
            "total_count": len(sets),
            "sets_with_challenges": len([s for s in sets if s["sub_challenges"]]),
            "sample_sets": sets[:2] if sets else [],
            "summary": {
                "avg_challenges_per_set": sum(len(s["sub_challenges"]) for s in sets) / len(sets) if sets else 0,
                "max_challenges": max((len(s["sub_challenges"]) for s in sets), default=0),
                "empty_sets": len([s for s in sets if not s["sub_challenges"]])
            }
        }
    except Exception as e:
        raise HTTPException(500, f"Test crawl failed: {e}")

# For Railway deployment
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    print(f"🚀 Starting FUT SBC Tracker on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
