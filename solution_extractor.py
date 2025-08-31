import re
import asyncio
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup
import asyncpg

# Optional: Only import if Playwright is available
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright not available - using static parsing only")

HOME = "https://www.fut.gg"

class SolutionExtractor:
    def __init__(self, use_browser: bool = True):
        self.use_browser = use_browser and PLAYWRIGHT_AVAILABLE
        self.browser = None
        self.context = None
        
    async def __aenter__(self):
        if self.use_browser:
            try:
                playwright = await async_playwright().__aenter__()
                self.browser = await playwright.chromium.launch(headless=True)
                self.context = await self.browser.new_context()
            except Exception as e:
                print(f"⚠️ Browser setup failed: {e}")
                self.use_browser = False
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()

    def extract_player_ids_from_html(self, html: str) -> List[str]:
        """Extract player IDs from webp image URLs in HTML with multiple patterns"""
        print(f"  🔍 Analyzing HTML content ({len(html)} characters)")
        
        # Multiple patterns to try
        patterns = [
            r'25-(\d+)\.[\w]+\.webp',           # Original webp pattern
            r'src="[^"]*25-(\d+)[^"]*\.webp',   # More specific src pattern
            r'25-(\d{6,})\.[\w]+',              # General pattern with 6+ digits  
            r'/25-(\d+)\.[\w]+\.',              # Path-based pattern
            r'25-(\d{8,})',                     # 8+ digit pattern (more specific)
        ]
        
        all_matches = set()
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                print(f"    Pattern '{pattern}' found {len(matches)} matches")
                all_matches.update(matches)
        
        # Filter out obviously invalid IDs (too short/long)
        valid_matches = []
        for match in all_matches:
            if 6 <= len(match) <= 12 and match.isdigit():  # Reasonable ID length
                valid_matches.append(match)
        
        unique_ids = list(set(valid_matches))
        print(f"  ✅ Found {len(unique_ids)} unique valid player IDs")
        
        if unique_ids:
            print(f"    Sample IDs: {unique_ids[:3]}")
        else:
            print("    ❌ No valid player IDs found")
            # Debug: show some HTML content
            sample_html = html[:500].replace('\n', ' ')
            print(f"    HTML sample: {sample_html}...")
        
        return unique_ids

    async def get_solution_players_static(self, solution_url: str) -> List[str]:
        """Get player IDs from solution page using static HTTP request"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = await client.get(solution_url, headers=headers, timeout=30)
                html = response.text
                
                return self.extract_player_ids_from_html(html)
                
        except Exception as e:
            print(f"  ❌ Static extraction failed: {e}")
            return []

    async def get_solution_players_browser(self, solution_url: str) -> List[str]:
        """Get player IDs from solution page using browser (for dynamic content)"""
        if not self.context:
            return await self.get_solution_players_static(solution_url)
        
        try:
            page = await self.context.new_page()
            await page.goto(solution_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)  # Wait for images to load
            
            # Get the HTML after JavaScript execution
            html = await page.content()
            await page.close()
            
            return self.extract_player_ids_from_html(html)
            
        except Exception as e:
            print(f"  ❌ Browser extraction failed: {e}")
            return await self.get_solution_players_static(solution_url)

    async def get_solution_players(self, solution_url: str) -> List[str]:
        """Get player IDs from solution page (tries browser first, falls back to static)"""
        print(f"📋 Extracting players from: {solution_url}")
        
        if self.use_browser:
            player_ids = await self.get_solution_players_browser(solution_url)
        else:
            player_ids = await self.get_solution_players_static(solution_url)
        
        print(f"  ✅ Extracted {len(player_ids)} player IDs")
        return player_ids

async def get_player_data_from_database(card_ids: List[str], pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    """Get player data from fut_players table using card_id column"""
    if not card_ids:
        return []
    
    try:
        async with pool.acquire() as conn:
            # Convert card_ids to integers for database query
            int_card_ids = []
            for card_id in card_ids:
                try:
                    int_card_ids.append(int(card_id))
                except ValueError:
                    print(f"⚠️ Invalid card_id: {card_id}")
            
            if not int_card_ids:
                return []
            
            # Query the fut_players table
            query = """
                SELECT card_id, name, rating, position, club, league, nation, price
                FROM fut_players 
                WHERE card_id = ANY($1)
                ORDER BY rating DESC, price ASC
            """
            
            rows = await conn.fetch(query, int_card_ids)
            
            players = []
            for row in rows:
                player_data = {
                    "card_id": row["card_id"],
                    "name": row["name"],
                    "rating": row["rating"], 
                    "position": row["position"],
                    "club": row["club"],
                    "league": row["league"],
                    "nation": row["nation"],
                    "price": row["price"] if row["price"] else 0
                }
                players.append(player_data)
            
            print(f"  📊 Found {len(players)} players in database out of {len(int_card_ids)} requested")
            
            # Report missing players
            found_ids = {player["card_id"] for player in players}
            missing_ids = set(int_card_ids) - found_ids
            if missing_ids:
                print(f"  ⚠️ Missing players in database: {missing_ids}")
            
            return players
            
    except Exception as e:
        print(f"💥 Database query failed: {e}")
        return []

async def find_solution_urls_for_sbc(sbc_url: str) -> List[str]:
    """Find solution URLs for a given SBC page"""
    solution_urls = []
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = await client.get(sbc_url, headers=headers, timeout=30)
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Look for solution links - they typically contain "squad-builder" in the URL
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "squad-builder" in href:
                    if href.startswith("/"):
                        href = urljoin(HOME, href)
                    solution_urls.append(href)
            
            # Remove duplicates
            solution_urls = list(set(solution_urls))
            
            print(f"🔍 Found {len(solution_urls)} solution URLs for SBC")
            
    except Exception as e:
        print(f"❌ Failed to find solution URLs: {e}")
    
    return solution_urls

async def get_sbc_solutions_with_players(sbc_url: str, pool: asyncpg.Pool) -> Dict[str, Any]:
    """Get complete SBC solution data with player information"""
    print(f"\n🎯 Processing SBC: {sbc_url}")
    
    # Find solution URLs
    solution_urls = await find_solution_urls_for_sbc(sbc_url)
    
    if not solution_urls:
        return {
            "sbc_url": sbc_url,
            "solutions": [],
            "total_solutions": 0
        }
    
    solutions = []
    
    async with SolutionExtractor(use_browser=True) as extractor:
        for i, solution_url in enumerate(solution_urls[:5], 1):  # Limit to first 5 solutions
            print(f"\n📋 Solution {i}: {solution_url}")
            
            # Extract player IDs from solution
            player_ids = await extractor.get_solution_players(solution_url)
            
            if not player_ids:
                print(f"  ⚠️ No player IDs found in solution {i}")
                continue
            
            # Get player data from database
            players = await get_player_data_from_database(player_ids, pool)
            
            if not players:
                print(f"  ⚠️ No player data found in database for solution {i}")
                continue
            
            # Calculate solution cost
            total_cost = sum(player.get("price", 0) for player in players)
            avg_rating = sum(player.get("rating", 0) for player in players) / len(players) if players else 0
            
            solution_data = {
                "solution_url": solution_url,
                "player_count": len(players),
                "total_cost": total_cost,
                "average_rating": round(avg_rating, 1),
                "players": players,
                "raw_player_ids": player_ids
            }
            
            solutions.append(solution_data)
            
            print(f"  ✅ Solution {i}: {len(players)} players, {total_cost:,} coins, {avg_rating:.1f} avg rating")
    
    return {
        "sbc_url": sbc_url,
        "solutions": solutions,
        "total_solutions": len(solutions),
        "cheapest_solution": min(solutions, key=lambda x: x["total_cost"]) if solutions else None
    }

# Test function
async def test_solution_extraction():
    """Test the solution extraction with a sample URL"""
    from db import get_pool  # Import your database pool
    
    # Test URLs
    test_sbc_url = "https://www.fut.gg/sbc/players/25-1253-georgia-stanway/"
    test_solution_url = "https://www.fut.gg/25/squad-builder/2e669820-9dc8-4ce7-af74-c75133f074c8/"
    
    print("🧪 Testing Solution Extraction")
    print("=" * 50)
    
    try:
        pool = await get_pool()
        
        # Test 1: Extract player IDs from a specific solution
        print("\n📋 Test 1: Extract Player IDs from Solution URL")
        async with SolutionExtractor(use_browser=True) as extractor:
            player_ids = await extractor.get_solution_players(test_solution_url)
            
            if player_ids:
                print(f"  ✅ Found player IDs: {player_ids[:5]}...")
                
                # Test 2: Get player data from database
                print("\n📊 Test 2: Get Player Data from Database")
                players = await get_player_data_from_database(player_ids, pool)
                
                if players:
                    print(f"  ✅ Found {len(players)} players in database")
                    for player in players[:3]:
                        print(f"    - {player['name']} ({player['rating']} OVR, {player['position']}) - {player['price']:,} coins")
                else:
                    print("  ❌ No players found in database")
            else:
                print("  ❌ No player IDs extracted")
        
        # Test 3: Full SBC solution analysis
        print("\n🎯 Test 3: Full SBC Solution Analysis")
        sbc_data = await get_sbc_solutions_with_players(test_sbc_url, pool)
        
        print(f"  📊 Found {sbc_data['total_solutions']} solutions")
        if sbc_data['cheapest_solution']:
            cheapest = sbc_data['cheapest_solution']
            print(f"  💰 Cheapest solution: {cheapest['total_cost']:,} coins")
            print(f"  ⭐ Average rating: {cheapest['average_rating']}")
            
        return True
        
    except Exception as e:
        print(f"💥 Test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_solution_extraction())
