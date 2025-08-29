# crawler.py

import re
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from normalizer import normalize_requirements

__all__ = ["crawl_all_sets", "parse_set_page", "discover_set_links"]

HOME = "https://www.fut.gg"

# Broader SBC URL matcher (accepts /sbc/<cat>/... and slugs)
SET_URL_RE = re.compile(r"^/sbc/(?:[^/]+/)?(?:\d{2}-\d{1,6}-|[A-Za-z0-9-]+/?)")


# ---------------- HTTP ----------------

async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }
    r = await client.get(url, timeout=30, follow_redirects=True, headers=headers)
    r.raise_for_status()
    return r.text


# -------------- Link discovery --------------

def discover_set_links(list_html: str) -> List[str]:
    soup = BeautifulSoup(list_html, "html.parser")
    links: set[str] = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
        clean = href.split("#")[0].split("?")[0]
        if (
            clean.startswith("/sbc/")
            and len(clean) > 5
            and clean != "/sbc/"
            and not clean.endswith("/sbc")
        ):
            links.add(urljoin(HOME, clean))

    print(f"🔍 Discovered {len(links)} unique SBC links")
    return sorted(links)


# -------------- Requirement helpers --------------

def is_valid_requirement(text: str) -> bool:
    t = (text or "").lower().strip()
    if not t:
        return False

    skip = [
        "solution", "cheapest", "price", "reward", "pack", "instagram", "discord",
        "squad builder", "fill player positions", "building chemistry",
        "challenges", "total cost",
    ]
    if any(s in t for s in skip):
        return False

    must_have = [
        "min", "max", "exactly", "chemistry", "rating", "players from", "league",
        "club", "nation", "ovr", "overall", "same", "different", "rare", "gold", "silver", "bronze"
    ]
    has_kw = any(k in t for k in must_have)
    has_num = any(ch.isdigit() for ch in t)

    return has_kw and (has_num or "same" in t or "different" in t) and 8 <= len(t) <= 160


def extract_requirements_from_container(container) -> List[str]:
    reqs: List[str] = []

    # lists first
    for li in container.select("ul li, ol li"):
        s = li.get_text(strip=True)
        if is_valid_requirement(s):
            reqs.append(s)

    # elements
    if not reqs:
        for el in container.select("div, span, p"):
            s = el.get_text(strip=True)
            if is_valid_requirement(s) and len(s) < 200:
                reqs.append(s)

    # line scan
    if not reqs:
        for line in container.get_text("\n", strip=True).splitlines():
            s = line.strip()
            if is_valid_requirement(s):
                reqs.append(s)

    # dedupe preserve order
    seen = set()
    out = []
    for r in reqs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


# -------------- Page parsing --------------

def _extract_expiry(soup: BeautifulSoup) -> Optional[datetime]:
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


def parse_set_page(html: str, url: str, debug: bool = False) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    # title
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

    expires_at = _extract_expiry(soup)

    # simple rewards by <img alt="... Pack">
    rewards: List[Dict[str, Any]] = []
    for img in soup.select("img[alt]"):
        alt = img.get("alt", "")
        if "pack" in alt.lower():
            rewards.append({"type": "pack", "label": alt.strip()})

    # find challenge-like containers
    sub_challenges: List[Dict[str, Any]] = []
    containers = soup.select(
        ".challenge, .squad, .sbc-challenge, [class*='challenge'], [class*='squad'], "
        ".card, section, article"
    )
    seen_titles = set()
    for c in containers:
        # container title
        title = None
        for h in c.select("h1, h2, h3, .title, .name, .heading, .font-bold, .text-lg"):
            txt = h.get_text(strip=True)
            if txt and txt.lower() not in {"requirements", "reward", "rewards", "cost", "squad", "team", "challenges"}:
                title = txt
                break
        if not title or title in seen_titles:
            continue

        reqs = extract_requirements_from_container(c)
        if not reqs:
            continue

        try:
            normalized = normalize_requirements(reqs)
        except Exception:
            normalized = [{"kind": "raw", "text": r} for r in reqs]

        sub_challenges.append(
            {"name": title, "cost": None, "reward": None, "requirements": normalized}
        )
        seen_titles.add(title)

    if debug:
        print(f"📊 Parsed '{name}' with {len(sub_challenges)} challenges")

    return {
        "slug": url.replace(HOME, ""),
        "url": url,
        "name": name,
        "repeatable": None,
        "expires_at": expires_at,
        "cost": None,
        "rewards": rewards,
        "sub_challenges": sub_challenges,
    }


# -------------- Crawl entrypoint --------------

async def crawl_all_sets(debug_first: bool = True) -> List[Dict[str, Any]]:
    """
    Crawl FUT.GG SBC index + a few category pages.
    Returns a list of dict payloads usable by db.upsert_set().
    """
    results: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient() as client:
            print("🌐 Fetching main SBC page…")
            list_html = await fetch_html(client, f"{HOME}/sbc/")
            links = discover_set_links(list_html)

            # also categories (best-effort)
            for cat in ["live", "players", "icons", "upgrades", "foundations"]:
                try:
                    print(f"🌐 Fetching category: {cat}")
                    cat_html = await fetch_html(client, f"{HOME}/sbc/{cat}/")
                    links.extend(discover_set_links(cat_html))
                except Exception as e:
                    print(f"⚠️ Category fetch failed ({cat}): {e}")

            links = sorted(set(links))
            print(f"🎯 Processing {len(links)} total SBC links")

            for i, link in enumerate(links, 1):
                try:
                    html = await fetch_html(client, link)
                    payload = parse_set_page(html, link, debug=(debug_first and i <= 3))
                    if payload.get("name") and (payload.get("sub_challenges") or payload.get("rewards")):
                        results.append(payload)
                    else:
                        print(f"⚠️ Skipping empty set: {link}")
                except Exception as e:
                    print(f"💥 Failed to parse {link}: {e}")

        print(f"✅ Successfully parsed {len(results)} SBC sets")
        return results
    except Exception as e:
        print(f"💥 crawl_all_sets failed: {e}")
        return []
