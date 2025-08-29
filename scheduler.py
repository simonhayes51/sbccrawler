import asyncio
from datetime import datetime, timezone
import pytz
from crawler import crawl_all_sets
from db import upsert_set, mark_all_inactive_before

UK = pytz.timezone("Europe/London")

async def run_job():
    print("🔄 SBC crawl started")
    sets = await crawl_all_sets()
    for s in sets:
        await upsert_set(s)
    await mark_all_inactive_before(datetime.now(timezone.utc))
    print(f"✅ {len(sets)} SBC sets upserted at {datetime.now(timezone.utc)}")

async def schedule_loop():
    while True:
        now = datetime.now(UK)
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now > target:
            target = target + pytz.timedelta(days=1)
        wait = (target - now).total_seconds()
        await asyncio.sleep(wait)
        await run_job()
