"""
Load & Stress Testing cho Vietnamese Medical RAG System

Usage:
    # Load test (normal traffic)
    locust -f locustfile.py --host=http://localhost:8000 --users 50 --spawn-rate 5 --run-time 5m

    # Stress test (peak traffic)
    locust -f locustfile.py --host=http://localhost:8000 --users 200 --spawn-rate 20 --run-time 10m

    # Spike test (sudden burst)
    locust -f locustfile.py --host=http://localhost:8000 --users 500 --spawn-rate 100 --run-time 2m

    # Web UI mode
    locust -f locustfile.py --host=http://localhost:8000
"""

import random
import json
import uuid
from locust import HttpUser, task, between, events
from locust.exception import RescheduleTask


# Test queries covering different complexity levels
MEDICAL_QUERIES = {
    "simple": [
        "Triệu chứng của cúm là gì?",
        "Sốt cao là bao nhiêu độ?",
        "Làm thế nào để hạ sốt?",
        "Viêm họng có nguy hiểm không?",
        "Paracetamol dùng để làm gì?",
    ],
    "medium": [
        "Triệu chứng điển hình của viêm phổi là gì?",
        "Phân biệt viêm phổi và viêm phế quản như thế nào?",
        "Khi nào cần đi khám bệnh viêm amidan?",
        "Thuốc kháng sinh nên uống như thế nào?",
        "Tiêm phòng cúm có tác dụng phụ không?",
    ],
    "complex": [
        "So sánh hiệu quả điều trị viêm phổi giữa Amoxicillin và Azithromycin?",
        "Quy trình chẩn đoán và điều trị bệnh lao phổi theo hướng dẫn mới nhất?",
        "Cơ chế tác động của corticosteroid trong điều trị hen phế quản cấp tính?",
        "Phác đồ kháng sinh cho nhiễm khuẩn hô hấp cấp ở bệnh nhân suy thận?",
        "Chỉ định và chống chỉ định sử dụng thuốc giãn phế quản trong COPD?",
    ],
}


class HealthCheckUser(HttpUser):
    """User chỉ check health endpoints (minimal load)"""

    wait_time = between(5, 10)
    weight = 1  # 5% of total users

    @task(10)
    def check_health(self):
        """Check health endpoint"""
        with self.client.get("/v1/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    def check_ready(self):
        """Check readiness endpoint"""
        with self.client.get("/v1/ready", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Ready check failed: {response.status_code}")

    @task(2)
    def check_cache_stats(self):
        """Check cache statistics"""
        self.client.get("/v1/cache/stats")


class LightRAGUser(HttpUser):
    """User gửi simple queries (light load)"""

    wait_time = between(2, 5)
    weight = 5  # 25% of total users

    def on_start(self):
        """Initialize user session"""
        self.user_id = f"light-user-{uuid.uuid4()}"
        self.thread_id = str(uuid.uuid4())

    @task(10)
    def simple_rag_query(self):
        """Send simple medical query"""
        query = random.choice(MEDICAL_QUERIES["simple"])
        payload = {
            "user_identifier": self.user_id,
            "thread_id": self.thread_id,
            "query": query,
        }

        with self.client.post("/v1/rag", json=payload, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if "response" in data and data["response"]:
                    response.success()
                else:
                    response.failure("Empty response")
            else:
                response.failure(f"Query failed: {response.status_code}")

    @task(3)
    def check_health(self):
        """Occasional health check"""
        self.client.get("/v1/health")


class MediumRAGUser(HttpUser):
    """User gửi medium complexity queries (normal load)"""

    wait_time = between(1, 3)
    weight = 10  # 50% of total users

    def on_start(self):
        """Initialize user session"""
        self.user_id = f"medium-user-{uuid.uuid4()}"
        self.thread_id = str(uuid.uuid4())

    @task(15)
    def medium_rag_query(self):
        """Send medium complexity medical query"""
        query = random.choice(MEDICAL_QUERIES["medium"])
        payload = {
            "user_identifier": self.user_id,
            "thread_id": self.thread_id,
            "query": query,
        }

        with self.client.post(
            "/v1/rag", json=payload, catch_response=True, name="/v1/rag [medium]"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "response" in data and data["response"]:
                    response.success()
                else:
                    response.failure("Empty response")
            elif response.status_code == 429:
                response.failure("Rate limited")
                raise RescheduleTask()
            else:
                response.failure(f"Query failed: {response.status_code}")

    @task(3)
    def embedding_request(self):
        """Test embedding endpoint"""
        payload = {
            "texts": [random.choice(MEDICAL_QUERIES["medium"])],
        }
        self.client.post("/v1/models/embed", json=payload, name="/v1/models/embed")

    @task(1)
    def check_cache_stats(self):
        """Check cache performance"""
        self.client.get("/v1/cache/stats")


class HeavyRAGUser(HttpUser):
    """User gửi complex queries (heavy load)"""

    wait_time = between(0.5, 2)
    weight = 4  # 20% of total users

    def on_start(self):
        """Initialize user session"""
        self.user_id = f"heavy-user-{uuid.uuid4()}"
        self.thread_id = str(uuid.uuid4())

    @task(20)
    def complex_rag_query(self):
        """Send complex medical query"""
        query = random.choice(MEDICAL_QUERIES["complex"])
        payload = {
            "user_identifier": self.user_id,
            "thread_id": self.thread_id,
            "query": query,
        }

        with self.client.post(
            "/v1/rag", json=payload, catch_response=True, name="/v1/rag [complex]"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "response" in data and data["response"]:
                    response.success()
                else:
                    response.failure("Empty response")
            elif response.status_code == 429:
                response.failure("Rate limited")
                raise RescheduleTask()
            elif response.status_code == 503:
                response.failure("Service unavailable")
                raise RescheduleTask()
            else:
                response.failure(f"Query failed: {response.status_code}")

    @task(5)
    def rerank_request(self):
        """Test reranking endpoint"""
        query = random.choice(MEDICAL_QUERIES["complex"])
        payload = {
            "query": query,
            "documents": [
                "Viêm phổi là bệnh nhiễm trùng đường hô hấp dưới.",
                "Triệu chứng bao gồm sốt cao, ho có đàm, khó thở.",
                "Điều trị bằng kháng sinh phù hợp.",
            ],
        }
        self.client.post("/v1/models/rerank", json=payload, name="/v1/models/rerank")

    @task(2)
    def guardrails_check(self):
        """Test guardrails endpoint"""
        query = random.choice(MEDICAL_QUERIES["complex"])
        payload = {"text": query}
        self.client.post("/v1/models/guard", json=payload, name="/v1/models/guard")


# Performance tracking hooks
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start"""
    print(f"\n{'='*60}")
    print(f"Starting load test: {environment.host}")
    print(
        f"Target users: {environment.runner.target_user_count if hasattr(environment.runner, 'target_user_count') else 'N/A'}"
    )
    print(f"{'='*60}\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test results summary"""
    stats = environment.stats
    print(f"\n{'='*60}")
    print(f"Load Test Summary")
    print(f"{'='*60}")
    print(f"Total requests: {stats.total.num_requests}")
    print(f"Total failures: {stats.total.num_failures}")
    print(f"Failure rate: {stats.total.fail_ratio * 100:.2f}%")
    print(f"Median response time: {stats.total.median_response_time} ms")
    print(f"95th percentile: {stats.total.get_response_time_percentile(0.95)} ms")
    print(f"99th percentile: {stats.total.get_response_time_percentile(0.99)} ms")
    print(f"Average RPS: {stats.total.current_rps:.2f}")
    print(f"{'='*60}\n")

    # Fail test if error rate > 5%
    if stats.total.fail_ratio > 0.05:
        print(
            f"⚠️  ERROR: Failure rate ({stats.total.fail_ratio * 100:.2f}%) exceeds threshold (5%)"
        )
        environment.process_exit_code = 1

    # Fail test if p95 latency > 5000ms
    p95 = stats.total.get_response_time_percentile(0.95)
    if p95 > 5000:
        print(f"⚠️  ERROR: P95 latency ({p95}ms) exceeds threshold (5000ms)")
        environment.process_exit_code = 1
