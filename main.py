@app.get("/api/players/prices")
async def get_player_prices(
    min_rating: int = Query(75, description="Minimum player rating"),
    max_rating: int = Query(95, description="Maximum player rating"),
    position: Optional[str]# main.py
import os, asyncio, traceback
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from db import init_db, get_pool
from scheduler import run_job, schedule_loop

app = FastAPI(title="FUT SBC Tracker", description="FIFA Ultimate Team Squad Building Challenge tracker and solver")

# Mount static files for CSS/JS
# app.mount("/static", StaticFiles(directory="static"), name="static")

status = {"ready": False, "last_run": None, "startup_error": None}

async def _initial_run():
    try:
        await run_job()
        status["ready"] = True
        status["last_run"] = "startup"
    except Exception as e:
        status["startup_error"] = f"{type(e).__name__}: {e}"
        print("💥 Initial crawl failed:\n" + "".join(traceback.format_exc()))

@app.on_event("startup")
async def on_startup():
    print(f"🧩 DATABASE_URL set: {bool(os.getenv('DATABASE_URL'))}")
    try:
        await init_db()
        # Kick off initial run in background so Uvicorn can finish starting
        asyncio.create_task(_initial_run())
        # Start the daily 18:00 UK scheduler
        asyncio.create_task(schedule_loop())
        print("✅ App bootstrapped; background tasks scheduled")
    except Exception as e:
        status["startup_error"] = f"{type(e).__name__}: {e}"
        print("💥 Startup failed:\n" + "".join(traceback.format_exc()))

# ==================== EXISTING ENDPOINTS ====================

@app.get("/health")
async def health():
    return status

@app.post("/force")
async def force():
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "DATABASE_URL missing")
    await run_job()
    status["ready"] = True
    status["last_run"] = "force"
    return {"ok": True}

@app.get("/db-stats")
async def db_stats():
    """Get database statistics"""
    try:
        pool = await get_pool()
        async with pool.acquire() as con:
            set_count = await con.fetchval("SELECT COUNT(*) FROM sbc_sets")
            challenge_count = await con.fetchval("SELECT COUNT(*) FROM sbc_challenges") 
            requirement_count = await con.fetchval("SELECT COUNT(*) FROM sbc_requirements")
            active_sets = await con.fetchval("SELECT COUNT(*) FROM sbc_sets WHERE is_active = TRUE")
            
            # Get some sample data
            sample_sets = await con.fetch("""
                SELECT s.name, COUNT(c.id) as challenge_count 
                FROM sbc_sets s 
                LEFT JOIN sbc_challenges c ON s.id = c.sbc_set_id 
                WHERE s.is_active = TRUE 
                GROUP BY s.id, s.name 
                ORDER BY challenge_count DESC 
                LIMIT 10
            """)
            
            return {
                "total_sets": set_count,
                "active_sets": active_sets,
                "total_challenges": challenge_count,
                "total_requirements": requirement_count,
                "sample_sets": [{"name": row["name"], "challenges": row["challenge_count"]} for row in sample_sets]
            }
    except Exception as e:
        raise HTTPException(500, f"Database stats failed: {e}")

# ==================== NEW SBC API ENDPOINTS ====================

@app.get("/api/sbcs")
async def get_sbcs(
    category: Optional[str] = Query(None, description="Filter by category (players, icons, upgrades, etc.)"),
    active_only: bool = Query(True, description="Show only active SBCs"),
    limit: int = Query(50, description="Maximum number of SBCs to return"),
    offset: int = Query(0, description="Offset for pagination")
):
    """Get list of SBCs with basic info"""
    try:
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
            param_placeholders = ", ".join([f"${i}" for i in range(len(params) - 1, len(params) + 1)])
            
            query = f"""
                SELECT 
                    s.id, s.slug, s.name, s.expires_at, s.reward_summary,
                    s.last_seen_at, s.is_active,
                    COUNT(c.id) as challenge_count,
                    COALESCE(SUM(c.site_cost), 0) as total_cost
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
                        "estimated_cost": row["total_cost"],
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
    try:
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
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(500, f"Failed to fetch SBC details: {e}")

@app.get("/api/categories")
async def get_categories():
    """Get available SBC categories"""
    try:
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
        raise HTTPException(500, f"Failed to fetch categories: {e}")

# ==================== SOLUTION CALCULATOR ====================

async def calculate_cheapest_solution(challenge_id: int) -> Dict[str, Any]:
    """Calculate the cheapest solution for a challenge based on requirements"""
    pool = await get_pool()
    async with pool.acquire() as con:
        # Get challenge requirements
        requirements = await con.fetch("""
            SELECT kind, key, op, value
            FROM sbc_requirements
            WHERE challenge_id = $1
        """, challenge_id)
        
        # Convert to format expected by solver
        req_list = []
        for req in requirements:
            req_dict = {
                "kind": req["kind"],
                "key": req["key"],
                "op": req["op"], 
                "value": req["value"]
            }
            req_list.append(req_dict)
        
        # Use the price system to solve
        solution = await solve_sbc_challenge(req_list)
@app.get("/api/players/prices")
async def get_player_prices(
    min_rating: int = Query(75, description="Minimum player rating"),
    max_rating: int = Query(95, description="Maximum player rating"),
    position: Optional[str] = Query(None, description="Filter by position"),
    league: Optional[str] = Query(None, description="Filter by league"),
    limit: int = Query(50, description="Maximum number of players to return")
):
    """Get current player prices for building squads"""
    try:
        from price_fetcher import price_db
        
        # Get players within rating range
        players = price_db.get_players_by_rating(min_rating, max_rating)
        
        # Apply additional filters
        if position:
            players = [p for p in players if p.position.lower() == position.lower()]
        
        if league:
            players = [p for p in players if league.lower() in p.league.lower()]
        
        # Limit results
        players = players[:limit]
        
        return {
            "players": [
                {
                    "name": p.name,
                    "rating": p.rating,
                    "position": p.position,
                    "league": p.league,
                    "club": p.club,
                    "nation": p.nation,
                    "price": p.price,
                    "rarity": p.rarity
                }
                for p in players
            ],
            "total_found": len(players),
            "last_updated": price_db.last_update.isoformat()
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get player prices: {e}")

# ==================== WEB UI ====================
async def get_challenge_solution(challenge_id: int):
    """Get cheapest solution for a specific challenge"""
    try:
        pool = await get_pool()
        async with pool.acquire() as con:
            # Verify challenge exists
            challenge = await con.fetchrow("""
                SELECT c.id, c.name, s.name as sbc_name
                FROM sbc_challenges c
                JOIN sbc_sets s ON c.sbc_set_id = s.id
                WHERE c.id = $1
            """, challenge_id)
            
            if not challenge:
                raise HTTPException(404, "Challenge not found")
            
            solution = await calculate_cheapest_solution(challenge_id)
            
            return {
                "challenge": {
                    "id": challenge["id"],
                    "name": challenge["name"],
                    "sbc_name": challenge["sbc_name"]
                },
                "solution": solution
            }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(500, f"Failed to calculate solution: {e}")

# ==================== WEB UI ====================

@app.get("/", response_class=HTMLResponse)
async def sbc_browser():
    """Main SBC browser page"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FUT SBC Browser</title>
        <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
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
            
            .modal-body {
                padding: 25px;
            }
            
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
            .solution-btn:hover {
                transform: translateY(-2px);
            }
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
                                <div class="stat-value">{{ formatCost(sbc.estimated_cost) }}</div>
                                <div class="stat-label">Est. Cost</div>
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
                                <div class="sbc-info" style="margin-bottom: 25px;">
                                    <p><strong>Rewards:</strong> {{ selectedSbc.rewards || 'Not specified' }}</p>
                                    <p v-if="selectedSbc.expires_at"><strong>Expires:</strong> {{ formatDate(selectedSbc.expires_at) }}</p>
                                    <p><strong>Total Challenges:</strong> {{ selectedSbc.challenges?.length || 0 }}</p>
                                </div>
                                
                                <div class="challenge-list">
                                    <div v-for="challenge in selectedSbc.challenges" :key="challenge.id" class="challenge-card">
                                        <div class="challenge-name">{{ challenge.name }}</div>
                                        <div class="requirements">
                                            <div v-for="req in challenge.requirements" :key="req.id" class="requirement">
                                                <span>{{ formatRequirement(req) }}</span>
                                                <span class="requirement-type">{{ req.kind }}</span>
                                            </div>
                                        </div>
                                        <div v-if="challenge.reward" style="color: #27ae60; font-weight: 600; margin-bottom: 10px;">
                                            🎁 {{ challenge.reward }}
                                        </div>
                                        <div class="solution-section">
                                            <button 
                                                class="solution-btn" 
                                                @click="loadSolution(challenge.id)"
                                                :disabled="loadingSolutions[challenge.id]"
                                            >
                                                {{ loadingSolutions[challenge.id] ? 'Loading...' : 'Find Cheapest Solution' }}
                                            </button>
                                            <div v-if="solutions[challenge.id]" style="margin-top: 15px;">
                                                <div style="font-weight: 700; color: #27ae60; margin-bottom: 10px;">
                                                    💰 Estimated Cost: {{ formatCost(solutions[challenge.id].total_cost) }}
                                                </div>
                                                <div style="font-size: 0.9em; color: #7f8c8d; margin-bottom: 15px;">
                                                    <p>⚡ Chemistry: {{ solutions[challenge.id].chemistry }}</p>
                                                    <p>⭐ Team Rating: {{ solutions[challenge.id].rating }}</p>
                                                    <p>👥 Players: {{ solutions[challenge.id].players.length }}</p>
                                                </div>
                                                
                                                <!-- Player List -->
                                                <div style="max-height: 200px; overflow-y: auto; background: #f8f9fa; border-radius: 8px; padding: 10px; margin-bottom: 10px;">
                                                    <div style="font-weight: 600; margin-bottom: 8px; color: #2c3e50;">Squad:</div>
                                                    <div v-for="player in solutions[challenge.id].players" :key="player.name" 
                                                         style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #e0e0e0;">
                                                        <span style="font-size: 0.85em;">
                                                            <strong>{{ player.name }}</strong> ({{ player.position }}) - {{ player.rating }} OVR
                                                        </span>
                                                        <span style="color: #27ae60; font-weight: 600; font-size: 0.85em;">
                                                            {{ formatCost(player.price) }}
                                                        </span>
                                                    </div>
                                                </div>
                                                
                                                <!-- Requirements Check -->
                                                <div style="background: #e8f5e8; border-radius: 6px; padding: 8px; font-size: 0.8em;">
                                                    <div style="font-weight: 600; color: #27ae60; margin-bottom: 5px;">Requirements Check:</div>
                                                    <div v-for="req in solutions[challenge.id].requirements_analysis" :key="req.requirement">
                                                        <span :style="req.satisfied ? 'color: #27ae60;' : 'color: #e74c3c;'">
                                                            {{ req.satisfied ? '✅' : '❌' }} {{ req.requirement }}
                                                        </span>
                                                    </div>
                                                </div>
                                                
                                                <p style="font-size: 0.75em; color: #95a5a6; margin-top: 8px; font-style: italic;">
                                                    💡 Prices are estimates and may vary based on current market conditions.
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
                        searchTimeout: null
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
                    await this.loadCategories();
                    await this.loadSbcs();
                },
                methods: {
                    async loadCategories() {
                        try {
                            const response = await axios.get('/api/categories');
                            this.categories = response.data.categories;
                        } catch (error) {
                            console.error('Failed to load categories:', error);
                        }
                    },
                    
                    async loadSbcs() {
                        this.loading = true;
                        try {
                            const params = {
                                active_only: this.activeOnly,
                                limit: 100
                            };
                            if (this.selectedCategory) {
                                params.category = this.selectedCategory;
                            }
                            
                            const response = await axios.get('/api/sbcs', { params });
                            this.sbcs = response.data.sbcs;
                        } catch (error) {
                            console.error('Failed to load SBCs:', error);
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
                        } catch (error) {
                            console.error('Failed to load SBC details:', error);
                            this.selectedSbc = null;
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
                        this.$set(this.loadingSolutions, challengeId, true);
                        
                        try {
                            const response = await axios.get(`/api/challenges/${challengeId}/solution`);
                            this.$set(this.solutions, challengeId, response.data.solution);
                        } catch (error) {
                            console.error('Failed to load solution:', error);
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
                        return new Date(dateString).toLocaleDateString('en-US', {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                        });
                    },
                    
                    formatCost(cost) {
                        if (!cost || cost === 0) return 'Free';
                        if (cost >= 1000000) return `${(cost / 1000000).toFixed(1)}M`;
                        if (cost >= 1000) return `${(cost / 1000).toFixed(0)}K`;
                        return cost.toString();
                    },
                    
                    formatRequirement(req) {
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
                            return req.value;
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

# ==================== DEBUG ENDPOINTS (keep existing ones) ====================

@app.get("/debug-single/{path:path}")
async def debug_single_sbc(path: str):
    """Debug a single SBC page to understand its structure"""
    if not path.startswith("sbc/"):
        raise HTTPException(400, "Path must start with 'sbc/'")
    
    from crawler import fetch_html, parse_set_page
    import httpx
    
    url = f"https://www.fut.gg/{path}"
    
    try:
        async with httpx.AsyncClient() as client:
            html = await fetch_html(client, url)
            parsed = parse_set_page(html, url, debug=True)
            
            return {
                "url": url,
                "parsed": parsed,
                "html_preview": html[:500] + "..." if len(html) > 500 else html
            }
    except Exception as e:
        raise HTTPException(500, f"Failed to debug SBC: {e}")

@app.get("/test-crawl")
async def test_crawl():
    """Test crawl with detailed output for debugging"""
    from crawler import crawl_all_sets
    
    try:
        sets = await crawl_all_sets(debug_first=True)
        
        return {
            "total_count": len(sets),
            "sets_with_challenges": len([s for s in sets if s["sub_challenges"]]),
            "sample_sets": sets[:3],
            "challenge_counts": [len(s["sub_challenges"]) for s in sets],
            "summary": {
                "avg_challenges_per_set": sum(len(s["sub_challenges"]) for s in sets) / len(sets) if sets else 0,
                "max_challenges": max(len(s["sub_challenges"]) for s in sets) if sets else 0,
                "empty_sets": len([s for s in sets if not s["sub_challenges"]])
            }
        }
    except Exception as e:
        raise HTTPException(500, f"Test crawl failed: {e}")

@app.get("/raw-html/{path:path}")
async def get_raw_html(path: str):
    """Get raw HTML from a fut.gg page for inspection"""
    if not path.startswith("sbc/"):
        raise HTTPException(400, "Path must start with 'sbc/'")
    
    from crawler import fetch_html
    import httpx
    
    url = f"https://www.fut.gg/{path}"
    
    try:
        async with httpx.AsyncClient() as client:
            html = await fetch_html(client, url)
            return JSONResponse({
                "url": url,
                "html": html,
                "length": len(html)
            })
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch HTML: {e}")
