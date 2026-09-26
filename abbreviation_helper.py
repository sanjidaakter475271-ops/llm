import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ABBR_PATH = os.path.join(SCRIPT_DIR, "abbreviation.md")

_abbr_dict = None

def load_abbreviations():
    global _abbr_dict
    if _abbr_dict is not None:
        return _abbr_dict
    
    _abbr_dict = {}
    if not os.path.exists(ABBR_PATH):
        return _abbr_dict
        
    with open(ABBR_PATH, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if "|" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2 and parts[0] != "Abbreviate" and parts[0] != "---":
                    full_term, abbr = parts[0], parts[1]
                    _abbr_dict[full_term.lower()] = f"{full_term} -> {abbr}"
                    _abbr_dict[abbr.lower()] = f"{full_term} -> {abbr}"
            else:
                m = re.match(r'^(.+?)\s+([A-Z0-9\/&\-\.]{2,})$', line)
                if m:
                    full_term, abbr = m.group(1).strip(), m.group(2).strip()
                    _abbr_dict[full_term.lower()] = f"{full_term} -> {abbr}"
                    _abbr_dict[abbr.lower()] = f"{full_term} -> {abbr}"
    return _abbr_dict

def get_relevant_abbreviations(text, limit=30):
    abbr_map = load_abbreviations()
    if not text:
        # Fallback to top entries
        results = list(dict.fromkeys(abbr_map.values()))[:limit]
        return "\n".join(results)
    
    words = re.findall(r'\b\w+\b', text.lower())
    matched = []
    for word in words:
        if word in abbr_map and abbr_map[word] not in matched:
            matched.append(abbr_map[word])
            if len(matched) >= limit:
                break
    
    if not matched:
        matched = list(dict.fromkeys(abbr_map.values()))[:limit]
        
    return "\n".join(matched)
