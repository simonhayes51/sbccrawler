# main.py — clean Railway-safe FastAPI app

import os
import sys
import asyncio
import traceback
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

print("🚀 Starting FUT SBC Tracker…")
print(f"🐍 Python: {sys.version}")
print(f"🌐 PORT: {os.getenv('PORT', '8080')}")
print(f"🔗 DATABASE_URL: {'✅ Set' if os.getenv('DATABASE_URL') else '❌ Missing'}")

app = FastAPI(title="FUT SBC Tracker", description="FIFA Ultimate Team Squad Building Challenge tracker and solver")

status = {
    "ready": False,
    "last_run": None,
    "startup_error": None,
    "imports": {}
}

# ---------- Optional: quick import self-check ----------
def _test_imports() -> Dict[str, str]:
    results = {}
    def try_imp(name, alias=None):
        try:
            __import__(alias or name)
            results[name] = "✅ OK"
        except Exception as e:
            results[name] = f"❌ {e}"
    for mod, alias in [("asyncpg", None), ("httpx", None), ("bs4", None), ("pytz", None), ("db", None), ("scheduler", None), ("crawler", None), ("normalizer", None)]:
        try_imp(mod, alias)
    return results

status["imports"] = _test_imports()
for k, v in status["imports"].items():
    print(f"🧪 {k}: {v}")

# ---------- Simple SBC solver (mock fallback) ----------
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

def _avg_rating(players: List[Dict[str, Any]]) -> float:
    return 0.0 if not players else sum(p.get("rating", 75) for p in players) / len(players)

def solve_simple_sbc(requirements: List[Dict[str, Any]]) -> Dict[str, Any]:
    selected: List[Dict[str, Any]] = []
    min_rating = 0
    required_from: Dict[str, int] = {}

    for req in requirements or []:
        if req.get("kind") == "team_rating_min":
            try:
                min_rating = int(req.get("value") or 0)
            except Exception:
                min_rating = 0
        elif req.get("kind") == "min_from" and req.get("key"):
            val = req.get("value")
            count = int(val) if str(val).isdigit() else 1
            required_from[req["key"]] = count

    # Satisfy "min from" cheaply
    for key, count in required_from.items():
        k = key.lower()
        matches = [p for p in MOCK_PLAYERS if k in p["league"].lower() or k in p["club"].lower() or k in p["nation"].lower()]
        matches.sort(key=lambda x: x["price"])
        selected.extend(matches[:max(0, min(count, len(matches)))])

    # Fill to 11 with cheapest
    remaining = [p for p in MOCK_PLAYERS if p not in selected]
    remaining.sort(key=lambda x: x["price"])
    i = 0
    while len(selected) < 11 and remaining:
        selected.append(remaining[i % len(remaining)])
        i += 1

    # Upgrade until min rating met (best effort)
    attempts = 0
    while _avg_rating(selected) < min_rating and attempts < 20:
        low = min(selected, key=lambda x: x.get("rating", 0))
        selected.remove(low)
        better = [p for p in MOCK_PLAYERS if p not in selected and p.get("rating", 0) > low.get("rating", 0)]
        if not better:
            selected.append(low)
            break
        better.sort(key=lambda x: x["price"])
        selected.append(better[0])
        attempts += 1

    total_cost = sum(p.get("price", 0) for p in selected)
    final_rating = round(_avg_rating(selected), 1)

    return {
        "total_cost": total_cost,
        "chemistry": 100,
        "rating": final_rating,
        "meets_requirements": final_rating >= min_rating if min_rating > 0 else True,
        "players": selected,
        "requirements_analysis": (
            [{"requirement": f"Min. Team Rating: {min_rating}" if min_rating else "No rating requirement",
              "satisfied": final_rating >= min_rating if min_rating else True}]
            + [{"requirement": f"Min. players from {k}", "satisfied": True, "notes": f"Added {v} player(s) from {k}"} for k, v in required_from.items()]
        ),
        "data_source": "Mock data (fallback)"
    }

# ---------- Startup ----------
async def _initial_run():
    try:
        from db import init_db
        from scheduler import run_job
        print("🔧 Initializing database…")
        await init_db()
        print("🔄 Running initial SBC crawl…")
        await run_job()
        status["ready"] = True
        status["last_run"] = "startup"
        print("✅ Initial setup complete")
    except Exception as e:
        status["startup_error"] = f"{type(e).__name__}: {e}"
        print("💥 Initial setup failed:", e)
        print("".join(traceback.format_exc()))

@app.on_event("startup")
async def on_startup():
    print(f"🧩 DATABASE_URL configured: {bool(os.getenv('DATABASE_URL'))}")
    try:
        if os.getenv("DATABASE_URL"):
            asyncio.create_task(_initial_run())
            try:
                from scheduler import schedule_loop
                asyncio.create_task(schedule_loop())
                print("✅ Background tasks scheduled")
            except Exception as e:
                print("⚠️ Scheduler not started:", e)
        else:
            print("⚠️ No DATABASE_URL — running without DB")
    except Exception as e:
        status["startup_error"] = f"{type(e).__name__}: {e}"
        print("💥 Startup failed:", e)
        print("".join(traceback.format_exc()))

# ---------- Health ----------
@app.get("/health")
async def health():
    return {
        "status": "ok" if not status.get("startup_error") else "error",
        "ready": status.get("ready", False),
        "last_run": status.get("last_run"),
        "startup_error": status.get("startup_error"),
        "database_configured": bool(os.getenv("DATABASE_URL")),
        "imports": status.get("imports", {}),
        "port": os.getenv("PORT"),
        "environment": os.getenv("RAILWAY_ENVIRONMENT"),
    }

# ---------- API: categories ----------
@app.get("/api/categories")
async def get_categories():
    if not os.getenv("DATABASE_URL"):
        return {"categories": []}
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
                  END AS category,
                  COUNT(*) AS count
                FROM sbc_sets
                WHERE is_active = TRUE
                GROUP BY 1
                ORDER BY count DESC
            """)
            return {"categories": [{"name": r["category"], "count": r["count"], "display_name": r["category"].title()} for r in rows]}
    except Exception as e:
        print("Categories query failed:", e)
        return {"categories": []}

# ---------- API: list SBCs ----------
@app.get("/api/sbcs")
async def get_sbcs(
    category: Optional[str] = Query(None, description="Filter by category"),
    active_only: bool = Query(True, description="Show only active SBCs"),
    limit: int = Query(50, description="Maximum number of SBCs to return"),
    offset: int = Query(0, description="Offset for pagination")
):
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            where = []
            params: List[Any] = []
            if active_only:
                where.append("s.is_active = TRUE")
            if category:
                where.append(f"s.slug LIKE ${len(params)+1}")
                params.append(f"%/{category}/%")
            where_clause = ("WHERE " + " AND ".join(where)) if where else ""
            params.extend([limit, offset])
            q = f"""
                SELECT s.id, s.slug, s.name, s.expires_at, s.reward_summary,
                       s.last_seen_at, s.is_active, COUNT(c.id) AS challenge_count
                FROM sbc_sets s
                LEFT JOIN sbc_challenges c ON s.id = c.sbc_set_id
                {where_clause}
                GROUP BY s.id, s.slug, s.name, s.expires_at, s.reward_summary, s.last_seen_at, s.is_active
                ORDER BY s.last_seen_at DESC
                LIMIT ${len(params)-1} OFFSET ${len(params)}
            """
            rows = await con.fetch(q, *params)
            return {
                "sbcs": [{
                    "id": r["id"],
                    "slug": r["slug"],
                    "name": r["name"],
                    "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                    "rewards": r["reward_summary"],
                    "challenge_count": r["challenge_count"],
                    "last_updated": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
                    "is_active": r["is_active"],
                    "category": r["slug"].split("/")[2] if len(r["slug"].split("/")) > 2 else "unknown",
                } for r in rows],
                "pagination": {"limit": limit, "offset": offset, "has_more": len(rows) == limit}
            }
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch SBCs: {e}")

# ---------- API: SBC details ----------
@app.get("/api/sbcs/{sbc_id}")
async def get_sbc_details(sbc_id: int):
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            sbc = await con.fetchrow("""
              SELECT id, slug, name, repeatable_text, expires_at, site_cost, reward_summary, last_seen_at, is_active
              FROM sbc_sets WHERE id = $1
            """, sbc_id)
            if not sbc:
                raise HTTPException(404, "SBC not found")

            challenges = await con.fetch("""
              SELECT id, name, site_cost, reward_text, order_index
              FROM sbc_challenges WHERE sbc_set_id = $1 ORDER BY order_index
            """, sbc_id)

            data = []
            for ch in challenges:
                reqs = await con.fetch("""
                    SELECT kind, key, op, value
                    FROM sbc_requirements WHERE challenge_id = $1 ORDER BY id
                """, ch["id"])
                data.append({
                    "id": ch["id"],
                    "name": ch["name"],
                    "cost": ch["site_cost"],
                    "reward": ch["reward_text"],
                    "order": ch["order_index"],
                    "requirements": [{"kind": r["kind"], "key": r["key"], "operator": r["op"], "value": r["value"]} for r in reqs]
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
                    "last_updated": sbc["last_seen_at"].isoformat() if sbc["last_seen_at"] else None,
                    "is_active": sbc["is_active"],
                    "url": f"https://www.fut.gg{sbc['slug']}",
                },
                "challenges": data
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch SBC details: {e}")

# ---------- API: calculate solution (DB-backed or mock) ----------
@app.get("/api/challenges/{challenge_id}/solution")
async def get_challenge_solution(challenge_id: int):
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            challenge = await con.fetchrow("""
                SELECT c.id, c.name, s.name AS sbc_name
                FROM sbc_challenges c
                JOIN sbc_sets s ON c.sbc_set_id = s.id
                WHERE c.id = $1
            """, challenge_id)
            if not challenge:
                raise HTTPException(404, "Challenge not found")

            reqs = await con.fetch("""
                SELECT kind, key, op, value
                FROM sbc_requirements
                WHERE challenge_id = $1
            """, challenge_id)

            req_list = [{"kind": r["kind"], "key": r["key"], "op": r["op"], "value": r["value"]} for r in reqs]
            solution = solve_simple_sbc(req_list)

            return {
                "challenge": {"id": challenge["id"], "name": challenge["name"], "sbc_name": challenge["sbc_name"]},
                "solution": solution
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to calculate solution: {e}")

# ---------- Force crawl ----------
@app.post("/force")
async def force():
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not available")
    try:
        from scheduler import run_job
        await run_job()
        status["ready"] = True
        status["last_run"] = "manual"
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Crawl failed: {e}")

# ---------- DB stats ----------
@app.get("/db-stats")
async def db_stats():
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not configured")
    try:
        from db import get_pool
        pool = await get_pool()
        async with pool.acquire() as con:
            set_count = await con.fetchval("SELECT COUNT(*) FROM sbc_sets WHERE is_active = TRUE")
            challenge_count = await con.fetchval("""
                SELECT COUNT(*) FROM sbc_challenges c
                JOIN sbc_sets s ON c.sbc_set_id = s.id
                WHERE s.is_active = TRUE
            """)
            requirement_count = await con.fetchval("""
                SELECT COUNT(*) FROM sbc_requirements r
                JOIN sbc_challenges c ON r.challenge_id = c.id
                JOIN sbc_sets s ON c.sbc_set_id = s.id
                WHERE s.is_active = TRUE
            """)
            return {
                "active_sets": set_count,
                "total_challenges": challenge_count,
                "total_requirements": requirement_count,
                "status": "connected"
            }
    except Exception as e:
        raise HTTPException(500, f"Database query failed: {e}")

# ---------- Minimal root UI (kept) ----------
@app.get("/", response_class=HTMLResponse)
async def root_page():
    return HTMLResponse("<h1>FUT SBC Browser</h1><p>Service is running.</p>")

# ---------- Local dev entrypoint ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), log_level="info", reload=False)
