# crawler.py
import re
from typing import Dict, Any, List, Set, Tuple
from urllib.parse import urljoin
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from normalizer import normalize_requirements

HOME = "https://www.fut.gg"
CATEGORY_PATH_RE = re.compile(r"/sbc/category/")

def _text(el) -> str:
    """Safe text extractor that tolerates dicts and non-tags."""
    if el is None:
        return ""
    if isinstance(el, dict):
        return el.get("text", "")
    try:
        return el.get_text(strip=True)
    except Exception:
        return str(el).strip()

async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def discover_set_links(html: str) -> List[str]:
    """Find SBC set links on a listing page, ignoring category index pages."""
    soup = BeautifulSoup(html, "html.parser")
    links: Set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        clean = href.split("#")[0].split("?")[0]
        if not clean.startswith("/sbc/"):
            continue
        if CATEGORY_PATH_RE.search(clean):
            continue
        if clean == "/sbc/":
            continue

        parts = [p for p in clean.split("/") if p]
        if len(parts) >= 2:  # ["sbc", "something", ...]
            links.add(urljoin(HOME, clean))

    return sorted(links)

def _parse_rewards(container: BeautifulSoup) -> List[Dict[str, Any]]:
    rewards: List[Dict[str, Any]] = []
    for sel in [
        ".squad-challenge-card__reward",
        ".challenge-reward",
        ".sbc-reward",
        ".reward",
    ]:
        for node in container.select(sel):
            txt = _text(node)
            if txt:
                rewards.append({"label": txt})
    # de-dupe
    seen = set()
    out = []
    for r in rewards:
        if r["label"] in seen:
            continue
        seen.add(r["label"])
        out.append(r)
    return out

def _normalize_req_nodes(nodes) -> List[Dict[str, Any]]:
    raw: List[Dict[str, Any]] = []
    for n in nodes:
        txt = _text(n)
        if txt:
            raw.append({"text": txt})
    return normalize_requirements(raw)

def _gather_requirements(container: BeautifulSoup) -> List[Dict[str, Any]]:
    """Try multiple patterns to find requirement list items."""
    # FUT.GG’s most common
    nodes = container.select(".squad-challenge-card__requirements li")
    if nodes:
        return _normalize_req_nodes(nodes)

    for sel in [
        ".challenge-requirements li",
        ".sbc-requirements li",
        ".requirements li",
        ".requirements .item",
        ".sbc__requirements li",
    ]:
        nodes = container.select(sel)
        if nodes:
            return _normalize_req_nodes(nodes)

    # Heuristic: any <li> under a block mentioning “Requirement”
    candidates = []
    for block in container.find_all(True):
        txt = (block.get_text(" ", strip=True) or "").lower()
        if "requirement" in txt:
            candidates.extend(block.select("li"))
    if candidates:
        return _normalize_req_nodes(candidates)

    # Extreme fallback: grab any <li> that looks like SBC constraints
    lst = []
    for li in container.select("li"):
        t = _text(li)
        if not t:
            continue
        if re.search(r"\b(Min\.|Max\.|Exactly|Players? from|Overall|Chemistry|Rating|Club|Nation|League)\b", t, re.I):
            lst.append(li)
    if lst:
        return _normalize_req_nodes(lst)

    return []

def parse_set_page(html: str) -> Dict[str, Any]:
    """Parse one SBC set page into a payload."""
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title = (
        _text(soup.select_one("h1"))
        or _text(soup.select_one(".page-title"))
        or _text(soup.select_one('[data-testid="sbc-title"]'))
        or "Unknown SBC"
    )

    candidates: List[Tuple[BeautifulSoup, str, str]] = []
    for div in soup.select(".squad-challenge-card"):
        t = _text(div.select_one(".squad-challenge-card__title")) or "Challenge"
        reward_text = _text(div.select_one(".squad-challenge-card__reward"))
        candidates.append((div, t, reward_text))

    if not candidates:
        for sel in [
            ".sbc-challenge", ".sbc__challenge", ".challenge", ".challenge-card",
            '[data-testid="challenge-card"]'
        ]:
            for div in soup.select(sel):
                t = (
                    _text(div.select_one(".challenge-title"))
                    or _text(div.select_one("h2"))
                    or _text(div.select_one('[data-testid="challenge-title"]'))
                    or "Challenge"
                )
                reward_text = (
                    _text(div.select_one(".challenge-reward"))
                    or _text(div.select_one(".sbc-reward"))
                    or _text(div.select_one('[data-testid="challenge-reward"]'))
                )
                candidates.append((div, t, reward_text))

    if not candidates:
        candidates = [(soup, title, "")]

    sub_challenges: List[Dict[str, Any]] = []
    seen_titles: Set[str] = set()
    seen_sigs: Set[str] = set()

    for container, ch_title, reward_text in candidates:
        normalized = _gather_requirements(container)
        sig = "|".join(
            f"{r.get('kind')}:{r.get('key') or ''}:{r.get('op') or ''}:{r.get('value') or r.get('text') or ''}"
            for r in normalized
        )

        if not normalized and container is not soup:
            continue
        if ch_title in seen_titles or sig in seen_sigs:
            continue

        sub_challenges.append({
            "name": ch_title,
            "cost": 0,
            "reward": reward_text,
            "requirements": normalized,
        })
        seen_titles.add(ch_title)
        seen_sigs.add(sig)

    set_rewards = _parse_rewards(soup)

    if not sub_challenges and not set_rewards:
        return {}

    return {
        "name": title,
        "rewards": set_rewards,
        "sub_challenges": sub_challenges,
    }

async def crawl_all_sets() -> List[Dict[str, Any]]:
    """Crawl FUT.GG SBC listing pages and return parsed sets."""
    results: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (crawler bot)"}) as client:
        home_html = await fetch_html(client, urljoin(HOME, "/sbc"))
        links = discover_set_links(home_html)

        for extra in ["/sbc/active", "/sbc/popular", "/sbc/live"]:
            try:
                extra_html = await fetch_html(client, urljoin(HOME, extra))
                links.extend(discover_set_links(extra_html))
            except Exception:
                pass

        uniq_links = []
        seen = set()
        for l in links:
            if l in seen:
                continue
            seen.add(l)
            uniq_links.append(l)

        print(f"🌐 Total SBC links to parse: {len(uniq_links)}")

        parsed_ok = 0
        failed = 0
        for link in uniq_links:
            try:
                html = await fetch_html(client, link)
                parsed = parse_set_page(html)
                if parsed.get("name") and (parsed.get("sub_challenges") or parsed.get("rewards")):
                    parsed["url"] = link
                    parsed["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    results.append(parsed)
                    parsed_ok += 1
                    print(f"✅ Parsed {parsed['name']} with {len(parsed['sub_challenges'])} challenges")
                else:
                    print(f"⚠️ Skipping empty/invalid set: {link}")
            except Exception as e:
                failed += 1
                print(f"💥 Failed to parse {link}: {e}")

        print(f"✅ Parsed {parsed_ok} sets; failed {failed}")
    return results
