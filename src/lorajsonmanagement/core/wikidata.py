"""
Logic for Wikidata integration and tag enrichment.

Note: Untested (Highly interactive and network-dependent).
"""

import re
import sys
import time
from typing import Optional, List, Tuple, Dict, Any

# For single keypress detection
try:
    import msvcrt  # Windows
    WINDOWS = True
except ImportError:
    WINDOWS = False
    try:
        import tty
        import termios
        UNIX = True
    except ImportError:
        UNIX = False

try:
    import requests
except ImportError:
    requests = None

COMMON_WORDS = {
    "and", "the", "or", "of", "in", "a", "an", "at", "to", "for", "on", "with",
    "from", "by", "as", "is", "was", "are", "were", "be", "been", "being"
}

COUNTRY_KEYWORDS = [
    "american", "british", "canadian", "australian", "french", "german", "italian",
    "spanish", "japanese", "chinese", "korean", "indian", "brazilian", "mexican",
    "russian", "turkish", "dutch", "swedish", "norwegian", "danish", "polish",
    "irish", "scottish", "welsh", "english", "south african", "new zealand"
]


def simplify_search_term(term: str, max_words: int = 3) -> str:
    """Simplify search term by removing everything after dash, parentheses, etc."""
    term = re.split(r'[-–—()\[\]{}]', term)[0].strip()
    words = term.split()[:max_words]
    return " ".join(words).strip()


def normalize_birth_year(text: str) -> str:
    """Normalize birth year formats to (born YYYY)."""
    text = re.sub(r'\(b\.\s*(\d{4})\)', r'(born \1)', text)
    return text


def extract_country_tag(description: str) -> Tuple[str, Optional[str]]:
    """Extract country from description and return (cleaned_desc, country_tag)."""
    desc_lower = description.lower()
    for country in COUNTRY_KEYWORDS:
        if country in desc_lower:
            cleaned = re.sub(rf'\b{country}\b', '', description, flags=re.IGNORECASE).strip()
            return cleaned, country
    return description, None


def parse_description_to_tags(description: str) -> List[str]:
    """Parse a Wikidata description into individual tag phrases."""
    description = normalize_birth_year(description)
    description, country_tag = extract_country_tag(description)
    
    tags = []
    if country_tag:
        tags.append(country_tag)
    
    paren_matches = re.findall(r'\([^)]+\)', description)
    for match in paren_matches:
        tags.append(match.strip().lower())
    
    description = re.sub(r'\([^)]+\)', '', description)
    parts = re.split(r'\s+and\s+|,', description, flags=re.IGNORECASE)
    
    for part in parts:
        part = part.strip().lower()
        if not part:
            continue
        
        words = part.split()
        words = [w for w in words if w not in COMMON_WORDS or len(words) == 1]
        
        if words:
            tag = " ".join(words)
            if tag and len(tag) > 1:
                tags.append(tag)
    
    return tags


def lookup_wikidata(search_term: str, limit: int = 3) -> List[Dict[str, str]]:
    """Lookup a search term in Wikidata and return results."""
    if requests is None:
        return []
    
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbsearchentities",
        "search": search_term,
        "language": "en",
        "format": "json",
        "limit": limit
    }
    headers = {
        "User-Agent": "LoraJsonManagement/1.0"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("search", []):
            label = item.get("label", "").strip()
            desc = item.get("description", "").strip()
            if desc:
                results.append({"label": label, "description": desc})
        
        return results
    except Exception:
        return []


def get_single_keypress() -> str:
    """Get a single keypress from user without waiting for Enter."""
    if WINDOWS:
        try:
            return msvcrt.getch().decode('utf-8', errors='ignore').upper()
        except Exception:
            return ""
    elif UNIX:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            return ch.upper()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    else:
        # Fallback to regular input
        return input().strip()[:1].upper()


def interactive_wikitag_lookup(model_name: str, existing_tags: List[str]) -> List[str]:
    """Interactive Wikidata tag lookup with user selection."""
    if requests is None:
        return existing_tags
    
    search_term = model_name
    simplify_attempts = 0
    
    while True:
        print(f"\n🔍 Searching Wikidata for: '{search_term}'")
        results = lookup_wikidata(search_term, limit=3)
        
        if not results:
            if simplify_attempts == 0:
                simplified = simplify_search_term(search_term, max_words=3)
                if simplified and simplified != search_term:
                    print(f"❌ No results. Trying simplified (3 words): '{simplified}'")
                    search_term = simplified
                    simplify_attempts = 1
                    continue
                simplify_attempts = 1
            
            if simplify_attempts == 1:
                simplified = simplify_search_term(model_name, max_words=2)
                if simplified and simplified != search_term:
                    print(f"❌ No results. Trying simplified (2 words): '{simplified}'")
                    search_term = simplified
                    simplify_attempts = 2
                    continue
            
            print("❌ No results found. Press any key to enter new search term, or 0 to skip")
            key = get_single_keypress()
            if key == "0":
                return existing_tags
            
            # Reset search term and simplification attempts
            search_term = input(f"Enter new search term [{model_name}]: ").strip() or model_name
            simplify_attempts = 0
            continue
        
        # Display results
        print("\n📋 Results:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result['label']} - {result['description']}")
        
        print("\nPress: 1-3 (select), 0 (skip), or any other key to search again")
        key = get_single_keypress()
        print()
        
        if key == "0":
            return existing_tags
        elif key in ["1", "2", "3"]:
            idx = int(key) - 1
            if idx < len(results):
                selected = results[idx]
                print(f"✅ Selected: {selected['label']}")
                new_tags = parse_description_to_tags(selected['description'])
                
                print("\n🏷️ Tags to add:")
                for tag in new_tags:
                    if tag.lower() not in [t.lower() for t in existing_tags]:
                        print(f"  + {tag}")
                
                existing_lower = {t.lower(): t for t in existing_tags}
                for tag in new_tags:
                    if tag.lower() not in existing_lower:
                        existing_tags.append(tag)
                return existing_tags
        else:
            search_term = input(f"Enter new search term [{model_name}]: ").strip() or model_name
            simplify_attempts = 0
            continue
