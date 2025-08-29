# main.py
import os, asyncio, traceback
from fastapi import FastAPI, HTTPException
from db import init_db
from scheduler import run_job, schedule_loop

app = FastAPI()
status = {"ready": False, "last_run": None, "startup_error": None}

@app.on_event("startup")
async def on_startup():
    print(f"🧩 DATABASE_URL set: {bool(os.getenv('DATABASE_URL'))}")
    try:
        await init_db()
        await run_job()
        asyncio.create_task(schedule_loop())
        status.update(ready=True, last_run="startup")
        print("✅ Startup complete")
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
    status.update(ready=True, last_run="force")
    return {"ok": True}
