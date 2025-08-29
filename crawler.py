# crawler.py
import re
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from normalizer import normalize_requirements

HOME = "https://www.fut.gg"

# More comprehensive SBC URL pattern
SET_URL_RE = re.compile(r"^/sbc/(?:[^/]+/)?(?:\d{2}-\d{1,6}-|[a-zA-Z0-9\-]+/?)")

async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }
    
    try:
        r = await client.get(url, timeout=30, follow_redirects=True, headers=headers)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"⚠️ Failed to fetch {url}: {e}")
        raise

def discover_set_links(list_html: str) -> List[str]:
    soup = BeautifulSoup(list_html, "html.parser")
    links: set[str] = set()
    
    # Look for SBC links in various formats
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
            
        # Remove fragment identifier and query params
        clean_href = href.split("#")[0].split("?")[0]
        
        # Match SBC URLs more broadly
        if (clean_href.startswith("/sbc/") and 
            len(clean_href) > 5 and 
            clean_href != "/sbc/" and
            not clean_href.endswith("/sbc")):
            full_url = urljoin(HOME, clean_href)
            links.add(full_url)
    
    print(f"🔍 Discovered {len(links)} unique SBC links")
    return sorted(links)

def debug_page_structure(soup: BeautifulSoup, url: str):
    """Debug function to understand page structure"""
    print(f"🔍 DEBUG: Analyzing structure of {url}")
    
    # Look for common container patterns
    containers = soup.select("div, section, article, main")
    print(f"  Found {len(containers)} total containers")
    
    # Look for headings
    headings = soup.select("h1, h2, h3, h4, h5, h6")
    print(f"  Found {len(headings)} headings:")
    for i, h in enumerate(headings[:10]):  # Show first 10
        text = h.get_text(strip=True)[:50]
        print(f"    {h.name}: {text}")
    
    # Look for lists
    lists = soup.select("ul, ol")
    print(f"  Found {len(lists)} lists")
    for i, lst in enumerate(lists[:5]):  # Show first 5
        items = lst.select("li")
        print(f"    List {i+1}: {len(items)} items")
        for j, item in enumerate(items[:3]):  # Show first 3 items
            text = item.get_text(strip=True)[:40]
            print(f"      - {text}")
    
    # Look for potential requirement/challenge containers
    requirement_patterns = [
        "requirement", "req", "challenge", "squad", "sbc",
        "min", "max", "exactly", "chemistry", "rating"
    ]
    
    for pattern in requirement_patterns:
        elements = soup.select(f"[class*='{pattern}' i], [id*='{pattern}' i]")
        if elements:
            print(f"  Found {len(elements)} elements matching '{pattern}':")
            for elem in elements[:3]:
                classes = ' '.join(elem.get('class', []))
                text = elem.get_text(strip=True)[:60]
                print(f"    {elem.name}.{classes}: {text}")

def extract_expiry_date(soup: BeautifulSoup) -> Optional[datetime]:
    """Try to extract expiry date from various possible locations"""
    
    # Look for common expiry patterns
    text_content = soup.get_text()
    
    # Pattern: "Expires: DD/MM/YYYY" or similar
    expiry_patterns = [
        r"expires?:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        r"ends?:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})",
        r"available until:?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})"
    ]
    
    for pattern in expiry_patterns:
        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(1)
                # Try to parse DD/MM/YYYY format (common for fut.gg)
                if '/' in date_str:
                    parts = date_str.split('/')
                elif '-' in date_str:
                    parts = date_str.split('-')
                else:
                    continue
                    
                if len(parts) == 3:
                    day, month, year = parts
                    return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
            except (ValueError, IndexError):
                continue
    
    return None

def parse_set_page(html: str, url: str, debug=False) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    
    if debug:
        debug_page_structure(soup, url)

    # Extract page title - try multiple selectors
    name = None
    title_selectors = [
        "h1", "h2", ".page-title", ".sbc-title", "[data-testid='title']",
        ".title", ".heading", ".main-title", ".sbc-name"
    ]
    
    for selector in title_selectors:
        title_el = soup.select_one(selector)
        if title_el:
            name = title_el.get_text(strip=True)
            if name and len(name) > 5:  # Ensure it's not just a short generic word
                break
    
    if not name:
        # Fallback to title tag
        title_tag = soup.select_one("title")
        if title_tag:
            name = title_tag.get_text(strip=True).replace(" | FUT.GG", "").replace("FUT.GG - ", "")

    # Extract metadata
    expires_at = extract_expiry_date(soup)
    
    # Look for repeatable indicator
    repeatable = None
    page_text = soup.get_text().lower()
    if "repeatable" in page_text:
        repeatable = "Yes" if "not repeatable" not in page_text else "No"

    # Extract rewards with better selectors
    rewards: List[Dict[str, Any]] = []
    
    # Look for reward images and text
    reward_selectors = [
        "img[alt*='pack' i]", "img[alt*='player' i]", "img[alt*='coins' i]",
        ".reward", ".pack", "[data-testid*='reward']", ".sbc-reward"
    ]
    
    for selector in reward_selectors:
        for elem in soup.select(selector):
            if elem.name == "img":
                alt_text = elem.get("alt", "")
                if alt_text and len(alt_text) > 2:
                    reward_type = "pack" if "pack" in alt_text.lower() else "other"
                    rewards.append({"type": reward_type, "label": alt_text.strip()})
            else:
                text = elem.get_text(strip=True)
                if text and len(text) > 2:
                    rewards.append({"type": "other", "label": text})

    # Parse sub-challenges with EXTENSIVE selector coverage
    sub_challenges: List[Dict[str, Any]] = []
    
    # Try EVERY possible selector pattern fut.gg might use
    challenge_selectors = [
        # Generic containers
        ".challenge", ".sbc-challenge", ".squad-building", ".squad",
        ".requirement", ".req", ".requirements", ".challenge-card",
        ".card", ".panel", ".section", ".block", ".container",
        
        # React/Vue style selectors
        "[data-testid*='challenge']", "[data-testid*='squad']", 
        "[data-testid*='requirement']", "[data-cy*='challenge']",
        
        # Grid/flex layouts
        ".grid-item", ".flex-item", ".col", ".column", ".row",
        
        # Generic semantic elements
        "section", "article", "div[class]", "main > div", 
        ".content > div", ".main > div", ".page > div",
        
        # FUT.GG specific patterns (educated guesses)
        "[class*='sbc' i]", "[class*='challenge' i]", "[class*='squad' i]",
        "[id*='sbc' i]", "[id*='challenge' i]", "[id*='squad' i]"
    ]
    
    processed_titles = set()  # Avoid duplicates
    
    for selector in challenge_selectors:
        try:
            containers = soup.select(selector)
            print(f"  Selector '{selector}': found {len(containers)} containers")
            
            for container in containers:
                # Extract challenge title with extensive search
                title = None
                title_selectors = [
                    "h1", "h2", "h3", "h4", "h5", "h6",
                    ".title", ".name", ".heading", ".header", 
                    ".challenge-name", ".squad-name", ".sbc-name",
                    ".font-bold", ".text-lg", ".text-xl", ".font-medium",
                    "[class*='title' i]", "[class*='name' i]", "[class*='heading' i]"
                ]
                
                for title_sel in title_selectors:
                    title_elem = container.select_one(title_sel)
                    if title_elem:
                        candidate_title = title_elem.get_text(strip=True)
                        # Skip if it's the main page title or too short/generic
                        if (candidate_title and 
                            len(candidate_title) >= 3 and 
                            candidate_title != name and
                            candidate_title.lower() not in ["requirements", "reward", "rewards", "cost", "squad", "team"]):
                            title = candidate_title
                            break
                
                # If no explicit title found, use container text as fallback
                if not title:
                    container_text = container.get_text(strip=True)
                    lines = container_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if (line and len(line) >= 5 and len(line) <= 50 and 
                            not any(keyword in line.lower() for keyword in ["min.", "max.", "exactly", "chemistry", "rating"])):
                            title = line
                            break
                
                if not title or title in processed_titles:
                    continue
                    
                processed_titles.add(title)
                print(f"    Found potential challenge: '{title}'")

                # Extract requirements with COMPREHENSIVE approach
                raw_reqs: List[str] = []
                
                # Method 1: Look for list items
                req_lists = container.select("ul li, ol li, .requirement, .req, .requirements li")
                for li in req_lists:
                    req_text = li.get_text(strip=True)
                    if req_text and len(req_text) > 5:
                        raw_reqs.append(req_text)
                        print(f"      Requirement (list): {req_text[:50]}")
                
                # Method 2: Look for paragraph/div elements with requirement keywords
                if not raw_reqs:
                    req_elements = container.select("p, div, span")
                    for elem in req_elements:
                        elem_text = elem.get_text(strip=True)
                        if (elem_text and len(elem_text) > 5 and
                            any(keyword in elem_text.lower() for keyword in 
                                ["min.", "max.", "exactly", "chemistry", "rating", "players", "from", "ovr"])):
                            raw_reqs.append(elem_text)
                            print(f"      Requirement (element): {elem_text[:50]}")
                
                # Method 3: Parse all text line by line for requirement patterns
                if not raw_reqs:
                    container_text = container.get_text("\n", strip=True)
                    for line in container_text.splitlines():
                        line = line.strip()
                        if (line and len(line) > 5 and len(line) < 200 and
                            any(keyword in line.lower() for keyword in 
                                ["min.", "max.", "exactly", "chemistry", "rating", "players", "from", "squad", "team"])):
                            raw_reqs.append(line)
                            print(f"      Requirement (text): {line[:50]}")

                if not raw_reqs:
                    print(f"      No requirements found for '{title}'")
                    continue

                # Remove duplicates while preserving order
                seen = set()
                unique_reqs = []
                for req in raw_reqs:
                    if req not in seen:
                        seen.add(req)
                        unique_reqs.append(req)

                # Normalize requirements
                try:
                    normalized = normalize_requirements(unique_reqs)
                    print(f"      Normalized {len(normalized)} requirements")
                except Exception as e:
                    print(f"⚠️ Failed to normalize requirements for {title}: {e}")
                    normalized = [{"kind": "raw", "text": req} for req in unique_reqs]

                # Extract cost and reward info
                cost = None
                reward_text = None
                
                container_text = container.get_text(" ", strip=True)
                
                # Look for cost patterns
                cost_patterns = [
                    r"(?:cost|price)\s*:?\s*([\d,\.]+)",
                    r"([\d,]+)\s*coins?\b"
                ]
                
                for pattern in cost_patterns:
                    match = re.search(pattern, container_text, re.IGNORECASE)
                    if match:
                        digits = re.sub(r"[^\d]", "", match.group(1))
                        if digits.isdigit():
                            cost = int(digits)
                            break
                
                # Look for reward text
                reward_match = re.search(r"(?:reward|prize)\s*:?\s*([^\n\r]{1,100})", container_text, re.IGNORECASE)
                if reward_match:
                    reward_text = reward_match.group(1).strip()

                sub_challenges.append({
                    "name": title,
                    "cost": cost,
                    "reward": reward_text,
                    "requirements": normalized,
                })
        
        except Exception as e:
            print(f"    Error with selector '{selector}': {e}")
            continue

    print(f"📊 Parsed '{name}' with {len(sub_challenges)} challenges")
    
    return {
        "slug": url.replace(HOME, ""),
        "url": url,
        "name": name,
        "repeatable": repeatable,
        "expires_at": expires_at,
        "cost": None,
        "rewards": rewards,
        "sub_challenges": sub_challenges,
    }

async def crawl_all_sets(debug_first=True) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        print("🌐 Fetching main SBC page...")
        list_html = await fetch_html(client, f"{HOME}/sbc/")
        links = discover_set_links(list_html)

        # Also check category pages for more comprehensive coverage
        categories = ["live", "players", "icons", "upgrades", "foundations"]
        for cat in categories:
            try:
                print(f"🌐 Fetching category: {cat}")
                cat_html = await fetch_html(client, f"{HOME}/sbc/{cat}/")
                category_links = discover_set_links(cat_html)
                links.extend(category_links)
            except Exception as e:
                print(f"⚠️ Failed to fetch category {cat}: {e}")
        
        # Remove duplicates and sort
        links = sorted(set(links))
        print(f"🎯 Processing {len(links)} total SBC links")

        results: List[Dict[str, Any]] = []
        failed_count = 0
        
        for i, link in enumerate(links, 1):
            try:
                print(f"📄 Processing {i}/{len(links)}: {link}")
                html = await fetch_html(client, link)
                
                # Debug the first few pages to understand structure
                debug = debug_first and i <= 3
                parsed_set = parse_set_page(html, link, debug=debug)
                
                # Only include sets that have actual content
                if parsed_set["name"] and (parsed_set["sub_challenges"] or parsed_set["rewards"]):
                    results.append(parsed_set)
                else:
                    print(f"⚠️ Skipping empty set: {link}")
                    
            except Exception as e:
                failed_count += 1
                print(f"💥 Failed to parse {link}: {e}")
                if failed_count > len(links) * 0.5:  # If more than 50% fail, something is wrong
                    print("💥 Too many failures, stopping crawl")
                    break
        
        print(f"✅ Successfully parsed {len(results)} SBC sets ({failed_count} failed)")
        return results
