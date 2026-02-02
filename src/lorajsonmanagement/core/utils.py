"""
Unified entry point for utility scripts, utilizing the modular core.

Note: Untested (Thin wrapper around tested core functions).
"""

from pathlib import Path
from lorajsonmanagement.core.hashing import get_autov3_hash
from lorajsonmanagement.core.processor import ModelProcessor

def compute_autov3_for_files(files: list[str], show_full: bool = False):
    """Refactored version of autov3sum.py logic."""
    from lorajsonmanagement.core.hashing import compute_autov3_hex
    
    for filename in files:
        path = Path(filename)
        digest = compute_autov3_hex(path)
        if digest is None:
            # Match original behavior: blank space if unreadable
            print(f"{'':12 if not show_full else 64}  {filename}")
        else:
            value = digest if show_full else digest[:12]
            print(f"{value}  {filename}")

def fix_cm_info_sizes(root_dir: str):
    """Refactored version of fixsizecminfo.py logic."""
    import os
    import json
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(".cm-info.json"):
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if ("FileMetadata" in data and isinstance(data["FileMetadata"], dict) 
                        and "size" in data["FileMetadata"] 
                        and isinstance(data["FileMetadata"]["size"], (int, float))):
                        data["FileMetadata"]["size"] = str(data["FileMetadata"]["size"])
                        with open(fpath, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        print(f"Fixed: {fpath}")
                except Exception as e:
                    print(f"Error processing {fpath}: {e}")
