# main.py
import os
import asyncio
import uvicorn
from fastapi import FastAPI, HTTPException
from db import init_db
from scheduler import run_job, schedule_loop

app = FastAPI()
_status = {"last_run": None, "ready": False}

@app.on_event("startup")
async def startup():
    # Log env presence
    has_db = bool(os.getenv("DATABASE_URL"))
    print(f"🧩 DATABASE_URL present: {has_db}")
    if not has_db:
        # Don’t crash; expose /health with a clear error
        print("❌ DATABASE_URL is not set. Set it in Railway service variables.")
        return
    try:
        await init_db()
        await run_job()  # initial run
        _status["last_run"] = "startup"
        _status["ready"] = True
        asyncio.create_task(schedule_loop())
    except Exception as e:
        print(f"💥 Startup failed: {e}")
        # keep server up so you can hit /health and logs

@app.get("/health")
async def health():
    if not os.getenv("DATABASE_URL"):
        return {"ok": False, "error": "DATABASE_URL missing"}
    return {"ok": _status["ready"], "last_run": _status["last_run"]}

@app.post("/force")
async def force_run():
    if not os.getenv("DATABASE_URL"):
        raise HTTPException(500, "DATABASE_URL missing")
    await run_job()
    _status["last_run"] = "force"
    _status["ready"] = True
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
