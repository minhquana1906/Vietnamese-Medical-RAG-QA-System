"""Qwen3Guard service for content moderation and guardrails."""

from typing import Dict, List, Optional, Tuple

import httpx
from loguru import logger

from ..configs.setup import get_backend_settings
from .model_config import (
    get_guardrails_model,
    get_guardrails_threshold,
    get_guardrails_triton_name,
    get_triton_http_url,
)

settings = get_backend_settings()


class Qwen3GuardService:
    """
    Qwen3Guard service for input/output validation.

    Validates both user queries (input) and LLM responses (output) for:
    - Harmful content (violence, self-harm)
    - Inappropriate content (sexual, offensive)
    - Off-topic queries (non-medical)
    - Privacy violations (personal data requests)
    - Medical advice without context
    """

    CATEGORIES = {
        "harmful": "Content promoting violence, self-harm, or illegal activities",
        "inappropriate": "Sexual, offensive, or discriminatory content",
        "off_topic": "Non-medical or irrelevant queries",
        "privacy_violating": "Requests for personal medical records or identifiable information",
        "medical_advice": "Requests for specific medical diagnoses without proper context",
        "hallucination": "Response contains unverified or fabricated medical information",
        "unsafe_advice": "Response provides potentially harmful medical advice",
    }

    def __init__(
        self,
        triton_url: Optional[str] = None,
        model_name: Optional[str] = None,
        threshold: Optional[float] = None,
    ):
        # Load from config
        self.triton_url = triton_url or get_triton_http_url()
        self.model_name = model_name or get_guardrails_triton_name()
        self.threshold = threshold or get_guardrails_threshold()
        self.huggingface_model = get_guardrails_model()  # For logging

        self.client = httpx.Client(timeout=10.0)

        logger.info(
            f"Initialized Qwen3GuardService: "
            f"HF={self.huggingface_model}, Triton={self.model_name}, "
            f"Threshold={self.threshold}"
        )

    def validate_query(self, query: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate user input query.

        Returns:
            Tuple[bool, Optional[str], Optional[Dict]]:
                - is_valid: True if query is safe
                - violation_category: Category of violation if any
                - metadata: Additional info (confidence, reason, etc.)
        """
        # Check for empty query
        if not query or not query.strip():
            logger.warning("Empty query blocked by guardrails")
            return False, "empty_query", {"message": "Query cannot be empty"}

        # Call Qwen3Guard model via Triton
        try:
            is_safe, category, confidence, details = self._check_with_triton(
                query, check_type="input"
            )

            if is_safe:
                logger.info(
                    f"✅ Input query passed guardrails (confidence={confidence:.3f}): {query[:80]}..."
                )
                return True, None, {"confidence": confidence, "details": details}
            else:
                logger.warning(
                    f"❌ Input query BLOCKED by guardrails: category={category}, "
                    f"confidence={confidence:.3f}, query={query[:80]}..."
                )
                return (
                    False,
                    category,
                    {
                        "confidence": confidence,
                        "category_description": self.CATEGORIES.get(
                            category or "unknown", "Unknown violation"
                        ),
                        "details": details,
                    },
                )
        except Exception as e:
            logger.error(f"❌ Guardrails check failed (input): {e}")
            # Fail open - allow query if guardrails service is down
            logger.warning(
                "⚠️  Guardrails service unavailable, ALLOWING query (fail-open)"
            )
            return True, None, {"error": str(e), "failover": True}

    def validate_response(
        self, response: str, query: str, max_retries: int = 2
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate LLM-generated response.

        Args:
            response: The generated response to validate
            query: Original user query (for context)
            max_retries: Maximum retry attempts (for regeneration loop)

        Returns:
            Tuple[bool, Optional[str], Optional[Dict]]:
                - is_valid: True if response is safe
                - violation_category: Category of violation if any
                - metadata: Additional info (confidence, feedback for retry, etc.)
        """
        # Check for empty response
        if not response or not response.strip():
            logger.warning("Empty response blocked by guardrails")
            return (
                False,
                "empty_response",
                {
                    "message": "Response is empty",
                    "feedback": "Please provide a meaningful response to the user's query.",
                },
            )

        # Call Qwen3Guard model via Triton
        try:
            # Combine query + response for context-aware validation
            combined_text = f"Query: {query}\n\nResponse: {response}"
            is_safe, category, confidence, details = self._check_with_triton(
                combined_text, check_type="output"
            )

            if is_safe:
                logger.info(
                    f"✅ Output response passed guardrails (confidence={confidence:.3f}): "
                    f"{response[:80]}..."
                )
                return True, None, {"confidence": confidence, "details": details}
            else:
                # Generate feedback for LLM to regenerate
                feedback = self._generate_regeneration_feedback(
                    category, details, query, response
                )

                logger.warning(
                    f"❌ Output response BLOCKED by guardrails: category={category}, "
                    f"confidence={confidence:.3f}, response={response[:80]}..."
                )
                logger.info(f"📝 Regeneration feedback: {feedback}")

                return (
                    False,
                    category,
                    {
                        "confidence": confidence,
                        "category_description": self.CATEGORIES.get(
                            category or "unknown", "Unknown violation"
                        ),
                        "details": details,
                        "feedback": feedback,  # For LLM regeneration
                        "original_response": response[:200],  # Keep truncated version
                    },
                )
        except Exception as e:
            logger.error(f"❌ Guardrails check failed (output): {e}")
            # Fail closed for output - reject if can't validate
            logger.warning(
                "⚠️  Guardrails service unavailable, REJECTING response (fail-closed)"
            )
            return (
                False,
                "guardrails_error",
                {
                    "error": str(e),
                    "failover": True,
                    "feedback": "Guardrails validation failed. Please provide a safer, more factual response.",
                },
            )

    def _check_with_triton(
        self, text: str, check_type: str = "input"
    ) -> Tuple[bool, Optional[str], float, Dict]:
        """
        Check text safety using Triton-served Qwen3Guard model.

        Args:
            text: Text to check
            check_type: "input" (user query) or "output" (LLM response)

        Returns:
            Tuple[is_safe, category, confidence, details]
        """
        try:
            payload = {
                "inputs": [
                    {
                        "name": "input_text",
                        "shape": [1],
                        "datatype": "BYTES",
                        "data": [text],
                    },
                    {
                        "name": "check_type",
                        "shape": [1],
                        "datatype": "BYTES",
                        "data": [check_type],
                    },
                ]
            }

            response = self.client.post(
                f"{self.triton_url}/v2/models/{self.model_name}/infer",
                json=payload,
                timeout=10.0,
            )

            if response.status_code == 200:
                result = response.json()
                outputs = result["outputs"]

                # Parse Triton outputs
                # Expected format: [safety_score, category, details]
                safety_score = float(
                    outputs[0]["data"][0]
                )  # 0.0 (unsafe) to 1.0 (safe)
                is_safe = safety_score >= self.threshold

                category = outputs[1]["data"][0] if len(outputs) > 1 else None
                details_json = outputs[2]["data"][0] if len(outputs) > 2 else "{}"

                # Parse details JSON
                import json

                try:
                    details = json.loads(details_json)
                except:
                    details = {"raw": details_json}

                logger.debug(
                    f"Qwen3Guard ({check_type}): safety_score={safety_score:.3f}, "
                    f"threshold={self.threshold}, is_safe={is_safe}, category={category}"
                )

                return is_safe, category, safety_score, details
            else:
                logger.error(
                    f"Triton guardrails inference failed: {response.status_code} - {response.text}"
                )
                raise Exception(f"Triton returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error calling Triton for guardrails ({check_type}): {e}")
            raise

    def _generate_regeneration_feedback(
        self, category: str, details: Dict, query: str, response: str
    ) -> str:
        """
        Generate feedback for LLM to regenerate a safer response.

        Args:
            category: Violation category
            details: Violation details from Qwen3Guard
            query: Original user query
            response: Blocked response

        Returns:
            Feedback string for LLM
        """
        feedback_templates = {
            "harmful": (
                "The response contains potentially harmful content. "
                "Please revise to remove any references to violence, self-harm, or dangerous activities. "
                "Focus on providing safe, supportive information."
            ),
            "inappropriate": (
                "The response contains inappropriate content. "
                "Please revise to be professional and respectful. "
                "Avoid any sexual, offensive, or discriminatory language."
            ),
            "hallucination": (
                "The response may contain unverified medical information. "
                "Please revise to include ONLY information that can be verified from the provided context. "
                "If unsure, acknowledge limitations and suggest consulting a healthcare professional."
            ),
            "unsafe_advice": (
                "The response provides potentially unsafe medical advice. "
                "Please revise to be more cautious. Add appropriate disclaimers and "
                "recommend consulting a qualified healthcare professional for specific medical concerns."
            ),
            "off_topic": (
                "The response deviates from the medical topic. "
                "Please revise to focus specifically on the health-related aspects of the query."
            ),
            "privacy_violating": (
                "The response may violate privacy guidelines. "
                "Please revise to avoid requesting or providing specific personal medical information. "
                "Provide general guidance instead."
            ),
        }

        base_feedback = feedback_templates.get(
            category,
            "The response does not meet safety guidelines. Please revise to be safer and more appropriate.",
        )

        # Add specific details if available
        if details and "reason" in details:
            base_feedback += f"\n\nSpecific issue: {details['reason']}"

        return base_feedback

    def _simple_rule_based_check(self, query: str) -> Tuple[bool, Optional[str]]:
        query_lower = query.lower()

        # Check for explicit harmful content keywords
        harmful_keywords = [
            "suicide",
            "self-harm",
            "kill myself",
            "tự tử",
            "tự sát",
            "giết người",
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
