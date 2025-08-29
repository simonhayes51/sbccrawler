# main.py
import os
import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ---- local modules ----
from scheduler import schedule_loop, run_job
from db import get_all_sets

# Optional: if you have this in db.py; otherwise remove the endpoint below or implement it.
try:
    from db import get_set_by_slug  # type: ignore
except Exception:
    get_set_by_slug = None  # endpoint will 404 if called

# =========================
# App + CORS
# =========================
app = FastAPI(title="SBC Crawler API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # adjust if you want to lock down later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Health state
# =========================
HEALTH = {
    "status": "ok",
    "ready": False,
    "last_run": None,          # "startup" or ISO timestamp set after a crawl
    "startup_error": None,
    "database_configured": bool(os.getenv("DATABASE_URL")),
}

# =========================
# Startup: kick off initial crawl + schedule
# =========================
@app.on_event("startup")
async def on_startup():
    try:
        # fire an initial crawl, but don't block app serving
        async def initial():
            try:
                HEALTH["last_run"] = "startup"
                await run_job()
                HEALTH["ready"] = True
            except Exception as e:
                HEALTH["startup_error"] = f"{type(e).__name__}: {e}"
                HEALTH["status"] = "error"
                HEALTH["ready"] = False

        asyncio.create_task(initial())
        asyncio.create_task(schedule_loop())
    except Exception as e:
        HEALTH["startup_error"] = f"{type(e).__name__}: {e}"
        HEALTH["status"] = "error"
        HEALTH["ready"] = False

# =========================
# Routes
# =========================
@app.get("/")
async def root():
    return {"ok": True}

@app.get("/api/health")
async def api_health():
    return {
        "status": HEALTH["status"],
        "ready": HEALTH["ready"],
        "last_run": HEALTH["last_run"],
        "startup_error": HEALTH["startup_error"],
        "database_configured": HEALTH["database_configured"],
    }

@app.post("/api/debug/trigger-crawl")
async def trigger_crawl():
    """
    Manually trigger a crawl from the UI.
    """
    try:
        await run_job()
        HEALTH["last_run"] = datetime.now(timezone.utc).isoformat()
        HEALTH["ready"] = True
        return {"ok": True, "message": "Manual crawl completed"}
    except Exception as e:
        HEALTH["status"] = "error"
        HEALTH["startup_error"] = f"{type(e).__name__}: {e}"
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sbcs")
async def list_sbcs():
    """
    Return all active SBC sets saved by the scheduler.
    Each row should include: slug, url, name, expires_at, repeatable, rewards, challenges, etc.
    """
    sets = await get_all_sets()
    return {"count": len(sets), "sets": sets}

@app.get("/api/sbc/{slug}")
async def get_sbc(slug: str):
    """
    Return a single SBC set by slug.
    Requires db.get_set_by_slug() to exist; otherwise this 404s by design.
    """
    if not callable(get_set_by_slug):
        raise HTTPException(status_code=404, detail="Endpoint not available")
    row = await get_set_by_slug(slug)
    if not row:
        raise HTTPException(status_code=404, detail="SBC not found")
    return row

# =========================
# Local uvicorn (optional)
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        log_level="info",
        reload=False,
    )
