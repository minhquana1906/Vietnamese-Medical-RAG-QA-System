from locust import HttpUser, task, between


class RAGUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def rag_query(self):
        payload = {
            "user_identifier": "locust-user",
            "thread_id": "locust-thread",
            "query": "Triệu chứng điển hình của viêm phổi là gì?",
        }
        self.client.post("/v1/rag", json=payload)
