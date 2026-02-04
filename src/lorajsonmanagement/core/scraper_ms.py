"""
MSScraperManager to coordinate Modelscope scraping and deduplication.

Tested in: tests/test_processing.py (Mocked)
"""

import os
from pathlib import Path
from typing import Optional, Dict, List, Any
from lorajsonmanagement.api.modelscope import ModelscopeAPI
from lorajsonmanagement.core.processor import ModelProcessor
from lorajsonmanagement.core.db import HashDatabase

class MSScraperManager:
    """
    Coordinates the scraping of Modelscope models, checking hashes before downloading.
    """
    
    def __init__(self, db_path: str = "downloaded_hashes.db", secondary_db: Optional[str] = None, 
                 domain: str = "ai", dry_run: bool = False, verbose: bool = True):
        self.api = ModelscopeAPI(domain=domain)
        self.processor = ModelProcessor(dry_run=dry_run, verbose=verbose)
        self.db = HashDatabase(db_path=db_path, secondary_db_path=secondary_db)
        self.dry_run = dry_run

    def sync_repo(self, repo_id: str, extensions: Optional[List[str]] = None,
                  output_dir: Optional[str] = None, size_limit: Optional[int] = None,
                  skip_vae: bool = False, skip_text_encoder: bool = False, 
                  base_models: Optional[List[str]] = None, force: bool = False):
        """
        Synchronize a single Modelscope repository, downloading only files not already in the DB.
        """
        self.processor.log(f"🔄 Syncing MS repo: {repo_id}")
        
        # 1. Get detailed info
        parts = repo_id.split("/")
        if len(parts) != 2:
            self.processor.log(f"❌ Invalid repo_id: {repo_id}")
            return
        
        username, reponame = parts
        details = self.api.get_model_details(username, reponame)
        if "error" in details:
            self.processor.log(f"⚠️ Error fetching details for {repo_id}: {details['error']}")
            return

        data = details.get("Data", {})
        
        # Base model filtering (client-side backup)
        if base_models:
            tags = data.get("Tags", [])
            description = data.get("Description", "").lower()
            # Include repo_id in search text for maximum robustness
            text_to_search = f"{repo_id} {' '.join(str(t) for t in tags)} {description}".lower()
            
            found = False
            for bm in base_models:
                bm_lower = bm.lower()
                # Try multiple variants for strings with underscores/hyphens (e.g., Z_IMAGE vs Z-IMAGE)
                variants = {bm_lower, bm_lower.replace("_", "-"), bm_lower.replace("_", " "), bm_lower.replace("_", "")}
                
                # Special cases for common ModelScope abbreviations
                if "z_image_turbo" in bm_lower:
                    variants.add("zit")
                if "qwen_image" in bm_lower:
                    variants.add("qwen")
                
                if any(v in text_to_search for v in variants):
                    found = True
                    break
            
            if not found:
                self.processor.log(f"⏭️ Skipping {repo_id} - does not match base models {base_models}")
                return

        # Modelscope separates files by type; we'll look at safetensors and potentially others
        file_infos = []
        model_infos = data.get("ModelInfos", {})
        for content_type in model_infos:
            file_infos.extend(model_infos[content_type].get("files", []))

        # 2. Filter files and check deduplication
        needs_download = False
        allow_patterns = []
        ignore_patterns = []

        if extensions:
            for ext in extensions:
                allow_patterns.append(f"*{ext}")
        if skip_vae:
            ignore_patterns.append("*vae*")
        if skip_text_encoder:
            ignore_patterns.append("*text_encoder*")

        for f_info in file_infos:
            fname = f_info.get("name")
            sha256 = f_info.get("sha256")
            size = f_info.get("size")

            # Check filters (redundant with snapshot_download but good for logging)
            if extensions and not any(fname.endswith(ext) for ext in extensions): continue
            if skip_vae and "vae" in fname.lower(): continue
            if skip_text_encoder and "text_encoder" in fname.lower(): continue
            if size_limit and size and size > size_limit:
                self.processor.log(f"⏩ Too large: {fname} ({size} bytes)")
                continue

            if sha256:
                if not force and self.db.has_hash(sha256):
                    self.processor.log(f"✅ Already in DB: {fname}")
                    continue
                else:
                    if force and self.db.has_hash(sha256):
                         self.processor.log(f"🔁 Forcing download for: {fname}")
                    needs_download = True
            else:
                # No hash in API, must download to find out
                needs_download = True

        # 3. Download if needed
        if needs_download:
            self.processor.log(f"📥 New content found in {repo_id}, downloading...")
            
            try:
                down_path = Path(output_dir or "downloads")
                target_dir = str(down_path / repo_id)
                
                if self.dry_run:
                    self.processor.log(f"💡 [Dry-run] Would download {repo_id} to {target_dir}")
                else:
                    actual_dir = self.api.download_repo(
                        repo_id, 
                        local_dir=target_dir,
                        allow_patterns=allow_patterns if allow_patterns else None,
                        ignore_patterns=ignore_patterns if ignore_patterns else None
                    )
                    self.processor.log(f"✅ Downloaded to {actual_dir}")
                    
                    # Generate metadata
                    self.processor.generate_metadata_from_modelscope(details, Path(actual_dir))
                    
                    # Record newly discovered hashes in DB
                    for f_info in file_infos:
                        sha = f_info.get("sha256")
                        if sha:
                            self.db.add_hash(sha, repo_id, f_info["name"], f_info)
                            
            except Exception as e:
                self.processor.log(f"❌ Failed to download {repo_id}: {e}")
        else:
            self.processor.log(f"⏭️ Skipping {repo_id} - all files accounted for.")

    def sync_batch(self, repo_list: List[str], base_models: Optional[List[str]] = None, force: bool = False, **kwargs):
        """Sync a list of Modelscope repositories."""
        for repo_id in repo_list:
            self.sync_repo(repo_id, base_models=None, force=force, **kwargs)

    def scrape_all(self, model_type: str = "LoRA", limit: Optional[int] = None, 
                   base_models: Optional[List[str]] = None, force: bool = False, **kwargs):
        """
        Scrape Modelscope for all models of a type, syncing each.
        """
        self.processor.log(f"🕵️ Starting scrape for {model_type} models...")
        
        count = 0
        for model_summary in self.api.iterate_models(model_type=model_type, limit=limit, base_models=base_models):
            repo_id = model_summary.get("modelName") or model_summary.get("Path")
            if not repo_id: continue
            
            if "/" not in repo_id and "Path" in model_summary and "Name" in model_summary:
                repo_id = f"{model_summary['Path']}/{model_summary['Name']}"

            self.sync_repo(repo_id, base_models=None, force=force, **kwargs)
            count += 1
            if limit and count >= limit: break

        self.processor.log("✨ Scrape complete.")
