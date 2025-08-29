# crawler.py
import asyncio
import logging
from bs4 import BeautifulSoup
from normalizer import normalize_requirements

logger = logging.getLogger(__name__)


async def parse_set_page(html: str):
    """
    Parse SBC set HTML and return sub_challenges (deduped).
    """
    soup = BeautifulSoup(html, "html.parser")

    sub_challenges = []
    processed_titles = set()
    processed_signatures = set()

    # Example containers – adjust selectors if needed
    containers = []
    for div in soup.select("div.sbc-challenge"):
        title = div.select_one(".challenge-title")
        title_text = title.get_text(strip=True) if title else "Unknown"
        reward = div.select_one(".reward")
        reward_text = reward.get_text(strip=True) if reward else ""
        containers.append((div, title_text, reward_text))

    for container, title, reward_text in containers:
        if title in processed_titles:
            continue

        req_elems = container.select(".requirement")
        unique_reqs = []
        for elem in req_elems:
            txt = elem.get_text(strip=True)
            if not txt:
                continue
            unique_reqs.append({"text": txt})

        normalized = normalize_requirements(unique_reqs)

        sig = "|".join(
            f"{r.get('kind')}:{r.get('key') or ''}:{r.get('op') or ''}:{r.get('value') or r.get('text') or ''}"
            for r in normalized
        )

        if sig in processed_signatures:
            continue

        sub_challenges.append(
            {
                "name": title,
                "cost": 0,  # filled by solver later
                "reward": reward_text,
                "requirements": normalized,
            }
        )

        processed_titles.add(title)
        processed_signatures.add(sig)

    return sub_challenges
