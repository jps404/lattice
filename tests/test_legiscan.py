"""Tests for LegiScan API client."""

import json
from unittest.mock import patch, MagicMock

from ingestion.legiscan import LegiScanClient, STATUS_MAP


def test_status_map_covers_common_codes():
    """All common status codes should have readable names."""
    assert STATUS_MAP[1] == "Introduced"
    assert STATUS_MAP[4] == "Passed"
    assert STATUS_MAP[6] == "Failed"


def test_client_init_with_key():
    """Client should accept an explicit API key."""
    client = LegiScanClient(api_key="test_key")
    assert client.api_key == "test_key"


@patch("ingestion.legiscan.requests.get")
def test_get_session_list(mock_get):
    """Should parse session list from API response."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": "OK",
        "sessions": [
            {"session_id": 2084, "session_title": "2026 Regular Session", "year_start": 2026, "year_end": 2026},
            {"session_id": 2000, "session_title": "2025 Regular Session", "year_start": 2025, "year_end": 2025},
        ],
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    client = LegiScanClient(api_key="test")
    sessions = client.get_session_list("LA")

    assert len(sessions) == 2
    assert sessions[0]["session_id"] == 2084


@patch("ingestion.legiscan.requests.get")
def test_get_master_list_filters_session_key(mock_get):
    """Master list should exclude the 'session' metadata key."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": "OK",
        "masterlist": {
            "session": {"session_id": 2084},
            "0": {"bill_id": 100, "number": "HB 1", "change_hash": "abc"},
            "1": {"bill_id": 101, "number": "SB 1", "change_hash": "def"},
        },
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    client = LegiScanClient(api_key="test")
    bills = client.get_master_list(2084)

    assert len(bills) == 2
    assert 100 in bills
    assert 101 in bills


@patch("ingestion.legiscan.requests.get")
def test_api_error_raises(mock_get):
    """Should raise RuntimeError on API error status."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": "ERROR",
        "alert": {"message": "Invalid API key"},
    }
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    client = LegiScanClient(api_key="bad_key")
    try:
        client.get_session_list("LA")
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "Invalid API key" in str(e)
