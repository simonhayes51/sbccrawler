# crawler.py
import re
from typing import Dict, Any, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from normalizer import normalize_requirements

HOME = "https://www.fut.gg"

# e.g. /sbc/upgrades/25-1207-84-x10-upgrade/
SET_URL_RE = re.compile(r"^/sbc/(?:[^/]+/)?\d{2}-\d{1,6}-")

async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def discover_set_links(list_html: str) -> List[str]:
    soup = BeautifulSoup(list_html, "html.parser")
    links: set[str] = set()
    for a in soup.select("a[href]"):
        href = a["href"]
        if SET_URL_RE.match(href):
            links.add(urljoin(HOME, href.split("#")[0]))
    return sorted(links)

def parse_set_page(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    # Title / name
    title_el = soup.select_one("h1, h2")
    name = title_el.get_text(strip=True) if title_el else None

    # Try to read some top-level meta if present (best-effort)
    repeatable = None
    expires_at = None
    site_cost = None
    rewards: List[Dict[str, Any]] = []

    # Heuristic reward icons/text
    for img in soup.select("img[alt]"):
        alt = (img.get("alt") or "").strip()
        if not alt:
            continue
        low = alt.lower()
        if "pack" in low or "evolution" in low or "unlock" in low:
            rewards.append({"type": "pack" if "pack" in low else "evolution" if "evolution" in low else "other",
                            "label": alt})

    # Sub-challenges: FUT.GG renders each challenge with a heading + a list of requirements
    sub_challenges: List[Dict[str, Any]] = []
    # Search broadly for blocks that look like a challenge card
    for blk in soup.select("section, article, div"):
        title = None
        h = blk.select_one("h3, h4, .text-lg, .font-bold")
        if h:
            t = h.get_text(strip=True)
            # avoid picking top page title
            if t and len(t) >= 3 and t != name:
                title = t

        if not title:
            continue

        # Requirements are usually in <ul><li>…</li></ul>
        raw_reqs: List[str] = [li.get_text(strip=True) for li in blk.select("ul li")]
        # Fallback: scan lines under the block for “Min./Max./Exactly”
        if not raw_reqs:
            text_lines = blk.get_text("\n", strip=True).splitlines()
            for line in text_lines:
                l = line.strip()
                if l.lower().startswith(("min.", "max.", "exactly")):
                    raw_reqs.append(l)

        if not raw_reqs:
            continue

        normalized = normalize_requirements(raw_reqs)

        # Nearby “cost” or “reward” hints (best-effort, often absent on list pages)
        cost = None
        reward_text = None
        blob = blk.get_text(" ", strip=True)
        m_cost = re.search(r"(?:cost|price)\s*:?\s*([\d,\.]+)", blob, flags=re.I)
        if m_cost:
            digits = re.sub(r"[^\d]", "", m_cost.group(1))
            if digits.isdigit():
                cost = int(digits)
        m_rew = re.search(r"(reward|rewards?)\s*:?\s*(.+?)(?=$|•)", blob, flags=re.I)
        if m_rew:
            reward_text = m_rew.group(2).strip()

        sub_challenges.append({
            "name": title,
            "cost": cost,
            "reward": reward_text,
            "requirements": normalized,
        })

    return {
        "slug": url.replace(HOME, ""),
        "url": url,
        "name": name,
        "repeatable": repeatable,
        "expires_at": expires_at,
        "cost": site_cost,
        "rewards": rewards,
        "sub_challenges": sub_challenges,
    }

async def crawl_all_sets() -> List[Dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        list_html = await fetch_html(client, f"{HOME}/sbc/")
        links = discover_set_links(list_html)

        # If categories exist, add more links (optional)
        # for cat in ["players", "challenges", "icons", "foundations", "upgrades"]:
        #     cat_html = await fetch_html(client, f"{HOME}/sbc/category/{cat}/")
        #     links.extend(discover_set_links(cat_html))
        # links = sorted(set(links))

        results: List[Dict[str, Any]] = []
        for link in links:
            try:
                html = await fetch_html(client, link)
                results.append(parse_set_page(html, link))
            except Exception as e:
                # Keep crawling even if one page fails
                print(f"⚠️ Failed to parse {link}: {e}")
        return results
