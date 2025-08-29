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

def is_valid_requirement(text: str) -> bool:
    """Check if text looks like an actual SBC requirement"""
    text_lower = text.lower()
    
    # Skip generic UI text
    skip_patterns = [
        "fill player positions", "building chemistry", "player positions while",
        "chemistry for", "rare gold players pack", "xx", "pack", 
        "instagram", "discord", "challenges", "solution", "squad builder",
        "cheapest", "price", "total cost", "reward"
    ]
    
    if any(skip in text_lower for skip in skip_patterns):
        return False
    
    # Must contain SBC requirement keywords
    requirement_keywords = [
        "min.", "max.", "exactly", "chemistry", "rating", "players from",
        "ovr", "overall", "squad", "team", "league", "club", "nation",
        "rare", "common", "gold", "silver", "bronze", "totw", "inform",
        "same", "different", "position"
    ]
    
    has_keyword = any(keyword in text_lower for keyword in requirement_keywords)
    
    # Must be reasonable length for a requirement
    reasonable_length = 10 <= len(text) <= 150
    
    # Must contain numbers (most SBC requirements have numbers)
    has_numbers = any(char.isdigit() for char in text)
    
    return has_keyword and reasonable_length and (has_numbers or "same" in text_lower or "different" in text_lower)

def extract_requirements_from_container(container) -> List[str]:
    """Extract SBC requirements from a container, filtering out noise"""
    raw_reqs = []
    
    # Method 1: Look for structured lists first
    for li in container.select("ul li, ol li"):
        text = li.get_text(strip=True)
        if is_valid_requirement(text):
            raw_reqs.append(text)
            print(f"      ✓ Valid requirement (list): {text[:60]}")
        else:
            print(f"      ✗ Skipped (list): {text[:60]}")
    
    # Method 2: Look for divs/spans with requirement-like content
    if not raw_reqs:
        for elem in container.select("div, span, p"):
            text = elem.get_text(strip=True)
            if is_valid_requirement(text):
                # Make sure this isn't a parent container with lots of text
                if len(text) < 200 and text not in raw_reqs:
                    raw_reqs.append(text)
                    print(f"      ✓ Valid requirement (element): {text[:60]}")
    
    # Method 3: Pattern matching on container text
    if not raw_reqs:
        container_text = container.get_text("\n", strip=True)
        for line in container_text.splitlines():
            line = line.strip()
            if is_valid_requirement(line):
                raw_reqs.append(line)
                print(f"      ✓ Valid requirement (text): {line[:60]}")
    
    return raw_reqs

def find_challenge_containers(soup: BeautifulSoup) -> List[tuple]:
    """Find containers that likely contain challenge/squad information"""
    containers = []
    
    # Look for containers with meaningful structure
    # Priority 1: Explicit challenge/squad containers
    for container in soup.select(".challenge, .squad, .sbc-challenge, [class*='challenge'], [class*='squad']"):
        title = extract_title_from_container(container)
        if title:
            containers.append((container, title, "explicit"))
    
    # Priority 2: Cards or sections with headings
    for container in soup.select(".card, .section, section, article"):
        title = extract_title_from_container(container)
        if title and has_requirement_content(container):
            containers.append((container, title, "card"))
    
    # Priority 3: Divs with classes that contain meaningful content
    processed_titles = set()
    for container in soup.select("div[class]"):
        title = extract_title_from_container(container)
        if (title and title not in processed_titles and 
            has_requirement_content(container) and 
            len(container.get_text(strip=True)) > 50):  # Has substantial content
            containers.append((container, title, "div"))
            processed_titles.add(title)
    
    print(f"  Found {len(containers)} potential challenge containers")
    return containers

def extract_title_from_container(container) -> Optional[str]:
    """Extract a meaningful title from a container"""
    # Look for headings
    for heading in container.select("h1, h2, h3, h4, h5, h6"):
        title = heading.get_text(strip=True)
        if title and len(title) >= 3 and len(title) <= 100:
            # Skip generic titles
            if title.lower() not in ["requirements", "reward", "rewards", "cost", "squad", "team", "challenges"]:
                return title
    
    # Look for emphasized text that might be titles
    for elem in container.select(".title, .name, .heading, .font-bold, .text-lg, [class*='title'], [class*='name']"):
        title = elem.get_text(strip=True)
        if title and len(title) >= 3 and len(title) <= 100:
            if title.lower() not in ["requirements", "reward", "rewards", "cost", "squad", "team"]:
                return title
    
    return None

def has_requirement_content(container) -> bool:
    """Check if container has SBC requirement-like content"""
    text = container.get_text().lower()
    requirement_indicators = [
        "min.", "max.", "exactly", "chemistry", "rating", 
        "players from", "ovr", "same club", "same league", "same nation"
    ]
    return any(indicator in text for indicator in requirement_indicators)

def extract_expiry_date(soup: BeautifulSoup) -> Optional[datetime]:
    """Try to extract expiry date from various possible locations"""
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

    # Extract page title
    name = None
    title_selectors = ["h1", "h2", ".page-title", ".sbc-title", ".title"]
    
    for selector in title_selectors:
        title_el = soup.select_one(selector)
        if title_el:
            name = title_el.get_text(strip=True)
            if name and len(name) > 5:
                break
    
    if not name:
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

    # Extract rewards
    rewards: List[Dict[str, Any]] = []
    for elem in soup.select("img[alt*='pack' i], img[alt*='player' i], img[alt*='coins' i]"):
        alt_text = elem.get("alt", "")
        if alt_text and len(alt_text) > 2:
            reward_type = "pack" if "pack" in alt_text.lower() else "other"
            rewards.append({"type": reward_type, "label": alt_text.strip()})

    # Parse sub-challenges using improved logic
    sub_challenges: List[Dict[str, Any]] = []
    
    # Find potential challenge containers
    containers = find_challenge_containers(soup)
    
    processed_titles = set()
    processed_requirements = set()  # Track requirement combinations to avoid duplicates
    
    for container, title, source_type in containers:
        if title in processed_titles:
            continue
        print(f"    Processing challenge '{title}' (from {source_type})")
        
        # Extract requirements with filtering
        raw_reqs = extract_requirements_from_container(container)
        
        if not raw_reqs:
            print(f"      No valid requirements found for '{title}'")
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
            print(f"      Normalized {len(normalized)} requirements for '{title}'")
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

        # Also check category pages
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
                if failed_count > len(links) * 0.5:
                    print("💥 Too many failures, stopping crawl")
                    break
        
        print(f"✅ Successfully parsed {len(results)} SBC sets ({failed_count} failed)")
        return results
