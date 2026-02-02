"""
Enhanced Hugging Face API wrapper with rate-limiting and metadata (LFS/Xet) support.

Tested in: tests/test_api_and_db.py (Mocked)
"""

import os
import re
import time
import requests
from collections import deque
from typing import List, Optional, Dict, Any, Tuple
from huggingface_hub import HfApi, hf_hub_download, get_token, list_repo_tree
from huggingface_hub.hf_api import RepoFile

class HuggingFaceAPI:
    """
    Client for interacting with the Hugging Face API with advanced metadata handling.
    """
    
    API_LIMIT = 1000
    API_WINDOW = 300
    THROTTLE_THRESHOLD = 500
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or get_token()
        self.api = HfApi(token=self.token) if HfApi else None
        self.api_requests = deque()

    def check_rate_limit(self):
        """Check and enforce proactive rate limiting."""
        current_time = time.time()
        while self.api_requests and current_time - self.api_requests[0] > self.API_WINDOW:
            self.api_requests.popleft()
            
        request_count = len(self.api_requests)
        if request_count >= self.THROTTLE_THRESHOLD:
            if self.api_requests:
                oldest_request = self.api_requests[0]
                time_until_expire = self.API_WINDOW - (current_time - oldest_request)
                
                if request_count >= self.API_LIMIT - 10:
                    wait_time = max(1, time_until_expire + 1)
                    time.sleep(wait_time)
                elif request_count >= self.THROTTLE_THRESHOLD + 200:
                    time.sleep(2)
                else:
                    time.sleep(0.5)
        
        self.api_requests.append(current_time)

    def get_sha256_from_xet_pointer(self, repo_id: str, filename: str, repo_type: str = "model") -> Tuple[Optional[str], Optional[int]]:
        """
        Download Xet/Git-LFS pointer and extract SHA256/size.
        """
        try:
            url = f"https://huggingface.co/{repo_id}/raw/main/{filename}"
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            content = response.text
            
            sha = None
            size = None
            
            # Match SHA256: xxxx or oid sha256:xxxx
            sha_match = re.search(r'SHA256:\s*([a-f0-9]{64})', content, re.IGNORECASE)
            if not sha_match:
                sha_match = re.search(r'oid sha256:([a-f0-9]{64})', content, re.IGNORECASE)
            
            if sha_match:
                sha = sha_match.group(1).lower()
            
            size_match = re.search(r'size[:\s]+(\d+)', content, re.IGNORECASE)
            if size_match:
                size = int(size_match.group(1))
                
            return sha, size
        except Exception:
            return None, None

    def get_repo_metadata_map(self, repo_id: str, repo_type: str = "model") -> Dict[str, Dict[str, Any]]:
        """
        Get metadata (SHA256, size) for all files in a repo using tree listing.
        """
        self.check_rate_limit()
        file_map = {}
        try:
            tree = list_repo_tree(repo_id, repo_type=repo_type, recursive=True, token=self.token)
            for f in tree:
                if isinstance(f, RepoFile):
                    sha = None
                    size = f.size if hasattr(f, 'size') else None
                    
                    if hasattr(f, 'lfs') and f.lfs:
                        sha = getattr(f.lfs, 'sha256', None) or f.lfs.get('sha256')
                        if hasattr(f.lfs, 'size'):
                            size = f.lfs.size
                        elif isinstance(f.lfs, dict):
                            size = f.lfs.get('size', size)
                            
                    file_map[f.path] = {'sha256': sha, 'size': size}
        except Exception:
            pass
        return file_map

    def list_user_repos(self, username: str) -> List[str]:
        """List all repos for a user."""
        if not self.api: return []
        repos = []
        try:
            models = self.api.list_models(author=username)
            repos.extend([m.modelId for m in models])
            datasets = self.api.list_datasets(author=username)
            repos.extend([d.id for d in datasets])
        except Exception:
            pass
        return repos

    def search_models(self, query: Optional[str] = None, author: Optional[str] = None, 
                      tags: Optional[List[str]] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for models on Hugging Face using filters."""
        if not self.api: return []
        self.check_rate_limit()
        try:
            models = self.api.list_models(
                search=query,
                author=author,
                tags=tags,
                limit=limit,
                sort="downloads",
                direction=-1
            )
            return [
                {
                    'id': m.modelId,
                    'author': m.author,
                    'lastModified': m.lastModified,
                    'downloads': m.downloads,
                    'tags': m.tags
                } for m in models
            ]
        except Exception:
            return []

    def download_file(self, repo_id: str, filename: str, local_dir: str, repo_type: str = "model"):
        """Download a single file from HF."""
        return hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type=repo_type,
            local_dir=local_dir,
            token=self.token
        )
