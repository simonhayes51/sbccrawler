import re
from typing import Dict, Any, List

def _clean(s: str) -> str:
    """Clean and normalize text"""
    # Remove extra whitespace and dots
    s = re.sub(r"\s+", " ", s).strip().rstrip(".")
    # Remove bullet points and other list markers
    s = re.sub(r"^[•\-\*\d+\.\)]\s*", "", s)
    # Remove common prefixes
    s = re.sub(r"^(requirement|req):\s*", "", s, flags=re.I)
    return s.strip()

def norm_requirement(line: str) -> Dict[str, Any]:
    """Normalize a single requirement line into structured data"""
    s = _clean(line)
    
    if not s:
        return {"kind": "empty", "text": ""}
    
    # Enhanced pattern matching for better detection
    patterns = []
    
    # Team Rating requirements (multiple variations)
    patterns.extend([
        (r"(?:Min\.?\s*)?Team\s*Rating:?\s*(\d+)", lambda m: {
            "kind": "team_rating_min", 
            "value": int(m.group(1)),
            "text": s
        }),
        (r"(?:Min\.?\s*)?Squad\s*Rating:?\s*(\d+)", lambda m: {
            "kind": "team_rating_min", 
            "value": int(m.group(1)),
            "text": s
        }),
        (r"(?:Team|Squad)\s*(?:Rating|OVR).*?(\d+)", lambda m: {
            "kind": "team_rating_min",
            "value": int(m.group(1)),
            "text": s
        }),
        (r"(\d+)\+?\s*(?:Team|Squad)\s*(?:Rating|OVR)", lambda m: {
            "kind": "team_rating_min",
            "value": int(m.group(1)),
            "text": s
        }),
    ])
    
    # Chemistry requirements
    patterns.extend([
        (r"(?:Min\.?\s*)?(?:Squad\s*)?Chem(?:istry)?:?\s*(\d+)", lambda m: {
            "kind": "chem_min",
            "value": int(m.group(1)),
            "text": s
        }),
        (r"Chemistry.*?(\d+)", lambda m: {
            "kind": "chem_min",
            "value": int(m.group(1)),
            "text": s
        }),
        (r"(\d+)\+?\s*Chem(?:istry)?", lambda m: {
            "kind": "chem_min",
            "value": int(m.group(1)),
            "text": s
        }),
    ])
    
    # Player count from specific groups (leagues, nations, clubs)
    patterns.extend([
        (r"(?:Min\.?\s*)?(\d+)\s*Players?\s*from:?\s*(.+)", lambda m: {
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
        (r"(\d+)\+\s*(.+?)\s*(?:Players?|Cards?)", lambda m: {
            "kind": "min_from",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
    ])
    
    # Special program requirements (TOTW, TOTS, etc.) - Enhanced detection
    special_programs = [
        "team of the week", "totw", "tots", "team of the season",
        "honourable mentions", "highlights", "featured", "special", 
        "in-form", "inform", "motm", "man of the match", "hero",
        "icon", "legend", "flashback", "sbc", "objective"
    ]
    
    if any(program in s.lower() for program in special_programs):
        # Extract count
        count_match = re.search(r"(?:Min\.?\s*)?(\d+)|(\d+)\s*(?:or\s*more|minimum)", s, re.I)
        count = 1
        if count_match:
            count = int(count_match.group(1) or count_match.group(2))
        
        # Extract program names, handle OR conditions
        program_text = re.sub(r"^.*?(?:Min\.?\s*\d+\s*)?Players?:?\s*", "", s, flags=re.I)
        program_text = re.sub(r"^.*?(?:\d+\s*(?:or\s*more\s*)?)", "", program_text, flags=re.I)
        
        programs = []
        for part in re.split(r"\s*(?:OR|,|&)\s*", program_text, flags=re.I):
            cleaned = _clean(part)
            if cleaned:
                programs.append(cleaned)
        
        if not programs:
            programs = [program_text.strip()]
        
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
        (r"(?:Max\.?|Maximum)\s*(\d+)\s*(.+)", lambda m: {
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
        (r"(?:Min\.?\s*)?(\d+)\s*(?:Players?\s*with\s*)?(\d+)\+?\s*(?:OVR|Overall|Rating)", lambda m: {
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
        (r"(\d+)\+\s*OVR.*?(\d+)\s*Players?", lambda m: {
            "kind": "min_rating_players",
            "rating": int(m.group(1)),
            "count": int(m.group(2)),
            "text": s
        }),
    ])
    
    # Same/Different constraints
    patterns.extend([
        (r"(?:Max\.?\s*)?(\d+)\s*(?:Players?\s*)?from\s*(?:the\s*)?same\s*(.+)", lambda m: {
            "kind": "same_constraint",
            "op": "le",
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
        (r"(?:Min\.?\s*)?(\d+)\s*different\s*(.+)", lambda m: {
            "kind": "different_constraint",
            "op": "ge", 
            "count": int(m.group(1)),
            "key": _clean(m.group(2)),
            "text": s
        }),
    ])
    
    # Rare/Quality constraints
    rarity_keywords = ["rare", "gold", "silver", "bronze", "common"]
    if any(rarity in s.lower() for rarity in rarity_keywords):
        count_match = re.search(r"(?:Min\.?\s*)?(\d+)|(\d+)\s*(?:or\s*more)", s, re.I)
        count = 1
        if count_match:
            count = int(count_match.group(1) or count_match.group(2))
        
        rarity = "rare"
        for r in rarity_keywords:
            if r in s.lower():
                rarity = r
                break
                
        return {
            "kind": "min_rarity",
            "count": count,
            "rarity": rarity,
            "text": s
        }
    
    # Position requirements
    position_pattern = r"(?:GK|CB|LB|RB|LWB|RWB|CDM|CM|CAM|LM|RM|LW|RW|CF|ST)"
    if re.search(position_pattern, s, re.I):
        positions = re.findall(position_pattern, s, re.I)
        return {
            "kind": "position_req",
            "text": s,
            "positions": [p.upper() for p in positions]
        }
    
    # Nation requirements (specific handling)
    nation_indicators = ["nation", "country", "nationality"]
    if any(indicator in s.lower() for indicator in nation_indicators):
        count_match = re.search(r"(?:Min\.?\s*)?(\d+)", s, re.I)
        count = int(count_match.group(1)) if count_match else 1
        
        return {
            "kind": "nation_req",
            "count": count,
            "text": s
        }
    
    # League requirements (specific handling)
    league_indicators = ["league", "competition", "division"]
    if any(indicator in s.lower() for indicator in league_indicators):
        count_match = re.search(r"(?:Min\.?\s*)?(\d+)", s, re.I)
        count = int(count_match.group(1)) if count_match else 1
        
        return {
            "kind": "league_req", 
            "count": count,
            "text": s
        }
    
    # Club requirements (specific handling) 
    club_indicators = ["club", "team", "side"]
    if any(indicator in s.lower() for indicator in club_indicators):
        count_match = re.search(r"(?:Min\.?\s*)?(\d+)", s, re.I)
        count = int(count_match.group(1)) if count_match else 1
        
        return {
            "kind": "club_req",
            "count": count, 
            "text": s
        }
    
    # Try all patterns
    for pattern, handler in patterns:
        match = re.search(pattern, s, re.I)
        if match:
            try:
                result = handler(match)
                return result
            except (ValueError, IndexError):
                continue
    
    # Enhanced fallback - check if it at least looks like a requirement
    requirement_indicators = [
        "min", "max", "exactly", "chemistry", "rating", "players", "team", 
        "squad", "club", "league", "nation", "same", "different", "rare", 
        "gold", "silver", "bronze", "ovr", "overall"
    ]
    
    if (any(indicator in s.lower() for indicator in requirement_indicators) and 
        any(char.isdigit() for char in s) and
        len(s) > 5):
        return {"kind": "generic_req", "text": s}
    
    # Final fallback
    return {"kind": "raw", "text": s}

def normalize_requirements(lines: List[str]) -> List[Dict[str, Any]]:
    """Normalize a list of requirement lines"""
    normalized = []
    
    for line in lines:
        if not line or not line.strip():
            continue
            
        try:
            norm = norm_requirement(line)
            if norm["kind"] not in ["empty"]:  # Include all non-empty requirements
                normalized.append(norm)
        except Exception as e:
            # Enhanced fallback for any parsing errors
            print(f"⚠️ Failed to parse requirement '{line}': {e}")
            clean_line = _clean(line)
            if clean_line:
                normalized.append({"kind": "raw", "text": clean_line})
    
    return normalized

def test_normalizer():
    """Enhanced test function for debugging"""
    test_cases = [
        # Basic requirements
        "Min. Team Rating: 84",
        "Min. Chemistry: 95", 
        "Team Rating: 91",
        "Squad Rating 88",
        
        # Player count requirements
        "Min. 2 Players from: Premier League",
        "Min. 1 Players from: England",
        "3 Players from Spain",
        "At least 2 players from Serie A",
        
        # Special programs
        "Min. 1 Team of the Week OR Team of the Season Player",
        "2 TOTS Honourable Mentions OR TOTS Highlights",
        "1 In-Form Player",
        "Min 1 Special Card",
        
        # Constraints
        "Exactly 11 Gold Players",
        "Max. 3 Players from the same Club",
        "Max 2 players from same nation", 
        "Min. 5 Different Leagues",
        
        # Rating requirements
        "Min. 2 Players with 86+ OVR",
        "3 Players 85+ Rating",
        "85+ OVR: Min 1 Player",
        
        # Quality requirements
        "Min. 1 Rare Gold Player",
        "2 Gold Players",
        "At least 3 rare players",
        
        # Position requirements
        "GK, CB, ST positions required",
        "Must include: GK, 4x CB, 2x CM, ST",
        
        # Edge cases
        "Same Club: Max. 3",
        "Different Nations: Min. 8",
        "Premier League: 2 Players"
    ]
    
    print("🧪 Enhanced Normalizer Test Results:")
    print("=" * 60)
    
    success_count = 0
    for i, case in enumerate(test_cases, 1):
        try:
            result = norm_requirement(case)
            kind = result["kind"]
            
            # Check if normalization was successful (not raw/generic fallback)
            success = kind not in ["raw", "generic_req"]
            status = "✅" if success else "⚠️"
            
            print(f"{status} {i:2d}. '{case}'")
            print(f"      -> {kind}: {result.get('value', result.get('count', 'N/A'))}")
            
            if success:
                success_count += 1
                
        except Exception as e:
            print(f"❌ {i:2d}. '{case}' -> ERROR: {e}")
    
    print("=" * 60)
    print(f"📊 Results: {success_count}/{len(test_cases)} successfully normalized")
    print(f"📈 Success rate: {success_count/len(test_cases)*100:.1f}%")
    
    return success_count / len(test_cases) >= 0.8  # 80% success rate

if __name__ == "__main__":
    test_normalizer()
