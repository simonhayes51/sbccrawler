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
SET_URL_RE = re.compile(r"^/sbc/(?:[^/]+/)?(?:\d{2}-\d{1,6}-|[a-zA-Z0-9-]+/?)")

async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue
        clean_href = href.split("#")[0].split("?")[0]
        if (clean_href.startswith("/sbc/") and 
            len(clean_href) > 5 and 
            clean_href != "/sbc/" and
            not clean_href.endswith("/sbc")):
            full_url = urljoin(HOME, clean_href)
            links.add(full_url)

    print(f"🔍 Discovered {len(links)} unique SBC links")
    return sorted(links)

# … and the rest of your functions the same, just replace every “ ” with " and """ for docstrings
