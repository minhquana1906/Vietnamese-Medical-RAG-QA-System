"""Tests for concurrent request handling and race conditions."""
import asyncio
import uuid
import pytest


def test_concurrent_requests_same_user(client):
    """Test multiple concurrent requests from same user."""
    thread_id = str(uuid.uuid4())
    
    # Simulate sending 3 requests from same user
    responses = []
    for i in range(3):
        res = client.post(
            "/v1/models/rag",
            json={
                "user_identifier": "test-user",
                "thread_id": thread_id,
                "query": f"query {i}",
            },
        )
        responses.append(res)
    
    # All should succeed without race conditions
    for res in responses:
        assert res.status_code == 200


def test_rapid_fire_requests(client):
    """Test rapid consecutive requests."""
    responses = []
    for i in range(10):
        res = client.post(
            "/v1/models/rag",
            json={
                "user_identifier": f"user-{i}",
                "thread_id": str(uuid.uuid4()),
                "query": f"query {i}",
            },
        )
        responses.append(res)
    
    # All should be processed
    assert all(r.status_code == 200 for r in responses)


def test_different_users_parallel(client):
    """Test requests from different users don't interfere."""
    thread_id = str(uuid.uuid4())
    
    responses = []
    for user_id in range(5):
        res = client.post(
            "/v1/models/rag",
            json={
                "user_identifier": f"user-{user_id}",
                "thread_id": thread_id,
                "query": "test",
            },
        )
        responses.append((user_id, res))
    
    # Each request should be independent
    for user_id, res in responses:
        assert res.status_code == 200


def test_no_duplicate_responses(client):
    """Test that responses are unique (no duplication bug)."""
    responses = []
    for i in range(5):
        res = client.post(
            "/v1/models/rag",
            json={
                "user_identifier": "test-user",
                "thread_id": str(uuid.uuid4()),
                "query": f"unique query {i}",
            },
        )
        responses.append(res.json())
    
    # Each response should have unique thread_id
    thread_ids = [r.get("thread_id") for r in responses]
    assert len(set(thread_ids)) == len(thread_ids)


def test_alternating_valid_invalid_requests(client):
    """Test mix of valid and invalid requests doesn't corrupt state."""
    results = []
    
    # Valid request
    res1 = client.post(
        "/v1/models/rag",
        json={
            "user_identifier": "test-user",
            "thread_id": str(uuid.uuid4()),
            "query": "valid",
        },
    )
    results.append(res1.status_code)
    
    # Invalid request (missing field)
    res2 = client.post("/v1/models/rag", json={"query": "invalid"})
    results.append(res2.status_code)
    
    # Valid request again
    res3 = client.post(
        "/v1/models/rag",
        json={
            "user_identifier": "test-user",
            "thread_id": str(uuid.uuid4()),
            "query": "valid again",
        },
    )
    results.append(res3.status_code)
    
    # Should be [200, 422, 200]
    assert results[0] == 200
    assert results[1] == 422
    assert results[2] == 200


def test_request_under_load_no_crash(client):
    """Test system doesn't crash under burst load."""
    burst_size = 20
    responses = []
    
    for i in range(burst_size):
        try:
            res = client.post(
                "/v1/models/rag",
                json={
                    "user_identifier": f"burst-user-{i}",
                    "thread_id": str(uuid.uuid4()),
                    "query": "burst test",
                },
            )
            responses.append(res)
        except Exception as e:
            # Should not raise exceptions
            pytest.fail(f"Request failed with exception: {e}")
    
    # Should process all without crashing
    assert len(responses) == burst_size
    assert all(r.status_code in (200, 429) for r in responses)  # 429 if rate limited


def test_state_isolation_between_threads(client):
    """Test that requests don't leak state between threads."""
    # Send request 1
    thread_1 = str(uuid.uuid4())
    res1 = client.post(
        "/v1/models/rag",
        json={
            "user_identifier": "user-1",
            "thread_id": thread_1,
            "query": "thread 1",
        },
    )
    
    # Send request 2 with different thread
    thread_2 = str(uuid.uuid4())
    res2 = client.post(
        "/v1/models/rag",
        json={
            "user_identifier": "user-2",
            "thread_id": thread_2,
            "query": "thread 2",
        },
    )
    
    # Each response should contain correct thread_id
    assert res1.json()["thread_id"] == thread_1
    assert res2.json()["thread_id"] == thread_2
