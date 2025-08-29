# main.py
import os, asyncio, traceback
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from db import init_db
from scheduler import run_job, schedule_loop

app = FastAPI()
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
        
        # Return summary with detailed info about first few sets
        return {
            "total_count": len(sets),
            "sets_with_challenges": len([s for s in sets if s["sub_challenges"]]),
            "sample_sets": sets[:3],  # First 3 sets with full details
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

@app.get("/db-stats")
async def db_stats():
    """Get database statistics"""
    from db import get_pool
    
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
