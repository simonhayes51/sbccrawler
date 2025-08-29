# scheduler.py
import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo  # built-in py3.9+
from crawler import crawl_all_sets
from db import upsert_set, mark_all_inactive_before

UK = ZoneInfo("Europe/London")

async def run_job():
    print("🔄 SBC crawl started")
    sets = await crawl_all_sets()
    for s in sets:
        await upsert_set(s)
    # Anything not seen in this run is marked inactive
    await mark_all_inactive_before(datetime.now(tz=ZoneInfo("UTC")))
    print(f"✅ {len(sets)} SBC sets upserted at {datetime.now(tz=ZoneInfo('UTC')).isoformat()}")

def next_uk_18():
    now_uk = datetime.now(UK)
    target_today = datetime.combine(now_uk.date(), time(18, 0, 0), tzinfo=UK)
    return target_today if now_uk <= target_today else target_today + timedelta(days=1)

async def schedule_loop():
    while True:
        target = next_uk_18()
        wait_seconds = (target - datetime.now(UK)).total_seconds()
        # Safety clamp
        if wait_seconds < 0:
            wait_seconds = 1
        print(f"⏳ Sleeping {int(wait_seconds)}s until {target.isoformat()}")
        await asyncio.sleep(wait_seconds)
        try:
            await run_job()
        except Exception as e:
            # Don't crash the loop
            print(f"💥 Scheduled run failed: {e}")
            await asyncio.sleep(5)
