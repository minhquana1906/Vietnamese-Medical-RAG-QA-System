"""
Locust load testing file for Vietnamese Medical RAG QA System.

Usage:
    locust -f locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10

Test scenarios:
    - simple_query: Common medical questions (weight 3)
    - complex_query: Multi-part medical questions (weight 1)
"""

import random

from locust import HttpUser, between, task


class RAGUser(HttpUser):
    """Simulates a user interacting with the Medical RAG system."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    # Sample medical queries in Vietnamese
    simple_queries = [
        "Triệu chứng của bệnh tiểu đường là gì?",
        "Cách điều trị cao huyết áp",
        "Thuốc paracetamol dùng như thế nào?",
        "Bệnh viêm gan B lây qua đường nào?",
        "Dấu hiệu nhận biết bệnh sốt xuất huyết",
        "Cách phòng ngừa bệnh COVID-19",
        "Thuốc kháng sinh amoxicillin có tác dụng phụ gì?",
        "Vitamin C có tác dụng gì với cơ thể?",
        "Bệnh tiểu đường type 2 có chữa khỏi được không?",
        "Dấu hiệu của bệnh ung thư phổi",
    ]

    complex_queries = [
        "Tôi bị đau đầu và sốt, nên uống thuốc gì và liều lượng ra sao?",
        "Bệnh nhân tiểu đường có thể dùng thuốc giảm đau paracetamol không? Liều lượng bao nhiêu?",
        "Phân biệt giữa cảm cúm và COVID-19 dựa trên triệu chứng",
        "Người bị cao huyết áp nên ăn gì và kiêng gì?",
        "Cách chăm sóc bệnh nhân sau phẫu thuật tim mạch",
    ]

    def on_start(self):
        """Called when a simulated user starts."""
        # Register/login to get JWT token
        response = self.client.post(
            "/auth/login",
            json={
                "email": f"test_user_{random.randint(1, 1000)}@example.com",
                "password": "test_password_123",
            },
            name="/auth/login",
        )

        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            # If login fails, try registration
            register_response = self.client.post(
                "/auth/register",
                json={
                    "email": f"test_user_{random.randint(1, 1000)}@example.com",
                    "password": "test_password_123",
                    "display_name": "Test User",
                },
                name="/auth/register",
            )
            if register_response.status_code == 200:
                # Login after registration
                login_response = self.client.post(
                    "/auth/login",
                    json={
                        "email": register_response.json().get("email"),
                        "password": "test_password_123",
                    },
                    name="/auth/login",
                )
                self.token = login_response.json().get("access_token")
            else:
                self.token = None

        # Create a chat session
        if self.token:
            session_response = self.client.post(
                "/chat/sessions",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"name": "Load Test Session"},
                name="/chat/sessions (create)",
            )
            if session_response.status_code == 200:
                self.session_id = session_response.json().get("id")
            else:
                self.session_id = None

    @task(3)
    def simple_query(self):
        """Send a simple medical query."""
        if not hasattr(self, "session_id") or not self.session_id:
            return

        query = random.choice(self.simple_queries)
        self.client.post(
            f"/chat/sessions/{self.session_id}/messages",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"content": query},
            name="/chat/sessions/{session_id}/messages (simple)",
        )

    @task(1)
    def complex_query(self):
        """Send a complex multi-part medical query."""
        if not hasattr(self, "session_id") or not self.session_id:
            return

        query = random.choice(self.complex_queries)
        self.client.post(
            f"/chat/sessions/{self.session_id}/messages",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"content": query},
            name="/chat/sessions/{session_id}/messages (complex)",
        )

    @task(1)
    def list_sessions(self):
        """List user's chat sessions."""
        if not hasattr(self, "token") or not self.token:
            return

        self.client.get(
            "/chat/sessions",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/chat/sessions (list)",
        )

    def on_stop(self):
        """Called when a simulated user stops."""
        # Logout
        if hasattr(self, "token") and self.token:
            self.client.post(
                "/auth/logout",
                headers={"Authorization": f"Bearer {self.token}"},
                name="/auth/logout",
            )


class SpikeTestUser(HttpUser):
    """User for spike testing - simulates sudden traffic surge."""

    wait_time = between(0.5, 1.5)  # Shorter wait time for spike test

    simple_queries = RAGUser.simple_queries

    def on_start(self):
        """Quick registration and session creation."""
        # Use simplified auth for spike test
        self.user_id = random.randint(1, 10000)

    @task
    def rapid_query(self):
        """Send rapid queries to test system under sudden load."""
        query = random.choice(self.simple_queries)
        # Direct POST to chat endpoint (simplified for spike test)
        self.client.post(
            "/chat/complete",
            json={
                "bot_id": "medical_bot",
                "user_id": f"spike_user_{self.user_id}",
                "user_message": query,
                "is_sync_request": True,
            },
            name="/chat/complete (spike)",
        )
