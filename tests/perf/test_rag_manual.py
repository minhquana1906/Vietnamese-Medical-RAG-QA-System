#!/usr/bin/env python3
"""Manual test script to verify RAG endpoint with random thread_id"""

import uuid
import requests
import json


def test_rag_endpoint():
    """Test RAG endpoint with random thread_id"""
    url = "http://localhost:8000/v1/rag"

    # Generate random IDs (like Locust does)
    user_id = f"test-user-{uuid.uuid4()}"
    thread_id = str(uuid.uuid4())

    payload = {
        "user_identifier": user_id,
        "thread_id": thread_id,
        "query": "Triệu chứng của cúm là gì?",
    }

    print(f"Testing RAG endpoint...")
    print(f"User ID: {user_id}")
    print(f"Thread ID: {thread_id}")
    print(f"Query: {payload['query']}")
    print("-" * 60)

    try:
        response = requests.post(url, json=payload, timeout=30)

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"Response: {data.get('response', 'N/A')[:200]}...")
            print(f"✅ Test PASSED - Thread auto-created successfully!")
            return True
        else:
            print(f"❌ Test FAILED - Status {response.status_code}")
            print(f"Error: {response.text[:500]}")
            return False

    except Exception as e:
        print(f"❌ Test FAILED - Exception: {e}")
        return False


if __name__ == "__main__":
    success = test_rag_endpoint()
    exit(0 if success else 1)
