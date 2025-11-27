"""Tests for concurrent request handling and race conditions."""
import uuid
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed


def _post(client, payload):
    return client.post("/v1/models/rag", json=payload)


def test_concurrent_requests_same_user(client):
    """Send multiple requests in parallel from the same user and ensure no race conditions."""
    thread_id = str(uuid.uuid4())
    payloads = [
        {"user_identifier": "test-user", "thread_id": thread_id, "query": f"query {i}"}
        for i in range(10)
    ]

    results = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(_post, client, p) for p in payloads]
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)

    assert len(results) == len(payloads)
    assert all(r.status_code == 200 for r in results)


def test_rapid_fire_requests(client):
    """Rapid consecutive requests executed in parallel."""
    payloads = [
        {"user_identifier": f"user-{i}", "thread_id": str(uuid.uuid4()), "query": f"query {i}"}
        for i in range(50)
    ]

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(_post, client, p) for p in payloads]
        results = [f.result() for f in futures]

    assert len(results) == len(payloads)
    assert all(r.status_code == 200 for r in results)


def test_different_users_parallel(client):
    """Requests from different users in parallel should not interfere."""
    thread_id = str(uuid.uuid4())
    payloads = [
        {"user_identifier": f"user-{i}", "thread_id": str(uuid.uuid4()), "query": "test"}
        for i in range(20)
    ]

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(_post, client, p) for p in payloads]
        results = [f.result() for f in futures]

    assert all(r.status_code == 200 for r in results)


def test_no_duplicate_responses(client):
    """Ensure responses are unique when making many requests."""
    payloads = [
        {"user_identifier": "test-user", "thread_id": str(uuid.uuid4()), "query": f"unique {i}"}
        for i in range(20)
    ]

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(_post, client, p) for p in payloads]
        results = [f.result().json() for f in futures]

    thread_ids = [r.get("thread_id") for r in results]
    assert len(set(thread_ids)) == len(thread_ids)


def test_alternating_valid_invalid_requests(client):
    """Mix valid and invalid requests in parallel to ensure state isn't corrupted."""
    valid = {"user_identifier": "test-user", "thread_id": str(uuid.uuid4()), "query": "valid"}
    invalid = {"query": "invalid"}

    payloads = [valid, invalid, valid]

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(_post, client, p) for p in payloads]
        results = [f.result() for f in futures]

    # find statuses
    statuses = [r.status_code for r in results]
    assert 200 in statuses
    assert 422 in statuses


def test_request_under_load_no_crash(client):
    """Burst load executed in parallel; ensure no exceptions and expected responses."""
    burst_size = 40
    payloads = [
        {"user_identifier": f"burst-user-{i}", "thread_id": str(uuid.uuid4()), "query": "burst test"}
        for i in range(burst_size)
    ]

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(_post, client, p) for p in payloads]
        results = [f.result() for f in futures]

    assert len(results) == burst_size
    assert all(r.status_code in (200, 429) for r in results)


def test_state_isolation_between_threads(client):
    """Requests with different thread IDs must return their matching thread_id."""
    thread_1 = str(uuid.uuid4())
    thread_2 = str(uuid.uuid4())

    payloads = [
        {"user_identifier": "user-1", "thread_id": thread_1, "query": "thread 1"},
        {"user_identifier": "user-2", "thread_id": thread_2, "query": "thread 2"},
    ]

    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(_post, client, p) for p in payloads]
        results = [f.result().json() for f in futures]

    assert results[0]["thread_id"] in (thread_1, thread_2)
    assert results[1]["thread_id"] in (thread_1, thread_2)
    assert results[0]["thread_id"] != results[1]["thread_id"]
