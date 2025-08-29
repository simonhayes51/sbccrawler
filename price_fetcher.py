# price_fetcher.py
import os
import asyncio
import asyncpg
import httpx
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict

PRICE_API_BASE = os.getenv("PRICE_API_BASE")  # e.g. https://backend...railway.app
PLATFORM = os.getenv("PRICE_PLATFORM", "ps")


@dataclass
class Player:
    name: str
    rating: int
    position: str
    league: str
    club: str
    nation: str
    price: int
    rarity: str = "rare"
    is_special: bool = False
    card_id: Optional[int] = None


class PriceDatabase:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.last_update: Optional[datetime] = None


price_db = PriceDatabase()


async def _get_pool():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return await asyncpg.create_pool(url, min_size=1, max_size=5)


async def get_player_price(card_id: int) -> int:
    if not card_id:
        return 0
    if not PRICE_API_BASE:
        return 0
    url = f"{PRICE_API_BASE}/api/fut-player-price/{card_id}?platform={PLATFORM}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "price" in data:
                return int(data["price"]) or 0
            return int(data) if str(data).isdigit() else 0
    except Exception:
        return 0


async def bootstrap_from_db(limit: int = 5000, min_rating: int = 79):
    pool = await _get_pool()
    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT 
              player_name, rating, position, 
              COALESCE(league,'') as league,
              COALESCE(club,'')   as club,
              COALESCE(nation,'') as nation,
              COALESCE(card_id, 0) as card_id
            FROM fut_players
            WHERE rating >= $1
            ORDER BY rating ASC
            LIMIT $2
            """,
            min_rating,
            limit,
        )

    tmp = {}
    for r in rows:
        tmp[r["player_name"]] = Player(
            name=r["player_name"],
            rating=int(r["rating"] or 0),
            position=r["position"] or "CM",
            league=r["league"],
            club=r["club"],
            nation=r["nation"],
            price=0,
            card_id=int(r["card_id"]) if r["card_id"] else None,
        )

    async def hydrate_one(p: Player):
        p.price = await get_player_price(p.card_id) if p.card_id else 0

    first = list(tmp.values())[:500]
    await asyncio.gather(*(hydrate_one(p) for p in first))

    price_db.players = tmp
    price_db.last_update = datetime.now()


async def update_player_prices():
    if not price_db.players:
        return

    async def refresh(p: Player):
        new_price = await get_player_price(p.card_id) if p.card_id else 0
        if new_price:
            p.price = new_price

    players = list(price_db.players.values())
    slice_size = max(200, len(players) // 10)
    for i in range(0, len(players), slice_size):
        chunk = players[i : i + slice_size]
        await asyncio.gather(*(refresh(p) for p in chunk))

    price_db.last_update = datetime.now()


async def price_update_loop():
    while True:
        try:
            await update_player_prices()
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"💥 Price update failed: {e}")
            await asyncio.sleep(300)


# Example solver (replace mock one)
async def solve_sbc_challenge(requirements):
    """
    Dummy SBC solver using real players+prices.
    Replace with your proper algorithm later.
    """
    solution = []
    total_cost = 0
    for req in requirements:
        candidate = next(iter(price_db.players.values()), None)
        if candidate:
            solution.append(candidate)
            total_cost += candidate.price
    return {"players": solution, "cost": total_cost}
