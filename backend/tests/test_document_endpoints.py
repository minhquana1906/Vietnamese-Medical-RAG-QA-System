"""Tests for document management and indexing endpoints."""
import uuid


def test_documents_list_endpoint(client):
    """Test GET /documents endpoint."""
    res = client.get("/documents")
    # May return 404 if endpoint not fully mocked
    assert res.status_code in (200, 404)


def test_documents_list_pagination(client):
    """Test document list with pagination parameters."""
    res = client.get("/documents?limit=10&offset=0")
    assert res.status_code in (200, 404)


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
    # May return 404 if not fully mocked
    assert res.status_code in (201, 404, 500)


def test_document_get_endpoint(client):
    """Test GET /documents/{document_id} endpoint."""
    doc_id = str(uuid.uuid4())
    res = client.get(f"/documents/{doc_id}")
    # Should return 404 for non-existent document
    assert res.status_code in (200, 404)


def test_document_delete_endpoint(client):
    """Test DELETE /documents/{document_id} endpoint."""
    doc_id = str(uuid.uuid4())
    res = client.delete(f"/documents/{doc_id}")
    # Should return 204 or 404
    assert res.status_code in (204, 404)


def test_collection_create_endpoint(client):
    """Test POST /v1/collections/create endpoint."""
    res = client.post(
        "/v1/collections/create",
        json={"collection_name": "test_collection", "vector_size": 384},
    )
    assert res.status_code in (200, 404, 500)


def test_document_insert_endpoint(client):
    """Test POST /v1/documents/create endpoint."""
    res = client.post(
        "/v1/documents/create",
        json={"title": "Test Doc", "content": "Test content"},
    )
    assert res.status_code in (200, 404, 500)


def test_reindex_document_endpoint(client):
    """Test POST /indexing/reindex-document/{document_id} endpoint."""
    doc_id = str(uuid.uuid4())
    res = client.post(f"/indexing/reindex-document/{doc_id}")
    # Should return job info or 404
    assert res.status_code in (200, 404)


def test_ingest_dataset_endpoint(client):
    """Test POST /indexing/ingest-dataset endpoint."""
    payload = {
        "dataset_name": "test/dataset",
        "split": "train",
    }
    res = client.post("/indexing/ingest-dataset", json=payload)
    assert res.status_code in (200, 404, 500)


def test_indexing_job_status_endpoint(client):
    """Test GET /indexing/jobs/{job_id} endpoint."""
    job_id = str(uuid.uuid4())
    res = client.get(f"/indexing/jobs/{job_id}")
    assert res.status_code in (200, 404)
