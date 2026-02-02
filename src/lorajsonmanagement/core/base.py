"""
Standardized interfaces for model service integrations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Generator

class BaseModelAPI(ABC):
    """
    Abstract base class for interacting with model hub APIs.
    """
    
    @abstractmethod
    def search_models(self, **kwargs) -> Dict[str, Any]:
        """Search for models."""
        pass

    @abstractmethod
    def get_model_details(self, repo_id: str, **kwargs) -> Dict[str, Any]:
        """Fetch detailed info for a repository."""
        pass

    @abstractmethod
    def iterate_models(self, limit: Optional[int] = None, **kwargs) -> Generator[Dict[str, Any], None, None]:
        """Generator for model summaries."""
        pass

class BaseScraperManager(ABC):
    """
    Abstract base class for coordinating scraping and deduplication logic.
    """
    
    @abstractmethod
    def sync_repo(self, repo_id: str, **kwargs):
        """Synchronize a single repository."""
        pass

    @abstractmethod
    def sync_batch(self, repo_list: List[str], **kwargs):
        """Synchronize a batch of repositories."""
        pass
