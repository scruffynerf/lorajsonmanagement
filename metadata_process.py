#!/usr/bin/env python3
"""
metadata_process.py

Unified pipeline that:
 - Recursively renames model file groups so they match model_name inside metadata.json (keeps original logic)
 - Normalizes/creates preview images: converts .webp/.png/.jpg or extracts first frame from .mp4 to <base>.preview.jpeg
 - Converts <base>.metadata.json -> <base>.cm-info.json following ConnectedModelInfo mapping
 - Supports dry-run, verbose, batch mode, and logging
 - Uses Pillow for image conversion and ffmpeg-python as wrapper where available; falls back to ffmpeg binary if necessary
 - Includes a --validate flag to validate generated .cm-info.json for required fields

Notes:
 - This script will create/modify files. Use --dry-run to preview actions.

Usage examples:
  python metadata_process.py /path/to/models
  python metadata_process.py /path/to/models/some.metadata.json

"""

import argparse
import json
import os
import re
import sys
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

# HTTP requests for Wikidata
try:
    import requests
except Exception:
    requests = None

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

# Image handling
try:
    from PIL import Image
except Exception:
    Image = None

# ffmpeg wrapper (ffmpeg-python)
try:
    import ffmpeg as ffmpeg_wrapper
except Exception:
    ffmpeg_wrapper = None

# ---------------------------------------------------------------------------
# Logging and small utilities (kept consistent with your original file)
# ---------------------------------------------------------------------------

def log(msg, logfile=None, verbose=False):
    print(msg) if verbose else None
    if logfile:
        logfile.write(msg + "\n")
        logfile.flush()


def sanitize_filename(name: str) -> str:
    """Sanitize model_name to be a valid filename."""
    bad_chars = '<>:"/\\|?*'
    for c in bad_chars:
        name = name.replace(c, "_")
    return name.strip()

# ---------------------------------------------------------------------------
# Rename logic (from rename_model_groups.py) — minimal edits
# ---------------------------------------------------------------------------

def build_filename_from_template(meta: dict, template: str, force_hash: bool = False) -> tuple[str, bool]:
    """Build filename from template string. Returns (filename, hash_used).
    
    Supported placeholders:
    - {ModelName} or {Name}: Cleaned model name
    - {BaseModel} or {Base}: Base model (e.g., "Flux.1 D")
    - {ModelType} or {Type}: Model type (e.g., "LORA")
    - {ModelVersion} or {Version}: Version name from civitai
    - {Creator} or {Author}: Creator username
    - {TriggerWord} or {Trigger}: First trained word/trigger
    - {AutoV2}: 10-char SHA256 hash (only used if force_hash=True or to prevent collision)
    """
    civitai = meta.get("civitai") or {}
    
    # Get cleaned model name
    model_name = meta.get("model_name", "")
    MODEL_NAME_CLEANUP = [
        "(Flux)", "(flux)", "[Flux]", "- FLUX", "(Flux LoRa)", "LoRa", "LoRA",
        "Flux", "flux", "FLux", "FLUX", "👑", "🎬", "🎤", "SDXL", "Hunyuan", "Pony",
        "SD1.5", "SD-1.5", "1.D", ".1 D", ".1D", "SoloLoRA", "|", "(++)", "(+)",
        "(_)", "( + )", "()", "[ ]", "[ + ]", "[]",
    ]
    model_name = model_name.replace("(Ca ", "(").replace("(CA ", "(")
    model_name = model_name.replace("( ", "(").replace(" )", ")")
    model_name = model_name.replace("  ", " ")
    for bad in MODEL_NAME_CLEANUP:
        model_name = model_name.replace(bad, "")
    model_name = model_name.replace("  ", " ").strip(" -_")
    
    # Extract trigger word (first trained word)
    trigger_word = ""
    trained_words = extract_trained_words(civitai)
    if trained_words and len(trained_words) > 0:
        trigger_word = trained_words[0]
    
    # Build replacement dict - ensure all values are strings
    replacements = {
        "{ModelName}": model_name,
        "{Name}": model_name,
        "{BaseModel}": meta.get("base_model") or civitai.get("baseModel") or "",
        "{Base}": meta.get("base_model") or civitai.get("baseModel") or "",
        "{ModelType}": map_model_type(meta),
        "{Type}": map_model_type(meta),
        "{ModelVersion}": civitai.get("name") or "",
        "{Version}": civitai.get("name") or "",
        "{Creator}": (civitai.get("creator") or {}).get("username") or "",
        "{Author}": (civitai.get("creator") or {}).get("username") or "",
        "{TriggerWord}": trigger_word,
        "{Trigger}": trigger_word,
        "{AutoV2}": meta.get("sha256", "")[:10] if force_hash else "",
    }
    
    # Apply replacements
    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    
    # Clean up: remove empty brackets/parentheses and extra spaces
    result = result.replace("[]", "").replace("()", "").replace("{}", "")
    result = result.replace("  ", " ").strip(" -_")
    
    hash_used = force_hash or "{AutoV2}" in template
    
    return sanitize_filename(result), hash_used


def process_metadata_file_for_rename(meta_path: Path, dry_run: bool, verbose: bool, logfile, rename_template: str = None, always_hash: bool = False):
    """Process a single metadata.json file and rename its related files as needed."""
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        log(f"⚠️ Could not read metadata file {meta_path}: {e}", logfile, verbose)
        return None

    directory = meta_path.parent
    file_name = meta.get("file_name")
    model_name = meta.get("model_name")
    sha256 = meta.get("sha256")

    if not (file_name and model_name and sha256):
        log(f"⚠️ Missing required fields in {meta_path}, skipping.", logfile, verbose)
        return None

    # collect group files: exact match or startswith file_name + "."
    group_files = sorted(
        [p for p in directory.iterdir() if p.is_file() and (p.name == file_name or p.name.startswith(file_name + "."))],
        key=lambda p: p.name
    )
    if not group_files:
        log(f"⚠️ No files found for base {file_name} in {directory}", logfile, verbose)
        return None

    # Build target filename using template or default
    if rename_template:
        target_base, hash_used = build_filename_from_template(meta, rename_template, force_hash=always_hash)
    else:
        # Default: just cleaned model name + hash
        target_base, hash_used = build_filename_from_template(meta, "{ModelName} {AutoV2}", force_hash=True)

    # Helper: check conflicts by constructing new name using the full suffix after file_name
    def conflicts(base):
        for f in group_files:
            suffix = f.name[len(file_name):]  # full suffix, e.g. ".cm-info.json"
            new_name = base + suffix
            new_path = directory / new_name

            # Case-insensitive conflict check
            for existing in directory.iterdir():
                if existing.is_file() and existing.name.lower() == new_name.lower():
                    if existing.resolve() != f.resolve():  # ensure not same file
                        return True
        return False

    # If hash not already in name and there's a conflict, add it
    if not hash_used and conflicts(target_base):
        log(f"⚠️ Collision detected for {target_base}, adding hash suffix", logfile, verbose)
        target_base = f"{target_base}_{sha256[:10]}"
        hash_used = True
    
    # Final check after adding hash
    if conflicts(target_base):
        log(f"❌ Name conflict even after adding sha256 suffix for {file_name}, skipping group.", logfile, verbose)
        return None

    # Describe planned changes
    log(f"\n📦 Processing group: {file_name}", logfile, verbose)
    log(f" → Target base name: {target_base}" + (" (with AutoV2 hash)" if hash_used else ""), logfile, verbose)
    for f in group_files:
        suffix = f.name[len(file_name):]              # full suffix retained
        new_name = target_base + suffix
        log(f"   - {f.name}  →  {new_name}", logfile, verbose)

    if dry_run:
        log("💡 Dry-run mode: no files renamed.", logfile, verbose)
        return {
            "meta": meta,
            "directory": directory,
            "file_name": file_name,
            "target_base": target_base,
            "group_files": group_files,
            "renamed": False
        }

    # Final safety check before mutating: ensure no target will overwrite an unrelated file
    for f in group_files:
        dest = directory / (target_base + f.name[len(file_name):])
        if dest.exists() and dest != f:
            log(f"❌ Collision detected for {dest}, aborting group.", logfile, verbose)
            return None

    # Perform renames (sequential; safe because prefixes differ)
    for f in group_files:
        dest = directory / (target_base + f.name[len(file_name):])
        try:
            f.rename(dest)
            log(f"✅ Renamed: {f.name} -> {dest.name}", logfile, verbose)
        except Exception as e:
            log(f"❌ Failed to rename {f} -> {dest}: {e}", logfile, verbose)
            return None

    # Update metadata file (now at new_base.metadata.json)
    new_meta_path = directory / f"{target_base}.metadata.json"
    try:
        safetensors_path = str(directory / f"{target_base}.safetensors")
        preview_path = str(directory / f"{target_base}.preview.jpeg")

        # Update model_name with cleaned version
        if rename_template:
            cleaned_name, _ = build_filename_from_template(meta, "{ModelName}", force_hash=False)
            meta["model_name"] = cleaned_name
        else:
            meta["model_name"] = model_name
        
        meta["file_name"] = target_base
        meta["file_path"] = safetensors_path
        meta["preview_url"] = preview_path

        with new_meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        log(f"✅ Updated metadata for {target_base}", logfile, verbose)
    except Exception as e:
        log(f"⚠️ Failed to update metadata JSON {new_meta_path}: {e}", logfile, verbose)

    return {
        "meta": meta,
        "directory": directory,
        "file_name": file_name,
        "target_base": target_base,
        "group_files": group_files,
        "renamed": True
    }

# ---------------------------------------------------------------------------
# Wikidata tag lookup and enhancement
# ---------------------------------------------------------------------------

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


def get_single_keypress():
    """Get a single keypress from user without waiting for Enter."""
    if WINDOWS:
        return msvcrt.getch().decode('utf-8', errors='ignore').upper()
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
        return input().strip().upper()


def simplify_search_term(term: str, max_words: int = 3) -> str:
    """Simplify search term by removing everything after dash, parentheses, etc."""
    # Split by common delimiters and take first part
    term = re.split(r'[-–—()\[\]{}]', term)[0].strip()
    # Take only first N words
    words = term.split()[:max_words]
    return " ".join(words).strip()


def lookup_wikidata(search_term: str, limit: int = 3):
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
        "User-Agent": "MetadataProcessScript/1.0"
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
    except Exception as e:
        print(f"⚠️ Wikidata lookup failed: {e}")
        return []


def normalize_birth_year(text: str) -> str:
    """Normalize birth year formats to (born YYYY)."""
    # Match (b. YYYY) or (born YYYY)
    text = re.sub(r'\(b\.\s*(\d{4})\)', r'(born \1)', text)
    return text


def extract_country_tag(description: str) -> tuple[str, str | None]:
    """Extract country from description and return (cleaned_desc, country_tag)."""
    desc_lower = description.lower()
    for country in COUNTRY_KEYWORDS:
        if country in desc_lower:
            # Remove country from description for further processing
            cleaned = re.sub(rf'\b{country}\b', '', description, flags=re.IGNORECASE).strip()
            return cleaned, country
    return description, None


def parse_description_to_tags(description: str) -> list[str]:
    """Parse a Wikidata description into individual tag phrases."""
    # Normalize birth year
    description = normalize_birth_year(description)
    
    # Extract country
    description, country_tag = extract_country_tag(description)
    
    tags = []
    if country_tag:
        tags.append(country_tag)
    
    # Split by common delimiters
    # First, extract anything in parentheses as separate tags
    paren_matches = re.findall(r'\([^)]+\)', description)
    for match in paren_matches:
        tags.append(match.strip().lower())
    
    # Remove parentheses content from main description
    description = re.sub(r'\([^)]+\)', '', description)
    
    # Split by "and" or commas
    parts = re.split(r'\s+and\s+|,', description, flags=re.IGNORECASE)
    
    for part in parts:
        part = part.strip().lower()
        if not part:
            continue
        
        # Remove common words at start/end
        words = part.split()
        words = [w for w in words if w not in COMMON_WORDS or len(words) == 1]
        
        if words:
            tag = " ".join(words)
            if tag and len(tag) > 1:  # Avoid single-char tags
                tags.append(tag)
    
    return tags


def interactive_wikitag_lookup(model_name: str, existing_tags: list) -> list[str]:
    """Interactive Wikidata tag lookup with user selection."""
    if requests is None:
        print("⚠️ requests library not installed. Cannot use --wikitag feature.")
        return existing_tags
    
    search_term = model_name
    simplify_attempts = 0  # Track simplification attempts: 0=none, 1=3 words, 2=2 words
    
    while True:
        print(f"\n🔍 Searching Wikidata for: '{search_term}'")
        results = lookup_wikidata(search_term, limit=3)
        
        if not results:
            # Auto-retry with simplified terms
            if simplify_attempts == 0:
                # First attempt: try 3 words
                simplified = simplify_search_term(search_term, max_words=3)
                if simplified and simplified != search_term:
                    print(f"❌ No results. Trying simplified (3 words): '{simplified}'")
                    search_term = simplified
                    simplify_attempts = 1
                    continue
                else:
                    # Already 3 words or less, skip to 2 words
                    simplify_attempts = 1
            
            if simplify_attempts == 1:
                # Second attempt: try 2 words
                simplified = simplify_search_term(model_name, max_words=2)
                if simplified and simplified != search_term:
                    print(f"❌ No results. Trying simplified (2 words): '{simplified}'")
                    search_term = simplified
                    simplify_attempts = 2
                    continue
            
            # No results after all attempts
            print("❌ No results found.")
            print("Press any key to enter new search term, or 0 to skip")
            
            key = get_single_keypress()
            
            if key == "0":
                return existing_tags
            else:
                # Treat first keypress as start of new search
                if key.isprintable() and key not in ["0", "1", "2", "3"]:
                    print(key, end='', flush=True)
                    rest = input()
                    search_term = (key + rest).strip()
                else:
                    search_term = input("Enter new search term: ").strip()
                
                if not search_term:
                    search_term = model_name
                simplify_attempts = 0  # Reset simplification attempts
                continue
        
        # Display results
        print("\n📋 Results:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result['label']} - {result['description']}")
        
        # Get user choice via keypress
        print("\nPress: 1-3 (select result), 0 (skip), or any other key to search again")
        
        key = get_single_keypress()
        print()  # newline after keypress
        
        if key == "0":
            return existing_tags
        elif key in ["1", "2", "3"]:
            idx = int(key) - 1
            if idx < len(results):
                selected = results[idx]
                print(f"✅ Selected: {selected['label']} - {selected['description']}")
                
                # Parse description into tags
                new_tags = parse_description_to_tags(selected['description'])
                
                # Show tags that will be added
                print("\n🏷️  Tags to add:")
                for tag in new_tags:
                    if tag.lower() not in [t.lower() for t in existing_tags]:
                        print(f"  + {tag}")
                    else:
                        print(f"  = {tag} (already exists)")
                
                # Merge tags (avoid duplicates, case-insensitive)
                existing_lower = {t.lower(): t for t in existing_tags}
                for tag in new_tags:
                    if tag.lower() not in existing_lower:
                        existing_tags.append(tag)
                
                return existing_tags
            else:
                print(f"❌ Invalid selection (only {len(results)} results available)")
                continue
        else:
            # Any other key = new search
            if key.isprintable() and key not in ["0", "1", "2", "3"]:
                print(f"Starting new search with: {key}", end='', flush=True)
                rest = input()
                search_term = (key + rest).strip()
            else:
                search_term = input("Enter new search term: ").strip()
            
            if not search_term:
                search_term = model_name
            simplify_attempts = 0  # Reset simplification attempts
            continue

VALID_MODEL_TYPES = {
    "Checkpoint",
    "Text2Image",
    "Image2Image",
    "Upscaler",
    "VAE",
    "LORA",
    "Embedding",
    "Hypernetwork",
    "Other",
}

VALID_SOURCES = {0: "Civitai", 1: "OpenModelDb"}

# Base model normalization map (case-insensitive matching)
BASE_MODEL_MAPPINGS = {
    # Flux variants
    "flux": "Flux.1 D",
    "flux.1": "Flux.1 D",
    "flux.1 d": "Flux.1 D",
    "flux.1d": "Flux.1 D",
    "flux 1 d": "Flux.1 D",
    "flux.1 s": "Flux.1 S",
    "flux.1s": "Flux.1 S",
    "flux 1 s": "Flux.1 S",
    "flux.1 kontext": "Flux.1 Kontext",
    "flux.1 krea": "Flux.1 Krea",
    
    # SD variants
    "sd 1.4": "SD 1.4",
    "sd1.4": "SD 1.4",
    "sd 1.5": "SD 1.5",
    "sd1.5": "SD 1.5",
    "sd 2.0": "SD 2.0",
    "sd2.0": "SD 2.0",
    "sd 2.1": "SD 2.1",
    "sd2.1": "SD 2.1",
    "sd 3": "SD 3",
    "sd3": "SD 3",
    "sd 3.5": "SD 3.5",
    "sd3.5": "SD 3.5",
    
    # SDXL variants
    "sdxl": "SDXL 1.0",
    "sdxl 1.0": "SDXL 1.0",
    "sdxl1.0": "SDXL 1.0",
    "sdxl 0.9": "SDXL 0.9",
    "sdxl0.9": "SDXL 0.9",
    "sdxl turbo": "SDXL Turbo",
    "sdxl lightning": "SDXL Lightning",
    "sdxl hyper": "SDXL Hyper",
    
    # Other common variants
    "pony": "Pony",
    "illustrious": "Illustrious",
    "noobai": "NoobAI",
    "hunyuan": "Hunyuan 1",
    "kolors": "Kolors",
}


def normalize_base_model(base_model: str | None) -> str:
    """Normalize base model name to match spec canonical names."""
    if not base_model:
        return "Other"
    
    # Try exact match first (case-insensitive)
    lower = base_model.lower().strip()
    
    # Check mappings
    if lower in BASE_MODEL_MAPPINGS:
        return BASE_MODEL_MAPPINGS[lower]
    
    # Check if it's already a valid canonical name (case-insensitive)
    # This handles cases where the input is already correct
    canonical_names = [
        "SD 1.4", "SD 1.5", "SD 1.5 Hyper", "SD 1.5 LCM", "SD 2.0", "SD 2.0 768",
        "SD 2.1", "SD 2.1 768", "SD 2.1 Unclip", "SD 3", "SD 3.5", "SD 3.5 Medium",
        "SD 3.5 Large", "SD 3.5 Large Turbo", "SDXL 0.9", "SDXL 1.0", "SDXL 1.0 LCM",
        "SDXL Turbo", "SDXL Lightning", "SDXL Hyper", "SDXL Distilled",
        "Flux.1 D", "Flux.1 S", "Flux.1 Kontext", "Flux.1 Krea",
        "Wan Video", "Wan Video 1.3B t2v", "Wan Video 14B t2v", "Wan Video 14B i2v 480p",
        "Wan Video 14B i2v 720p", "Wan Video 2.2 I2V-A14B", "Wan Video 2.2 T2V-A14B",
        "Wan Video 2.2 TI2V-5B", "Wan Video 2.5 I2V", "Wan Video 2.5 T2V",
        "Hunyuan 1", "Hunyuan Video", "Playground v2", "Illustrious", "Flux", "Pony",
        "Kolors", "Stable Cascade", "HiDream", "LTXV", "PixArt E", "PixArt a",
        "Chroma", "SVD", "SVD XT", "AuraFlow", "Lumina", "Qwen", "Mochi", "ODOR",
        "Nano Banana", "OpenAI", "Imagen4", "Seedream", "NoobAI", "Veo 3", "Other"
    ]
    
    for canonical in canonical_names:
        if canonical.lower() == lower:
            return canonical
    
    return "Other"


def unix_to_iso(ts: float) -> str:
    """Convert Unix timestamp (float) to ISO-8601 UTC string"""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def map_model_type(meta: dict) -> str:
    """Map metadata class or field to ConnectedModelInfo.ModelType"""
    # First check civitai.model.type
    civitai = meta.get("civitai") or {}
    civitai_type = civitai.get("model", {}).get("type", "")
    if civitai_type:
        upper = civitai_type.upper()
        if upper in VALID_MODEL_TYPES:
            return upper
        # Handle common variations
        if "CHECKPOINT" in upper or "CK" in upper:
            return "Checkpoint"
        if "EMBED" in upper or "TEXTUAL" in upper:
            return "Embedding"
    
    # Then check metadata.model_type
    mt = meta.get("model_type", "") or ""
    if isinstance(mt, str):
        lower = mt.lower()
        if lower.startswith("check"):
            return "Checkpoint"
        if lower.startswith("lora"):
            return "LORA"
        if lower.startswith("embed"):
            return "Embedding"
    
    # Fallback: infer from filename or path
    name = (meta.get("file_name") or "").lower()
    path = (meta.get("file_path") or "").lower()
    if "lora" in name or "lora" in path:
        return "LORA"
    if "embed" in name or "embed" in path:
        return "Embedding"
    if "checkpoint" in name or "checkpoint" in path:
        return "Checkpoint"
    
    return "Other"


def extract_stats(civitai: dict | None) -> dict | None:
    """Extract stats from civitai.model.stats if available"""
    try:
        if not civitai:
            return None
        stats = civitai.get("model", {}).get("stats", {})
        if not stats:
            return None
        return {
            "Downloads": stats.get("downloadCount", 0),
            "Faves": stats.get("favoriteCount", 0)
        }
    except Exception:
        return None


def extract_trained_words(civitai: dict | None) -> list | None:
    """Extract trainedWords from civitai.model.versions if present"""
    try:
        if not civitai:
            return None
        # various civitai shapes: try multiple keys
        versions = civitai.get("model", {}).get("modelVersions") or civitai.get("model", {}).get("versions") or []
        for v in versions:
            if v and isinstance(v, dict) and v.get("trainedWords"):
                return v["trainedWords"]
        # Also check top-level trainedWords
        if civitai.get("trainedWords"):
            return civitai["trainedWords"]
        return None
    except Exception:
        return None


def build_cm_info(metadata: dict) -> dict:
    """Convert metadata.json content to cm-info.json structure"""
    civitai = metadata.get("civitai") or {}
    sha256 = (metadata.get("sha256") or "").lower()
    file_path = metadata.get("file_path") or ""
    file_name = metadata.get("file_name") or os.path.splitext(os.path.basename(file_path))[0]
    file_ext = os.path.splitext(file_path)[1].lstrip(".")
    
    # Extract and normalize base model
    base_model = civitai.get("baseModel") or metadata.get("base_model")
    base_model = normalize_base_model(base_model)

    cm = {
        "ModelId": civitai.get("modelId"),
        "ModelName": metadata.get("model_name"),
        "ModelDescription": metadata.get("modelDescription") or "",
        "Nsfw": (metadata.get("preview_nsfw_level", 0) >= 1),
        "Tags": metadata.get("tags", []),
        "ModelType": map_model_type(metadata),
        "VersionId": civitai.get("versionId") or civitai.get("modelVersionId") or civitai.get("id"),
        "VersionName": civitai.get("name") or "",
        "VersionDescription": None,
        "BaseModel": base_model,
        "FileMetadata": None,
        "ImportedAt": unix_to_iso(metadata.get("modified", datetime.now().timestamp())),
        "Hashes": {
            "SHA256": sha256 if sha256 else None,
            "CRC32": None,
            "BLAKE3": None
        },
        "TrainedWords": extract_trained_words(civitai),
        "Stats": None,
        "UserTitle": None,
        "ThumbnailImageUrl": metadata.get("preview_url"),
        "InferenceDefaults": None,
        "Source": 0 if metadata.get("from_civitai", True) else 1
    }

    # Remove empty values but keep explicit None fields and required fields
    # Keep: VersionDescription, FileMetadata, UserTitle, InferenceDefaults, Stats as None
    # Keep: ModelDescription even if empty string (required)
    # Keep: Tags even if empty array (required)
    # Remove: empty strings for optional fields, but not required ones
    result = {}
    for k, v in cm.items():
        if k in ("VersionDescription", "FileMetadata", "UserTitle", "InferenceDefaults", "Stats"):
            result[k] = v  # Keep None values for these
        elif k in ("ModelDescription", "Tags", "Hashes", "ThumbnailImageUrl", "BaseModel"):
            result[k] = v  # Always include required/important fields
        elif v not in ([], {}, ""):
            result[k] = v
    
    return result


def validate_cminfo(cm: dict) -> tuple[bool, list]:
    """Validate generated cm-info dict; return (is_valid, errors)"""
    required = [
        "ModelName",
        "ModelDescription",
        "Nsfw",
        "Tags",
        "ModelType",
        "BaseModel",
        "ImportedAt",
        "Hashes",
        "ThumbnailImageUrl",
        "Source",
    ]
    errors = []
    for r in required:
        if r not in cm:
            errors.append(f"Missing required field: {r}")
    
    # SHA256 or BLAKE3 check
    if "Hashes" in cm:
        if not isinstance(cm["Hashes"], dict):
            errors.append("Hashes must be a dict")
        elif not (cm["Hashes"].get("SHA256") or cm["Hashes"].get("BLAKE3")):
            errors.append("Hashes must contain at least SHA256 or BLAKE3")
    
    # enums
    if "ModelType" in cm and cm["ModelType"] not in VALID_MODEL_TYPES:
        errors.append(f"Invalid ModelType: {cm.get('ModelType')}")
    if "Source" in cm and cm["Source"] not in VALID_SOURCES:
        errors.append(f"Invalid Source: {cm.get('Source')} (must be 0 or 1)")
    
    # BaseModel validation
    if "BaseModel" in cm:
        normalized = normalize_base_model(cm["BaseModel"])
        if normalized == "Other" and cm["BaseModel"] != "Other":
            errors.append(f"BaseModel '{cm['BaseModel']}' not recognized (normalized to 'Other')")

    return (len(errors) == 0, errors)

# ---------------------------------------------------------------------------
# Preview image/video conversion helpers
# ---------------------------------------------------------------------------

def ffmpeg_available() -> bool:
    """Return True if ffmpeg-python wrapper is available or ffmpeg binary exists."""
    if ffmpeg_wrapper is not None:
        return True
    # check ffmpeg binary
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def extract_frame_from_mp4(src: Path, dest: Path, verbose: bool = False) -> bool:
    """Extract first frame from mp4 to JPEG. Uses wrapper if available, else calls ffmpeg binary."""
    if ffmpeg_wrapper is not None:
        try:
            # using ffmpeg-python to extract first frame
            (ffmpeg_wrapper
                .input(str(src), ss=0)
                .output(str(dest), vframes=1)
                .overwrite_output()
                .run(quiet=not verbose))
            return dest.exists()
        except Exception as e:
            log(f"❌ ffmpeg-python extraction failed: {e}", None, verbose)
            return False
    else:
        # fallback to ffmpeg binary
        try:
            cmd = ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", str(dest)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return dest.exists()
        except Exception as e:
            log(f"❌ ffmpeg extraction failed: {e}", None, verbose)
            return False


def convert_image_to_jpeg(src: Path, dest: Path, verbose: bool = False) -> bool:
    """Convert image (webp/png/etc.) to JPEG using Pillow."""
    if Image is None:
        log("❌ Pillow is not installed; cannot convert images.", None, verbose)
        return False
    try:
        with Image.open(src) as im:
            # Convert to RGB if needed, then save as JPEG
            if im.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[3] if im.mode == "RGBA" else None)
                bg.save(dest, format="JPEG", quality=90)
            else:
                rgb = im.convert("RGB")
                rgb.save(dest, format="JPEG", quality=90)
        return dest.exists()
    except Exception as e:
        log(f"❌ Image conversion failed for {src}: {e}", None, verbose)
        return False


def find_preview_source(directory: Path, base: str) -> Path | None:
    """Look for preview file candidates next to metadata: webp/png/jpg/jpeg/mp4 (in that order)."""
    candidates = [f"{base}.preview.webp", f"{base}.webp", f"{base}.png", f"{base}.jpg", f"{base}.jpeg", f"{base}.mp4"]
    for c in candidates:
        p = directory / c
        if p.exists():
            return p
    return None


def ensure_preview(metadata_obj: dict, directory: Path, base: str, dry_run: bool, verbose: bool, logfile) -> str | None:
    """Ensure there's a <base>.preview.jpeg file and metadata.preview_url points to it.
    Returns path (str) to preview jpeg or None if not available.
    """
    # If metadata already has preview_url and file exists, keep it
    existing_preview = metadata_obj.get("preview_url")
    if existing_preview:
        p = Path(existing_preview)
        if not p.is_absolute():
            # relative path -> treat as in same directory
            p = directory / p
        if p.exists():
            # If it's jpeg, done. If not, convert to jpeg
            if p.suffix.lower() in (".jpg", ".jpeg"):
                log(f"ℹ️ Using existing preview: {p}", logfile, verbose)
                return str((directory / f"{base}.preview.jpeg").as_posix())
            else:
                dest = directory / f"{base}.preview.jpeg"
                if p.suffix.lower() == ".mp4":
                    log(f"ℹ️ Extracting frame from existing mp4 preview {p}", logfile, verbose)
                    if dry_run:
                        log("💡 Dry-run: would extract mp4 frame to " + str(dest), logfile, verbose)
                        return str(dest.as_posix())
                    ok = extract_frame_from_mp4(p, dest, verbose=verbose)
                    if ok:
                        metadata_obj["preview_url"] = str(dest.as_posix())
                        return str(dest.as_posix())
                        
                else:
                    log(f"ℹ️ Converting existing preview {p} -> {base}.preview.jpeg", logfile, verbose)
                    if dry_run:
                        log("💡 Dry-run: would convert image to " + str(dest), logfile, verbose)
                        return str(dest.as_posix())
                    ok = convert_image_to_jpeg(p, dest, verbose=verbose)
                    if ok:
                        metadata_obj["preview_url"] = str(dest.as_posix())
                        return str(dest.as_posix())

    # Otherwise search for local files matching base
    source = find_preview_source(directory, base)
    if not source:
        log(f"ℹ️ No preview source found for {base}", logfile, verbose)
        return None

    dest = directory / f"{base}.preview.jpeg"

    # If it's mp4, extract first frame
    if source.suffix.lower() == ".mp4":
        log(f"ℹ️ Extracting frame from {source} -> {dest}", logfile, verbose)
        if dry_run:
            log("💡 Dry-run: would extract mp4 frame", logfile, verbose)
            return str(dest.as_posix())
        ok = extract_frame_from_mp4(source, dest, verbose=verbose)
        if ok:
            metadata_obj["preview_url"] = str(dest.as_posix())
            return str(dest.as_posix())
        return None

    # If it's an image, convert to jpeg if needed
    if source.suffix.lower() in (".webp", ".png", ".jpg", ".jpeg"):
        log(f"ℹ️ Converting image {source} -> {dest}", logfile, verbose)
        if dry_run:
            log("💡 Dry-run: would convert image to " + str(dest), logfile, verbose)
            return str(dest.as_posix())
        # If source already jpeg and name equals dest, just copy
        if source.suffix.lower() in (".jpg", ".jpeg"):
            try:
                shutil.copy2(source, dest)
                metadata_obj["preview_url"] = str(dest.as_posix())
                return str(dest.as_posix())
            except Exception as e:
                log(f"❌ Failed to copy jpeg preview {source} -> {dest}: {e}", logfile, verbose)
                return None
        else:
            ok = convert_image_to_jpeg(source, dest, verbose=verbose)
            if ok:
                metadata_obj["preview_url"] = str(dest.as_posix())
                return str(dest.as_posix())
            return None

    return None

# ---------------------------------------------------------------------------
# Integration: run rename -> preview -> cm-info conversion for a single metadata
# ---------------------------------------------------------------------------

def process_group_and_convert(meta_path: Path, dry_run: bool, verbose: bool, logfile, validate: bool, rename_template: str = None, always_hash: bool = False, wikitag: bool = False):
    """Runs rename (if needed), ensures preview, generates cm-info.json"""
    # Step 1: rename group (this will also update metadata file if renamed)
    rename_result = process_metadata_file_for_rename(meta_path, dry_run, verbose, logfile, rename_template, always_hash)

    # If rename_result is None -> either skipped or error
    if rename_result is None:
        # if metadata exists, still attempt conversion from original path
        try_paths = [meta_path]
    else:
        # If rename occurred, metadata file may have moved to new name
        if rename_result.get("renamed"):
            new_meta = rename_result["directory"] / f"{rename_result['target_base']}.metadata.json"
            try_paths = [new_meta]
        else:
            try_paths = [meta_path]

    # Process each candidate metadata (usually one)
    for mp in try_paths:
        if not mp.exists():
            log(f"⚠️ Metadata file not found for conversion: {mp}", logfile, verbose)
            continue

        # Load metadata
        try:
            with mp.open("r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            log(f"⚠️ Failed to read metadata {mp}: {e}", logfile, verbose)
            continue

        directory = mp.parent
        base = metadata.get("file_name") or os.path.splitext(mp.name)[0]

        # Step 1.5: Interactive Wikidata tag enhancement
        if wikitag and not dry_run:
            model_name = metadata.get("model_name", "")
            existing_tags = metadata.get("tags", [])
            
            if model_name:
                print(f"\n{'='*60}")
                print(f"Model: {model_name}")
                print(f"Current tags: {', '.join(existing_tags) if existing_tags else 'none'}")
                
                updated_tags = interactive_wikitag_lookup(model_name, existing_tags[:])
                
                if updated_tags != existing_tags:
                    metadata["tags"] = updated_tags
                    try:
                        with mp.open("w", encoding="utf-8") as f:
                            json.dump(metadata, f, indent=2)
                        log(f"✅ Updated tags for {base}", logfile, verbose)
                    except Exception as e:
                        log(f"⚠️ Failed to write metadata after tag update: {e}", logfile, verbose)
                
                time.sleep(0.5)  # polite delay between lookups

        # Step 2: ensure preview exists and metadata.preview_url points to it
        preview = ensure_preview(metadata, directory, base, dry_run, verbose, logfile)

        # If preview created, update metadata file
        if preview and not dry_run:
            try:
                with mp.open("w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)
                log(f"✅ Updated metadata preview_url for {base}", logfile, verbose)
            except Exception as e:
                log(f"⚠️ Failed to write metadata after preview update: {e}", logfile, verbose)

        # Step 3: build cm-info and optionally validate
        cm_info = build_cm_info(metadata)
        if validate:
            ok, errors = validate_cminfo(cm_info)
            if not ok:
                log(f"❌ Validation failed for {base}.cm-info.json:\n  - " + "\n  - ".join(errors), logfile, verbose)
                continue
            else:
                log(f"✅ Validation passed for {base}.cm-info.json", logfile, verbose)

        # Step 4: write cm-info.json
        cm_path = directory / f"{base}.cm-info.json"
        if dry_run:
            log(f"💡 Dry-run: would write {cm_path}", logfile, verbose)
        else:
            try:
                with cm_path.open("w", encoding="utf-8") as f:
                    json.dump(cm_info, f, ensure_ascii=False, separators=(',', ':'))
                log(f"✅ Wrote {cm_path}", logfile, verbose)
            except Exception as e:
                log(f"❌ Failed to write {cm_path}: {e}", logfile, verbose)

# ---------------------------------------------------------------------------
# Batch traversal
# ---------------------------------------------------------------------------

def recurse_and_process(root: Path, dry_run: bool, verbose: bool, logfile, recursive: bool, validate: bool, rename_template: str = None, always_hash: bool = False, wikitag: bool = False):
    for meta_file in root.rglob("*.metadata.json"):
        # If not recursive, only process files in top-level directory
        if not recursive and meta_file.parent != root:
            continue
        process_group_and_convert(meta_file, dry_run, verbose, logfile, validate, rename_template, always_hash, wikitag)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Process metadata: rename groups, normalize previews, produce .cm-info.json files",
        epilog="""
Rename template placeholders:
  {ModelName} or {Name}     - Cleaned model name
  {BaseModel} or {Base}     - Base model (e.g., "Flux.1 D", "SDXL 1.0")
  {ModelType} or {Type}     - Model type (e.g., "LORA", "Checkpoint")
  {ModelVersion} or {Version} - Version name from civitai
  {Creator} or {Author}     - Creator username
  {TriggerWord} or {Trigger} - First trained word/trigger
  {AutoV2}                  - 10-char SHA256 hash (AutoV2)

Examples:
  --rename "[{BaseModel}] {ModelName} - {Version} - {Creator}"
  --rename "{ModelName} ({Trigger})"
  --rename "[{Base}] {Name} - {Trigger} - {Author}"
  --rename "{ModelName} {AutoV2}"  (always includes hash)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="File or directory to process (directories process recursively by default)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without renaming/writing files")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output (default is verbose)")
    parser.add_argument("--no-recursive", action="store_true", help="Don't recurse into subdirectories (default is recursive)")
    parser.add_argument("--validate", action="store_true", help="Validate generated cm-info.json before writing")
    parser.add_argument("--rename", type=str, metavar="TEMPLATE", help="Rename template using placeholders (see examples below)")
    parser.add_argument("--always-hash", action="store_true", help="Always include AutoV2 hash in filename (even without collision)")
    parser.add_argument("--wikitag", action="store_true", help="Interactive Wikidata tag lookup and enhancement (requires manual confirmation)")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        print(f"Error: target not found: {target}")
        sys.exit(1)

    # Verbose is True by default, False if --quiet is specified
    verbose = not args.quiet
    # Recursive is True by default, False if --no-recursive is specified
    recursive = not args.no_recursive

    logname = f"metadata_process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    with open(logname, "w", encoding="utf-8") as logfile:
        log(f"=== Metadata Process Started at {datetime.now()} ===", logfile, True)
        log(f"Target: {target}", logfile, True)
        log(f"Dry run: {args.dry_run}", logfile, True)
        log(f"Quiet mode: {args.quiet}", logfile, True)
        log(f"Recursive: {recursive}", logfile, True)
        log(f"Validate: {args.validate}", logfile, True)
        log(f"Rename template: {args.rename or 'default (ModelName + AutoV2)'}", logfile, True)
        log(f"Always hash: {args.always_hash}", logfile, True)
        log(f"Wikitag: {args.wikitag}", logfile, True)

        # Check dependencies
        if Image is None:
            log("⚠️ Pillow (PIL) is not installed. Image conversion will fail.", logfile, True)
        if not ffmpeg_available():
            log("⚠️ ffmpeg (or ffmpeg-python) not available. Video extraction will fail.", logfile, True)
        if args.wikitag and requests is None:
            log("⚠️ requests library not installed. --wikitag feature will not work.", logfile, True)
            print("❌ Error: --wikitag requires 'requests' library. Install with: pip install requests")
            sys.exit(1)

        # Single file target (metadata or other)
        if target.is_file():
            if target.suffix == ".json" and target.name.endswith(".metadata.json"):
                process_group_and_convert(target, args.dry_run, verbose, logfile, args.validate, args.rename, args.always_hash, args.wikitag)
            else:
                print("Error: target file must be a *.metadata.json when providing a file")
                sys.exit(1)
        else:
            # Directory target - always process recursively (batch mode)
            recurse_and_process(target, args.dry_run, verbose, logfile, recursive, args.validate, args.rename, args.always_hash, args.wikitag)

        log(f"=== Completed at {datetime.now()} ===", logfile, True)

if __name__ == "__main__":
    main()
