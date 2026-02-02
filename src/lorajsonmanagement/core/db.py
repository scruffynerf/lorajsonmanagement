"""
Deduplication database for tracking downloaded model hashes.

Tested in: tests/test_api_and_db.py
"""

import os
import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, List, Any

class HashDatabase:
    """
    Manages an SQLite database of SHA256 hashes for deduplication.
    """
    
    def __init__(self, db_path: str = "codetointegrate/default.sqlite"):
        self.db_path = db_path
        # No _init_db here since we expect the DB to exist and be read-only

    def has_hash(self, sha256: str) -> bool:
        """Check if a hash already exists in the external database."""
        if not os.path.exists(self.db_path):
            return False
            
        sha = sha256.lower()
        with sqlite3.connect(self.db_path) as conn:
            try:
                cursor = conn.execute("SELECT 1 FROM hash_index WHERE sha256 = ?", (sha,))
                return cursor.fetchone() is not None
            except sqlite3.OperationalError:
                # Table might not exist in some versions of the DB
                return False

    def add_hash(self, sha256: str, repo_id: str, file_name: str, meta_data: Dict[str, Any]):
        """
        Record a newly downloaded hash. 
        Note: The user requested not to keep a separate DB, so this is now a no-op 
        unless they explicitly specify a writable DB.
        """
        pass

    def get_all_hashes(self) -> List[str]:
        """Retrieve all known SHA256 hashes from the external DB."""
        if not os.path.exists(self.db_path):
            return []
            
        with sqlite3.connect(self.db_path) as conn:
            try:
                cursor = conn.execute("SELECT sha256 FROM hash_index")
                return [row[0] for row in cursor.fetchall()]
            except sqlite3.OperationalError:
                return []
            
    def get_repo_files(self, repo_id: str) -> List[str]:
        """Retrieve all known filenames for a given repo."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT file_name FROM model_hashes WHERE repo_id = ?", (repo_id,))
            return [row[0] for row in cursor.fetchall()]
