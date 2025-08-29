import asyncio
from datetime import datetime, timezone, timedelta

from db import upsert_set, mark_all_inactive_before

RUN_AT_HOUR_UTC = 17  # daily

async def run_job(debug_first: bool = False):
    # Lazy import to avoid import-time issues
    try:
        from crawler import crawl_all_sets
    except Exception as e:
        print(f"❌ scheduler: failed to import crawl_all_sets: {e}")
        return

    try:
        print("🔄 scheduler: starting crawl…")
        sets = await crawl_all_sets(debug_first=debug_first)
        print(f"✅ scheduler: fetched {len(sets)} sets")

        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            await mark_all_inactive_before(cutoff)
        except Exception as e:
            print(f"⚠️ scheduler: mark_all_inactive_before failed: {e}")

        upserts = 0
        for payload in sets:
            try:
                await upsert_set(payload)
                upserts += 1
            except Exception as e:
                print(f"⚠️ scheduler: upsert failed for {payload.get('slug')}: {e}")

        print(f"✅ scheduler: upserted {upserts}/{len(sets)} sets")
    except Exception as e:
        print(f"💥 scheduler: run_job failed: {e}")

async def _sleep_until_next_run(hour_utc: int):
    while True:
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run + timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        return

async def schedule_loop():
    print("🕒 scheduler: loop started")
    # Initial run on boot
    try:
        await run_job(debug_first=True)
    except Exception as e:
        print(f"⚠️ scheduler: initial run failed: {e}")

    while True:
        try:
            await _sleep_until_next_run(RUN_AT_HOUR_UTC)
            await run_job(debug_first=False)
        except Exception as e:
            print(f"⚠️ scheduler: loop error: {e}")
            await asyncio.sleep(60)
