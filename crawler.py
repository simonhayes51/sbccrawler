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
    if el is None:
        return ""
    if isinstance(el, dict):  # defensive
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
    soup = BeautifulSoup(html, "html.parser")
    links: Set[str] = set()
    for a in soup.find_all("a", href=True):
        clean = a["href"].split("#")[0].split("?")[0]
        if not clean.startswith("/sbc/"):
            continue
        if CATEGORY_PATH_RE.search(clean):
            continue
        if clean == "/sbc/":
            continue
        parts = [p for p in clean.split("/") if p]
        if len(parts) >= 2:
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
    seen, out = set(), []
    for r in rewards:
        if r["label"] not in seen:
            seen.add(r["label"])
            out.append(r)
    return out

def _normalize_req_nodes(nodes) -> List[Dict[str, Any]]:
    """Always feed normalize_requirements a list of plain strings."""
    texts: List[str] = []
    for n in nodes:
        t = _text(n)
        if t:
            texts.append(t)
    # normalize_requirements should now only get strings
    norm = normalize_requirements([{"text": t} for t in texts])
    return norm

def _gather_requirements(container: BeautifulSoup) -> List[Dict[str, Any]]:
    nodes = container.select(".squad-challenge-card__requirements li")
    if not nodes:
        for sel in [
            ".challenge-requirements li",
            ".sbc-requirements li",
            ".requirements li",
            ".requirements .item",
            ".sbc__requirements li",
        ]:
            nodes = container.select(sel)
            if nodes:
                break
    return _normalize_req_nodes(nodes)

def parse_set_page(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
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
        if not normalized:
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

    return {"name": title, "rewards": set_rewards, "sub_challenges": sub_challenges}

async def crawl_all_sets() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (crawler bot)"}) as client:
        home_html = await fetch_html(client, urljoin(HOME, "/sbc"))
        links = discover_set_links(home_html)

        uniq_links, seen = [], set()
        for l in links:
            if l not in seen:
                seen.add(l)
                uniq_links.append(l)

        print(f"🌐 Total SBC links to parse: {len(uniq_links)}")

        parsed_ok, failed = 0, 0
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
