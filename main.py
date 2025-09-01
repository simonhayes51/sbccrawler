from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from typing import List, Optional
import os

app = FastAPI(title="FUT SBC Tracker")

@app.get("/")
def root():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>SBC Solution Builder</title>
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://unpkg.com/axios/dist/axios.min.js"></script>
    <style>
        body { font-family: system-ui; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .player-card { border: 1px solid #ddd; padding: 10px; margin: 5px; border-radius: 5px; display: inline-block; min-width: 150px; }
        .search-box { width: 300px; padding: 8px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }
        button { padding: 8px 16px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        .solution-builder { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .formation { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
        .position { border: 2px dashed #ccc; padding: 20px; text-align: center; min-height: 100px; }
        .position.filled { border-color: #28a745; background: #f8fff9; }
        .stats { background: #f8f9fa; padding: 10px; border-radius: 5px; }
        [v-cloak] { display: none; }
    </style>
</head>
<body>
    <div id="app" v-cloak>
        <div class="container">
            <h1>SBC Solution Builder</h1>
            
            <div class="solution-builder">
                <!-- Left Panel: Squad Builder -->
                <div class="card">
                    <h3>Squad Builder</h3>
                    
                    <!-- Formation (simplified 11 positions) -->
                    <div class="formation">
                        <div v-for="(position, index) in squad" :key="index" 
                             class="position" 
                             :class="{ filled: position.player }"
                             @click="selectPosition(index)">
                            <div v-if="position.player">
                                <strong>{{ position.player.name }}</strong><br>
                                {{ position.player.rating }} {{ position.player.position }}<br>
                                {{ position.player.club }}
                            </div>
                            <div v-else>
                                {{ position.name }}<br>
                                <small>Click to add player</small>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Squad Stats -->
                    <div class="stats">
                        <strong>Squad Stats:</strong><br>
                        Players: {{ filledPositions }}/11<br>
                        Avg Rating: {{ averageRating }}<br>
                        Total Cost: {{ totalCost.toLocaleString() }} coins
                    </div>
                    
                    <div style="margin-top: 15px;">
                        <button @click="clearSquad">Clear Squad</button>
                        <button @click="saveSquad" :disabled="filledPositions < 11">Save Solution</button>
                    </div>
                </div>
                
                <!-- Right Panel: Player Search -->
                <div class="card">
                    <h3>Player Search</h3>
                    <div v-if="selectedPositionIndex !== null">
                        <p><strong>Adding player for: {{ squad[selectedPositionIndex].name }}</strong></p>
                    </div>
                    
                    <input v-model="searchTerm" @input="searchPlayers" 
                           placeholder="Search players..." class="search-box">
                    
                    <div>
                        <label>Min Rating: </label>
                        <input type="number" v-model="minRating" @input="searchPlayers" style="width: 80px;">
                        
                        <label style="margin-left: 15px;">Position: </label>
                        <select v-model="filterPosition" @change="searchPlayers">
                            <option value="">Any</option>
                            <option value="GK">GK</option>
                            <option value="CB">CB</option>
                            <option value="LB">LB</option>
                            <option value="RB">RB</option>
                            <option value="CM">CM</option>
                            <option value="CAM">CAM</option>
                            <option value="CDM">CDM</option>
                            <option value="LW">LW</option>
                            <option value="RW">RW</option>
                            <option value="ST">ST</option>
                        </select>
                    </div>
                    
                    <div style="max-height: 400px; overflow-y: auto; margin-top: 15px;">
                        <div v-for="player in searchResults" :key="player.card_id" 
                             class="player-card"
                             @click="addPlayerToSquad(player)"
                             style="cursor: pointer;">
                            <strong>{{ player.name }}</strong><br>
                            {{ player.rating }} OVR {{ player.position }}<br>
                            {{ player.club }} ({{ player.league }})<br>
                            <small>{{ player.price ? player.price.toLocaleString() + ' coins' : 'No price' }}</small>
                        </div>
                        
                        <div v-if="searchResults.length === 0 && searchTerm">
                            No players found
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Saved Solutions -->
            <div class="card" v-if="savedSolutions.length > 0">
                <h3>Saved Solutions</h3>
                <div v-for="solution in savedSolutions" :key="solution.id">
                    <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px;">
                        <strong>Solution {{ solution.id }}</strong> - 
                        Avg Rating: {{ solution.avgRating }} - 
                        Cost: {{ solution.totalCost.toLocaleString() }} coins
                        <button @click="loadSolution(solution)" style="margin-left: 10px;">Load</button>
                        <div style="margin-top: 10px; font-size: 12px;">
                            {{ solution.players.map(p => p.name).join(', ') }}
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
                    squad: [
                        { name: 'GK', player: null },
                        { name: 'CB', player: null },
                        { name: 'CB', player: null },
                        { name: 'LB', player: null },
                        { name: 'RB', player: null },
                        { name: 'CM', player: null },
                        { name: 'CM', player: null },
                        { name: 'CAM', player: null },
                        { name: 'LW', player: null },
                        { name: 'RW', player: null },
                        { name: 'ST', player: null }
                    ],
                    selectedPositionIndex: null,
                    searchTerm: '',
                    minRating: 75,
                    filterPosition: '',
                    searchResults: [],
                    savedSolutions: [],
                    solutionCounter: 1
                }
            },
            computed: {
                filledPositions() {
                    return this.squad.filter(pos => pos.player).length;
                },
                averageRating() {
                    const players = this.squad.filter(pos => pos.player).map(pos => pos.player);
                    if (players.length === 0) return 0;
                    const total = players.reduce((sum, player) => sum + player.rating, 0);
                    return Math.round(total / players.length);
                },
                totalCost() {
                    const players = this.squad.filter(pos => pos.player).map(pos => pos.player);
                    return players.reduce((sum, player) => sum + (player.price || 0), 0);
                }
            },
            methods: {
                selectPosition(index) {
                    this.selectedPositionIndex = index;
                },
                async searchPlayers() {
                    if (this.searchTerm.length < 2) {
                        this.searchResults = [];
                        return;
                    }
                    
                    try {
                        const params = new URLSearchParams();
                        if (this.searchTerm) params.append('name', this.searchTerm);
                        if (this.minRating) params.append('min_rating', this.minRating);
                        if (this.filterPosition) params.append('position', this.filterPosition);
                        params.append('limit', '20');
                        
                        const response = await axios.get(`/api/players/search?${params}`);
                        this.searchResults = response.data.players || [];
                    } catch (error) {
                        console.error('Search failed:', error);
                        this.searchResults = [];
                    }
                },
                addPlayerToSquad(player) {
                    if (this.selectedPositionIndex !== null) {
                        // Check if player already in squad
                        const alreadyInSquad = this.squad.some(pos => pos.player && pos.player.card_id === player.card_id);
                        if (alreadyInSquad) {
                            alert('Player already in squad!');
                            return;
                        }
                        
                        this.squad[this.selectedPositionIndex].player = player;
                        this.selectedPositionIndex = null;
                    }
                },
                clearSquad() {
                    this.squad.forEach(pos => pos.player = null);
                    this.selectedPositionIndex = null;
                },
                saveSquad() {
                    if (this.filledPositions < 11) {
                        alert('Squad must be complete (11 players)');
                        return;
                    }
                    
                    const solution = {
                        id: this.solutionCounter++,
                        players: this.squad.map(pos => pos.player),
                        avgRating: this.averageRating,
                        totalCost: this.totalCost,
                        timestamp: new Date().toLocaleString()
                    };
                    
                    this.savedSolutions.push(solution);
                    alert('Solution saved!');
                },
                loadSolution(solution) {
                    solution.players.forEach((player, index) => {
                        this.squad[index].player = player;
                    });
                }
            },
            mounted() {
                // Initial search for high-rated players
                this.searchTerm = '';
                this.minRating = 80;
                // Don't auto-search to avoid API calls
            }
        }).mount('#app');
    </script>
</body>
</html>
    """)

@app.get("/api/players/search")
async def search_players(
    name: Optional[str] = None,
    min_rating: Optional[int] = None,
    position: Optional[str] = None,
    limit: int = 20
):
    """Search players in database"""
    try:
        from db import get_pool
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            where_conditions = []
            params = []
            param_count = 0
            
            if name:
                param_count += 1
                where_conditions.append(f"name ILIKE ${param_count}")
                params.append(f"%{name}%")
            
            if min_rating:
                param_count += 1
                where_conditions.append(f"rating >= ${param_count}")
                params.append(min_rating)
                
            if position:
                param_count += 1
                where_conditions.append(f"position = ${param_count}")
                params.append(position)
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            param_count += 1
            params.append(limit)
            
            query = f"""
                SELECT card_id, name, rating, position, club, league, nation, price
                FROM fut_players 
                {where_clause}
                ORDER BY rating DESC, price ASC NULLS LAST
                LIMIT ${param_count}
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
                    "price": row["price"]
                })
            
            return {
                "status": "success",
                "players": players,
                "count": len(players)
            }
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/solutions/save")
async def save_solution(solution_data: dict):
    """Save a squad solution to database"""
    try:
        from db import get_pool
        import json
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            solution_id = await conn.fetchval("""
                INSERT INTO sbc_solutions (name, players_json, avg_rating, total_cost, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                RETURNING id
            """, 
                solution_data.get("name", "Manual Solution"),
                json.dumps(solution_data.get("players", [])),
                solution_data.get("avg_rating", 0),
                solution_data.get("total_cost", 0)
            )
            
            return {"status": "success", "solution_id": solution_id}
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/solutions")
async def get_solutions():
    """Get saved solutions"""
    try:
        from db import get_pool
        import json
        
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, players_json, avg_rating, total_cost, created_at
                FROM sbc_solutions
                ORDER BY created_at DESC
                LIMIT 50
            """)
            
            solutions = []
            for row in rows:
                solutions.append({
                    "id": row["id"],
                    "name": row["name"],
                    "players": json.loads(row["players_json"]),
                    "avg_rating": row["avg_rating"],
                    "total_cost": row["total_cost"],
                    "created_at": row["created_at"].isoformat()
                })
            
            return {"status": "success", "solutions": solutions}
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/health")
def health():
    return {"status": "ok", "database": bool(os.getenv("DATABASE_URL"))}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
