import re
from typing import Dict, Any, List

def _clean(s: str) -> str:
    """Clean and normalize text"""
    # Remove extra whitespace and dots
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    # Remove bullet points and other list markers
    s = re.sub(r"^[•\-\*\d+\.\)]\s*", "", s)
    return s

def norm_requirement(line: str) -> Dict[str, Any]:
    """Normalize a single requirement line into structured data"""
    s = _clean(line)
    
    if not s:
        return {"kind": "empty", "text": ""}
    
    # Team Rating requirements
    patterns = [
        (r"Min\.?\s*Team\s*Rating:?\s*(\d+)", lambda m: {
            "kind": "team_rating_min", 
            "value": int(m.group(1)),
            "text": s
        }),
        (r"(?:Team\s*Rating|Overall\s*Rating).*?(\d+)\s*(?:min|minimum|or\s*higher)", lambda m: {
            "kind": "team_rating_min",
            "value": int(m.group(1)),
            "text": s
        }),
    ]
    
    # Chemistry requirements
    patterns.extend([
        (r"Min\.?\s*(?:Squad\s*)?Chem(?:istry)?:?\s*(\d+)", lambda m: {
            "kind": "chem_min",
            "value": int(m.group(1)),
            "text": s
        }),
        (r"(?:Chemistry|Chem).*?(\d+)\s*(?:min|minimum|or\s*higher)", lambda m: {
            "kind": "chem_min",
            "value": int(m.group(1)),
            "text": s
        }),
    ])
    
    # Player count from specific groups (leagues, nations, clubs)
    patterns.extend([
        (r"Min\.?\s*(\d+)\s*Players?\s*from:?\s*(.+)", lambda m: {
            "kind": "min_from",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
        (r"(\d+)\s*(?:or\s*more\s*)?Players?\s*from\s*(.+)", lambda m: {
            "kind": "min_from",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
        (r"At\s*least\s*(\d+).*?from\s*(.+)", lambda m: {
            "kind": "min_from",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
    ])
    
    # Special program requirements (TOTW, TOTS, etc.)
    if re.search(r"Team\s*of\s*the\s*Week|TOTS|TOTW|Honourable|Highlights|Featured|Special|In[- ]?Form", s, re.I):
        count_match = re.search(r"Min\.?\s*(\d+)|(\d+)\s*(?:or\s*more|minimum)", s, re.I)
        count = int(count_match.group(1) or count_match.group(2)) if count_match else 1
        
        # Extract program names, handle OR conditions
        program_text = re.sub(r"^.*?(?:Min\.?\s*\d+\s*)?Players?:?\s*", "", s, flags=re.I)
        programs = [_clean(p) for p in re.split(r"\s*(?:OR|,)\s*", program_text)]
        
        return {
            "kind": "min_program",
            "count": count,
            "programs": programs,
            "text": s
        }
    
    # Count constraints (Exactly X, Max X)
    patterns.extend([
        (r"Exactly\s*(\d+)\s*(.+)", lambda m: {
            "kind": "count_constraint",
            "op": "eq",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
        (r"Max\.?\s*(\d+)\s*(.+)", lambda m: {
            "kind": "count_constraint",
            "op": "le",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
        (r"No\s*more\s*than\s*(\d+)\s*(.+)", lambda m: {
            "kind": "count_constraint",
            "op": "le",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
    ])
    
    # Player rating requirements
    patterns.extend([
        (r"Min\.?\s*(\d+)\s*(?:Players?\s*with\s*)?(\d+)\+?\s*(?:OVR|Overall|Rating)", lambda m: {
            "kind": "min_rating_players",
            "count": int(m.group(1)),
            "rating": int(m.group(2)),
            "text": s
        }),
        (r"(\d+)\s*(?:or\s*more\s*)?Players?\s*(?:with\s*)?(\d+)\+?\s*(?:OVR|Overall|Rating)", lambda m: {
            "kind": "min_rating_players",
            "count": int(m.group(1)),
            "rating": int(m.group(2)),
            "text": s
        }),
    ])
    
    # Rare players
    if re.search(r"rare|gold|silver|bronze", s, re.I):
        count_match = re.search(r"Min\.?\s*(\d+)|(\d+)\s*(?:or\s*more)", s, re.I)
        count = int(count_match.group(1) or count_match.group(2)) if count_match else 1
        
        rarity = "rare"
        if re.search(r"gold", s, re.I):
            rarity = "gold"
        elif re.search(r"silver", s, re.I):
            rarity = "silver" 
        elif re.search(r"bronze", s, re.I):
            rarity = "bronze"
            
        return {
            "kind": "min_rarity",
            "count": count,
            "rarity": rarity,
            "text": s
        }
    
    # Position requirements
    if re.search(r"(?:GK|CB|LB|RB|CDM|CM|CAM|LM|RM|LW|RW|CF|ST)", s, re.I):
        return {
            "kind": "position_req",
            "text": s,
            "positions": re.findall(r"(?:GK|CB|LB|RB|CDM|CM|CAM|LM|RM|LW|RW|CF|ST)", s, re.I)
        }
    
    # Try all patterns
    for pattern, handler in patterns:
        match = re.match(pattern, s, re.I)
        if match:
            try:
                return handler(match)
            except (ValueError, IndexError):
                continue
    
    # Fallback - return as raw text
    return {"kind": "raw", "text": s}

def normalize_requirements(lines: List[str]) -> List[Dict[str, Any]]:
    """Normalize a list of requirement lines"""
    normalized = []
    
    for line in lines:
        if not line or not line.strip():
            continue
            
        try:
            norm = norm_requirement(line)
            if norm["kind"] != "empty":  # Skip empty requirements
                normalized.append(norm)
        except Exception as e:
            # Fallback for any parsing errors
            print(f"⚠️ Failed to parse requirement '{line}': {e}")
            normalized.append({"kind": "raw", "text": _clean(line)})
    
    return normalized

# Test function for debugging
def test_normalizer():
    """Test the normalizer with common SBC requirements"""
    test_cases = [
        "Min. Team Rating: 84",
        "Min. Chemistry: 95",
        "Min. 2 Players from: Premier League",
        "Exactly 11 Gold Players",
        "Max. 3 Players from the same Club",
        "Min. 1 Team of the Week OR Team of the Season Player",
        "Min. 2 Players with 86+ OVR",
        "At least 1 Rare Gold Player",
        "GK, CB, ST positions required"
    ]
    
    print("🧪 Testing normalizer:")
    for case in test_cases:
        result = norm_requirement(case)
        print(f"  '{case}' -> {result}")

if __name__ == "__main__":
    test_normalizer()
