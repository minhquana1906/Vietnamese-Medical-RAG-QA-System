from uuid import UUID


def test_documents_create_list_get_delete(client):
    # Create
    create_payload = {
        "title": "Hướng dẫn viêm phổi (test)",
        "content": "Viêm phổi là nhiễm trùng nhu mô phổi...",
        "source": "integration_test",
        "doc_type": "guideline",
        "language": "vi",
        "metadata": {"test": True},
    }
    resp_create = client.post("/v1/documents/create", json=create_payload)
    assert resp_create.status_code in (200, 201)
    created = resp_create.json()
    doc_id = created.get("id")
    assert doc_id is not None

    # List
    resp_list = client.get("/v1/documents/list?limit=10&offset=0")
    assert resp_list.status_code == 200
    data_list = resp_list.json()
    assert "documents" in data_list and isinstance(data_list["documents"], list)

    # Get
    resp_get = client.get(f"/v1/documents/{doc_id}")
    assert resp_get.status_code == 200
    detail = resp_get.json()
    assert detail.get("id") == doc_id

    # Delete
    resp_del = client.delete(f"/v1/documents/{doc_id}")
    assert resp_del.status_code in (200, 204)
