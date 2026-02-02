import pytest
import json
import sqlite3
import struct
from pathlib import Path
from lorajsonmanagement.analyzer.signature_analyzer import SignatureAnalyzer

def test_signature_analyzer_matching(tmp_path):
    db_path = tmp_path / "test_signatures.db"
    analyzer = SignatureAnalyzer(db_path=str(db_path))
    
    # 1. Setup a test signature
    keyset = {"model.diffusion_model.input_blocks.0.0.weight:320x4x3x3", "model.diffusion_model.out.2.weight:320x320"}
    from lorajsonmanagement.core.hashing import compute_key_hash
    khash = compute_key_hash(keyset)
    
    analyzer.add_signature(
        base_model="SD 1.5",
        model_type="lora",
        key_hash=khash,
        key_count=len(keyset),
        keyset=keyset,
        example_sha256="fake_sha",
        example_path="fake_path"
    )
    
    # 2. Test exact match
    matches = analyzer.find_matches(keyset)
    assert len(matches) == 1
    assert matches[0]["base_model"] == "SD 1.5"
    assert matches[0]["match_type"] == "exact"
    
    # 3. Test subset match (keyset is a subset of the provided keys)
    larger_keyset = keyset | {"extra_layer:128"}
    matches_subset = analyzer.find_matches(larger_keyset)
    assert len(matches_subset) == 1
    assert matches_subset[0]["match_type"] == "subset"
    assert matches_subset[0]["base_model"] == "SD 1.5"

def test_safetensor_header_parsing(tmp_path):
    analyzer = SignatureAnalyzer()
    
    # Create a dummy safetensor file
    st_file = tmp_path / "dummy.safetensors"
    # Header: {"__metadata__": {"format": "pt"}, "layer1": {"dtype": "F16", "shape": [1, 2], "offsets": [0, 4]}}
    header_dict = {
        "__metadata__": {"format": "pt"},
        "layer1": {"dtype": "F16", "shape": [1, 2], "offsets": [0, 4]}
    }
    header_json = json.dumps(header_dict).encode('utf-8')
    header_size = len(header_json)
    
    with open(st_file, "wb") as f:
        f.write(struct.pack("<Q", header_size))
        f.write(header_json)
        f.write(b"\x00\x00\x00\x00") # Data
        
    keys, shapes, meta = analyzer.read_safetensor_metadata(str(st_file))
    assert "layer1" in keys
    assert shapes["layer1"] == (1, 2)
    assert meta["format"] == "pt"
