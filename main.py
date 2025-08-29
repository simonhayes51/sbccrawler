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
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FUT SBC Browser</title>
    <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
    <script src="https://unpkg.com/axios/dist/axios.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        
        /* Header */
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
            text-align: center;
        }
        .header h1 { 
            color: #2c3e50; 
            margin-bottom: 10px;
            font-size: 2.5em;
            font-weight: 700;
        }
        .header p { color: #7f8c8d; font-size: 1.1em; }
        
        /* Filters */
        .filters {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
        }
        .filter-group {
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .filter-group label {
            font-weight: 600;
            color: #34495e;
            font-size: 0.9em;
        }
        select, input {
            padding: 8px 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s ease;
        }
        select:focus, input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        /* SBC Grid */
        .sbc-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        /* SBC Card */
        .sbc-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            cursor: pointer;
            position: relative;
            overflow: hidden;
        }
        .sbc-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(31, 38, 135, 0.5);
        }
        .sbc-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #667eea, #764ba2);
        }
        
        .sbc-title {
            font-size: 1.2em;
            font-weight: 700;
            color: #2c3e50;
            margin-bottom: 10px;
            line-height: 1.4;
        }
        
        .sbc-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            font-size: 0.9em;
            color: #7f8c8d;
        }
        
        .sbc-category {
            background: #667eea;
            color: white;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.8em;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .sbc-stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 15px;
        }
        .stat-item {
            text-align: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .stat-value {
            font-size: 1.2em;
            font-weight: 700;
            color: #2c3e50;
        }
        .stat-label {
            font-size: 0.8em;
            color: #7f8c8d;
            text-transform: uppercase;
            font-weight: 600;
        }
        
        .sbc-rewards {
            background: #e8f5e8;
            border-left: 4px solid #27ae60;
            padding: 10px;
            border-radius: 0 8px 8px 0;
            font-size: 0.9em;
            color: #27ae60;
            font-weight: 600;
        }
        
        /* Challenge Modal */
        .modal {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            padding: 20px;
        }
        .modal-content {
            background: white;
            border-radius: 15px;
            max-width: 900px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            position: relative;
        }
        .modal-header {
            padding: 25px;
            border-bottom: 1px solid #e0e0e0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-title {
            font-size: 1.5em;
            font-weight: 700;
            color: #2c3e50;
        }
        .close-btn {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #7f8c8d;
            padding: 5px;
        }
        .close-btn:hover { color: #e74c3c; }
        
        .modal-body { padding: 25px; }
        
        /* Challenge Cards */
        .challenge-list {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .challenge-card {
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            padding: 20px;
            transition: border-color 0.3s ease;
        }
        .challenge-card:hover {
            border-color: #667eea;
        }
        .challenge-name {
            font-size: 1.1em;
            font-weight: 700;
            color: #2c3e50;
            margin-bottom: 15px;
        }
        
        .requirements {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-bottom: 15px;
        }
        .requirement {
            padding: 8px 12px;
            background: #f8f9fa;
            border-radius: 6px;
            font-size: 0.9em;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .requirement-type {
            font-weight: 600;
            color: #667eea;
        }
        
        .solution-section {
            margin-top: 20px;
            padding: 15px;
            background: linear-gradient(135deg, #f8f9fa, #e9ecef);
            border-radius: 10px;
        }
        .solution-btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: transform 0.2s ease;
        }
        .solution-btn:hover { transform: translateY(-2px); }
        .solution-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        /* Loading States */
        .loading {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }
        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #e0e0e0;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        /* Status Messages */
        .status-message {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            color: #856404;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        
        .error-message {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        
        /* Button styles */
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: transform 0.2s ease;
        }
        .btn-primary {
            background: #667eea;
            color: white;
        }
        .btn:hover { transform: translateY(-2px); }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .container { padding: 15px; }
            .sbc-grid { grid-template-columns: 1fr; }
            .filters { flex-direction: column; align-items: stretch; }
            .filter-group { flex-direction: row; align-items: center; gap: 10px; }
            .modal-content { margin: 10px; }
        }
    </style>
</head>
<body>
    <div id="app">
        <div class="container">
            <!-- Header -->
            <div class="header">
                <h1>⚽ FUT SBC Browser</h1>
                <p>Find the cheapest solutions for FIFA Ultimate Team Squad Building Challenges</p>
            </div>
            
            <!-- Status Messages -->
            <div v-if="!dbReady && !loading" class="status-message">
                <strong>⚠️ Database is initializing...</strong> SBC data may not be available yet. 
                <button @click="checkStatus" class="btn btn-primary" style="margin-left: 10px; padding: 5px 10px;">
                    Refresh Status
                </button>
            </div>
            
            <div v-if="error" class="error-message">
                <strong>❌ Error:</strong> {{ error }}
            </div>
            
            <!-- Filters -->
            <div class="filters">
                <div class="filter-group">
                    <label>Category:</label>
                    <select v-model="selectedCategory" @change="loadSbcs">
                        <option value="">All Categories</option>
                        <option v-for="cat in categories" :key="cat.name" :value="cat.name">
                            {{ cat.display_name }} ({{ cat.count }})
                        </option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Search:</label>
                    <input 
                        type="text" 
                        v-model="searchQuery" 
                        placeholder="Search SBCs..."
                        @input="debounceSearch"
                    >
                </div>
                <div class="filter-group">
                    <label>
                        <input type="checkbox" v-model="activeOnly" @change="loadSbcs"> 
                        Active Only
                    </label>
                </div>
            </div>
            
            <!-- Loading State -->
            <div v-if="loading" class="loading">
                <div class="spinner"></div>
                <p>Loading SBCs...</p>
            </div>
            
            <!-- Empty State -->
            <div v-else-if="filteredSbcs.length === 0 && !loading" class="loading">
                <p>{{ sbcs.length === 0 ? '📭 No SBCs found. The database may still be initializing.' : '🔍 No SBCs match your search criteria.' }}</p>
                <button v-if="sbcs.length === 0" @click="forceCrawl" :disabled="crawling" class="btn btn-primary" style="margin-top: 15px;">
                    {{ crawling ? 'Crawling...' : 'Run Manual SBC Crawl' }}
                </button>
            </div>
            
            <!-- SBC Grid -->
            <div v-else class="sbc-grid">
                <div 
                    v-for="sbc in filteredSbcs" 
                    :key="sbc.id" 
                    class="sbc-card"
                    @click="openSbc(sbc.id)"
                >
                    <div class="sbc-title">{{ sbc.name }}</div>
                    <div class="sbc-meta">
                        <span class="sbc-category">{{ sbc.category }}</span>
                        <span>{{ formatDate(sbc.last_updated) }}</span>
                    </div>
                    <div class="sbc-stats">
                        <div class="stat-item">
                            <div class="stat-value">{{ sbc.challenge_count }}</div>
                            <div class="stat-label">Challenges</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">{{ sbc.expires_at ? 'Limited' : 'Permanent' }}</div>
                            <div class="stat-label">Duration</div>
                        </div>
                    </div>
                    <div v-if="sbc.rewards" class="sbc-rewards">
                        🎁 {{ sbc.rewards }}
                    </div>
                </div>
            </div>
            
            <!-- SBC Detail Modal -->
            <div v-if="selectedSbc" class="modal" @click="closeSbc">
                <div class="modal-content" @click.stop>
                    <div class="modal-header">
                        <h2 class="modal-title">{{ selectedSbc.name }}</h2>
                        <button class="close-btn" @click="closeSbc">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div v-if="loadingDetails" class="loading">
                            <div class="spinner"></div>
                            <p>Loading challenges...</p>
                        </div>
                        <div v-else>
                            <div class="sbc-info" style="margin-bottom: 25px; background: #f8f9fa; padding: 15px; border-radius: 8px;">
                                <p><strong>🎁 Rewards:</strong> {{ selectedSbc.rewards || 'Not specified' }}</p>
                                <p v-if="selectedSbc.expires_at"><strong>⏰ Expires:</strong> {{ formatDate(selectedSbc.expires_at) }}</p>
                                <p><strong>🎯 Total Challenges:</strong> {{ selectedSbc.challenges?.length || 0 }}</p>
                                <p><strong>🔗 Source:</strong> <a :href="selectedSbc.url" target="_blank" style="color: #667eea;">View on FUT.GG</a></p>
                            </div>
                            
                            <div v-if="selectedSbc.challenges?.length === 0" class="loading">
                                <p>📭 No challenges found for this SBC.</p>
                            </div>
                            
                            <div v-else class="challenge-list">
                                <div v-for="challenge in selectedSbc.challenges" :key="challenge.id" class="challenge-card">
                                    <div class="challenge-name">{{ challenge.name }}</div>
                                    <div v-if="challenge.requirements?.length > 0" class="requirements">
                                        <div v-for="req in challenge.requirements" :key="req.id || req.kind" class="requirement">
                                            <span>{{ formatRequirement(req) }}</span>
                                            <span class="requirement-type">{{ req.kind }}</span>
                                        </div>
                                    </div>
                                    <div v-else style="padding: 10px; background: #f8f9fa; border-radius: 6px; color: #7f8c8d; font-style: italic;">
                                        No specific requirements found
                                    </div>
                                    <div v-if="challenge.reward" style="color: #27ae60; font-weight: 600; margin: 10px 0;">
                                        🎁 {{ challenge.reward }}
                                    </div>
                                    <div class="solution-section">
                                        <button 
                                            class="solution-btn" 
                                            @click="loadSolution(challenge.id)"
                                            :disabled="loadingSolutions[challenge.id]"
                                        >
                                            {{ loadingSolutions[challenge.id] ? 'Calculating...' : 'Find Cheapest Solution' }}
                                        </button>
                                        <div v-if="solutions[challenge.id]" style="margin-top: 15px;">
                                            <div style="font-weight: 700; color: #27ae60; margin-bottom: 10px; font-size: 1.1em;">
                                                💰 Total Cost: {{ formatCost(solutions[challenge.id].total_cost) }}
                                            </div>
                                            <div style="font-size: 0.9em; color: #7f8c8d; margin-bottom: 15px; display: flex; gap: 20px;">
                                                <span>⚡ Chemistry: {{ solutions[challenge.id].chemistry }}</span>
                                                <span>⭐ Rating: {{ solutions[challenge.id].rating }}</span>
                                                <span>👥 Players: {{ solutions[challenge.id].players.length }}</span>
                                            </div>
                                            
                                            <!-- Player List -->
                                            <div style="max-height: 200px; overflow-y: auto; background: #f8f9fa; border-radius: 8px; padding: 10px; margin-bottom: 10px;">
                                                <div style="font-weight: 600; margin-bottom: 8px; color: #2c3e50;">Suggested Squad:</div>
                                                <div v-for="player in solutions[challenge.id].players" :key="player.name" 
                                                     style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #e0e0e0; font-size: 0.85em;">
                                                    <span>
                                                        <strong>{{ player.name }}</strong> ({{ player.position }}) - {{ player.rating }} OVR
                                                    </span>
                                                    <span style="color: #27ae60; font-weight: 600;">
                                                        {{ formatCost(player.price) }}
                                                    </span>
                                                </div>
                                            </div>
                                            
                                            <p style="font-size: 0.75em; color: #95a5a6; margin-top: 8px; font-style: italic;">
                                                💡 Prices are estimates based on typical market values. Actual costs may vary.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const { createApp } = Vue;
        
        createApp({
            data() {
                return {
                    sbcs: [],
                    categories: [],
                    selectedCategory: '',
                    searchQuery: '',
                    activeOnly: true,
                    loading: true,
                    selectedSbc: null,
                    loadingDetails: false,
                    solutions: {},
                    loadingSolutions: {},
                    searchTimeout: null,
                    dbReady: true,
                    error: null,
                    crawling: false
                }
            },
            computed: {
                filteredSbcs() {
                    if (!this.searchQuery) return this.sbcs;
                    const query = this.searchQuery.toLowerCase();
                    return this.sbcs.filter(sbc => 
                        sbc.name.toLowerCase().includes(query) ||
                        (sbc.rewards && sbc.rewards.toLowerCase().includes(query))
                    );
                }
            },
            async mounted() {
                console.log('Vue app mounted');
                await this.checkStatus();
                await this.loadCategories();
                await this.loadSbcs();
            },
            methods: {
                async checkStatus() {
                    try {
                        const response = await axios.get('/health');
                        this.dbReady = response.data.ready && response.data.database_configured;
                        if (response.data.startup_error) {
                            this.error = response.data.startup_error;
                        } else {
                            this.error = null;
                        }
                        console.log('Health check:', response.data);
                    } catch (error) {
                        this.error = 'Failed to check app status';
                        console.error('Health check failed:', error);
                    }
                },
                
                async forceCrawl() {
                    this.crawling = true;
                    try {
                        const response = await axios.post('/force');
                        console.log('Manual crawl result:', response.data);
                        await this.loadSbcs();
                        await this.loadCategories();
                        this.dbReady = true;
                    } catch (error) {
                        this.error = 'Failed to run manual crawl: ' + (error.response?.data?.detail || error.message);
                        console.error('Manual crawl failed:', error);
                    } finally {
                        this.crawling = false;
                    }
                },
                
                async loadCategories() {
                    try {
                        const response = await axios.get('/api/categories');
                        this.categories = response.data.categories || [];
                        console.log('Loaded categories:', this.categories.length);
                    } catch (error) {
                        console.error('Failed to load categories:', error);
                        this.categories = [];
                    }
                },
                
                async loadSbcs() {
                    this.loading = true;
                    this.error = null;
                    try {
                        const params = {
                            active_only: this.activeOnly,
                            limit: 100
                        };
                        if (this.selectedCategory) {
                            params.category = this.selectedCategory;
                        }
                        
                        const response = await axios.get('/api/sbcs', { params });
                        this.sbcs = response.data.sbcs || [];
                        console.log('Loaded SBCs:', this.sbcs.length);
                    } catch (error) {
                        console.error('Failed to load SBCs:', error);
                        this.error = 'Failed to load SBCs: ' + (error.response?.data?.detail || error.message);
                        this.sbcs = [];
                    } finally {
                        this.loading = false;
                    }
                },
                
                async openSbc(sbcId) {
                    this.loadingDetails = true;
                    this.selectedSbc = { name: 'Loading...' };
                    
                    try {
                        const response = await axios.get(`/api/sbcs/${sbcId}`);
                        this.selectedSbc = response.data.sbc;
                        this.selectedSbc.challenges = response.data.challenges;
                        console.log('Loaded SBC details:', this.selectedSbc.name, 'with', this.selectedSbc.challenges.length, 'challenges');
                    } catch (error) {
                        console.error('Failed to load SBC details:', error);
                        this.selectedSbc = null;
                        this.error = 'Failed to load SBC details: ' + (error.response?.data?.detail || error.message);
                    } finally {
                        this.loadingDetails = false;
                    }
                },
                
                closeSbc() {
                    this.selectedSbc = null;
                    this.solutions = {};
                    this.loadingSolutions = {};
                },
                
                async loadSolution(challengeId) {
                    if (!this.loadingSolutions) this.loadingSolutions = {};
                    this.$set(this.loadingSolutions, challengeId, true);
                    
                    try {
                        const response = await axios.get(`/api/challenges/${challengeId}/solution`);
                        if (!this.solutions) this.solutions = {};
                        this.$set(this.solutions, challengeId, response.data.solution);
                        console.log('Loaded solution for challenge', challengeId);
                    } catch (error) {
                        console.error('Failed to load solution:', error);
                        this.error = 'Failed to calculate solution: ' + (error.response?.data?.detail || error.message);
                    } finally {
                        this.$set(this.loadingSolutions, challengeId, false);
                    }
                },
                
                debounceSearch() {
                    clearTimeout(this.searchTimeout);
                    this.searchTimeout = setTimeout(() => {
                        // Search is handled by computed property
                    }, 300);
                },
                
                formatDate(dateString) {
                    if (!dateString) return 'No date';
                    try {
                        return new Date(dateString).toLocaleDateString('en-US', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                        });
                    } catch {
                        return 'Invalid date';
                    }
                },
                
                formatCost(cost) {
                    if (!cost || cost === 0) return 'Free';
                    if (cost >= 1000000) return `${(cost / 1000000).toFixed(1)}M`;
                    if (cost >= 1000) return `${(cost / 1000).toFixed(0)}K`;
                    return cost.toString();
                },
                
                formatRequirement(req) {
                    if (!req) return 'Unknown requirement';
                    
                    if (req.kind === 'team_rating_min') {
                        return `Min. Team Rating: ${req.value}`;
                    } else if (req.kind === 'chem_min') {
                        return `Min. Chemistry: ${req.value}`;
                    } else if (req.kind === 'min_from') {
                        return `Min. ${req.value} Players from: ${req.key}`;
                    } else if (req.kind === 'count_constraint') {
                        const op = req.operator === 'eq' ? 'Exactly' : req.operator === 'le' ? 'Max.' : 'Min.';
                        return `${op} ${req.value} ${req.key}`;
                    } else if (req.kind === 'min_program') {
                        return `Min. ${req.value} Special Players`;
                    } else if (req.kind === 'raw') {
                        return req.value || 'Raw requirement';
                    } else {
                        return `${req.kind}: ${req.value || req.key || 'Unknown'}`;
                    }
                }
            }
        }).mount('#app');
    </script>
</body>
</html>
    """)

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
