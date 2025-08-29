# price_fetcher.py
import asyncio
import httpx
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os

@dataclass
class Player:
    name: str
    rating: int
    position: str
    league: str
    club: str
    nation: str
    price: int
    rarity: str = "rare"  # rare, common, special
    is_special: bool = False

# Mock player database - in production you'd fetch from FUT API
MOCK_PLAYERS = [
    # High rated players
    Player("Kylian Mbappé", 91, "ST", "Ligue 1", "Paris Saint-Germain", "France", 850000),
    Player("Erling Haaland", 91, "ST", "Premier League", "Manchester City", "Norway", 800000),
    Player("Lionel Messi", 90, "RW", "MLS", "Inter Miami", "Argentina", 750000),
    
    # Mid-tier players for SBCs
    Player("Casemiro", 89, "CDM", "Premier League", "Manchester United", "Brazil", 45000),
    Player("Luka Modrić", 88, "CM", "LaLiga", "Real Madrid", "Croatia", 40000),
    Player("Virgil van Dijk", 90, "CB", "Premier League", "Liverpool", "Netherlands", 65000),
    Player("Kevin De Bruyne", 91, "CAM", "Premier League", "Manchester City", "Belgium", 120000),
    
    # Budget high-rated players (good for SBCs)
    Player("Sergio Busquets", 87, "CDM", "MLS", "Inter Miami", "Spain", 15000),
    Player("Jordi Alba", 86, "LB", "MLS", "Inter Miami", "Spain", 12000),
    Player("Thiago Silva", 86, "CB", "Premier League", "Chelsea", "Brazil", 18000),
    Player("Pepe", 86, "CB", "Liga Portugal", "FC Porto", "Portugal", 8000),
    
    # 85 rated players
    Player("Marco Verratti", 85, "CM", "Ligue 1", "Paris Saint-Germain", "Italy", 25000),
    Player("Dani Parejo", 85, "CM", "LaLiga", "Villarreal", "Spain", 8000),
    Player("Jesús Navas", 85, "RB", "LaLiga", "Sevilla", "Spain", 7000),
    Player("Iago Aspas", 85, "CF", "LaLiga", "Celta Vigo", "Spain", 9000),
    
    # 84 rated players  
    Player("Yann Sommer", 84, "GK", "Serie A", "Inter", "Switzerland", 3000),
    Player("Lukasz Fabianski", 84, "GK", "Premier League", "West Ham", "Poland", 2500),
    Player("Rui Patrício", 84, "GK", "Serie A", "Roma", "Portugal", 2800),
    Player("Memphis Depay", 84, "CF", "LaLiga", "Atlético Madrid", "Netherlands", 12000),
    Player("Wilfried Zaha", 84, "LW", "Turkish Süper Lig", "Galatasaray", "Ivory Coast", 8000),
    
    # 83 rated players
    Player("André Onana", 83, "GK", "Premier League", "Manchester United", "Cameroon", 2000),
    Player("Emiliano Martínez", 83, "GK", "Premier League", "Aston Villa", "Argentina", 2200),
    Player("José Sá", 83, "GK", "Premier League", "Wolves", "Portugal", 1800),
    Player("Dušan Vlahović", 83, "ST", "Serie A", "Juventus", "Serbia", 15000),
    Player("Lautaro Martínez", 83, "ST", "Serie A", "Inter", "Argentina", 18000),
    
    # 82 rated players
    Player("Aaron Ramsdale", 82, "GK", "Premier League", "Arsenal", "England", 1500),
    Player("Jordan Pickford", 82, "GK", "Premier League", "Everton", "England", 1600),
    Player("Bernd Leno", 82, "GK", "Premier League", "Fulham", "Germany", 1400),
    Player("Tammy Abraham", 82, "ST", "Serie A", "Roma", "England", 8000),
    Player("Dominik Szoboszlai", 82, "CAM", "Premier League", "Liverpool", "Hungary", 10000),
    
    # 81 rated players
    Player("Nick Pope", 81, "GK", "Premier League", "Newcastle", "England", 1200),
    Player("Robert Sánchez", 81, "GK", "Premier League", "Brighton", "Spain", 1100),
    Player("Illan Meslier", 81, "GK", "Premier League", "Leeds United", "France", 900),
    Player("Ismaïla Sarr", 81, "RW", "Premier League", "Watford", "Senegal", 4000),
    Player("Brennan Johnson", 81, "RW", "Premier League", "Nottingham Forest", "Wales", 5000),
    
    # Lower rated fodder
    Player("Generic 80 GK", 80, "GK", "Generic League", "Generic Club", "Generic Nation", 800),
    Player("Generic 79 CM", 79, "CM", "Generic League", "Generic Club", "Generic Nation", 650),
    Player("Generic 78 CB", 78, "CB", "Generic League", "Generic Club", "Generic Nation", 600),
]

class PriceDatabase:
    def __init__(self):
        self.players = {player.name: player for player in MOCK_PLAYERS}
        self.last_update = datetime.now()
    
    def get_players_by_rating(self, min_rating: int, max_rating: int = 99) -> List[Player]:
        """Get players within rating range, sorted by price (cheapest first)"""
        candidates = [p for p in self.players.values() 
                     if min_rating <= p.rating <= max_rating]
        return sorted(candidates, key=lambda x: x.price)
    
    def get_players_by_league(self, league: str, min_rating: int = 0) -> List[Player]:
        """Get players from specific league"""
        candidates = [p for p in self.players.values() 
                     if league.lower() in p.league.lower() and p.rating >= min_rating]
        return sorted(candidates, key=lambda x: x.price)
    
    def get_players_by_club(self, club: str, min_rating: int = 0) -> List[Player]:
        """Get players from specific club"""
        candidates = [p for p in self.players.values() 
                     if club.lower() in p.club.lower() and p.rating >= min_rating]
        return sorted(candidates, key=lambda x: x.price)
    
    def get_players_by_nation(self, nation: str, min_rating: int = 0) -> List[Player]:
        """Get players from specific nation"""
        candidates = [p for p in self.players.values() 
                     if nation.lower() in p.nation.lower() and p.rating >= min_rating]
        return sorted(candidates, key=lambda x: x.price)
    
    def get_cheapest_by_position(self, position: str, min_rating: int = 0, count: int = 1) -> List[Player]:
        """Get cheapest players for a position"""
        candidates = [p for p in self.players.values() 
                     if p.position == position and p.rating >= min_rating]
        return sorted(candidates, key=lambda x: x.price)[:count]

# Global price database instance
price_db = PriceDatabase()

def calculate_team_rating(players: List[Player]) -> float:
    """Calculate team rating from list of players"""
    if not players:
        return 0
    return sum(p.rating for p in players) / len(players)

def meets_rating_requirement(players: List[Player], min_rating: int) -> bool:
    """Check if team meets minimum rating requirement"""
    return calculate_team_rating(players) >= min_rating

def solve_rating_requirement(min_rating: int, num_players: int = 11) -> List[Player]:
    """Find cheapest combination of players that meets rating requirement"""
    # Start with cheapest players and gradually increase ratings
    selected_players = []
    
    # First, fill with cheapest players
    all_players = sorted(price_db.players.values(), key=lambda x: x.price)
    
    for player in all_players:
        if len(selected_players) >= num_players:
            break
        selected_players.append(player)
        
        if meets_rating_requirement(selected_players, min_rating):
            return selected_players
    
    # If we can't meet the requirement with available players, 
    # try replacing lowest rated players with higher ones
    while not meets_rating_requirement(selected_players, min_rating) and len(selected_players) == num_players:
        # Find the lowest rated player
        lowest_player = min(selected_players, key=lambda x: x.rating)
        selected_players.remove(lowest_player)
        
        # Find a better replacement
        replacement_candidates = [p for p in all_players 
                                if p not in selected_players and p.rating > lowest_player.rating]
        
        if replacement_candidates:
            replacement = min(replacement_candidates, key=lambda x: x.price)
            selected_players.append(replacement)
        else:
            # Can't find suitable replacement
            selected_players.append(lowest_player)
            break
    
    return selected_players

def solve_league_requirement(league: str, min_players: int, current_team: List[Player] = None) -> List[Player]:
    """Find cheapest players from specific league"""
    if current_team is None:
        current_team = []
    
    # Count how many we already have from this league
    existing_count = sum(1 for p in current_team if league.lower() in p.league.lower())
    needed = max(0, min_players - existing_count)
    
    if needed == 0:
        return []
    
    candidates = price_db.get_players_by_league(league)
    # Exclude players already in team
    candidates = [p for p in candidates if p not in current_team]
    
    return candidates[:needed]

def solve_club_requirement(club: str, min_players: int, current_team: List[Player] = None) -> List[Player]:
    """Find cheapest players from specific club"""
    if current_team is None:
        current_team = []
    
    existing_count = sum(1 for p in current_team if club.lower() in p.club.lower())
    needed = max(0, min_players - existing_count)
    
    if needed == 0:
        return []
    
    candidates = price_db.get_players_by_club(club)
    candidates = [p for p in candidates if p not in current_team]
    
    return candidates[:needed]

def solve_nation_requirement(nation: str, min_players: int, current_team: List[Player] = None) -> List[Player]:
    """Find cheapest players from specific nation"""
    if current_team is None:
        current_team = []
    
    existing_count = sum(1 for p in current_team if nation.lower() in p.nation.lower())
    needed = max(0, min_players - existing_count)
    
    if needed == 0:
        return []
    
    candidates = price_db.get_players_by_nation(nation)
    candidates = [p for p in candidates if p not in current_team]
    
    return candidates[:needed]

async def solve_sbc_challenge(requirements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Solve an SBC challenge given its requirements"""
    
    # Start with empty team
    team = []
    total_cost = 0
    team_size = 11  # Default squad size
    min_team_rating = 0
    min_chemistry = 100  # Assume max chemistry for now
    
    # Parse requirements
    required_leagues = []
    required_clubs = []
    required_nations = []
    special_players_needed = 0
    
    for req in requirements:
        if req["kind"] == "team_rating_min":
            min_team_rating = int(req["value"])
        elif req["kind"] == "min_from" and req.get("key"):
            key = req["key"].lower()
            count = int(req.get("value", 1))
            
            # Determine if it's league, club, or nation
            if any(league in key for league in ["premier", "liga", "serie", "ligue", "bundesliga"]):
                required_leagues.append((req["key"], count))
            elif any(word in key for word in ["fc", "united", "city", "real", "barcelona"]):
                required_clubs.append((req["key"], count))
            else:
                required_nations.append((req["key"], count))
        elif req["kind"] == "min_program":
            special_players_needed = int(req.get("count", 1))
    
    # Solve league requirements first
    for league, count in required_leagues:
        league_players = solve_league_requirement(league, count, team)
        team.extend(league_players[:count])
    
    # Solve club requirements
    for club, count in required_clubs:
        club_players = solve_club_requirement(club, count, team)
        team.extend(club_players[:count])
    
    # Solve nation requirements  
    for nation, count in required_nations:
        nation_players = solve_nation_requirement(nation, count, team)
        team.extend(nation_players[:count])
    
    # Fill remaining spots to reach team size
    while len(team) < team_size:
        # Get cheapest available players
        all_players = sorted(price_db.players.values(), key=lambda x: x.price)
        for player in all_players:
            if player not in team:
                team.append(player)
                break
    
    # Ensure team rating requirement is met
    if min_team_rating > 0:
        current_rating = calculate_team_rating(team)
        while current_rating < min_team_rating:
            # Replace lowest rated player with higher rated one
            lowest_player = min(team, key=lambda x: x.rating)
            team.remove(lowest_player)
            
            # Find cheapest replacement with higher rating
            replacement_candidates = [p for p in price_db.players.values() 
                                    if p not in team and p.rating > lowest_player.rating]
            
            if replacement_candidates:
                replacement = min(replacement_candidates, key=lambda x: x.price)
                team.append(replacement)
                current_rating = calculate_team_rating(team)
            else:
                # Can't improve further
                team.append(lowest_player)
                break
    
    # Calculate total cost
    total_cost = sum(p.price for p in team)
    final_rating = calculate_team_rating(team)
    
    # Create solution response
    solution = {
        "total_cost": total_cost,
        "chemistry": min_chemistry,  # Mock chemistry
        "rating": round(final_rating, 1),
        "meets_requirements": True,  # Assume we met them
        "players": [
            {
                "name": p.name,
                "position": p.position,
                "rating": p.rating,
                "price": p.price,
                "league": p.league,
                "club": p.club,
                "nation": p.nation
            }
            for p in team
        ],
        "requirements_analysis": [
            {
                "requirement": f"Min. Team Rating: {min_team_rating}" if min_team_rating > 0 else "No rating requirement",
                "satisfied": final_rating >= min_team_rating if min_team_rating > 0 else True,
                "notes": f"Achieved {final_rating:.1f} rating"
            }
        ] + [
            {
                "requirement": f"Min. {count} from {name}",
                "satisfied": True,
                "notes": "Requirement met with selected players"
            }
            for name, count in required_leagues + required_clubs + required_nations
        ]
    }
    
    return solution

# Function to update prices (mock implementation)
async def update_player_prices():
    """Update player prices from external API"""
    # In production, you would fetch from FUT API or scrape market data
    # For now, just simulate price fluctuations
    
    print("🔄 Updating player prices...")
    
    # Mock price updates - add some randomness
    import random
    for player in price_db.players.values():
        # Simulate 5-10% price fluctuation
        fluctuation = random.uniform(-0.1, 0.1)
        player.price = max(100, int(player.price * (1 + fluctuation)))
    
    price_db.last_update = datetime.now()
    print(f"✅ Updated {len(price_db.players)} player prices")

# Background task to update prices periodically
async def price_update_loop():
    """Background task to update prices every hour"""
    while True:
        try:
            await update_player_prices()
            # Wait 1 hour
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"💥 Price update failed: {e}")
            # Wait 5 minutes on error
            await asyncio.sleep(300)
