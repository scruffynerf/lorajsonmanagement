import sys
import os
from pathlib import Path

# Add src to sys.path
sys.path.append(os.path.abspath("src"))

from lorajsonmanagement.core.processor import ModelProcessor

def verify_samples():
    sample_dir = Path("sample json files")
    processor = ModelProcessor(dry_run=True, verbose=True)
    
    print("--- Verifying Sample JSON Files (Dry Run) ---")
    for json_file in sample_dir.glob("*.metadata.json"):
        print(f"\nProcessing: {json_file.name}")
        # Test conversion logic
        processor.convert_to_cminfo(json_file)

if __name__ == "__main__":
    verify_samples()
