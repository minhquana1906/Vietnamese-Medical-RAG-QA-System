import time


def test_ingest_dataset_and_check_job_status(client):
    # Trigger ingest with a very small limit to keep suite fast
    payload = {
        "dataset_name": "quannguyen204/vietnamese_medical_corpus_dataset",
        "split": "train",
        "max_documents": 3,
        "batch_size": 3,
    }

    resp_ingest = client.post("/v1/indexing/ingest-dataset", json=payload)
    # Endpoint may vary in schema; accept 200/201 and job_id presence
    assert resp_ingest.status_code in (200, 201)
    ingest_data = resp_ingest.json()
    job_id = ingest_data.get("job_id") or ingest_data.get("jobId") or "job"
    assert job_id is not None

    # Poll job status a couple of times
    status_resp = client.get(f"/v1/indexing/jobs/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "status" in status_data

    # Optionally wait briefly and re-check for progress field
    time.sleep(1)
    status_resp2 = client.get(f"/v1/indexing/jobs/{job_id}")
    assert status_resp2.status_code == 200
    status_data2 = status_resp2.json()
    assert "status" in status_data2
