"""
Qwen3Guard service for content moderation and guardrails.

Implementation following official Qwen3Guard-Gen-0.6B best practices.
Reference: https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B
"""

from typing import Dict, Optional, Tuple
import re
import httpx
from loguru import logger

from ..configs.setup import get_backend_settings
from .model_config import (
    get_guardrails_model,
    get_guardrails_threshold,
)

settings = get_backend_settings()


class Qwen3GuardService:
    """
    Qwen3Guard service following official Qwen3Guard-Gen-0.6B specification.

    Key Features:
    - Three-tiered severity: Safe, Unsafe, Controversial
    - 9 safety categories as per Qwen3Guard policy
    - Output format: "Safety: {label}\nCategories: {categories}\nRefusal: {yes/no}"
    - Supports prompt moderation and response moderation

    Reference: https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B
    """

    # Qwen3Guard official safety categories
    QWEN3GUARD_CATEGORIES = {
        "Violent": "Content providing detailed instructions on violence or weapon manufacture",
        "Non-violent Illegal Acts": "Content guiding non-violent illegal activities (hacking, drugs, stealing)",
        "Sexual Content or Sexual Acts": "Content with explicit sexual imagery or illegal sexual acts",
        "PII": "Unauthorized sharing of personally identifiable information",
        "Suicide & Self-Harm": "Content advocating or detailing methods for self-harm or suicide",
        "Unethical Acts": "Bias, discrimination, hate speech, harassment, misinformation",
        "Politically Sensitive Topics": "False information about government actions or public figures",
        "Copyright Violation": "Unauthorized reproduction of copyrighted materials",
        "Jailbreak": "Attempts to override model's system prompt (input only)",
        "None": "No safety violations detected",
    }

    # Severity levels (Qwen3Guard specification)
    SEVERITY_LEVELS = ["Safe", "Controversial", "Unsafe"]

    def __init__(
        self,
        local_url: str = "http://localhost:8000",
        threshold: Optional[float] = None,
    ):
        """
        Initialize Qwen3Guard service.

        Args:
            local_url: Local FastAPI backend URL
            threshold: Safety threshold (not used in Qwen3Guard, kept for compatibility)
        """
        self.local_url = local_url
        self.threshold = threshold or get_guardrails_threshold()
        self.huggingface_model = get_guardrails_model()

        self.client = httpx.Client(timeout=10.0)

        logger.debug(
            f"Init Qwen3GuardService: Local={local_url}, Model={self.huggingface_model}"
        )

    def validate_query(self, query: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate user input query using Qwen3Guard prompt moderation.

        Qwen3Guard expects:
        - Input: user query
        - Output format: "Safety: {Safe|Unsafe|Controversial}\nCategories: {categories}"

        Returns:
            Tuple[bool, Optional[str], Optional[Dict]]:
                - is_valid: True if query is safe
                - violation_category: First category of violation if any
                - metadata: {severity, categories, details}
        """
        # Check for empty query
        if not query or not query.strip():
            logger.warning("Empty query blocked by guardrails")
            return False, "empty_query", {"reason": "Empty query"}

        # Call Qwen3Guard model via local endpoint
        try:
            is_safe, severity, categories, refusal, details = self._check_with_local(
                query, check_type="input"
            )

            if is_safe or severity == "Safe":
                logger.debug(f"✅ Query passed Qwen3Guard: severity={severity}")
                return (
                    True,
                    None,
                    {
                        "severity": severity,
                        "categories": categories,
                        "details": details,
                    },
                )

            # Query is unsafe or controversial
            violation_category = (
                categories[0] if categories and categories[0] != "None" else "unknown"
            )
            metadata = {
                "severity": severity,
                "categories": categories,
                "details": details,
            }

            logger.warning(
                f"❌ Query BLOCKED by Qwen3Guard: severity={severity}, categories={categories}"
            )
            return False, violation_category, metadata

        except Exception as e:
            logger.error(f"❌ Qwen3Guard validation error: {e}")
            # Fail open - allow query if guardrails service is down
            logger.warning(
                "⚠️  Guardrails service unavailable, ALLOWING query (fail-open)"
            )
            return True, None, {"error": str(e), "failover": True}

    def validate_response(
        self, response: str, query: str, max_retries: int = 2
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate LLM-generated response using Qwen3Guard response moderation.

        Qwen3Guard expects:
        - Input: [{"role": "user", "content": query}, {"role": "assistant", "content": response}]
        - Output format: "Safety: {Safe|Unsafe|Controversial}\nCategories: {categories}\nRefusal: {Yes|No}"

        Args:
            response: The generated response to validate
            query: Original user query (for context)
            max_retries: Maximum retry attempts (for regeneration loop)

        Returns:
            Tuple[bool, Optional[str], Optional[Dict]]:
                - is_valid: True if response is safe
                - violation_category: First category of violation if any
                - metadata: {severity, categories, refusal, retry_feedback, details}
        """
        # Check for empty response
        if not response or not response.strip():
            logger.warning("Empty response blocked by guardrails")
            return (
                False,
                "empty_response",
                {
                    "reason": "Empty response",
                    "retry_feedback": "Generate a non-empty response to the user's query.",
                },
            )

        # Call Qwen3Guard model via local endpoint
        try:
            is_safe, severity, categories, refusal, details = self._check_with_local(
                response, check_type="output", query=query
            )

            # Safe response or proper refusal
            if is_safe or severity == "Safe":
                logger.debug(
                    f"✅ Response passed Qwen3Guard: severity={severity}, refusal={refusal}"
                )
                return (
                    True,
                    None,
                    {
                        "severity": severity,
                        "categories": categories,
                        "refusal": refusal,
                        "details": details,
                    },
                )

            # Response is unsafe or controversial
            violation_category = (
                categories[0] if categories and categories[0] != "None" else "unknown"
            )
            metadata = {
                "severity": severity,
                "categories": categories,
                "refusal": refusal,
                "details": details,
            }

            # Generate feedback for regeneration
            if max_retries > 0:
                feedback = self._generate_regeneration_feedback(
                    violation_category, details, query, response
                )
                metadata["retry_feedback"] = feedback

            logger.warning(
                f"❌ Response BLOCKED by Qwen3Guard: severity={severity}, categories={categories}, refusal={refusal}"
            )
            return False, violation_category, metadata

        except Exception as e:
            logger.error(f"❌ Qwen3Guard response validation error: {e}")
            # Fail open for response validation
            logger.warning(
                "⚠️  Guardrails service unavailable, ALLOWING response (fail-open)"
            )
            return True, None, {"error": str(e), "failover": True}

    def _check_with_local(
        self, text: str, check_type: str = "input", query: Optional[str] = None
    ) -> Tuple[bool, str, list, Optional[str], Dict]:
        """
        Check text safety using local FastAPI endpoint with Qwen3Guard-Gen-0.6B.

        Args:
            text: Text to check (query for input, response for output)
            check_type: "input" (user query) or "output" (LLM response)
            query: Original query (required for output moderation)

        Returns:
            Tuple[is_safe, severity, categories, refusal, details]
            - is_safe: bool (True if severity == "Safe")
            - severity: "Safe" | "Controversial" | "Unsafe"
            - categories: List[str] of violation categories
            - refusal: "Yes" | "No" | None (only for output)
            - details: Dict with raw response and parsed data
        """
        try:
            payload = {"text": text, "check_type": check_type}
            if check_type == "output" and query:
                payload["query"] = query

            response = self.client.post(
                f"{self.local_url}/v1/models/guard",
                json=payload,
                timeout=10.0,
            )

            if response.status_code != 200:
                raise Exception(
                    f"Qwen3Guard failed: {response.status_code} - {response.text}"
                )

            result = response.json()

            # Parse Qwen3Guard output
            # Expected format:
            # Safety: Safe|Unsafe|Controversial
            # Categories: Violent|None|...
            # Refusal: Yes|No (only for output)

            raw_output = result.get("raw_output", "")
            severity = self._parse_severity(raw_output)
            categories = self._parse_categories(raw_output)
            refusal = (
                self._parse_refusal(raw_output) if check_type == "output" else None
            )

            # Determine is_safe based on severity
            is_safe = severity == "Safe"

            details = {
                "raw_output": raw_output,
                "model": self.huggingface_model,
            }

            logger.debug(
                f"Qwen3Guard check: severity={severity}, categories={categories}, "
                f"refusal={refusal}, is_safe={is_safe}"
            )

            return is_safe, severity, categories, refusal, details

        except Exception as e:
            logger.error(f"❌ Qwen3Guard local check failed: {e}")
            raise

    def _parse_severity(self, raw_output: str) -> str:
        """Parse severity level from Qwen3Guard output."""
        match = re.search(
            r"Safety:\s*(Safe|Unsafe|Controversial)", raw_output, re.IGNORECASE
        )
        if match:
            return match.group(1).capitalize()
        return "Safe"  # Default to Safe if parsing fails

    def _parse_categories(self, raw_output: str) -> list:
        """Parse categories from Qwen3Guard output."""
        match = re.search(
            r"Categories?:\s*(.+?)(?:\n|$)", raw_output, re.IGNORECASE | re.DOTALL
        )
        if match:
            categories_str = match.group(1).strip()
            # Split by comma, pipe, or newline
            categories = re.split(r"[,|\n]+", categories_str)
            return [cat.strip() for cat in categories if cat.strip()]
        return ["None"]

    def _parse_refusal(self, raw_output: str) -> Optional[str]:
        """Parse refusal label from Qwen3Guard output (output moderation only)."""
        match = re.search(r"Refusal:\s*(Yes|No)", raw_output, re.IGNORECASE)
        if match:
            return match.group(1).capitalize()
        return None

    def _generate_regeneration_feedback(
        self, category: str, details: Dict, query: str, response: str
    ) -> str:
        """
        Generate feedback for LLM to regenerate a safer response.

        Args:
            category: Violation category from Qwen3Guard
            details: Violation details
            query: Original user query
            response: Blocked response

        Returns:
            Feedback string for LLM regeneration
        """
        # Map Qwen3Guard categories to feedback templates
        feedback_templates = {
            "Violent": (
                "The response contains potentially violent content. "
                "Please revise to remove any references to violence, weapons, or dangerous activities. "
                "Focus on providing safe, supportive information."
            ),
            "Non-violent Illegal Acts": (
                "The response provides guidance on illegal activities. "
                "Please revise to comply with legal standards and avoid suggesting illegal actions."
            ),
            "Sexual Content or Sexual Acts": (
                "The response contains inappropriate sexual content. "
                "Please revise to be professional and avoid any explicit sexual references."
            ),
            "PII": (
                "The response may violate privacy guidelines. "
                "Please revise to avoid requesting or providing specific personal information. "
                "Provide general guidance instead."
            ),
            "Suicide & Self-Harm": (
                "The response contains harmful content related to self-harm. "
                "Please revise to provide supportive, safe information and encourage seeking professional help."
            ),
            "Unethical Acts": (
                "The response contains unethical content (bias, discrimination, hate speech). "
                "Please revise to be respectful, unbiased, and professional."
            ),
            "Politically Sensitive Topics": (
                "The response may contain misinformation about political topics. "
                "Please revise to provide factual, neutral information or acknowledge limitations."
            ),
            "Copyright Violation": (
                "The response may violate copyright. "
                "Please revise to avoid reproducing copyrighted materials verbatim. "
                "Summarize or paraphrase instead."
            ),
        }

        base_feedback = feedback_templates.get(
            category,
            "The response does not meet safety guidelines. Please revise to be safer and more appropriate.",
        )

        # Add specific details if available
        raw_output = details.get("raw_output", "")
        if raw_output:
            base_feedback += f"\n\nDetails: {raw_output[:200]}"

        return base_feedback

    def get_rejection_message(self, category: str, language: str = "vi") -> str:
        """
        Get user-facing rejection message based on violation category.

        Args:
            category: Violation category from Qwen3Guard
            language: Language for message (vi or en)

        Returns:
            User-facing rejection message
        """
        messages_vi = {
            "Violent": "Xin lỗi, tôi không thể trả lời các câu hỏi liên quan đến bạo lực hoặc vũ khí.",
            "Non-violent Illegal Acts": "Xin lỗi, tôi không thể cung cấp hướng dẫn về các hoạt động bất hợp pháp.",
            "Sexual Content or Sexual Acts": "Xin lỗi, tôi không thể trả lời các câu hỏi có nội dung không phù hợp.",
            "PII": "Xin lỗi, tôi không thể chia sẻ hoặc yêu cầu thông tin cá nhân nhạy cảm.",
            "Suicide & Self-Harm": "Tôi rất lo lắng về bạn. Vui lòng liên hệ với chuyên gia tâm lý hoặc đường dây nóng hỗ trợ khủng hoảng.",
            "Unethical Acts": "Xin lỗi, tôi không thể trả lời các câu hỏi có nội dung phân biệt đối xử hoặc kỳ thị.",
            "Politically Sensitive Topics": "Xin lỗi, tôi không thể cung cấp thông tin về các chủ đề chính trị nhạy cảm.",
            "Copyright Violation": "Xin lỗi, tôi không thể cung cấp nội dung vi phạm bản quyền.",
            "Jailbreak": "Xin lỗi, tôi không thể thực hiện yêu cầu của bạn.",
            "empty_query": "Xin vui lòng nhập câu hỏi của bạn.",
        }

        messages_en = {
            "Violent": "I'm sorry, I cannot answer questions related to violence or weapons.",
            "Non-violent Illegal Acts": "I'm sorry, I cannot provide guidance on illegal activities.",
            "Sexual Content or Sexual Acts": "I'm sorry, I cannot answer questions with inappropriate content.",
            "PII": "I'm sorry, I cannot share or request sensitive personal information.",
            "Suicide & Self-Harm": "I'm very concerned about you. Please contact a mental health professional or crisis hotline.",
            "Unethical Acts": "I'm sorry, I cannot answer questions with discriminatory or offensive content.",
            "Politically Sensitive Topics": "I'm sorry, I cannot provide information on politically sensitive topics.",
            "Copyright Violation": "I'm sorry, I cannot provide copyrighted content.",
            "Jailbreak": "I'm sorry, I cannot fulfill your request.",
            "empty_query": "Please enter your question.",
        }

        messages = messages_vi if language == "vi" else messages_en
        default_msg = (
            "Xin lỗi, tôi không thể trả lời câu hỏi này vì lý do an toàn."
            if language == "vi"
            else "I'm sorry, I cannot answer this question for safety reasons."
        )

        return messages.get(category, default_msg)

    def health_check(self) -> bool:
        """Check if Qwen3Guard service is healthy."""
        try:
            response = self.client.get(f"{self.local_url}/v1/ready", timeout=5.0)
            if response.status_code == 200:
                logger.info("✅ Qwen3Guard service is healthy")
                return True
            else:
                logger.warning(
                    f"⚠️  Qwen3Guard health check failed: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"❌ Qwen3Guard health check error: {e}")
            return False


# Singleton instance
_guardrails_service_instance = None


def get_guardrails_service() -> Qwen3GuardService:
    """Get singleton instance of Qwen3Guard service."""
    global _guardrails_service_instance
    if _guardrails_service_instance is None:
        _guardrails_service_instance = Qwen3GuardService()
    return _guardrails_service_instance
