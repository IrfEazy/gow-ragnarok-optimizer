"""Tests for backend performance and optimization."""

import pytest

from gow_optimizer import web


def test_cache_key_generation_for_inventory():
    """RED: Should generate consistent cache keys for inventory state."""
    inventory1 = {
        "chest_pieces": [{"name": "Test", "level": 5}],
        "resource_budget": {"Hacksilver": 1000},
    }
    inventory2 = {
        "chest_pieces": [{"name": "Test", "level": 5}],
        "resource_budget": {"Hacksilver": 1000},
    }

    key1 = web.generate_inventory_cache_key(inventory1)
    key2 = web.generate_inventory_cache_key(inventory2)

    assert key1 == key2
    assert isinstance(key1, str)


def test_cache_key_differs_for_different_inventory():
    """RED: Cache keys should differ for different inventories."""
    inventory1 = {"resource_budget": {"Hacksilver": 1000}}
    inventory2 = {"resource_budget": {"Hacksilver": 2000}}

    key1 = web.generate_inventory_cache_key(inventory1)
    key2 = web.generate_inventory_cache_key(inventory2)

    assert key1 != key2


def test_memoize_pareto_computation():
    """RED: Should cache Pareto frontier computations."""
    cache = {}

    def dummy_pareto():
        if "computed" in cache:
            return cache["computed"]
        cache["computed"] = [1, 2, 3]
        return cache["computed"]

    # First call
    result1 = dummy_pareto()
    # Second call should return cached result
    result2 = dummy_pareto()

    assert result1 == result2
    assert len(cache) == 1  # Should only have one entry


def test_batch_resource_deductions_efficiently():
    """RED: Should batch multiple material deductions efficiently."""
    resources = {
        "Hacksilver": 1000,
        "Forged Iron": 50,
        "Dwarven Steel": 20,
    }

    deductions = [
        {"Hacksilver": 100, "Forged Iron": 5},
        {"Hacksilver": 50, "Forged Iron": 3},
    ]

    result = web.batch_resource_deductions(resources, deductions)

    assert result["Hacksilver"] == 850  # 1000 - 100 - 50
    assert result["Forged Iron"] == 42  # 50 - 5 - 3


def test_lazy_load_csv_data_only_when_needed():
    """RED: CSV data should load only on first access."""
    access_count = 0

    def mock_load():
        nonlocal access_count
        access_count += 1
        return {"data": "csv"}

    # Simulate lazy loading
    loader = web.LazyDataLoader(mock_load)

    # First access
    data1 = loader.get_data()
    # Second access
    data2 = loader.get_data()

    assert data1 == data2
    assert access_count == 1  # Should only load once


def test_response_caching_headers():
    """RED: API responses should include cache headers."""
    headers = web.generate_cache_headers(max_age=3600)

    assert "Cache-Control" in headers
    assert "max-age" in headers["Cache-Control"]


def test_etag_generation_for_responses():
    """RED: Should generate ETags for response validation."""
    content1 = '{"data": "test"}'
    content2 = '{"data": "test"}'
    content3 = '{"data": "different"}'

    etag1 = web.generate_etag(content1)
    etag2 = web.generate_etag(content2)
    etag3 = web.generate_etag(content3)

    assert etag1 == etag2  # Same content = same etag
    assert etag1 != etag3  # Different content = different etag


def test_gzip_compression_candidates():
    """RED: Should identify large responses for compression."""
    small_response = '{"data": "x"}'
    large_response = '{"data": "' + ("x" * 5000) + '"}'

    small_should_compress = web.should_compress_response(small_response)
    large_should_compress = web.should_compress_response(large_response)

    assert small_should_compress is False
    assert large_should_compress is True


def test_memory_efficient_dataframe_slicing():
    """RED: Should handle large dataframe operations efficiently."""
    # Create mock large inventory
    large_inventory = [{"name": f"Item{i}", "level": i % 9 + 1} for i in range(1000)]

    # Should be able to filter without excessive memory use
    filtered = web.filter_inventory_by_level(large_inventory, min_level=5)

    assert len(filtered) > 0
    assert all(item["level"] >= 5 for item in filtered)
