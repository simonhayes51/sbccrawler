# scheduler.py
import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from crawler import crawl_all_sets
from db import upsert_set, mark_all_inactive_before

UK = ZoneInfo("Europe/London")

async def run_job():
    print("🔄 SBC crawl started")
    sets = await crawl_all_sets()
    for s in sets:
        await upsert_set(s)
    await mark_all_inactive_before(datetime.now(ZoneInfo("UTC")))
    print(f"✅ {len(sets)} SBC sets upserted")

def next_uk_18():
    now = datetime.now(UK)
    target = datetime.combine(now.date(), time(18,0), tzinfo=UK)
    if now > target:
        target += timedelta(days=1)
    return target

async def schedule_loop():
    while True:
        target = next_uk_18()
        wait = max(1, int((target - datetime.now(UK)).total_seconds()))
        print(f"⏳ Sleeping {wait}s until {target.isoformat()}")
        await asyncio.sleep(wait)
        try:
            await run_job()
        except Exception as e:
            print(f"💥 Scheduled run failed: {e}")
            await asyncio.sleep(5)
