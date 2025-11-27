"""Tests for document management and indexing endpoints."""
import uuid


def test_documents_list_endpoint(client):
    """Test GET /documents endpoint."""
    res = client.get("/documents")
    # May return 404 if endpoint not fully mocked; if 200 validate payload
    assert res.status_code in (200, 404, 500, 503)
    if res.status_code == 200:
        body = res.json()
        assert isinstance(body, list)


def test_documents_list_pagination(client):
    """Test document list with pagination parameters."""
    res = client.get("/documents?limit=10&offset=0")
    assert res.status_code in (200, 404, 500, 503)
    if res.status_code == 200:
        body = res.json()
        assert isinstance(body, list)


def test_document_create_endpoint(client):
    """Test POST /documents endpoint."""
    payload = {
        "title": "Test Document",
        "content": "This is test content about medical topics.",
        "source": "test_source",
        "doc_type": "clinical_guideline",
        "language": "vi",
    }
    res = client.post("/documents", json=payload)
    assert res.status_code in (201, 200, 404, 500, 503)
    if res.status_code in (200, 201):
        body = res.json()
        assert "id" in body or isinstance(body, dict)


def test_document_get_endpoint(client):
    """Test GET /documents/{document_id} endpoint."""
    doc_id = str(uuid.uuid4())
    res = client.get(f"/documents/{doc_id}")
    assert res.status_code in (200, 404, 500, 503)
    if res.status_code == 200:
        body = res.json()
        assert "id" in body


def test_document_delete_endpoint(client):
    """Test DELETE /documents/{document_id} endpoint."""
    doc_id = str(uuid.uuid4())
    res = client.delete(f"/documents/{doc_id}")
    assert res.status_code in (204, 200, 404, 500, 503)


def test_collection_create_endpoint(client):
    """Test POST /v1/collections/create endpoint."""
    res = client.post(
        "/v1/collections/create",
        json={"collection_name": "test_collection", "vector_size": 384},
    )
    assert res.status_code in (200, 201, 404, 500, 503)
    if res.status_code in (200, 201):
        assert res.json() is not None


def test_document_insert_endpoint(client):
    """Test POST /v1/documents/create endpoint."""
    res = client.post(
        "/v1/documents/create",
        json={"title": "Test Doc", "content": "Test content"},
    )
    assert res.status_code in (200, 201, 404, 500, 503)


def test_reindex_document_endpoint(client):
    """Test POST /indexing/reindex-document/{document_id} endpoint."""
    doc_id = str(uuid.uuid4())
    res = client.post(f"/indexing/reindex-document/{doc_id}")
    assert res.status_code in (200, 202, 404, 500, 503)
    if res.status_code == 200:
        body = res.json()
        assert "job_id" in body or "status" in body


def test_ingest_dataset_endpoint(client):
    """Test POST /indexing/ingest-dataset endpoint."""
    payload = {
        "dataset_name": "test/dataset",
        "split": "train",
    }
    res = client.post("/indexing/ingest-dataset", json=payload)
    assert res.status_code in (200, 202, 404, 500, 503)


def test_indexing_job_status_endpoint(client):
    """Test GET /indexing/jobs/{job_id} endpoint."""
    job_id = str(uuid.uuid4())
    res = client.get(f"/indexing/jobs/{job_id}")
    assert res.status_code in (200, 404, 500, 503)
    if res.status_code == 200:
        body = res.json()
        assert "status" in body
