import pytest
from lorajsonmanagement.api.modelscope import ModelscopeAPI

def test_modelscope_token_init(mocker):
    # Mock HubApi
    mock_hub_api = mocker.Mock()
    mocker.patch("modelscope.hub.api.HubApi", return_value=mock_hub_api)
    
    token = "test_token_123"
    api = ModelscopeAPI(token=token)
    
    assert api.token == token
    assert api.headers["Authorization"] == f"Bearer {token}"
    mock_hub_api.login.assert_called_once_with(token)

def test_modelscope_download_repo_passes_token(mocker):
    # Mock HubApi to avoid actual login
    mocker.patch("modelscope.hub.api.HubApi")
    mock_snapshot = mocker.patch("modelscope.snapshot_download")
    
    token = "test_token_123"
    api = ModelscopeAPI(token=token)
    
    api.download_repo("test/repo")
    
    mock_snapshot.assert_called_once()
    args, kwargs = mock_snapshot.call_args
    assert kwargs["token"] == token

def test_modelscope_download_repo_explicit_token(mocker):
    mocker.patch("modelscope.hub.api.HubApi")
    mock_snapshot = mocker.patch("modelscope.snapshot_download")
    
    api = ModelscopeAPI()
    api.download_repo("test/repo", token="explicit_token")
    
    args, kwargs = mock_snapshot.call_args
    assert kwargs["token"] == "explicit_token"
