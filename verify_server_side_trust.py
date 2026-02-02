
import sys
import os
from unittest.mock import MagicMock, patch
from lorajsonmanagement.core.scraper_ms import MSScraperManager

def test_server_side_trust():
    print("🧪 Testing Server-Side Trust in Scraper...")
    
    # Mock dependencies
    mock_api = MagicMock()
    mock_processor = MagicMock()
    mock_db = MagicMock()
    
    # Create manager with mocks
    manager = MSScraperManager(dry_run=True, verbose=True)
    manager.api = mock_api
    manager.processor = mock_processor
    manager.db = mock_db
    
    # Mock iterate_models to return a result that DEFINITELY fails client-side filtering
    # if it were applied.
    # e.g. base_model="SDXL" but this model has no tags and description="foo"
    fake_model = {
        "modelName": "test_user/test_repo",
        "Path": "test_user",
        "Name": "test_repo"
    }
    mock_api.iterate_models.return_value = [fake_model]
    
    # Mock sync_repo to just print/log validation
    # We want to verified it IS called.
    manager.sync_repo = MagicMock()
    
    # Run scrape_all with a base model filter
    # This simulates: lora-mgmt ms-scrape --base-model "SDXL"
    print("🚀 Calling scrape_all(base_models=['SDXL'])...")
    manager.scrape_all(base_models=["SDXL"])
    
    # Verification
    # iterate_models should be called WITH the filter (server-side)
    mock_api.iterate_models.assert_called_with(model_type="LoRA", limit=None, base_models=["SDXL"])
    print("✅ iterate_models called with base_models=['SDXL']")
    
    # sync_repo should be called WITHOUT the filter (client-side disabled)
    # OR if it is called with the filter, it must be ignored.
    # The user request is specifically to DISABLE client filtering here.
    # So we expect base_models=None or base_models=[] passed to sync_repo
    
    call_args = manager.sync_repo.call_args
    if not call_args:
        print("❌ sync_repo was NOT called! Client-side filtering might be happening inside scrape_all or iterator didn't yield.")
        sys.exit(1)
        
    _, kwargs = call_args
    passed_base_models = kwargs.get('base_models')
    
    if passed_base_models:
        print(f"❌ FAIL: sync_repo called with base_models={passed_base_models}. It should be None/Empty to trust server.")
        sys.exit(1)
    else:
        print("✅ PASS: sync_repo called with base_models=None. Server results trusted.")

if __name__ == "__main__":
    try:
        test_server_side_trust()
        print("\n✨ Test Passed!")
    except Exception as e:
        print(f"\n💥 Test Error: {e}")
        sys.exit(1)
