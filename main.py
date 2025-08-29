import asyncio
import uvicorn
from fastapi import FastAPI
from db import init_db
from scheduler import run_job, schedule_loop

app = FastAPI()
last_run = None

@app.on_event("startup")
async def startup():
    global last_run
    await init_db()
    await run_job()
    last_run = "initial"
    asyncio.create_task(schedule_loop())

@app.get("/force")
async def force_run():
    await run_job()
    return {"status":"forced"}

@app.get("/last")
async def last_status():
    return {"last_run": str(last_run)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
