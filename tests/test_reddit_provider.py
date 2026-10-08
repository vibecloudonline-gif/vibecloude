"""Tests para Reddit research provider."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.research_providers.reddit_provider import RedditProvider


@pytest.mark.asyncio
async def test_search_products_success():
    mock_data = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "Best wireless earbuds under $50?",
                        "subreddit": "BuyItForLife",
                        "score": 342,
                        "num_comments": 87,
                        "permalink": "/r/BuyItForLife/comments/abc123/best_wireless_earbuds/",
                    }
                },
                {
                    "data": {
                        "title": "AirPods Pro vs Sony XM5 review",
                        "subreddit": "headphones",
                        "score": 1200,
                        "num_comments": 230,
                        "permalink": "/r/headphones/comments/def456/airpods_review/",
                    }
                },
            ]
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status = MagicMock()

    provider = RedditProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("earbuds")

    assert len(results) == 2
    assert results[0].source == "Reddit r/BuyItForLife"
    assert results[0].review_count == 342 + 87
    assert results[0].is_demo is False
    assert "reddit.com" in results[0].url


@pytest.mark.asyncio
async def test_search_products_empty():
    mock_data = {"data": {"children": []}}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status = MagicMock()

    provider = RedditProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("xyznotfound")

    assert results == []


@pytest.mark.asyncio
async def test_search_products_http_error():
    provider = RedditProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        import httpx
        mock_request = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "rate limited", request=mock_request, response=mock_resp,
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await provider.search_products("test")

    assert results == []


@pytest.mark.asyncio
async def test_estimate_demand_high():
    mock_data = {
        "data": {
            "dist": 25,
            "children": [
                {"data": {"score": 3000, "num_comments": 600, "subreddit": "tech"}},
                {"data": {"score": 2500, "num_comments": 500, "subreddit": "gadgets"}},
            ],
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status = MagicMock()

    provider = RedditProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        demand = await provider.estimate_demand("earbuds")

    assert demand.confidence_level == "alto"
    assert "Reddit" in demand.source_description


@pytest.mark.asyncio
async def test_estimate_demand_no_results():
    mock_data = {"data": {"dist": 0, "children": []}}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_data
    mock_response.raise_for_status = MagicMock()

    provider = RedditProvider()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        demand = await provider.estimate_demand("xyznotfound")

    assert demand.confidence_level == "bajo"
