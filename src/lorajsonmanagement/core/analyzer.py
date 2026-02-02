"""
Safetensors analysis and signature-based base model detection.
"""

import json
import struct
import hashlib
import sqlite3
import os
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Set
from lorajsonmanagement.core.config import get_default_signature_db_path


def read_safetensor_metadata(filepath: Path) -> Tuple[List[str], Dict[str, Any], Dict[str, Any]]:
    """
    Read safetensor file and extract:
    - List of tensor keys (layer names)
    - Dict of key -> shape tuples
    - Metadata dict (if present)
    """
    try:
        with open(filepath, 'rb') as f:
            header8 = f.read(8)
            if len(header8) < 8:
                return [], {}, {}
            header_size = struct.unpack('<Q', header8)[0]
            
            header_json = f.read(header_size)
            header = json.loads(header_json)
        
        metadata = header.pop('__metadata__', {})
        tensor_keys = list(header.keys())
        
        shapes = {}
        for key, info in header.items():
            if isinstance(info, dict) and 'shape' in info:
                shapes[key] = info['shape']
            else:
                shapes[key] = []
        
        return tensor_keys, shapes, metadata
    except Exception:
        return [], {}, {}


def extract_trained_words_from_st(st_metadata: Dict[str, Any]) -> List[str]:
    """Try to extract trigger/trained words from safetensor metadata (mostly Kohya format)."""
    words = []
    
    # Kohya format: ss_tag_frequency contains a JSON string or dict
    if 'ss_tag_frequency' in st_metadata:
        try:
            tag_freq = st_metadata['ss_tag_frequency']
            if isinstance(tag_freq, str):
                tag_freq = json.loads(tag_freq)
            
            if isinstance(tag_freq, dict):
                for subset_tags in tag_freq.values():
                    if isinstance(subset_tags, dict):
                        words.extend(subset_tags.keys())
        except (json.JSONDecodeError, TypeError):
            pass
            
    return sorted(list(set(words)))


def compute_key_hash(keys: List[str], shapes: Dict[str, Any]) -> str:
    """Compute a unique hash based on layer names and shapes to identify model architecture."""
    # Create key:shape strings and sort them for stability
    formatted_keys = []
    for k in keys:
        shape = shapes.get(k, [])
        shape_str = 'x'.join(str(d) for d in shape) if shape else ""
        formatted_keys.append(f"{k}:{shape_str}")
    
    sorted_keys = sorted(formatted_keys)
    key_string = '\n'.join(sorted_keys)
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()


class SignatureAnalyzer:
    """Analyzes model layer signatures to detect base models."""
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_signature_db_path()

    def detect_base_model(self, filepath: Path) -> Optional[str]:
        """Attempt to detect base model by inspecting layer keys and shapes."""
        if not os.path.exists(self.db_path):
            return None
            
        keys, shapes, _ = read_safetensor_metadata(filepath)
        if not keys:
            return None
            
        key_hash = compute_key_hash(keys, shapes)
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # 1. Try exact Match
            cur.execute("SELECT base_model FROM model_signatures WHERE key_hash = ?", (key_hash,))
            row = cur.fetchone()
            if row:
                conn.close()
                return row["base_model"]
            
            # 2. Match by key count (faster approximation)
            key_count = len(keys)
            cur.execute("SELECT base_model, key_list FROM model_signatures WHERE key_count = ?", (key_count,))
            rows = cur.fetchall()
            
            if rows:
                # In a real impl we'd do overlap checks, for now return if count is unique
                if len(rows) == 1:
                    conn.close()
                    return rows[0]["base_model"]
            
            conn.close()
        except Exception:
            pass
            
        return None
