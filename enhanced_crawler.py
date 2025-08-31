import asyncio
import json
import re
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from normalizer import normalize_requirements

# Optional: Only import if Playwright is available
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright not available - dynamic content extraction disabled")

HOME = "https://www.fut.gg"

async def check_playwright_available():
    """Check if Playwright browsers are actually available"""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            await browser.close()
            return True
    except Exception:
        return False

class EnhancedSBCCrawler:
    def __init__(self, use_browser: bool = False):
        self.use_browser = use_browser and PLAYWRIGHT_AVAILABLE
        self.browser = None
        self.context = None
        self.browser_actually_available = None
        
    async def __aenter__(self):
        if self.use_browser:
            # Check if browsers are actually available before trying to launch
            self.browser_actually_available = await check_playwright_available()
            if not self.browser_actually_available:
                print("⚠️ Playwright installed but browsers not available - falling back to static parsing")
                self.use_browser = False
                return self
                
            playwright = await async_playwright().__aenter__()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()

    async def fetch_html_static(self, client: httpx.AsyncClient, url: str) -> str:
        """Fetch HTML using static HTTP request"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
        }
        r = await client.get(url, timeout=30, follow_redirects=True, headers=headers)
        r.raise_for_status()
        return r.text

    async def parse_sbc_page_enhanced(self, url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Parse SBC page using fut.gg's two-step structure"""
        
        # Step 1: Get the main SBC page
        static_html = await self.fetch_html_static(client, url)
        soup = BeautifulSoup(static_html, "html.parser")
        
        # Extract main SBC info
        sbc_name = None
        title_el = soup.select_one("title")
        if title_el:
            sbc_name = title_el.get_text(strip=True).replace(" | FUT.GG", "").replace("FUT.GG - ", "")
        
        # Step 2: Find all challenge containers on the main page
        challenges = []
        challenge_containers = soup.select('div.bg-gray-600.rounded-lg.p-1')
        
        print(f"Found {len(challenge_containers)} challenge containers for {sbc_name}")
        
        for container in challenge_containers:
            try:
                # Get challenge name
                challenge_title = container.select_one('h4.font-bold')
                challenge_name = challenge_title.get_text(strip=True) if challenge_title else "Unknown Challenge"
                
                # Get basic requirements from the main page
                basic_requirements = []
                requirement_list = container.select_one('ul.flex.flex-col.gap-1')
                if requirement_list:
                    for li in requirement_list.select('li.text-xs'):
                        req_text = li.get_text(strip=True)
                        if req_text and len(req_text) > 5:
                            basic_requirements.append(req_text)
                
                # Get squad builder link for detailed requirements
                squad_link = container.select_one('a[href*="/squad-builder/"]')
                detailed_requirements = basic_requirements.copy()  # Start with basic requirements
                
                if squad_link and self.use_browser:
                    try:
                        squad_url = urljoin(HOME, squad_link.get('href'))
                        print(f"  Fetching detailed requirements from: {squad_url}")
                        
                        # Get detailed requirements from squad builder page
                        if self.context:
                            page = await self.context.new_page()
                            await page.goto(squad_url, timeout=15000)
                            await page.wait_for_timeout(2000)  # Wait for content to load
                            
                            # Look for additional requirements on the squad builder page
                            additional_reqs = await page.evaluate("""
                                () => {
                                    const reqElements = document.querySelectorAll('li, .requirement, [class*="requirement"]');
                                    const requirements = [];
                                    reqElements.forEach(el => {
                                        const text = el.textContent.trim();
                                        if (text.length > 8 && text.length < 150 && 
                                            (text.toLowerCase().includes('min') || 
                                             text.toLowerCase().includes('max') || 
                                             text.toLowerCase().includes('exactly') ||
                                             text.toLowerCase().includes('chemistry') ||
                                             text.toLowerCase().includes('rating') ||
                                             text.toLowerCase().includes('players from'))) {
                                            requirements.push(text);
                                        }
                                    });
                                    return [...new Set(requirements)]; // Remove duplicates
                                }
                            """)
                            
                            # Merge requirements, avoiding duplicates
                            for req in additional_reqs:
                                if req not in detailed_requirements:
                                    detailed_requirements.append(req)
                            
                            await page.close()
                            print(f"    Found {len(additional_reqs)} additional requirements")
                            
                    except Exception as e:
                        print(f"    Failed to get detailed requirements: {e}")
                
                # Get cost if available
                cost = None
                cost_element = container.select_one('span.text-sm.font-bold')
                if cost_element:
                    cost_text = cost_element.get_text(strip=True).replace(',', '')
                    if cost_text.isdigit():
                        cost = int(cost_text)
                
                # Get reward info
                reward = None
                reward_element = container.select_one('span.text-xs.font-bold')
                if reward_element:
                    reward = reward_element.get_text(strip=True)
                
                # Normalize requirements
                try:
                    normalized_requirements = normalize_requirements(detailed_requirements)
                except Exception as e:
                    print(f"    Normalization failed: {e}")
                    normalized_requirements = [{"kind": "raw", "text": req} for req in detailed_requirements]
                
                challenges.append({
                    "name": challenge_name,
                    "cost": cost,
                    "reward": reward,
                    "requirements": normalized_requirements,
                    "raw_requirements": detailed_requirements  # Keep for debugging
                })
                
                print(f"    Challenge '{challenge_name}': {len(normalized_requirements)} requirements")
                
            except Exception as e:
                print(f"  Failed to parse challenge container: {e}")
                continue
        
        # Extract expiry date
        expires_at = self._extract_expiry(soup)
        
        result = {
            "slug": url.replace(HOME, ""),
            "url": url,
            "name": sbc_name,
            "expires_at": expires_at,
            "sub_challenges": challenges,
            "rewards": []
        }
        
        total_requirements = sum(len(ch.get('requirements', [])) for ch in challenges)
        print(f"Parsed '{sbc_name}': {len(challenges)} challenges, {total_requirements} total requirements")
        
        return result

    def _extract_expiry(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract expiry date from HTML"""
        txt = soup.get_text(" ", strip=True)
        for pat in (
            r"expires?:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
            r"ends?:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
            r"available until:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        ):
            m = re.search(pat, txt, re.I)
            if not m:
                continue
            d = m.group(1)
            try:
                day, month, year = map(int, re.split(r"[/\-]", d))
                return datetime(year, month, day, tzinfo=timezone.utc)
            except Exception:
                pass
        return None

# Updated crawl function
async def crawl_all_sets_enhanced(use_browser: bool = True, debug_first: bool = True) -> List[Dict[str, Any]]:
    """Enhanced crawling with dynamic content support"""
    results = []
    
    async with EnhancedSBCCrawler(use_browser=use_browser) as crawler:
        async with httpx.AsyncClient() as client:
            print("🌐 Fetching main SBC page…")
            list_html = await crawler.fetch_html_static(client, f"{HOME}/sbc/")
            links = discover_set_links(list_html)
            
            # Add category pages
            for cat in ["live", "players", "icons", "upgrades", "foundations"]:
                try:
                    cat_html = await crawler.fetch_html_static(client, f"{HOME}/sbc/{cat}/")
                    links.extend(discover_set_links(cat_html))
                except Exception as e:
                    print(f"⚠️ Category fetch failed ({cat}): {e}")
            
            links = sorted(set(links))
            
            # Limit for testing
            if debug_first:
                links = links[:3]  # Only test first 3 SBCs
                print(f"🧪 Debug mode: testing first 3 SBCs only")
            
            print(f"🎯 Processing {len(links)} SBC links {'with browser support' if use_browser else 'static only'}")
            
            for i, link in enumerate(links, 1):
                try:
                    print(f"\n📋 Processing {i}/{len(links)}: {link}")
                    payload = await crawler.parse_sbc_page_enhanced(link, client)
                    
                    if payload.get("name") and payload.get("sub_challenges"):
                        # Count actual requirements found
                        req_count = sum(len(ch.get('requirements', [])) 
                                      for ch in payload.get('sub_challenges', []))
                        print(f"✅ {payload['name']}: {len(payload['sub_challenges'])} challenges, {req_count} requirements")
                        results.append(payload)
                    else:
                        print(f"⚠️ Skipping incomplete SBC: {link}")
                        
                except Exception as e:
                    print(f"💥 Failed to parse {link}: {e}")
    
    print(f"\n✅ Successfully parsed {len(results)} SBC sets")
    return results

def discover_set_links(list_html: str) -> List[str]:
    """Discover SBC set links from listing page HTML"""
    soup = BeautifulSoup(list_html, "html.parser")
    links = set()
    
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
        clean = href.split("#")[0].split("?")[0]
        if (clean.startswith("/sbc/") and len(clean) > 5 and 
            clean != "/sbc/" and not clean.endswith("/sbc")):
            links.add(urljoin(HOME, clean))
    
    return sorted(links)
