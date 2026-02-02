import pytest
from pathlib import Path
from lorajsonmanagement.core.scraper import ScraperManager
from lorajsonmanagement.core.scraper_hf import HFScraperManager
from lorajsonmanagement.core.processor import ModelProcessor

def test_scraper_manager_skip_existing(mocker, tmp_path):
    # Mock DB, API and Processor
    mock_db = mocker.Mock()
    mock_db.has_hash.return_value = True # Already in DB
    
    mock_api = mocker.Mock()
    mock_api.iterate_models.return_value = [{"modelName": "user/repo"}]
    mock_api.get_model_details.return_value = {
        "Data": {"ModelInfos": {"safetensor": {"files": [{"name": "f1.st", "sha256": "h1"}]}}}
    }
    
    mocker.patch("lorajsonmanagement.core.scraper.ModelscopeAPI", return_value=mock_api)
    mocker.patch("lorajsonmanagement.core.scraper.HashDatabase", return_value=mock_db)
    
    manager = ScraperManager(dry_run=True, verbose=False)
    manager.scrape_all(limit=1)
    
    # Should NOT call download_repo if has_hash is True
    assert mock_api.download_repo.called is False

def test_hf_scraper_manager_sync(mocker, tmp_path):
    mock_db = mocker.Mock()
    mock_db.has_hash.return_value = False # Not in DB
    
    mock_api = mocker.Mock()
    # Mock repo_info siblings
    mock_sibling = mocker.Mock()
    mock_sibling.rfilename = "model.safetensors"
    mock_sibling.size = 1000
    
    mock_repo_info = mocker.Mock()
    mock_repo_info.siblings = [mock_sibling]
    
    mock_api.api.repo_info.return_value = mock_repo_info
    mock_api.get_repo_metadata_map.return_value = {"model.safetensors": {"sha256": "hash123", "size": 1000}}
    
    mocker.patch("lorajsonmanagement.core.scraper_hf.HuggingFaceAPI", return_value=mock_api)
    mocker.patch("lorajsonmanagement.core.scraper_hf.HashDatabase", return_value=mock_db)
    
    manager = HFScraperManager(dry_run=True, verbose=False)
    manager.sync_repo("org/repo")
    
    # In dry_run, check if it identified the file
    # (Since it's dry-run, download_file won't be called, but we can check if it iterated)
    assert mock_api.api.repo_info.called is True

def test_processor_modelscope_metadata(tmp_path):
    processor = ModelProcessor(dry_run=False, verbose=False)
    download_dir = tmp_path / "model_repo"
    download_dir.mkdir()
    st_file = download_dir / "test.safetensors"
    st_file.write_text("dummy content")
    
    api_data = {
        "Data": {
            "Name": "Cool Model",
            "CreatedBy": "Author",
            "LastUpdatedTime": 12345,
            "Description": "Desc",
            "TriggerWords": ["word1"],
            "OfficialTags": [{"Name": "tag1"}]
        }
    }
    
    processor.generate_metadata_from_modelscope(api_data, download_dir)
    
    meta_path = download_dir / "test.metadata.json"
    assert meta_path.exists()
    import json
    with meta_path.open() as f:
        data = json.load(f)
        assert data["model_name"] == "Cool Model"
        assert "tag1" in data["tags"]
        assert "word1" in data["tags"]
