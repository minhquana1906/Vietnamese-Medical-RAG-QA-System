"""Qwen3Guard service for content moderation and guardrails."""

import httpx
from typing import Dict, Optional, Tuple
from loguru import logger

from ..configs.setup import get_backend_settings

settings = get_backend_settings()


class Qwen3GuardService:
    CATEGORIES = {
        "harmful": "Content promoting violence, self-harm, or illegal activities",
        "inappropriate": "Sexual, offensive, or discriminatory content",
        "off_topic": "Non-medical or irrelevant queries",
        "privacy_violating": "Requests for personal medical records or identifiable information",
        "medical_advice": "Requests for specific medical diagnoses without proper context",
    }

    def __init__(
        self, triton_url: Optional[str] = None, model_name: str = "qwen3_guard"
    ):

        self.triton_url = triton_url or settings.triton_http_url
        self.model_name = model_name
        self.client = httpx.Client(timeout=10.0)

    def validate_query(self, query: str) -> Tuple[bool, Optional[str], Optional[Dict]]:

        # Check for empty query
        if not query or not query.strip():
            return False, "empty_query", {"message": "Query cannot be empty"}

        # Call Qwen3Guard model
        try:
            is_safe, category, confidence = self._check_with_triton(query)

            if is_safe:
                logger.debug(f"Query passed guardrails: {query[:50]}...")
                return True, None, {"confidence": confidence}
            else:
                logger.warning(
                    f"Query filtered by guardrails: {query[:50]}... (category: {category})"
                )
                return (
                    False,
                    category,
                    {
                        "confidence": confidence,
                        "category_description": self.CATEGORIES.get(
                            category or "unknown", "Unknown violation"
                        ),
                    },
                )
        except Exception as e:
            logger.error(f"Guardrails check failed: {e}")
            # Fail open - allow query if guardrails service is down
            logger.warning("Guardrails service unavailable, allowing query")
            return True, None, {"error": str(e), "failover": True}

    def _check_with_triton(self, query: str) -> Tuple[bool, Optional[str], float]:
        try:
            payload = {
                "inputs": [
                    {
                        "name": "input_text",
                        "shape": [1],
                        "datatype": "BYTES",
                        "data": [query],
                    }
                ]
            }

            response = self.client.post(
                f"{self.triton_url}/v2/models/{self.model_name}/infer",
                json=payload,
            )

            if response.status_code == 200:
                result = response.json()
                # Assuming output format: {"is_safe": bool, "category": str, "confidence": float}
                outputs = result["outputs"]
                is_safe = outputs[0]["data"][0]
                category = outputs[1]["data"][0] if len(outputs) > 1 else None
                confidence = outputs[2]["data"][0] if len(outputs) > 2 else 1.0

                return is_safe, category, confidence
            else:
                logger.error(
                    f"Triton guardrails inference failed: {response.status_code}"
                )
                raise Exception(f"Triton returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error calling Triton for guardrails: {e}")
            raise

    def _simple_rule_based_check(self, query: str) -> Tuple[bool, Optional[str]]:
        query_lower = query.lower()

        # Check for explicit harmful content keywords
        harmful_keywords = [
            "suicide",
            "self-harm",
            "kill myself",
            "tự tử",
            "tự sát",
            "giết mình",
        ]
        for keyword in harmful_keywords:
            if keyword in query_lower:
                return False, "harmful"

        # Check for privacy violations
        privacy_keywords = [
            "social security",
            "ssn",
            "credit card",
            "password",
            "số chứng minh",
            "cmnd",
            "cccd",
            "mật khẩu",
        ]
        for keyword in privacy_keywords:
            if keyword in query_lower:
                return False, "privacy_violating"

        # Check query length (too short might be spam)
        if len(query.strip()) < 5:
            return False, "invalid_query"

        # Check query length (too long might be attempting injection)
        if len(query) > 2000:
            return False, "query_too_long"

        # Default: allow query
        return True, None

    def get_rejection_message(self, category: str, language: str = "vi") -> str:

        messages_vi = {
            "harmful": "Xin lỗi, tôi không thể hỗ trợ các yêu cầu có nội dung nguy hiểm hoặc có hại. Nếu bạn đang gặp vấn đề khẩn cấp, vui lòng liên hệ với dịch vụ hỗ trợ tâm lý hoặc y tế địa phương.",
            "inappropriate": "Xin lỗi, câu hỏi này chứa nội dung không phù hợp. Vui lòng đặt câu hỏi khác liên quan đến y tế.",
            "off_topic": "Xin lỗi, câu hỏi này dường như không liên quan đến y tế. Tôi chỉ có thể trả lời các câu hỏi về sức khỏe và y tế.",
            "privacy_violating": "Xin lỗi, tôi không thể cung cấp thông tin cá nhân hoặc hồ sơ y tế riêng tư. Vui lòng liên hệ với cơ sở y tế của bạn để truy cập hồ sơ cá nhân.",
            "medical_advice": "Xin lỗi, tôi không thể đưa ra chẩn đoán y tế cụ thể. Vui lòng tham khảo ý kiến bác sĩ để được tư vấn chính xác.",
            "empty_query": "Vui lòng nhập câu hỏi của bạn.",
            "invalid_query": "Câu hỏi không hợp lệ. Vui lòng đặt câu hỏi rõ ràng hơn.",
            "query_too_long": "Câu hỏi quá dài. Vui lòng rút gọn câu hỏi của bạn.",
        }

        messages_en = {
            "harmful": "I'm sorry, but I cannot assist with requests involving harmful or dangerous content. If you're experiencing an emergency, please contact your local mental health or medical services.",
            "inappropriate": "I'm sorry, but this question contains inappropriate content. Please ask another medical-related question.",
            "off_topic": "I'm sorry, but this question doesn't seem to be related to healthcare. I can only answer health and medical questions.",
            "privacy_violating": "I'm sorry, but I cannot provide personal information or private medical records. Please contact your healthcare provider to access your personal records.",
            "medical_advice": "I'm sorry, but I cannot provide specific medical diagnoses. Please consult a doctor for accurate medical advice.",
            "empty_query": "Please enter your question.",
            "invalid_query": "Invalid query. Please ask a clearer question.",
            "query_too_long": "Query is too long. Please shorten your question.",
        }

        messages = messages_vi if language == "vi" else messages_en
        return messages.get(category) or messages.get("invalid_query", "Invalid query")

    def health_check(self) -> bool:

        try:
            response = self.client.get(
                f"{self.triton_url}/v2/health/ready", timeout=5.0
            )
            if response.status_code == 200:
                logger.info("Qwen3Guard service is healthy")
                return True
            return False
        except Exception as e:
            logger.warning(f"Qwen3Guard health check failed: {e}")
            return False


_guardrails_service_instance = None


def get_guardrails_service() -> Qwen3GuardService:
    global _guardrails_service_instance
    if _guardrails_service_instance is None:
        _guardrails_service_instance = Qwen3GuardService()
    return _guardrails_service_instance
