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
                "bot_id": "meddy",
                "user_id": f"spike_user_{self.user_id}",
                "user_message": query,
                "is_sync_request": True,
            },
            name="/chat/complete (spike)",
        )
