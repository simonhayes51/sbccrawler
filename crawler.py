import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import Dict, Any, List, Set, Optional
from normalizer import normalize_requirements

HOME = "https://www.fut.gg"
LIST_URLS = [f"{HOME}/sbc/"]
SET_URL_RE = re.compile(r"^/sbc/(?:[^/]+/)?\d{2}-\d{1,5}-")

async def
