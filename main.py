import os
import sys
import asyncio
import traceback
from typing import Optional, Any, List, Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

print("🚀 Starting FUT SBC Tracker…")
print(f"🐍 Python: {sys.version}")
print(f"🌐 PORT: {os.getenv('PORT', '8080')}")
print(f"🔗 DATABASE_URL: {'✅ Set' if os.getenv('DATABASE_URL') else '❌ Missing'}")

app = FastAPI(title="FUT SBC Tracker", description="FIFA Ultimate Team SBC tracker and solver")

status: Dict[str, Any] = {"ready": False, "startup_error": None, "imports": {}, "last_run": None}

def _test_imports() -> Dict[str, str]:
    results = {}
    def try_imp(name):
        try:
            __import__(name)
            results[name] = "✅ OK"
        except Exception as e:
            results[name] = f"❌ {e}"
    for m in ["asyncpg", "httpx", "bs4", "pytz", "db", "scheduler", "crawler", "normalizer"]:
        try_imp(m)
    return results

status["imports"] = _test_imports()
for k, v in status["imports"].items():
    print(f"🧪 {k}: {v}")

# Serve built SPA if you want (optional). Put your built files under ./static
if os.path.exists("static/index.html"):
    app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def ui_root():
        return FileResponse("static/index.html")
else:
    @app.get("/", response_class=HTMLResponse)
    async def root_min():
        return HTMLResponse("<h1>FUT SBC Browser</h1><p>Service is running.</p>")

# ---------------- Startup: schedule loop only (single place runs the crawl) ----------------

@app.on_event("startup")
async def on_startup():
    print(f"🧩 DATABASE_URL configured: {bool(os.getenv('DATABASE_URL'))}")
    if not os.getenv("DATABASE_URL"):
        status["startup_error"] = "DATABASE_URL not configured"
        return
    try:
        # Initialize DB (schema)
        from db import init_db
        await init_db()
        # Start scheduler loop (it will do an initial run itself)
        try:
            from scheduler import schedule_loop
            asyncio.create_task(schedule_loop())
            print("✅ Background tasks scheduled")
        except Exception as e:
            print(f"⚠️ Scheduler not started: {e}")
        status["ready"] = True
    except Exception as e:
        status["startup_error"] = f"{type(e).__name__}: {e}"
        print("💥 Startup failed:", e)
        print("".join(traceback.format_exc()))

# ---------------- Health ----------------

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

# ---------------- API: categories ----------------

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

# ---------------- API: list SBCs ----------------

@app.get("/api/sbcs")
async def get_sbcs(
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(50),
    offset: int = Query(0),
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
                ORDER BY s.last_seen_at DESC NULLS LAST
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

# ---------------- API: SBC details ----------------

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
                    SELECT id, kind, key, op, value
                    FROM sbc_requirements WHERE challenge_id = $1 ORDER BY id
                """, ch["id"])
                data.append({
                    "id": ch["id"],
                    "name": ch["name"],
                    "cost": ch["site_cost"],
                    "reward": ch["reward_text"],
                    "order": ch["order_index"],
                    "requirements": [{"id": r["id"], "kind": r["kind"], "key": r["key"], "operator": r["op"], "value": r["value"]} for r in reqs]
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

# ---------------- Force crawl (manual) ----------------

@app.post("/force")
async def force():
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "Database not available")
    try:
        from scheduler import run_job
        await run_job(debug_first=True)
        status["last_run"] = "manual"
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Crawl failed: {e}")

# ---------------- DB stats ----------------

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), log_level="info")
