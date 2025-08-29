# crawler.py
import re
from typing import Dict, Any, List, Optional, Set, Tuple
from urllib.parse import urljoin
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from normalizer import normalize_requirements

HOME = "https://www.fut.gg"

# Broad SBC URL pattern (covers both slugged and dated variants)
SET_URL_RE = re.compile(r"^/sbc/(?:[^/]+/)?(?:\d{2}-\d{1,6}-|[a-zA-Z0-9\-]+/?)")

async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def discover_set_links(html: str) -> List[str]:
    """Find SBC set links on a page."""
    soup = BeautifulSoup(html, "html.parser")
    links: Set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue

        clean = href.split("#")[0].split("?")[0]
        if not clean.startswith("/sbc/"):
            continue
        if clean == "/sbc/":
            continue
        if clean.endswith("/sbc"):
            continue
        if not SET_URL_RE.search(clean):
            # still allow most /sbc/* pages, as fut.gg varies structure
            if len(clean) <= 5:
                continue

        links.add(urljoin(HOME, clean))

    print(f"🔍 Discovered {len(links)} SBC links")
    return sorted(links)

def _text(el) -> str:
    return el.get_text(strip=True) if el else ""

def _parse_rewards(container: BeautifulSoup) -> List[Dict[str, Any]]:
    rewards: List[Dict[str, Any]] = []
    # Try a few common selectors; fut.gg pages vary a bit
    for sel in [".reward", ".rewards", ".challenge-reward", ".sbc-reward"]:
        for node in container.select(sel):
            txt = _text(node)
            if txt:
                rewards.append({"label": txt})
    # Deduplicate labels
    seen = set()
    uniq = []
    for r in rewards:
        label = r["label"]
        if label in seen:
            continue
        seen.add(label)
        uniq.append(r)
    return uniq

def _normalize_req_elems(req_nodes: List[BeautifulSoup]) -> List[Dict[str, Any]]:
    raw: List[Dict[str, Any]] = []
    for node in req_nodes:
        t = _text(node)
        if t:
            raw.append({"text": t})
    return normalize_requirements(raw)

def parse_set_page(html: str) -> Dict[str, Any]:
    """
    Parse a single SBC set page and return a set payload:
    {
      "name": str,
      "url": str (optional, filled by caller),
      "rewards": [...],
      "sub_challenges": [
         {"name": str, "cost": 0, "reward": str, "requirements":[...]}
      ]
    }
    """
    soup = BeautifulSoup(html, "html.parser")

    # Best-effort title
    title = _text(soup.select_one("h1")) or _text(soup.select_one(".page-title")) or "Unknown SBC"

    # Each challenge container
    candidates: List[Tuple[BeautifulSoup, str, str]] = []
    for sel in [
        ".sbc-challenge",          # common wrapper
        ".challenge",              # alternate
        ".sbc__challenge",         # variant
        ".sbc-challenge-card",     # cards
    ]:
        for div in soup.select(sel):
            t = _text(div.select_one(".challenge-title")) or _text(div.select_one("h2")) or "Challenge"
            reward_text = _text(div.select_one(".reward")) or _text(div.select_one(".challenge-reward"))
            candidates.append((div, t, reward_text))

    # Fallback: sometimes challenges are listed in grouped sections
    if not candidates:
        sections = soup.select(".sbc-set, .sbc-group, .challenges")
        for sec in sections:
            t = _text(sec.select_one("h2")) or _text(sec.select_one(".title")) or "Challenge"
            reward_text = _text(sec.select_one(".reward")) or ""
            candidates.append((sec, t, reward_text))

    sub_challenges: List[Dict[str, Any]] = []
    seen_titles: Set[str] = set()
    seen_sigs: Set[str] = set()

    for container, ch_title, reward_text in candidates:
        if ch_title in seen_titles:
            continue

        # gather requirement nodes with several selector attempts
        req_nodes = []
        for sel in [
            ".requirement", ".requirements li", ".requirements .item",
            ".sbc-requirements li", ".sbc-requirements .item",
            ".requirements", ".challenge-requirements li",
        ]:
            req_nodes.extend(container.select(sel))

        normalized = _normalize_req_elems(req_nodes)

        # build a stable signature to de-dupe equivalent blocks
        sig = "|".join(
            f"{r.get('kind')}:{r.get('key') or ''}:{r.get('op') or ''}:{r.get('value') or r.get('text') or ''}"
            for r in normalized
        )
        if sig in seen_sigs:
            continue

        sub_challenges.append({
            "name": ch_title,
            "cost": 0,  # filled by solver later
            "reward": reward_text,
            "requirements": normalized,
        })
        seen_titles.add(ch_title)
        seen_sigs.add(sig)

    # Set-level rewards (not per-challenge)
    set_rewards = _parse_rewards(soup)

    return {
        "name": title,
        "rewards": set_rewards,
        "sub_challenges": sub_challenges,
    }

async def crawl_all_sets() -> List[Dict[str, Any]]:
    """
    Crawl fut.gg SBC listing pages and return parsed sets.
    This is what scheduler.run_job() expects to import and call.
    """
    results: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (crawler bot)"}) as client:
        # 1) load main SBC page
        home_html = await fetch_html(client, urljoin(HOME, "/sbc"))
        links = discover_set_links(home_html)

        # 2) also follow pagination/topical pages if present
        # (light touch – many sites link them from the main page anyway)
        for extra in ["/sbc/active", "/sbc/popular", "/sbc/live"]:
            try:
                extra_html = await fetch_html(client, urljoin(HOME, extra))
                links.extend(discover_set_links(extra_html))
            except Exception:
                pass

        # unique links, keep order a bit stable
        seen = set()
        uniq_links = []
        for l in links:
            if l in seen:
                continue
            seen.add(l)
            uniq_links.append(l)

        print(f"🌐 Total SBC links to parse: {len(uniq_links)}")

        # 3) parse each set page
        failed = 0
        for link in uniq_links:
            try:
                html = await fetch_html(client, link)
                parsed = parse_set_page(html)
                if parsed.get("name") and (parsed.get("sub_challenges") or parsed.get("rewards")):
                    parsed["url"] = link
                    parsed["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    results.append(parsed)
                else:
                    print(f"⚠️ Skipping empty/invalid set: {link}")
            except Exception as e:
                failed += 1
                print(f"💥 Failed to parse {link}: {e}")
                if failed > max(3, int(len(uniq_links) * 0.5)):
                    print("💥 Too many failures, aborting crawl early.")
                    break

    print(f"✅ Successfully parsed {len(results)} SBC sets (failed {failed})")
    return results
