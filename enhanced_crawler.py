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

class EnhancedSBCCrawler:
    def __init__(self, use_browser: bool = False):
        self.use_browser = use_browser and PLAYWRIGHT_AVAILABLE
        self.browser = None
        self.context = None
        
    async def __aenter__(self):
        if self.use_browser:
            playwright = await async_playwright().__aenter__()
            self.browser = await playwright.chromium.launch(headless=True)
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

    async def fetch_html_dynamic(self, url: str) -> tuple[str, List[Dict[str, Any]]]:
        """Fetch HTML using browser automation and intercept API calls"""
        if not self.use_browser:
            raise RuntimeError("Browser automation not available")
        
        captured_requests = []
        
        async def handle_response(response):
            """Capture API responses that might contain SBC data"""
            if response.status == 200:
                content_type = response.headers.get('content-type', '').lower()
                url_lower = response.url.lower()
                
                # Look for JSON responses that might contain SBC data
                if ('json' in content_type and 
                    any(keyword in url_lower for keyword in ['api', 'sbc', 'data', 'challenge'])):
                    try:
                        data = await response.json()
                        captured_requests.append({
                            'url': response.url,
                            'data': data,
                            'content_type': content_type
                        })
                    except:
                        pass
        
        page = await self.context.new_page()
        page.on('response', handle_response)
        
        try:
            # Navigate and wait for dynamic content
            await page.goto(url, wait_until='networkidle')
            await page.wait_for_timeout(3000)  # Wait for any lazy-loaded content
            
            html = await page.content()
            return html, captured_requests
        finally:
            await page.close()

    async def parse_sbc_page_enhanced(self, url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Parse SBC page using both static and dynamic methods"""
        
        # First try static parsing
        static_html = await self.fetch_html_static(client, url)
        static_result = self.parse_static_html(static_html, url)
        
        # If we got requirements from static parsing, return that
        if static_result.get('sub_challenges') and any(
            ch.get('requirements') for ch in static_result.get('sub_challenges', [])
        ):
            print(f"✅ Static parsing successful for {url}")
            return static_result
        
        # If static parsing failed and we have browser support, try dynamic
        if self.use_browser:
            try:
                print(f"🔄 Trying dynamic parsing for {url}")
                dynamic_html, api_responses = await self.fetch_html_dynamic(url)
                
                # First check if any API responses contain structured SBC data
                for api_response in api_responses:
                    structured_data = self.extract_from_api_response(api_response['data'], url)
                    if structured_data and structured_data.get('sub_challenges'):
                        print(f"✅ Found SBC data in API response: {api_response['url']}")
                        return structured_data
                
                # Fall back to parsing the fully-rendered HTML
                dynamic_result = self.parse_dynamic_html(dynamic_html, url)
                if dynamic_result.get('sub_challenges'):
                    print(f"✅ Dynamic HTML parsing successful for {url}")
                    return dynamic_result
                
            except Exception as e:
                print(f"⚠️ Dynamic parsing failed for {url}: {e}")
        
        # Return static result even if incomplete
        print(f"⚠️ Using incomplete static result for {url}")
        return static_result

    def parse_static_html(self, html: str, url: str) -> Dict[str, Any]:
        """Your existing static HTML parsing logic"""
        soup = BeautifulSoup(html, "html.parser")
        
        # Try Next.js JSON data first
        structured = self._parse_next_data(soup)
        if structured and structured.get("sub_challenges"):
            return {
                "slug": url.replace(HOME, ""),
                "url": url,
                "name": structured.get("name"),
                "expires_at": self._extract_expiry(soup),
                "sub_challenges": structured.get("sub_challenges", []),
                "rewards": structured.get("rewards", []),
            }
        
        # Fall back to HTML heuristics
        return self._parse_html_fallback(soup, url)

    def parse_dynamic_html(self, html: str, url: str) -> Dict[str, Any]:
        """Parse fully-rendered HTML with dynamic content loaded"""
        soup = BeautifulSoup(html, "html.parser")
        
        # Enhanced selectors for dynamically loaded content
        enhanced_selectors = [
            '[data-testid*="requirement"]',
            '[data-testid*="challenge"]', 
            '[class*="requirement"]',
            '[class*="sbc-requirement"]',
            '[class*="challenge-requirement"]',
            'li:contains("Min.")',
            'li:contains("Max.")',
            'li:contains("Exactly")',
            'li:contains("Rating")',
            'li:contains("Chemistry")',
            'li:contains("Players from")',
        ]
        
        requirements = []
        
        # Try standard selectors first
        for li in soup.select("ul li, ol li"):
            text = li.get_text(strip=True)
            if self._is_valid_requirement(text):
                requirements.append(text)
        
        # Try enhanced selectors
        for selector in enhanced_selectors:
            try:
                if ':contains(' in selector:
                    # Handle pseudo-selectors manually
                    elements = soup.find_all('li')
                    search_term = selector.split(':contains("')[1].split('")')[0]
                    elements = [el for el in elements if search_term in el.get_text()]
                else:
                    elements = soup.select(selector)
                
                for element in elements:
                    text = element.get_text(strip=True)
                    if self._is_valid_requirement(text) and text not in requirements:
                        requirements.append(text)
            except Exception:
                continue
        
        # Extract name and other metadata
        name = None
        for selector in ["h1", "h2", ".page-title", ".sbc-title", ".title"]:
            el = soup.select_one(selector)
            if el:
                name = el.get_text(strip=True)
                break
        
        if not name:
            title_el = soup.select_one("title")
            if title_el:
                name = title_el.get_text(strip=True).replace(" | FUT.GG", "").replace("FUT.GG - ", "")
        
        # Create challenge structure
        sub_challenges = []
        if requirements:
            try:
                normalized = normalize_requirements(requirements)
                sub_challenges = [{
                    "name": name or "Main Challenge",
                    "cost": None,
                    "reward": None,
                    "requirements": normalized
                }]
            except Exception as e:
                print(f"⚠️ Normalization failed: {e}")
                sub_challenges = [{
                    "name": name or "Main Challenge", 
                    "cost": None,
                    "reward": None,
                    "requirements": [{"kind": "raw", "text": req} for req in requirements]
                }]
        
        return {
            "slug": url.replace(HOME, ""),
            "url": url,
            "name": name,
            "expires_at": self._extract_expiry(soup),
            "sub_challenges": sub_challenges,
            "rewards": []
        }

    def extract_from_api_response(self, data: Dict[str, Any], url: str) -> Optional[Dict[str, Any]]:
        """Extract SBC data from API response JSON"""
        try:
            # Look for common SBC data structures
            if isinstance(data, dict):
                # Check for direct SBC data
                if 'challenges' in data or 'requirements' in data:
                    return self._parse_api_sbc_data(data, url)
                
                # Check nested structures
                for key, value in data.items():
                    if isinstance(value, (list, dict)):
                        nested_result = self.extract_from_api_response(value, url)
                        if nested_result:
                            return nested_result
            
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        result = self.extract_from_api_response(item, url)
                        if result:
                            return result
            
            return None
        except Exception as e:
            print(f"⚠️ API response parsing failed: {e}")
            return None

    def _parse_api_sbc_data(self, data: Dict[str, Any], url: str) -> Dict[str, Any]:
        """Parse structured API data into SBC format"""
        name = data.get('name') or data.get('title') or "Unknown SBC"
        
        sub_challenges = []
        challenges_data = data.get('challenges', [data])  # Single challenge or array
        
        for challenge in challenges_data if isinstance(challenges_data, list) else [challenges_data]:
            if not isinstance(challenge, dict):
                continue
                
            challenge_name = challenge.get('name') or challenge.get('title') or name
            requirements_raw = challenge.get('requirements', [])
            
            # Convert API requirements to normalized format
            requirements = []
            for req in requirements_raw:
                if isinstance(req, dict):
                    # Structured requirement
                    requirements.append({
                        "kind": req.get('type', 'raw'),
                        "text": req.get('text', str(req)),
                        "value": req.get('value'),
                        "key": req.get('key')
                    })
                else:
                    # Text requirement
                    requirements.append({"kind": "raw", "text": str(req)})
            
            sub_challenges.append({
                "name": challenge_name,
                "cost": challenge.get('cost'),
                "reward": challenge.get('reward'),
                "requirements": requirements
            })
        
        return {
            "slug": url.replace(HOME, ""),
            "url": url,
            "name": name,
            "sub_challenges": sub_challenges,
            "rewards": data.get('rewards', []),
            "expires_at": None
        }

    def _is_valid_requirement(self, text: str) -> bool:
        """Check if text looks like a valid SBC requirement"""
        t = (text or "").lower().strip()
        if not t or len(t) < 8 or len(t) > 200:
            return False
        
        skip_words = ["solution", "cheapest", "price", "reward", "pack", "cost", "discord"]
        if any(word in t for word in skip_words):
            return False
        
        requirement_indicators = [
            "min.", "max.", "exactly", "chemistry", "rating", "players from", 
            "league", "club", "nation", "ovr", "overall", "same", "different",
            "rare", "gold", "silver", "bronze"
        ]
        
        has_indicator = any(indicator in t for indicator in requirement_indicators)
        has_number = any(ch.isdigit() for ch in t)
        
        return has_indicator and (has_number or "same" in t or "different" in t)

    def _parse_next_data(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Parse Next.js JSON data"""
        script = soup.select_one('script#___NEXT_DATA__') or soup.select_one('script#__NEXT_DATA__')
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
        except Exception:
            return None

        # Look for SBC data in the Next.js data
        def _find_in_json(obj, want_keys=("requirements", "subChallenges", "challenges")):
            found = []
            stack = [obj]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    if ("name" in cur or "title" in cur) and any(k in cur for k in want_keys):
                        found.append(cur)
                    for v in cur.values():
                        stack.append(v)
                elif isinstance(cur, list):
                    stack.extend(cur)
            return found

        name = None
        raw_challenges = _find_in_json(data)
        sub_challenges = []
        rewards = []

        for ch in raw_challenges:
            title = ch.get("name") or ch.get("title")
            if not title:
                continue

            reqs_raw = (
                ch.get("requirements")
                or ch.get("subRequirements") 
                or ch.get("reqs")
                or ch.get("requirementList")
                or []
            )
            
            if not isinstance(reqs_raw, list):
                continue

            req_texts = []
            for x in reqs_raw:
                if isinstance(x, dict):
                    for k in ("text", "label", "name", "value"):
                        if k in x and x[k]:
                            req_texts.append(str(x[k]))
                            break
                else:
                    req_texts.append(str(x))

            try:
                normalized = normalize_requirements(req_texts)
            except Exception:
                normalized = [{"kind": "raw", "text": s} for s in req_texts]

            reward_text = ch.get("rewardText") or ch.get("reward") or None
            if reward_text:
                rewards.append({"type": "other", "label": str(reward_text)})

            sub_challenges.append({
                "name": str(title),
                "cost": ch.get("cost") if isinstance(ch.get("cost"), int) else None,
                "reward": reward_text,
                "requirements": normalized,
            })

        if not name and sub_challenges:
            name = sub_challenges[0]["name"]

        if sub_challenges:
            return {
                "name": name,
                "rewards": rewards,
                "sub_challenges": sub_challenges,
            }
        
        return None

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
    
    def _parse_html_fallback(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """HTML fallback parsing"""
        name = None
        for sel in ["h1", "h2", ".page-title", ".sbc-title", ".title"]:
            el = soup.select_one(sel)
            if el:
                txt = el.get_text(strip=True)
                if txt and len(txt) > 3:
                    name = txt
                    break
        
        if not name:
            t = soup.select_one("title")
            if t:
                name = t.get_text(strip=True).replace(" | FUT.GG", "").replace("FUT.GG - ", "")

        # Look for requirements in containers
        requirements = []
        containers = soup.select(
            ".challenge, .squad, .sbc-challenge, [class*='challenge'], [class*='squad'], "
            ".card, section, article"
        )
        
        for container in containers:
            for li in container.select("ul li, ol li"):
                s = li.get_text(strip=True)
                if self._is_valid_requirement(s):
                    requirements.append(s)
        
        sub_challenges = []
        if requirements:
            try:
                normalized = normalize_requirements(requirements)
                sub_challenges = [{
                    "name": name or "Main Challenge",
                    "cost": None,
                    "reward": None,
                    "requirements": normalized
                }]
            except Exception:
                sub_challenges = [{
                    "name": name or "Main Challenge",
                    "cost": None,
                    "reward": None,
                    "requirements": [{"kind": "raw", "text": r} for r in requirements]
                }]

        return {
            "slug": url.replace(HOME, ""),
            "url": url,
            "name": name,
            "repeatable": None,
            "expires_at": self._extract_expiry(soup),
            "cost": None,
            "rewards": [],
            "sub_challenges": sub_challenges,
        }

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
            print(f"🎯 Processing {len(links)} SBC links {'with browser support' if use_browser else 'static only'}")
            
            for i, link in enumerate(links, 1):
                try:
                    payload = await crawler.parse_sbc_page_enhanced(link, client)
                    
                    if payload.get("name") and payload.get("sub_challenges"):
                        # Count actual requirements found
                        req_count = sum(len(ch.get('requirements', [])) 
                                      for ch in payload.get('sub_challenges', []))
                        print(f"✅ {i}/{len(links)}: {payload['name']} ({req_count} requirements)")
                        results.append(payload)
                    else:
                        print(f"⚠️ {i}/{len(links)}: Skipping incomplete SBC: {link}")
                        
                except Exception as e:
                    print(f"💥 {i}/{len(links)}: Failed to parse {link}: {e}")
    
    print(f"✅ Successfully parsed {len(results)} SBC sets")
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
