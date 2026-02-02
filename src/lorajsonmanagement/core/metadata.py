"""
Core logic for handling .metadata.json and .cm-info.json formats, 
including normalization, mapping, and validation.

Tested in: tests/test_api_and_db.py, tests/test_processing.py
"""

import os
import json
import re
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any
from lorajsonmanagement.core.hashing import file_hashes, get_autov3_hash

from lorajsonmanagement.core.config import (
    VALID_MODEL_TYPES,
    VALID_SOURCES,
    BASE_MODEL_MAPPINGS,
    CANONICAL_BASE_MODELS,
    MODEL_TYPE_MAPPINGS
)

def sanitize_filename(name: str) -> str:
    """Sanitize model_name to be a valid filename."""
    bad_chars = '<>:"/\\|?*'
    for c in bad_chars:
        name = name.replace(c, "_")
    return name.strip()


def normalize_base_model(base_model: Optional[str]) -> str:
    """Normalize base model name to match spec canonical names."""
    if not base_model:
        return "Other"
    
    lower = base_model.lower().strip()
    
    if lower in BASE_MODEL_MAPPINGS:
        return BASE_MODEL_MAPPINGS[lower]
    
    canonical_names = CANONICAL_BASE_MODELS
    
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


def map_model_type(meta: Dict[str, Any]) -> str:
    """Map metadata class or field to ConnectedModelInfo.ModelType"""
    civitai = meta.get("civitai") or {}
    civitai_type = civitai.get("model", {}).get("type", "")
    if civitai_type:
        upper = civitai_type.upper()
        if upper in VALID_MODEL_TYPES:
            return upper
        if "CHECKPOINT" in upper or "CK" in upper:
            return "Checkpoint"
        if "EMBED" in upper or "TEXTUAL" in upper:
            return "Embedding"
    
    mt = meta.get("model_type", "") or ""
    if isinstance(mt, str):
        lower = mt.lower()
        if lower in MODEL_TYPE_MAPPINGS:
            return MODEL_TYPE_MAPPINGS[lower]
        
        # Fallback keyword matching
        if "check" in lower: return "Checkpoint"
        if "lora" in lower: return "LORA"
        if "embed" in lower: return "Embedding"
    
    name = (meta.get("file_name") or "").lower()
    path = (meta.get("file_path") or "").lower()
    if "lora" in name or "lora" in path:
        return "LORA"
    if "embed" in name or "embed" in path:
        return "Embedding"
    if "checkpoint" in name or "checkpoint" in path:
        return "Checkpoint"
    
    return "Other"


def extract_stats(civitai: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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


def extract_trained_words(civitai: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Extract trainedWords from civitai.model.versions if present"""
    try:
        if not civitai:
            return None
        versions = civitai.get("model", {}).get("modelVersions") or civitai.get("model", {}).get("versions") or []
        for v in versions:
            if v and isinstance(v, dict) and v.get("trainedWords"):
                return v["trainedWords"]
        if civitai.get("trainedWords"):
            return civitai["trainedWords"]
        return None
    except Exception:
        return None


def build_cm_info(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Convert metadata.json content to cm-info.json structure"""
    civitai = metadata.get("civitai") or {}
    sha256 = (metadata.get("sha256") or "").upper()
    file_path = metadata.get("file_path") or ""
    
    filecrc32, fileblake3 = None, None
    if file_path and os.path.isfile(file_path):
       filecrc32, fileblake3 = file_hashes(file_path)
    
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
        "FileMetadata": {
            "fp": None,
            "size": str(metadata.get("size")) if metadata.get("size") else None,
            "format": "SafeTensor"
        },
        "ImportedAt": unix_to_iso(datetime.now().timestamp()),
        "Hashes": {
            "SHA256": sha256 if sha256 else None,
            "CRC32": filecrc32,
            "BLAKE3": fileblake3,
            "AutoV3": get_autov3_hash(Path(file_path)) if file_path else None
        },
        "TrainedWords": extract_trained_words(civitai),
        "Stats": extract_stats(civitai),
        "UserTitle": None,
        "ThumbnailImageUrl": metadata.get("preview_url"),
        "InferenceDefaults": None,
        "Source": 0 if metadata.get("from_civitai", True) else 1
    }
    
    result = {}
    for k, v in cm.items():
        if k in ("VersionDescription", "FileMetadata", "UserTitle", "InferenceDefaults", "Stats"):
            result[k] = v
        elif k in ("ModelDescription", "Tags", "Hashes", "ThumbnailImageUrl", "BaseModel"):
            result[k] = v
        elif v not in ([], {}, "", None):
            result[k] = v
    
    return result


def validate_cminfo(cm: Dict[str, Any]) -> Tuple[bool, List[str]]:
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
    
    if "Hashes" in cm:
        if not isinstance(cm["Hashes"], dict):
            errors.append("Hashes must be a dict")
        elif not (cm["Hashes"].get("SHA256") or cm["Hashes"].get("BLAKE3")):
            errors.append("Hashes must contain at least SHA256 or BLAKE3")
    
    if "ModelType" in cm and cm["ModelType"] not in VALID_MODEL_TYPES:
        errors.append(f"Invalid ModelType: {cm.get('ModelType')}")
    if "Source" in cm and cm["Source"] not in VALID_SOURCES:
        errors.append(f"Invalid Source: {cm.get('Source')} (must be 0 or 1)")
    
    if "BaseModel" in cm:
        normalized = normalize_base_model(cm["BaseModel"])
        if normalized == "Other" and cm["BaseModel"] != "Other":
            errors.append(f"BaseModel '{cm['BaseModel']}' not recognized (normalized to 'Other')")

    return (len(errors) == 0, errors)


def add_trained_words_to_json(json_metadata: Dict[str, Any], words: List[str]):
    """
    Add trained words to the metadata JSON, preferring the Civitai section.
    Modifies the dict in place.
    """
    if not words:
        return

    # 1. Ensure Civitai section exists
    if 'civitai' not in json_metadata or not isinstance(json_metadata['civitai'], dict):
        json_metadata['civitai'] = {}
    
    civitai = json_metadata['civitai']
    
    # 2. Add to civitai.trainedWords directly
    if 'trainedWords' not in civitai:
        civitai['trainedWords'] = []
    
    if not isinstance(civitai['trainedWords'], list):
        civitai['trainedWords'] = [civitai['trainedWords']] if civitai['trainedWords'] else []
        
    existing = set(civitai['trainedWords'])
    for word in words:
        if word not in existing:
            civitai['trainedWords'].append(word)

def update_metadata_after_rename(meta: Dict[str, Any], target_base: str, directory: Path) -> Dict[str, Any]:
    """Update metadata fields after a model file group has been renamed."""
    meta["file_name"] = target_base
    meta["file_path"] = str(directory / f"{target_base}.safetensors")
    meta["preview_url"] = str(directory / f"{target_base}.preview.jpeg")
    return meta
