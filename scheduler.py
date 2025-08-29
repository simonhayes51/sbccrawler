# scheduler.py
import asyncio
from datetime import datetime, time, timedelta
import pytz  # container-friendly tz
from crawler import crawl_all_sets
from db import save_set, mark_all_inactive_before

UK = pytz.timezone("Europe/London")

async def run_job():
    print("🔄 SBC crawl started")
    start_time = datetime.now(pytz.UTC)
    sets = await crawl_all_sets()

    print(f"📊 Found {len(sets)} SBC sets")
    success_count = 0
    for s in sets:
        try:
            # Derive slug if missing
            slug = s.get("slug")
            if not slug:
                url = s.get("url", "").rstrip("/")
                parts = [p for p in url.split("/") if p]
                slug = parts[-1] if parts else None

            await save_set(
                slug=slug,
                url=s.get("url"),
                name=s.get("name"),
                expires_at=s.get("expires_at"),
                repeatable=s.get("repeatable", False),
                rewards=s.get("rewards", []),
                challenges=s.get("sub_challenges", []),
            )
            success_count += 1
            print(f"💾 Saved {s.get('name')}")
        except Exception as e:
            print(f"⚠️ Failed to save set {s.get('name', 'Unknown')}: {e}")

    await mark_all_inactive_before(start_time)
    print(f"✅ {success_count}/{len(sets)} SBC sets successfully processed")

def next_uk_18():
    now = datetime.now(UK)
    target = datetime.combine(now.date(), time(18, 0))
    target = UK.localize(target)
    if now > target:
        target += timedelta(days=1)
    return target

async def schedule_loop():
    while True:
        target = next_uk_18()
        now = datetime.now(UK)
        wait = max(1, int((target - now).total_seconds()))
        print(f"⏳ Sleeping {wait}s until {target.isoformat()}")
        await asyncio.sleep(wait)
        try:
            await run_job()
        except Exception as e:
            print(f"💥 Scheduled run failed: {e}")
            await asyncio.sleep(300)  # backoff on error
