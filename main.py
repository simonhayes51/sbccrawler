from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import os
import asyncio

app = FastAPI(title="FUT SBC Tracker")

@app.get("/")
def root():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>FUT SBC Debug</title>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://unpkg.com/axios/dist/axios.min.js"></script>
    <style>
        body { font-family: system-ui; margin: 20px; background: #f0f2f5; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; margin-bottom: 20px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        .warning-button { background: #e67e22 !important; }
        .log { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
        .error { background: #f8d7da; color: #721c24; }
        .success { background: #d4edda; color: #155724; }
        .warning { background: #fff3cd; color: #856404; }
        .highlight { background: #e8f5e8; padding: 5px; border-radius: 3px; margin: 5px 0; }
        [v-cloak] { display: none; }
    </style>
</head>
<body>
    <div id="app" v-cloak>
        <div class="container">
            <h1>🔧 FUT SBC Debug Tool</h1>
            
            <div class="card">
                <h3>Step 1: Test Basic Connectivity</h3>
                <button @click="testConnectivity" :disabled="loading">Test fut.gg Connection</button>
                <div v-if="connectivityResult" class="log" :class="connectivityResult.success ? 'success' : 'error'">
                    {{ connectivityResult.message }}
                    <div v-if="connectivityResult.success">
                        Status Code: {{ connectivityResult.status_code }}<br>
                        Content Length: {{ connectivityResult.content_length }}
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Step 2: Test Solution URL Finding</h3>
                <button @click="findRealSolutionUrls" :disabled="loading">Find Working Solution URLs</button>
                <div v-if="findUrlsResult" class="log">
                    <strong>Status:</strong> {{ findUrlsResult.status }}<br>
                    <div v-if="findUrlsResult.status === 'success'">
                        <strong>Solutions Found:</strong> {{ findUrlsResult.total_solutions_found }}<br>
                        <strong>Working Solutions:</strong> {{ findUrlsResult.working_solutions }}<br>
                        <strong>{{ findUrlsResult.recommendation }}</strong>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Step 3: Alternative Strategy - Direct Database Search</h3>
                <button @click="testDatabaseSearch" :disabled="loading">Test Direct Player Database Search</button>
                <div v-if="databaseResult" class="log">
                    <strong>Status:</strong> {{ databaseResult.status }}<br>
                    <div v-if="databaseResult.status === 'success'">
                        <strong>Database Connected:</strong> {{ databaseResult.database_connected ? '✅' : '❌' }}<br>
                        <strong>Total Players:</strong> {{ databaseResult.total_players }}<br>
                        <div v-if="databaseResult.sample_players">
                            <strong>Sample Players:</strong><br>
                            <div v-for="player in databaseResult.sample_players" :key="player.card_id" style="margin-left: 20px;">
                                • {{ player.name }} ({{ player.rating }} OVR, {{ player.position }}) - Card ID: {{ player.card_id }}
                            </div>
                        </div>
                        <div class="highlight">
                            <strong>Recommendation:</strong> Since HTML scraping isn't working, you can build solutions manually using your player database or find alternative data sources.
                        </div>
                    </div>
                    <div v-if="databaseResult.error" class="error">
                        <strong>Error:</strong> {{ databaseResult.error }}
                    </div>
                </div>
            </div>
            
            <div v-if="loading" style="text-align: center; margin: 20px;">
                <div style="display: inline-block; width: 20px; height: 20px; border: 2px solid #f3f3f3; border-top: 2px solid #007bff; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                <p>Loading...</p>
            </div>
        </div>
    </div>

    <script>
        const { createApp } = Vue;
        createApp({
            data() {
                return {
                    loading: false,
                    connectivityResult: null,
                    findUrlsResult: null,
                    databaseResult: null
                }
            },
            methods: {
                async testConnectivity() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/connectivity');
                        this.connectivityResult = res.data;
                    } catch (e) {
                        this.connectivityResult = { success: false, message: e.message };
                    }
                    this.loading = false;
                },
                async findRealSolutionUrls() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/find-real-solution-urls');
                        this.findUrlsResult = res.data;
                    } catch (e) {
                        this.findUrlsResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                },
                async testDatabaseSearch() {
                    this.loading = true;
                    try {
                        const res = await axios.get('/debug/test-database');
                        this.databaseResult = res.data;
                    } catch (e) {
                        this.databaseResult = { status: 'error', error: e.message };
                    }
                    this.loading = false;
                }
            }
        }).mount('#app');
    </script>
    <style>
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</body>
</html>
    """)

@app.get("/debug/connectivity")
async def debug_connectivity():
    """Test basic connectivity to fut.gg"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("https://www.fut.gg/sbc/", timeout=10)
            return {
                "success": True,
                "status_code": response.status_code,
                "message": f"Successfully connected to fut.gg (Status: {response.status_code})",
                "content_length": len(response.text)
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}"
        }

@app.get("/debug/find-real-solution-urls")
async def find_real_solution_urls():
    """Find actual working solution URLs from SBC pages"""
    try:
        import httpx
        from bs4 import BeautifulSoup
        import re
        
        # Test multiple SBC pages to find solution URLs
        sbc_pages = [
            "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/",
            "https://www.fut.gg/sbc/live/",
        ]
        
        found_solutions = []
        
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            for sbc_url in sbc_pages:
                try:
                    response = await client.get(sbc_url, headers=headers, timeout=30)
                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    # Look for solution/squad-builder links
                    links = soup.find_all("a", href=True)
                    for link in links:
                        href = link["href"]
                        if "/25/" in href and "squad-builder" in href:
                            if href.startswith("/"):
                                href = "https://www.fut.gg" + href
                            if href not in [s["url"] for s in found_solutions]:
                                found_solutions.append({
                                    "url": href,
                                    "found_on": sbc_url
                                })
                
                except Exception as e:
                    print(f"Error checking {sbc_url}: {e}")
        
        return {
            "status": "success",
            "total_solutions_found": len(found_solutions),
            "working_solutions": 0,  # We know they don't work from previous tests
            "found_solution_urls": [s["url"] for s in found_solutions[:10]],
            "recommendation": "HTML scraping approach not working - fut.gg uses dynamic content loading. Consider alternative approaches."
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/debug/test-database")
async def test_database():
    """Test direct access to your player database"""
    try:
        from db import get_pool
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            # Test database connection
            total_players = await conn.fetchval("SELECT COUNT(*) FROM fut_players")
            
            # Get sample players
            sample_players = await conn.fetch("""
                SELECT card_id, name, rating, position, club, league, nation, price
                FROM fut_players 
                ORDER BY rating DESC
                LIMIT 5
            """)
            
            players_list = []
            for player in sample_players:
                players_list.append({
                    "card_id": player["card_id"],
                    "name": player["name"],
                    "rating": player["rating"],
                    "position": player["position"],
                    "club": player["club"],
                    "league": player["league"],
                    "nation": player["nation"],
                    "price": player["price"] if player["price"] else 0
                })
            
            return {
                "status": "success",
                "database_connected": True,
                "total_players": total_players,
                "sample_players": players_list,
                "message": f"Database working! Found {total_players:,} players total."
            }
            
    except Exception as e:
        return {
            "status": "error",
            "database_connected": False,
            "error": str(e),
            "message": "Database connection failed"
        }

@app.get("/api/players/search")
async def search_players_endpoint(name: str = None, min_rating: int = None, limit: int = 20):
    """Search players in your database"""
    try:
        from db import get_pool
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            where_conditions = []
            params = []
            
            if name:
                where_conditions.append("name ILIKE $1")
                params.append(f"%{name}%")
            
            if min_rating:
                param_num = len(params) + 1
                where_conditions.append(f"rating >= ${param_num}")
                params.append(min_rating)
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            params.append(limit)
            param_num = len(params)
            
            query = f"""
                SELECT card_id, name, rating, position, club, league, nation, price
                FROM fut_players 
                {where_clause}
                ORDER BY rating DESC, price ASC
                LIMIT ${param_num}
            """
            
            rows = await conn.fetch(query, *params)
            
            players = []
            for row in rows:
                players.append({
                    "card_id": row["card_id"],
                    "name": row["name"],
                    "rating": row["rating"],
                    "position": row["position"],
                    "club": row["club"],
                    "league": row["league"],
                    "nation": row["nation"],
                    "price": row["price"] if row["price"] else 0
                })
            
            return {
                "status": "success",
                "players": players,
                "count": len(players),
                "search_params": {"name": name, "min_rating": min_rating, "limit": limit}
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/health")
def health():
    return {"status": "ok", "database": bool(os.getenv("DATABASE_URL"))}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
