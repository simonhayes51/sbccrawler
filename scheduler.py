# scheduler.py
import asyncio
from datetime import datetime, timezone, timedelta

from db import upsert_set, mark_all_inactive_before

RUN_AT_HOUR_UTC = 17  # choose whatever; 17:00 UTC by default

async def run_job(debug_first: bool = False) -> None:
    """
    Run one crawl + upsert pass.
    Lazy-import crawler so scheduler can import even if crawler is temporarily broken.
    """
    try:
        from crawler import crawl_all_sets  # lazy import fixes circular/early import issues
    except Exception as e:
        print(f"❌ scheduler: failed to import crawl_all_sets: {e}")
        return

    try:
        print("🔄 scheduler: starting crawl…")
        sets = await crawl_all_sets(debug_first=debug_first)
        print(f"✅ scheduler: fetched {len(sets)} sets")

        # Mark old sets inactive first (optional: yesterday)
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            await mark_all_inactive_before(cutoff)
        except Exception as e:
            print(f"⚠️ scheduler: mark_all_inactive_before failed: {e}")

        # Upsert each set
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

async def _sleep_until_next_run(hour_utc: int) -> None:
    """
    Sleep until the next time today's/tomorrow's hour_utc occurs.
    """
    while True:
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        if next_run <= now:
            # schedule tomorrow
            next_run = next_run.replace(day=now.day) + timedelta(days=1)
        seconds = (next_run - now).total_seconds()
        if seconds > 0:
            await asyncio.sleep(seconds)
            return
        await asyncio.sleep(60)

async def schedule_loop() -> None:
    """
    Simple daily loop. You can make this every 6/12/24h if you prefer.
    """
    print("🕒 scheduler: loop started")
    # Optional immediate run on boot:
    try:
        await run_job(debug_first=True)
    except Exception as e:
        print(f"⚠️ scheduler: initial run failed: {e}")

    # Daily at RUN_AT_HOUR_UTC
    while True:
        try:
            from datetime import timedelta
            await _sleep_until_next_run(RUN_AT_HOUR_UTC)
            await run_job(debug_first=False)
        except Exception as e:
            print(f"⚠️ scheduler: loop error: {e}")
            await asyncio.sleep(60)
