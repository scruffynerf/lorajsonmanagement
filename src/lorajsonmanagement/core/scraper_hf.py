"""
HFScraperManager for parallel deduplicated downloads from Hugging Face.

Tested in: tests/test_processing.py (Mocked)
"""

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any, Set
from lorajsonmanagement.api.huggingface import HuggingFaceAPI
from lorajsonmanagement.core.processor import ModelProcessor
from lorajsonmanagement.core.db import HashDatabase

class HFScraperManager:
    """
    Coordinates the scraping of Hugging Face repositories with deduplication.
    """
    
    def __init__(self, db_path: str = "downloaded_hashes.db", secondary_db: Optional[str] = None, 
                 token: Optional[str] = None, dry_run: bool = False, verbose: bool = True):
        self.api = HuggingFaceAPI(token=token)
        self.processor = ModelProcessor(dry_run=dry_run, verbose=verbose)
        self.db = HashDatabase(db_path=db_path, secondary_db_path=secondary_db)
        self.dry_run = dry_run
        self.verbose = verbose

    def sync_repo(self, repo_id: str, repo_type: str = "model", extensions: Optional[List[str]] = None,
                  output_dir: Optional[str] = None, max_workers: int = 4, size_limit: Optional[int] = None,
                  skip_vae: bool = False, skip_text_encoder: bool = False, base_model: Optional[str] = None):
        """
        Synchronize a repository, downloading only files not already in the DB.
        """
        self.processor.log(f"🔄 Syncing HF repo: {repo_id} ({repo_type})")
        
        # 1. Get repo info and metadata map
        try:
            repo_info = self.api.api.repo_info(repo_id, repo_type=repo_type, files_metadata=True)
            
            # Base model filtering
            if base_model:
                tags = getattr(repo_info, 'tags', [])
                if not tags: tags = []
                if base_model.lower() not in [t.lower() for t in tags]:
                    self.processor.log(f"⏭️ Skipping {repo_id} - does not match base model {base_model}")
                    return

            metadata_map = self.api.get_repo_metadata_map(repo_id, repo_type=repo_type)
        except Exception as e:
            self.processor.log(f"❌ Error accessing repo {repo_id}: {e}")
            return

        base_dir = Path(output_dir or f"downloaded/{repo_id.replace('/', '_')}")
        if not self.dry_run: base_dir.mkdir(parents=True, exist_ok=True)

        # 2. Filter files
        to_download = []
        for sibling in repo_info.siblings:
            fname = sibling.rfilename
            
            # Filters
            if extensions and not any(fname.endswith(ext) for ext in extensions): continue
            if skip_vae and ('/vae/' in fname or fname.startswith('vae/')): continue
            if skip_text_encoder and ('/text_encoder/' in fname or fname.startswith('text_encoder/')): continue
            
            # Get SHA/Size
            meta = metadata_map.get(fname, {})
            sha = meta.get('sha256')
            size = meta.get('size') or (sibling.size if hasattr(sibling, 'size') else None)
            
            # Fallback to Xet pointer if no SHA
            if not sha:
                self.api.check_rate_limit()
                sha, xet_size = self.api.get_sha256_from_xet_pointer(repo_id, fname, repo_type)
                if xet_size: size = xet_size
            
            if size_limit and size and size > size_limit:
                self.processor.log(f"⏩ Too large: {fname} ({size} bytes)")
                continue

            # 3. Check Deduplication
            if sha and self.db.has_hash(sha):
                self.processor.log(f"✅ Already in DB: {fname}")
                continue
                
            if not sha:
                self.processor.log(f"⚠️  No SHA256 for {fname}, will download if needed.")
            
            to_download.append({'filename': fname, 'sha': sha, 'size': size})

        if not to_download:
            self.processor.log(f"✨ Repo {repo_id} is up to date.")
            return

        # 4. Parallel Download
        self.processor.log(f"📥 Downloading {len(to_download)} files with {max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.api.download_file, repo_id, item['filename'], str(base_dir), repo_type): item 
                for item in to_download if not self.dry_run
            }
            
            if self.dry_run:
                for item in to_download:
                    self.processor.log(f"💡 [Dry-run] Would download {item['filename']} (SHA: {item['sha']})")
                return

            for future in as_completed(futures):
                item = futures[future]
                try:
                    path = future.result()
                    self.processor.log(f"  ✅ Downloaded: {item['filename']}")
                    # Add to DB
                    if item['sha']:
                        self.db.add_hash(item['sha'], repo_id, item['filename'], {'size': item['size']})
                except Exception as e:
                    self.processor.log(f"  ❌ Failed {item['filename']}: {e}")

    def sync_batch(self, repo_list: List[str], **kwargs):
        """Sync a list of repositories."""
        for repo_id in repo_list:
            self.sync_repo(repo_id, **kwargs)
