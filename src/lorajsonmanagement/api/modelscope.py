"""
A robust wrapper for the Modelscope API, facilitating model search, details retrieval, and downloading.

Tested in: tests/test_api_and_db.py (Mocked)
"""

import requests
import json
import time
import re
from collections import deque
from typing import Optional, Dict, Any, List, Tuple

class ModelscopeAPI:
    """
    Client for interacting with the Modelscope API.
    """
    
    DOMAINS = {
        "ai": "https://modelscope.ai",
        "cn": "https://modelscope.cn"
    }
    
    API_LIMIT = 500
    API_WINDOW = 60
    THROTTLE_THRESHOLD = 300
    
    def __init__(self, domain: str = "ai", user_agent: Optional[str] = None, token: Optional[str] = None):
        self.domain = domain
        self.base_url = self.DOMAINS.get(domain, self.DOMAINS["ai"])
        self.headers = {
            "User-Agent": user_agent or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{self.base_url}/models",
        }
        self.token = token
        if token:
            self.login(token)
        self.api_requests = deque()

    def login(self, token: str):
        """Login to ModelScope using the provided token."""
        try:
            from modelscope.hub.api import HubApi
            api = HubApi()
            api.login(token)
            # Standard HubApi login might set some global state or session.
            # We also update headers for direct REST calls if needed.
            self.headers["Authorization"] = f"Bearer {token}"
            self.token = token
        except ImportError:
            # Fallback to general modelscope import if HubApi is nested differently
            import modelscope
            if hasattr(modelscope, 'HubApi'):
                api = modelscope.HubApi()
                api.login(token)
                self.headers["Authorization"] = f"Bearer {token}"
                self.token = token
            else:
                raise ImportError("Could not find HubApi in modelscope. Please ensure modelscope is installed.")

    def check_rate_limit(self):
        """Check and enforce proactive rate limiting for Modelscope."""
        current_time = time.time()
        while self.api_requests and current_time - self.api_requests[0] > self.API_WINDOW:
            self.api_requests.popleft()
            
        request_count = len(self.api_requests)
        if request_count >= self.THROTTLE_THRESHOLD:
            # Consistent with HF implementation
            sleep_time = 0.5
            if request_count >= self.API_LIMIT - 10:
                sleep_time = 2
            time.sleep(sleep_time)
        
        self.api_requests.append(current_time)

    def search_models(self, model_type: str = "LoRA", page: int = 1, sort: str = "GmtModified", 
                      base_models: Optional[List[str]] = None,
                      base_model_no_ver: Optional[List[str]] = None,
                      base_model_relation: Optional[str] = None) -> Dict[str, Any]:
        """Search for models on Modelscope using the dolphin endpoint with robust payload."""
        url = f"{self.base_url}/api/v1/dolphin/models"
        
        # Map common sort keys to API valid values
        if sort == "latest":
            sort = "GmtModified"

        # Robust payload as discovered in telemetry/user-feedback
        payload = {
            "PageSize": 30,
            "PageNumber": page,
            "SortBy": sort,
            "Target": "",
            "IsAigc": True,
            "Name": "",
            "ImgUrl": "",
            "SingleCriterion": [
                {
                    "category": "aigc_type",
                    "DateType": "string",
                    "predicate": "equal",
                    "StringValue": model_type
                },
                {
                    "category": "vision_foundation",
                    "DateType": "string",
                    "predicate": "equal",
                    "StringValue": "all"
                }
            ],
            "Criterion": []
        }

        if base_models:
            payload["Criterion"].append({
                "category": "sub_vision_foundation",
                "predicate": "contains",
                "values": base_models
            })

        if base_model_no_ver:
            payload["Criterion"].append({
                "category": "base_model_no_ver",
                "predicate": "contains",
                "values": base_model_no_ver
            })

        if base_model_relation:
            payload["SingleCriterion"].append({
                "category": "base_model_relation",
                "DateType": "string",
                "predicate": "equal",
                "StringValue": base_model_relation
            })
            
        try:
            self.check_rate_limit()
            # Note: Modelscope uses PUT for this search endpoint
            response = requests.put(url, json=payload, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}", "text": response.text}
        except Exception as e:
            return {"error": str(e)}

    def get_model_details(self, username: str, reponame: str) -> Dict[str, Any]:
        """Fetch detailed info for a specific model repository."""
        url = f"{self.base_url}/api/v1/models/{username}/{reponame}"
        try:
            self.check_rate_limit()
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}", "text": response.text}
        except Exception as e:
            return {"error": str(e)}

    def get_git_url(self, repo_id: str) -> str:
        """Get the Git clone URL for a repository."""
        return f"{self.base_url}/{repo_id}.git"

    def get_sha256_from_lfs_pointer(self, repo_id: str, filename: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Download Git-LFS pointer from ModelScope and extract SHA256/size.
        """
        try:
            url = f"{self.base_url}/api/v1/models/{repo_id}/repo/files?path={filename}"
            # This is a guestimating pattern based on common MaaS behaviors
            # Actually, ModelScope's get_model_details often includes these already.
            # But for raw access:
            raw_url = f"{self.base_url}/{repo_id}/raw/master/{filename}"
            self.check_rate_limit()
            response = requests.get(raw_url, timeout=10)
            response.raise_for_status()
            content = response.text
            
            sha = None
            size = None
            
            sha_match = re.search(r'oid sha256:([a-f0-9]{64})', content)
            if sha_match:
                sha = sha_match.group(1).lower()
            
            size_match = re.search(r'size\s+(\d+)', content)
            if size_match:
                size = int(size_match.group(1))
                
            return sha, size
        except Exception:
            return None, None

    def download_repo(self, repo_id: str, local_dir: Optional[str] = None, revision: str = "master",
                      allow_patterns: Optional[List[str]] = None, ignore_patterns: Optional[List[str]] = None,
                      token: Optional[str] = None) -> str:
        """
        Download a model repository using the modelscope library.
        Returns the local directory path.
        """
        try:
            from modelscope import snapshot_download
        except ImportError:
            raise ImportError("Please install the modelscope library: pip install modelscope")
            
        return snapshot_download(
            repo_id, 
            local_dir=local_dir, 
            revision=revision,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
            token=token or self.token
        )

    def iterate_models(self, model_type: str = "LoRA", sort: str = "GmtModified", limit: Optional[int] = None,
                       base_models: Optional[List[str]] = None,
                       base_model_no_ver: Optional[List[str]] = None,
                       base_model_relation: Optional[str] = None):
        """
        Generator that yields model summaries from search results, 
        handling pagination automatically.
        """
        page = 1
        count = 0
        while True:
            results = self.search_models(model_type=model_type, page=page, sort=sort, 
                                       base_models=base_models,
                                       base_model_no_ver=base_model_no_ver,
                                       base_model_relation=base_model_relation)
            
            if "error" in results:
                break
                
            data = results.get("Data", {}) or results.get("data", {}) 
            model_data = data.get("Model", {})
            models = model_data.get("Models", [])
            
            if not models:
                break
                
            for model in models:
                yield model
                count += 1
                if limit and count >= limit:
                    return
            
            page += 1
            if page > 1000: # Safety break
                break


def main():
    """Example usage of the ModelscopeAPI class."""
    api = ModelscopeAPI()
    # Search example
    results = api.search_models()
    if "error" not in results:
        models = results.get("Data", {}).get("Model", {}).get("Models", [])
        print(f"Successfully retrieved {len(models)} models.")
    
    # Details example
    # Example: api.get_model_details("damo", "cv_resnet50_face-detection_retinaface")
    details = api.get_model_details("author", "model_name")
    if "error" not in details:
        print(f"Model ID: {details.get('Data', {}).get('Id')}")

if __name__ == "__main__":
    main()
