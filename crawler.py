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

# Looks like FUT.GG often renders requirements as plain <li> text with no classes.
# We therefore fall back to regex matching for typical SBC phrases.
REQ_LINE_RE = re.compile(
    r"\b(Min\.|Max\.|Exactly|Players?\s+from|Overall|Team\s+Rating|Squad\s+Total\s+Chemistry|Chemistry|Club|Nation|League|Rare|Gold|Silver|Bronze|Common)\b",
    re.I,
)

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
    """Find SBC set links on listing pages, ignoring /sbc/category/*."""
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
        if len(parts) >= 2:  # ["sbc", "slug", ...]
            links.add(urljoin(HOME, clean))

    return sorted(links)

def _parse_rewards(container: BeautifulSoup) -> List[Dict[str, Any]]:
    """Try a few selectors; also accept plain text that includes 'Pack'."""
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

    # Fallback: any text node mentioning 'Pack' near 'Rewards'
    # (This is best-effort; we keep it simple to avoid false positives.)
    if not rewards:
        # scan all elements; if heading-like text contains "Rewards",
        # grab the following sibling text that includes "Pack"
        for heading in container.find_all(text=True):
            t = (heading or "").strip()
            if not t:
                continue
            if "reward" in t.lower():
                parent = getattr(heading, "parent", None)
                if not parent:
                    continue
                # look ahead a few siblings for "Pack"
                nxt = parent
                for _ in range(5):
                    nxt = nxt.find_next(string=True)
                    if not nxt:
                        break
                    s = (nxt or "").strip()
                    if s and "pack" in s.lower():
                        rewards.append({"label": s})
                        break
                if rewards:
                    break

    # de-dupe
    seen = set()
    out = []
    for r in rewards:
        label = r.get("label") or ""
        if not label or label in seen:
            continue
        seen.add(label)
        out.append({"label": label})
    return out

def _normalize_req_texts(texts: List[str]) -> List[Dict[str, Any]]:
    """Always pass normalize_requirements a list of dicts with 'text' keys."""
    # Filter out junk/duplicates early
    cleaned = []
    seen = set()
    for t in texts:
        tt = (t or "").strip()
        if not tt:
            continue
        if tt in seen:
            continue
        seen.add(tt)
        cleaned.append(tt)
    return normalize_requirements([{"text": t} for t in cleaned])

def _gather_requirements(container: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Try multiple patterns to find requirement lines.
    FUT.GG often renders plain <li> with no classes, so we include a regex fallback.
    """
    # Prefer known class patterns first
    for sel in [
        ".squad-challenge-card__requirements li",
        ".challenge-requirements li",
        ".sbc-requirements li",
        ".requirements li",
        ".requirements .item",
        ".sbc__requirements li",
    ]:
        nodes = container.select(sel)
        if nodes:
            return _normalize_req_texts([_text(n) for n in nodes])

    # Heuristic fallback: any <li> that looks like an SBC constraint
    li_texts = []
    for li in container.select("li"):
        t = _text(li)
        if t and REQ_LINE_RE.search(t):
            li_texts.append(t)

    if li_texts:
        return _normalize_req_texts(li_texts)

    # Super-fallback: scan all <p> and bare text nodes for lines that match the pattern
    p_texts = []
    for p in container.select("p"):
        t = _text(p)
        if t and REQ_LINE_RE.search(t):
            # Split on bullets or newlines if needed
            for line in re.split(r"[\n•]+", t):
                line = line.strip(" -\u2022\t\r\n")
                if line and REQ_LINE_RE.search(line):
                    p_texts.append(line)
    if p_texts:
        return _normalize_req_texts(p_texts)

    return []

def parse_set_page(html: str) -> Dict[str, Any]:
    """Parse one SBC set page into a payload compatible with our DB/UI."""
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title = (
        _text(soup.select_one("h1"))
        or _text(soup.select_one(".page-title"))
        or _text(soup.select_one('[data-testid="sbc-title"]'))
        or "Unknown SBC"
    )

    # FUT.GG sometimes has card wrappers; if not, use the whole page as a single challenge
    candidates: List[Tuple[BeautifulSoup, str, str]] = []
    for div in soup.select(".squad-challenge-card"):
        t = _text(div.select_one(".squad-challenge-card__title")) or "Challenge"
        reward_text = _text(div.select_one(".squad-challenge-card__reward"))
        candidates.append((div, t, reward_text))

    # If none found, fall back to the whole page as 1 challenge (most single-page SBCs)
    if not candidates:
        # Secondary attempt: some pages use H2 as the challenge title
        h2 = soup.select_one("h2")
        ch_title = _text(h2) or title
        candidates = [(soup, ch_title, "")]

    sub_challenges: List[Dict[str, Any]] = []
    seen_titles: Set[str] = set()
    seen_sigs: Set[str] = set()

    for container, ch_title, reward_text in candidates:
        normalized = _gather_requirements(container)

        # If nothing matched but this is the whole page, try one last sweep for list items anywhere:
        if not normalized and container is soup:
            all_li = [li for li in soup.select("li") if REQ_LINE_RE.search(_text(li))]
            if all_li:
                normalized = _normalize_req_texts([_text(li) for li in all_li])

        # De-dupe signature
        sig = "|".join(
            f"{r.get('kind')}:{r.get('key') or ''}:{r.get('op') or ''}:{r.get('value') or r.get('text') or ''}"
            for r in normalized
        )

        if not normalized:
            # no requirements → skip this candidate
            continue
        if ch_title in seen_titles or sig in seen_sigs:
            continue

        sub_challenges.append({
            "name": ch_title,
            "cost": 0,  # solver will fill
            "reward": reward_text,
            "requirements": normalized,
        })
        seen_titles.add(ch_title)
        seen_sigs.add(sig)

    set_rewards = _parse_rewards(soup)

    # If still nothing, return empty so scheduler skips gracefully
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
        # Load main SBC page and collect links
        home_html = await fetch_html(client, urljoin(HOME, "/sbc"))
        links = discover_set_links(home_html)

        # (Optional) you can also probe other listing pages if needed
        # for extra in ["/sbc/active", "/sbc/popular", "/sbc/live"]:
        #     try:
        #         extra_html = await fetch_html(client, urljoin(HOME, extra))
        #         links.extend(discover_set_links(extra_html))
        #     except Exception:
        #         pass

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
