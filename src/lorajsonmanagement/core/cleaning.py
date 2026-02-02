"""
Centralized logic for model name cleaning and normalization.
"""

import re

# Core architecture keywords to strip (case-insensitive)
# These will be matched as whole words or within delimiters
# These will be matched as whole words or within delimiters
# If a word is a "Subject" (like 'Pony' sometimes), move it to a comment or specialized list
CLEANUP_KEYWORDS = [
    # Base Architectures
    "Flux",
    "SDXL",
    "SD1.5",
    "SD-1.5",
    "Hunyuan",
    "Pony",
    "Wan",
    "LTXV",
    "LTXV2",
    "Illustrious",
    "Qwen",
    "Chroma",
    "ZimageBase",
    "ZImageTurbo",
    "ZIT",
    "NoobAI",
    # Types & Extensions
    "LoRa",
    "LoRA",
    "Lora",
    "Checkpoint",
    "VAE",
    "ControlNet",
    "Embedding",
    "Turbo",
    "safetensors",
    "Safe"
]

# Literal tags that should be removed exactly (before emoji removal)
CREATOR_TAGS = [
    "[LuisaP❤️]",
    "SoloLoRA",
    "ZIT_IL",
    "& IL",
    "ZIT &"
]

def clean_model_name(name: str) -> str:
    """
    Clean up a model name by removing emojis, architecture tags, and fixing formatting.
    Generally seeks to isolate the "Subject" of the model.
    """
    if not name:
        return ""

    original_name = name

    # 1. First, remove known literal tags (important for tags that contain emojis)
    for tag in CREATOR_TAGS:
        name = name.replace(tag, " ")

    # 2. Remove non-ASCII (emojis, etc.)
    name = re.sub(r'[^\x00-\x7F]+', ' ', name)

    # 3. Legacy/Specific fixes
    name = name.replace("(Ca ", "(").replace("(CA ", "(")

    # 4. Remove keywords within common delimiters using regex
    delim = r'[\(\)\[\]\{\}\_\-\|\+\s]'
    for word in CLEANUP_KEYWORDS:
        pattern = rf'({delim}*{re.escape(word)}{delim}*)'
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

    # 5. Handle versioning (V1, v2, v3.0, 1.3B, etc.)
    # Matches v1, V2.0, 1.3b, 1.4B, etc. surrounded by delimiters
    version_pattern = rf'({delim}*[vV]?\d+(\.\d+)*[bB]?{delim}*)'
    name = re.sub(version_pattern, ' ', name)
    
    # Standalone legacy patterns
    name = name.replace("1.D", " ").replace(".1 D", " ").replace(".1D", " ")

    # 6. Final formatting cleanup
    # Remove empty brackets/parentheses leftovers
    name = re.sub(r'[\(\[\{][\s\_\-\|\+]*[\)\]\}]', ' ', name)
    
    # Strip double separators and extra spaces
    name = re.sub(r'[\_\-\|\+\s]{2,}', ' ', name)
    
    # Final trim of all possible boundary characters
    cleaned = name.strip(" -_&+.|()[]{},")

    # Protection: If we've stripped so much that practically nothing is left,
    # or the result is just a generic word like 'Video', we might have over-stripped.
    # For now, we return the cleaned name, but we ensure it's not empty.
    if not cleaned or len(cleaned) < 2:
        # Fallback to a simplified version of original if cleaning was too aggressive
        # (e.g., just remove extension and emojis)
        fallback = re.sub(r'[^\x00-\x7F]+', ' ', original_name)
        fallback = re.sub(r'\.(safetensors|metadata|cm-info)?(\.json)?$', '', fallback, flags=re.IGNORECASE)
        return fallback.strip(" -_&+.")

    return cleaned
