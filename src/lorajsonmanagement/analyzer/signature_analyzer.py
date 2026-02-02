"""
Modular tool for analyzing safetensor file signatures to identify base models.

Tested in: tests/test_analyzer.py
"""

import hashlib
import json
import os
import sqlite3
import struct
from pathlib import Path
from typing import Optional, List, Dict, Set, Any, Tuple
from lorajsonmanagement.core.hashing import compute_file_sha256, compute_key_hash
from lorajsonmanagement.core.metadata import (
    update_metadata_after_rename,
    add_trained_words_to_json
)

class SignatureAnalyzer:
    """
    Analyzes safetensor files to identify base models by their layer structure.
    """
    
    def __init__(self, db_path: str = "codetointegrate/model_signatures.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the signatures database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_signatures (
                    base_model TEXT NOT NULL,
                    model_type TEXT NOT NULL DEFAULT 'lora',
                    key_hash TEXT NOT NULL,
                    key_count INTEGER NOT NULL,
                    key_list TEXT,
                    example_sha256 TEXT,
                    example_path TEXT,
                    created_at REAL,
                    PRIMARY KEY (base_model, model_type, key_hash)
                )
            ''')
            conn.commit()

    def read_safetensor_metadata(self, filepath: str) -> Tuple[List[str], Dict[str, Tuple[int, ...]], Dict[str, Any]]:
        """Read safetensor file and extract tensor keys, shapes, and metadata."""
        with open(filepath, 'rb') as f:
            header_size_bytes = f.read(8)
            header_size = struct.unpack('<Q', header_size_bytes)[0]
            header_json = f.read(header_size)
            header = json.loads(header_json)
        
        metadata = header.pop('__metadata__', {})
        tensor_keys = list(header.keys())
        shapes = {key: tuple(info.get('shape', ())) for key, info in header.items() if isinstance(info, dict)}
        
        return tensor_keys, shapes, metadata

    def make_keyset_with_shapes(self, keys: List[str], shapes: Dict[str, Tuple[int, ...]]) -> Set[str]:
        """Create a set of key:shape strings."""
        result = set()
        for key in keys:
            shape = shapes.get(key, ())
            if shape:
                shape_str = 'x'.join(str(d) for d in shape)
                result.add(f"{key}:{shape_str}")
            else:
                result.add(key)
        return result

    def add_signature(self, base_model: str, model_type: str, key_hash: str, 
                      key_count: int, keyset: Set[str], example_sha256: str, example_path: str):
        """Add a new signature to the database."""
        import time
        key_list = sorted(keyset)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO model_signatures 
                (base_model, model_type, key_hash, key_count, key_list, example_sha256, example_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (base_model, model_type, key_hash, key_count, json.dumps(key_list), 
                  example_sha256, example_path, time.time()))
            conn.commit()

    def find_matches(self, keyset_with_shapes: Set[str]) -> List[Dict[str, Any]]:
        """Find signatures that match the provided keyset (exact or subset)."""
        key_hash = compute_key_hash(keyset_with_shapes)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Try exact match first
            cursor.execute('SELECT base_model, model_type FROM model_signatures WHERE key_hash = ?', (key_hash,))
            exact_matches = [{'base_model': r[0], 'model_type': r[1], 'match_type': 'exact'} for r in cursor.fetchall()]
            if exact_matches:
                return exact_matches
            
            # Try subset matching
            cursor.execute('SELECT base_model, model_type, key_count, key_list, key_hash FROM model_signatures')
            subset_matches = []
            for row in cursor.fetchall():
                base_model, model_type, key_count, key_list_json, stored_hash = row
                if not key_list_json: continue
                stored_keys = set(json.loads(key_list_json))
                if stored_keys <= keyset_with_shapes:
                    subset_matches.append({
                        'base_model': base_model,
                        'model_type': model_type,
                        'key_count': key_count,
                        'key_hash': stored_hash,
                        'matched_keys': len(stored_keys),
                        'extra_keys': len(keyset_with_shapes) - len(stored_keys),
                        'match_type': 'subset'
                    })
            subset_matches.sort(key=lambda m: -m['matched_keys'])
            return subset_matches

    def guess_model_type(self, filepath: str, tensor_keys: List[str]) -> str:
        """Guess the model type from filepath and tensor keys."""
        path_lower = filepath.lower()
        if any(x in path_lower for x in ['/checkpoint', '/checkpoints']): return 'checkpoint'
        if any(x in path_lower for x in ['/lora', '/loras']): return 'lora'
        if '/vae' in path_lower: return 'vae'
        
        if any('lora_' in k.lower() for k in tensor_keys): return 'lora'
        if any('diffusion_model' in k for k in tensor_keys):
            return 'checkpoint' if len(tensor_keys) > 500 else 'controlnet'
        
        return 'unknown'

    def extract_trained_words_from_st(self, st_metadata: Dict[str, Any]) -> List[str]:
        """Try to extract trigger/trained words from safetensor metadata (Kohya format)."""
        words = []
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
        return words[:20]

    def load_metadata_json(self, safetensor_path: str) -> Optional[Dict[str, Any]]:
        """Load the companion .metadata.json file for a safetensor, checking multiple patterns."""
        st_path = Path(safetensor_path)
        # Patterns: .metadata.json, .safetensors.metadata.json, or stem.metadata.json
        candidates = [
            st_path.with_suffix('.metadata.json'),
            Path(str(st_path) + '.metadata.json'),
            st_path.parent / f"{st_path.stem}.metadata.json"
        ]
        for p in candidates:
            if p.exists():
                with open(p, 'r') as f:
                    return json.load(f)
        return None

    def save_metadata_json(self, safetensor_path: str, metadata: Dict[str, Any]):
        """Save the companion .metadata.json file."""
        st_path = Path(safetensor_path)
        json_path = st_path.parent / f"{st_path.stem}.metadata.json"
        with open(json_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def add_trained_words_to_json(self, json_metadata: Dict[str, Any], words: List[str], filepath: str):
        """Add trained words to JSON metadata and save."""
        add_trained_words_to_json(json_metadata, words)
        self.save_metadata_json(filepath, json_metadata)

    def analyze_file(self, filepath: str, dry_run: bool = False) -> bool:
        """Analyze a single file and interact with user if needed."""
        print(f"\n🔍 Analyzing: {filepath}")
        
        json_metadata = self.load_metadata_json(filepath)
        if json_metadata is None:
            print(f"  ⚠️ No .metadata.json found, skipping.")
            return True

        base_model = json_metadata.get('base_model', 'Unknown')
        
        try:
            tensor_keys, shapes, st_metadata = self.read_safetensor_metadata(filepath)
        except Exception as e:
            print(f"  ❌ Error reading safetensor: {e}")
            return True

        keyset_with_shapes = self.make_keyset_with_shapes(tensor_keys, shapes)
        key_hash = compute_key_hash(keyset_with_shapes)
        
        # Check for trained words
        st_trained_words = self.extract_trained_words_from_st(st_metadata)
        if st_trained_words and not dry_run:
            # Simple interactive check (simplified for modular use)
            print(f"  ✨ Found trained words in ST: {st_trained_words[:5]}")
            # ... identification logic would go here ...
        
        matches = self.find_matches(keyset_with_shapes)
        if matches:
            best = matches[0]
            print(f"  ✅ Match found: {best['base_model']} ({best['match_type']})")
            if base_model == 'Unknown' and not dry_run:
                json_metadata['base_model'] = best['base_model']
                self.save_metadata_json(filepath, json_metadata)
                print(f"  ✓ Updated JSON base_model.")
        else:
            print(f"  ❓ No signature match found.")
            # ... interactive identification loop ...
            
        return True
