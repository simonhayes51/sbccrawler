import re

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().rstrip(".")

def norm_requirement(line: str) -> dict:
    s = _clean(line)

    m = re.match(r"Min\. Team Rating:\s*(\d+)", s, re.I)
    if m:
        return {"kind":"team_rating_min","value":int(m.group(1))}

    m = re.match(r"Min\. (?:Squad )?Chem(?:istry)?:\s*(\d+)", s, re.I)
    if m:
        return {"kind":"chem_min","value":int(m.group(1))}

    m = re.match(r"Min\. (\d+)\s+Players?\s+from\s*:\s*(.+)", s, re.I)
    if m:
        return {"kind":"min_from","count":int(m.group(1)),"key":_clean(m.group(2))}

    if re.search(r"Team of the Week|TOTS|Honourable|Highlights", s, re.I):
        m = re.search(r"Min\.\s*(\d+)", s, re.I)
        cnt = int(m.group(1)) if m else 1
        programs = re.split(r"\s*OR\s*", re.sub(r"^Min\.\s*\d+\s*Players:\s*", "", s, flags=re.I))
        return {"kind":"min_program","count":cnt,"programs":[_clean(p) for p in programs]}

    m = re.match(r"(Exactly|Max\.)\s*(\d+)\s*(.+)", s, re.I)
    if m:
        op = "eq" if m.group(1).lower().startswith("exact") else "le"
        return {"kind":"count_constraint","op":op,"count":int(m.group(2)),"key":_clean(m.group(3))}

    return {"kind":"raw","text":s}

def normalize_requirements(lines):
    return [norm_requirement(x) for x in lines]
