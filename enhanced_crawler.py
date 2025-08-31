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

    def _looks_like_requirement(self, text: str) -> bool:
        """Check if text looks like an SBC requirement"""
        if not text or len(text.strip()) < 8:
            return False
        
        text = text.strip().lower()
        
        # Skip obvious non-requirements
        skip_phrases = [
            'solution', 'cheapest', 'price', 'reward', 'pack', 'squad builder',
            'building chemistry', 'fill player positions', 'total cost',
            'discord', 'instagram', 'futbin', 'fut.gg', 'twitter', 'youtube',
            'subscribe', 'follow', 'like', 'comment', 'share', 'video',
            'guide', 'tutorial', 'walkthrough', 'gameplay'
        ]
        
        if any(phrase in text for phrase in skip_phrases):
            return False
        
        # Must have requirement keywords
        requirement_keywords = [
            'min', 'max', 'exactly', 'chemistry', 'rating', 'players from',
            'league', 'club', 'nation', 'ovr', 'overall', 'same', 'different',
            'rare', 'gold', 'silver', 'bronze', 'team rating', 'squad rating'
        ]
        
        has_keyword = any(keyword in text for keyword in requirement_keywords)
        has_number = any(char.isdigit() for char in text)
        reasonable_length = 8 <= len(text) <= 150
        
        return has_keyword and has_number and reasonable_length

    async def parse_sbc_page_enhanced(self, url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Enhanced parsing with comprehensive requirement detection"""
        
        print(f"\n🔍 ENHANCED ANALYSIS: {url}")
        
        # Get static HTML first
        static_html = await self.fetch_html_static(client, url)
        static_soup = BeautifulSoup(static_html, "html.parser")
        
        # Extract title
        sbc_name = None
        title_el = static_soup.select_one("title")
        if title_el:
            sbc_name = title_el.get_text(strip=True).replace(" | FUT.GG", "").replace("FUT.GG - ", "")
        
        challenges = []
        
        if self.use_browser and self.context:
            # Use browser for dynamic content
            try:
                page = await self.context.new_page()
                await page.goto(url, wait_until='networkidle', timeout=30000)
                await page.wait_for_timeout(3000)
                
                print("  🤖 Using browser-based extraction")
                
                # Method 1: Use JavaScript to find ALL requirement-like text
                requirement_candidates = await page.evaluate("""
                    () => {
                        const candidates = [];
                        const keywords = ['min', 'max', 'exactly', 'chemistry', 'rating', 'players', 'team', 'club', 'league', 'nation', 'ovr', 'overall'];
                        
                        // Get all text nodes
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );
                        
                        let node;
                        while (node = walker.nextNode()) {
                            const text = node.textContent.trim();
                            if (text.length > 8 && text.length < 200 && 
                                keywords.some(k => text.toLowerCase().includes(k)) &&
                                /\\d/.test(text)) {
                                
                                const parent = node.parentElement;
                                candidates.push({
                                    text: text,
                                    parentTag: parent ? parent.tagName : null,
                                    parentClass: parent ? parent.className : null,
                                    parentId: parent ? parent.id : null
                                });
                            }
                        }
                        
                        return candidates;
                    }
                """)
                
                print(f"  Found {len(requirement_candidates)} potential requirements")
                
                # Method 2: Look for structural containers
                container_selectors = [
                    'div[class*="challenge"]',
                    'div[class*="squad"]',
                    'div[class*="requirement"]',
                    'div[class*="gray"]',
                    'section',
                    'article',
                    'div.rounded',
                    '[class*="bg-"]',
                    '[class*="p-"]'
                ]
                
                for selector in container_selectors:
                    try:
                        containers = await page.query_selector_all(selector)
                        
                        for container in containers:
                            container_text = await container.inner_text()
                            if not container_text or len(container_text) < 50:
                                continue
                            
                            # Check if this looks like a challenge container
                            container_lower = container_text.lower()
                            if not any(word in container_lower for word in ['min', 'chemistry', 'rating', 'players']):
                                continue
                            
                            # Extract challenge name
                            challenge_name = "Unknown Challenge"
                            
                            # Look for headings within container
                            headings = await container.query_selector_all('h1, h2, h3, h4, h5, h6, .font-bold, [class*="title"], [class*="heading"]')
                            for heading in headings:
                                heading_text = await heading.inner_text()
                                if heading_text and 3 < len(heading_text.strip()) < 100:
                                    challenge_name = heading_text.strip()
                                    break
                            
                            # Extract requirements from this container
                            container_requirements = []
                            
                            # Look for list items first
                            list_items = await container.query_selector_all('li')
                            for li in list_items:
                                li_text = await li.inner_text()
                                if self._looks_like_requirement(li_text):
                                    container_requirements.append(li_text.strip())
                            
                            # If no list items, look for divs/spans/paragraphs
                            if not container_requirements:
                                elements = await container.query_selector_all('div, span, p')
                                for elem in elements:
                                    elem_text = await elem.inner_text()
                                    if self._looks_like_requirement(elem_text) and len(elem_text.strip()) < 100:
                                        container_requirements.append(elem_text.strip())
                            
                            # If still no requirements, parse the full container text
                            if not container_requirements:
                                lines = container_text.split('\n')
                                for line in lines:
                                    line = line.strip()
                                    if self._looks_like_requirement(line):
                                        container_requirements.append(line)
                            
                            # Remove duplicates and filter
                            container_requirements = list(set(container_requirements))
                            container_requirements = [req for req in container_requirements if len(req) > 8]
                            
                            if container_requirements:
                                print(f"    ✅ Challenge '{challenge_name}': {len(container_requirements)} requirements")
                                for req in container_requirements[:3]:
                                    print(f"      - {req}")
                                
                                # Normalize requirements
                                try:
                                    normalized_requirements = normalize_requirements(container_requirements)
                                except Exception as e:
                                    print(f"      ⚠️ Normalization failed: {e}")
                                    normalized_requirements = [{"kind": "raw", "text": req} for req in container_requirements]
                                
                                challenges.append({
                                    "name": challenge_name,
                                    "cost": None,
                                    "reward": None,
                                    "requirements": normalized_requirements,
                                    "raw_requirements": container_requirements
                                })
                                
                                # Prevent too many duplicates
                                if len(challenges) >= 15:
                                    break
                    
                    except Exception as e:
                        print(f"    ⚠️ Error with selector {selector}: {e}")
                        continue
                    
                    # If we found challenges, don't need to try more selectors
                    if challenges:
                        break
                
                # If browser method didn't work, try the requirement candidates directly
                if not challenges and requirement_candidates:
                    print("  📋 Grouping individual requirements into challenges")
                    
                    # Group requirements by their parent containers
                    grouped_reqs = {}
                    for candidate in requirement_candidates:
                        if self._looks_like_requirement(candidate['text']):
                            parent_key = f"{candidate['parentTag']}_{candidate['parentClass']}"
                            if parent_key not in grouped_reqs:
                                grouped_reqs[parent_key] = []
                            grouped_reqs[parent_key].append(candidate['text'])
                    
                    # Create challenges from grouped requirements
                    for i, (parent_key, reqs) in enumerate(grouped_reqs.items()):
                        if len(reqs) >= 2:  # Only groups with multiple requirements
                            try:
                                normalized_requirements = normalize_requirements(reqs)
                            except:
                                normalized_requirements = [{"kind": "raw", "text": req} for req in reqs]
                            
                            challenges.append({
                                "name": f"Challenge {i+1}",
                                "cost": None,
                                "reward": None,
                                "requirements": normalized_requirements,
                                "raw_requirements": reqs
                            })
                            
                            print(f"    ✅ Grouped Challenge {i+1}: {len(reqs)} requirements")
                
                await page.close()
                
            except Exception as e:
                print(f"  💥 Browser parsing failed: {e}")
                # Fall back to static parsing
                challenges = self._parse_static_fallback(static_soup)
        
        else:
            # Static parsing only
            print("  📄 Using static parsing")
            challenges = self._parse_static_fallback(static_soup)
        
        # Remove duplicate challenges based on requirements
        unique_challenges = []
        seen_req_sets = set()
        
        for challenge in challenges:
            # Create a signature based on the requirements
            req_texts = [req.get('text', '') for req in challenge.get('requirements', [])]
            req_signature = '|'.join(sorted(req_texts))
            
            if req_signature and req_signature not in seen_req_sets:
                seen_req_sets.add(req_signature)
                unique_challenges.append(challenge)
        
        challenges = unique_challenges[:10]  # Limit to 10 challenges max
        
        total_requirements = sum(len(ch.get('requirements', [])) for ch in challenges)
        print(f"  🎯 FINAL: {len(challenges)} challenges, {total_requirements} requirements")
        
        if total_requirements == 0:
            print("  ⚠️ No requirements found - this might indicate a parsing issue")
        
        return {
            "slug": url.replace(HOME, ""),
            "url": url,
            "name": sbc_name,
            "expires_at": self._extract_expiry(static_soup),
            "sub_challenges": challenges,
            "rewards": []
        }

    def _parse_static_fallback(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Comprehensive static parsing fallback"""
        print("    📄 Using comprehensive static parsing")
        
        challenges = []
        
        # Strategy 1: Look for ANY text that looks like requirements
        all_text_elements = soup.find_all(text=True)
        potential_requirements = []
        
        for text_node in all_text_elements:
            text = text_node.strip()
            if self._looks_like_requirement(text):
                potential_requirements.append(text)
        
        print(f"    Found {len(potential_requirements)} potential requirements in static HTML")
        
        if potential_requirements:
            # Group requirements logically
            # Remove duplicates
            unique_requirements = list(set(potential_requirements))
            
            # Try to group by common patterns or split into logical chunks
            if len(unique_requirements) > 10:
                # If too many, try to group them
                chunk_size = max(3, len(unique_requirements) // 3)  # Create ~3 challenges
                for i in range(0, len(unique_requirements), chunk_size):
                    chunk = unique_requirements[i:i + chunk_size]
                    
                    try:
                        normalized_requirements = normalize_requirements(chunk)
                    except:
                        normalized_requirements = [{"kind": "raw", "text": req} for req in chunk]
                    
                    challenges.append({
                        "name": f"Challenge {len(challenges) + 1}",
                        "cost": None,
                        "reward": None,
                        "requirements": normalized_requirements,
                        "raw_requirements": chunk
                    })
            else:
                # Single challenge with all requirements
                try:
                    normalized_requirements = normalize_requirements(unique_requirements)
                except:
                    normalized_requirements = [{"kind": "raw", "text": req} for req in unique_requirements]
                
                challenges.append({
                    "name": "Main Challenge",
                    "cost": None,
                    "reward": None,
                    "requirements": normalized_requirements,
                    "raw_requirements": unique_requirements
                })
        
        # Strategy 2: If Strategy 1 failed, look for structured containers
        if not challenges:
            print("    📦 Trying container-based parsing")
            
            containers = soup.select('div, section, article')
            
            for container in containers:
                container_text = container.get_text(' ', strip=True)
                if len(container_text) < 50:
                    continue
                
                # Check if container has requirement-like content
                if not any(word in container_text.lower() for word in ['min', 'chemistry', 'rating', 'players']):
                    continue
                
                # Extract challenge name
                challenge_name = "Unknown Challenge"
                for header in container.select('h1, h2, h3, h4, h5, h6'):
                    header_text = header.get_text(strip=True)
                    if header_text and 3 < len(header_text) < 100:
                        challenge_name = header_text
                        break
                
                # Extract requirements
                requirements = []
                
                # Try list items first
                for li in container.select('li'):
                    li_text = li.get_text(strip=True)
                    if self._looks_like_requirement(li_text):
                        requirements.append(li_text)
                
                # Try other elements
                if not requirements:
                    for elem in container.select('div, span, p'):
                        elem_text = elem.get_text(strip=True)
                        if self._looks_like_requirement(elem_text) and len(elem_text) < 100:
                            requirements.append(elem_text)
                
                # Try parsing full text
                if not requirements:
                    lines = container_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if self._looks_like_requirement(line):
                            requirements.append(line)
                
                if requirements:
                    # Remove duplicates
                    requirements = list(set(requirements))
                    
                    try:
                        normalized_requirements = normalize_requirements(requirements)
                    except:
                        normalized_requirements = [{"kind": "raw", "text": req} for req in requirements]
                    
                    challenges.append({
                        "name": challenge_name,
                        "cost": None,
                        "reward": None,
                        "requirements": normalized_requirements,
                        "raw_requirements": requirements
                    })
                    
                    print(f"    ✅ Container challenge '{challenge_name}': {len(requirements)} requirements")
        
        return challenges

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
    """Enhanced crawling with comprehensive requirement detection"""
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
                        
                        if req_count > 0:
                            print(f"✅ {payload['name']}: {len(payload['sub_challenges'])} challenges, {req_count} requirements")
                            results.append(payload)
                        else:
                            print(f"⚠️ Skipping SBC with 0 requirements: {link}")
                    else:
                        print(f"⚠️ Skipping incomplete SBC: {link}")
                        
                except Exception as e:
                    print(f"💥 Failed to parse {link}: {e}")
    
    print(f"\n✅ Successfully parsed {len(results)} SBC sets with requirements")
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
