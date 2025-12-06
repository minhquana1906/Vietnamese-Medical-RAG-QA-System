import random

from locust import HttpUser, between, task


class RAGUser(HttpUser):
    """Simulates a user interacting with the Medical RAG system."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    SAMPLE_QUERIES = [
        "Triệu chứng điển hình của viêm phổi là gì?",
        "Thuốc hạ sốt nào an toàn cho trẻ em?",
        "Khi nào cần xét nghiệm HbA1c cho bệnh nhân tiểu đường?",
        "Phân biệt cảm cúm và cúm mùa như thế nào?",
    ]

    @task(5)
    def rag_text(self):
        query = random.choice(self.SAMPLE_QUERIES)
        body = {"query": query, "top_k": 5, "return_sources": True}
        self.client.post("/v1/rag", json=body, name="rag_text")

    @task(1)
    def health(self):
        self.client.get("/v1/health", name="health")

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

class AudioUser(HttpUser):
    wait_time = between(2.0, 4.0)

    @task
    def rag_audio(self):
        # Expect a small Vietnamese WAV file present at testing/sample_audio_vn.wav
        try:
            with open("testing/sample_audio_vn.wav", "rb") as f:
                files = {"file": ("sample_audio_vn.wav", f, "audio/wav")}
                data = {"top_k": 5, "return_sources": "true"}
                self.client.post("/v1/rag/audio", files=files, data=data, name="rag_audio")
        except FileNotFoundError:
            # Fallback: hit STT endpoint without file to surface error handling
            self.client.post("/v1/models/stt", name="stt_no_file")
