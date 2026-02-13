import pytest
import sqlite3
import json
import os
from pathlib import Path
from lorajsonmanagement.api.modelscope import ModelscopeAPI
from lorajsonmanagement.api.huggingface import HuggingFaceAPI
from lorajsonmanagement.core.db import HashDatabase

# --- ModelscopeAPI Tests ---

def test_modelscope_search(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"Data": {"Models": [{"Name": "test-model"}]}}
    mocker.patch("requests.put", return_value=mock_response)
    
    api = ModelscopeAPI(domain="ai")
    results = api.search_models()
    assert results["Data"]["Models"][0]["Name"] == "test-model"

def test_modelscope_iterate(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"Data": {"Model": {"Models": [{"Name": "m1"}, {"Name": "m2"}]}}}
    mocker.patch("requests.put", return_value=mock_response)
    
    api = ModelscopeAPI()
    models = list(api.iterate_models(limit=2))
    assert len(models) == 2
    assert models[0]["Name"] == "m1"

# --- HuggingFaceAPI Tests ---

def test_hf_rate_limiting(mocker):
    api = HuggingFaceAPI()
    # Mock time to track requests
    mocker.patch("time.time", side_effect=[100, 101, 102])
    api.check_rate_limit()
    api.check_rate_limit()
    assert len(api.api_requests) == 2

def test_hf_xet_pointer(mocker):
    mock_res = mocker.Mock()
    mock_res.status_code = 200
    mock_res.text = "oid sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890\nsize 1234"
    mocker.patch("requests.get", return_value=mock_res)
    
    api = HuggingFaceAPI()
    sha, size = api.get_sha256_from_xet_pointer("repo", "file.st")
    assert sha == "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    assert size == 1234

# --- HashDatabase Tests ---

def test_hash_db_readonly(tmp_path):
    # Create a fake default.sqlite
    db_file = tmp_path / "default.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE hash_index (model_type TEXT, sha256 TEXT, file_path TEXT)")
    conn.execute("INSERT INTO hash_index (sha256) VALUES ('fakehash123')")
    conn.commit()
    conn.close()
    
    db = HashDatabase(db_path=str(db_file))
    assert db.has_hash("fakehash123") is True
    assert db.has_hash("missing") is False
    
    # Verify add_hash is a no-op
    db.add_hash("newhash", "repo", "file", {})
    assert db.has_hash("newhash") is False

def test_hash_db_missing_file():
    db = HashDatabase(db_path="nonexistent.sqlite")
    assert db.has_hash("any") is False
    assert db.get_all_hashes() == []
