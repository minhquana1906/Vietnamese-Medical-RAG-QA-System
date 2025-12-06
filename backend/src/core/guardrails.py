"""
Qwen3Guard service for content moderation and guardrails.

Implementation following official Qwen3Guard-Gen-0.6B best practices.
Reference: https://huggingface.co/Qwen/Qwen3Guard-Gen-0.6B
"""

import re
from typing import Dict, Optional, Tuple

import httpx
from loguru import logger

from ..configs.setup import get_backend_settings
from .model_config import get_guardrails_model, get_guardrails_threshold

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
        local_url: Optional[str] = None,
        threshold: Optional[float] = None,
    ):
        """Initialize Qwen3Guard service."""
        if settings.qwen3_models_enabled:
            self.local_url = local_url or settings.qwen3_models_url
        else:
            self.local_url = local_url or settings.backend_api_url

        self.threshold = threshold or get_guardrails_threshold()
        self.huggingface_model = get_guardrails_model()
        self.client = httpx.Client(timeout=180.0)

    def validate_query(self, query: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate user input query using Qwen3Guard prompt moderation.

        Returns:
            Tuple[bool, Optional[str], Optional[Dict]]:
                - is_valid: True if query is safe
                - violation_category: First category of violation if any
                - metadata: {severity, categories, details}
        """
        if not query or not query.strip():
            return False, "empty_query", {"reason": "Empty query"}

        try:
            is_safe, severity, categories, refusal, details = self._check_with_local(
                query, check_type="input"
            )

            if is_safe or severity == "Safe":
                return (
                    True,
                    None,
                    {
                        "severity": severity,
                        "categories": categories,
                        "details": details,
                    },
                )

            violation_category = (
                categories[0] if categories and categories[0] != "None" else "unknown"
            )
            metadata = {
                "severity": severity,
                "categories": categories,
                "details": details,
            }

            return False, violation_category, metadata

        except Exception as e:
            logger.warning(f"[GUARD] Service unavailable, fail-open: {e}")
            return True, None, {"error": str(e), "failover": True}

    def validate_response(
        self, response: str, query: str, max_retries: int = 2
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate LLM-generated response using Qwen3Guard response moderation.

        Returns:
            Tuple[bool, Optional[str], Optional[Dict]]:
                - is_valid: True if response is safe
                - violation_category: First category of violation if any
                - metadata: {severity, categories, refusal, retry_feedback, details}
        """
        if not response or not response.strip():
            return (
                False,
                "empty_response",
                {
                    "reason": "Empty response",
                    "retry_feedback": "Generate a non-empty response to the user's query.",
                },
            )

        try:
            is_safe, severity, categories, refusal, details = self._check_with_local(
                response, check_type="output", query=query
            )

            if is_safe or severity == "Safe":
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

            violation_category = (
                categories[0] if categories and categories[0] != "None" else "unknown"
            )
            metadata = {
                "severity": severity,
                "categories": categories,
                "refusal": refusal,
                "details": details,
            }

            if max_retries > 0:
                feedback = self._generate_regeneration_feedback(
                    violation_category, details, query, response
                )
                metadata["retry_feedback"] = feedback

            return False, violation_category, metadata

        except Exception as e:
            logger.warning(f"[GUARD] Service unavailable, fail-open: {e}")
            return True, None, {"error": str(e), "failover": True}

    def _check_with_local(
        self,
        text: str,
        check_type: str = "input",
        query: Optional[str] = None,
        max_retries: int = 2,
    ) -> Tuple[bool, str, list, Optional[str], Dict]:
        """Check text safety using local FastAPI endpoint with Qwen3Guard-Gen-0.6B with retry logic."""
        import time

        payload = {"text": text, "check_type": check_type}
        if check_type == "output" and query:
            payload["query"] = query

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = self.client.post(
                    f"{self.local_url}/v1/models/guard",
                    json=payload,
                    timeout=30.0,  # Increased for load testing
                )

                if response.status_code != 200:
                    raise Exception(
                        f"Qwen3Guard failed: {response.status_code} - {response.text}"
                    )

                result = response.json()
                raw_output = result.get("raw_output", "")
                severity = self._parse_severity(raw_output)
                categories = self._parse_categories(raw_output)
                refusal = (
                    self._parse_refusal(raw_output) if check_type == "output" else None
                )

                is_safe = severity == "Safe"
                details = {
                    "raw_output": raw_output,
                    "model": self.huggingface_model,
                    "attempt": attempt + 1,
                }

                return is_safe, severity, categories, refusal, details

            except httpx.TimeoutException as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = (2**attempt) * 0.5  # 0.5s, 1s, 2s
                    logger.warning(
                        f"[GUARD] Timeout on attempt {attempt + 1}/{max_retries + 1}, retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[GUARD] Check failed after {max_retries + 1} attempts: {e}"
                    )
                    raise
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = (2**attempt) * 0.5
                    logger.warning(
                        f"[GUARD] Error on attempt {attempt + 1}/{max_retries + 1}, retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"[GUARD] Check failed after {max_retries + 1} attempts: {e}"
                    )
                    raise

    def _parse_severity(self, raw_output: str) -> str:
        """Parse severity level from Qwen3Guard output."""
        match = re.search(
            r"Safety:\s*(Safe|Unsafe|Controversial)", raw_output, re.IGNORECASE
        )
        if match:
            return match.group(1).capitalize()
        return "Safe"

    def _parse_categories(self, raw_output: str) -> list:
        """Parse categories from Qwen3Guard output."""
        match = re.search(
            r"Categories?:\s*(.+?)(?:\n|$)", raw_output, re.IGNORECASE | re.DOTALL
        )
        if match:
            categories_str = match.group(1).strip()
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
        """Generate feedback for LLM to regenerate a safer response."""
        feedback_templates = {
            "Violent": (
                "The response contains potentially violent content. "
                "Please revise to remove any references to violence, weapons, or dangerous activities."
            ),
            "Non-violent Illegal Acts": (
                "The response provides guidance on illegal activities. "
                "Please revise to comply with legal standards."
            ),
            "Sexual Content or Sexual Acts": (
                "The response contains inappropriate sexual content. "
                "Please revise to be professional."
            ),
            "PII": (
                "The response may violate privacy guidelines. "
                "Please revise to avoid personal information."
            ),
            "Suicide & Self-Harm": (
                "The response contains harmful content related to self-harm. "
                "Please provide supportive, safe information."
            ),
            "Unethical Acts": (
                "The response contains unethical content. "
                "Please revise to be respectful and professional."
            ),
            "Politically Sensitive Topics": (
                "The response may contain misinformation. "
                "Please provide factual, neutral information."
            ),
            "Copyright Violation": (
                "The response may violate copyright. "
                "Please summarize or paraphrase instead."
            ),
        }

        return feedback_templates.get(
            category,
            "The response does not meet safety guidelines. Please revise to be safer.",
        )

    def get_rejection_message(self, category: str, language: str = "vi") -> str:
        """Get user-facing rejection message based on violation category."""
        messages_vi = {
            "Violent": "Là một trợ lý y tế, tôi ưu tiên sự an toàn và sức khỏe con người. Tôi xin từ chối thảo luận các nội dung liên quan đến bạo lực, gây thương tích hoặc sử dụng vũ khí.",
            "Non-violent Illegal Acts": "Tôi hoạt động dựa trên các quy định pháp luật và đạo đức y khoa. Tôi không thể hỗ trợ hoặc hướng dẫn các hành vi trái pháp luật dưới bất kỳ hình thức nào.",
            "Sexual Content or Sexual Acts": "Tôi có thể giải đáp các vấn đề về sức khỏe sinh sản dưới góc độ y học. Tuy nhiên, tôi xin từ chối phản hồi các nội dung mang tính khiêu dâm hoặc không phù hợp chuẩn mực.",
            "PII": "Để bảo vệ quyền riêng tư và tuân thủ bảo mật dữ liệu y tế, tôi không được phép thu thập, chia sẻ hoặc truy xuất thông tin định danh cá nhân cụ thể.",
            "Suicide & Self-Harm": "Nếu bạn hoặc ai đó đang gặp nguy hiểm, xin hãy gọi ngay số cấp cứu (115) hoặc đến cơ sở y tế gần nhất. Tôi là AI và không thể thay thế sự can thiệp khẩn cấp của bác sĩ.",
            "Unethical Acts": "Nội dung này không phù hợp với chuẩn mực đạo đức y khoa và cộng đồng. Tôi xin phép không tham gia thảo luận về các vấn đề mang tính kỳ thị hoặc phi đạo đức.",
            "Politically Sensitive Topics": "Chức năng của tôi là hỗ trợ thông tin y tế và sức khỏe. Tôi xin phép không bình luận về các chủ đề chính trị hoặc các vấn đề xã hội nhạy cảm nằm ngoài phạm vi chuyên môn.",
            "Copyright Violation": "Tôi không thể cung cấp trực tiếp tài liệu này do quy định về bản quyền. Tuy nhiên, tôi có thể giải thích các khái niệm y khoa liên quan nếu bạn cần.",
            "Jailbreak": "Tôi là trợ lý AI chuyên về y tế với các thiết lập an toàn nghiêm ngặt. Tôi không thể thực hiện các yêu cầu nhằm thay đổi vai trò hoặc vượt qua các rào cản bảo mật này.",
            "empty_query": "Tôi chưa nhận được nội dung từ bạn. Bạn đang quan tâm đến vấn đề sức khỏe hoặc triệu chứng nào không?",
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
            return response.status_code == 200
        except Exception:
            return False


# Singleton instance
_guardrails_service_instance = None


def get_guardrails_service() -> Qwen3GuardService:
    """Get singleton instance of Qwen3Guard service."""
    global _guardrails_service_instance
    if _guardrails_service_instance is None:
        _guardrails_service_instance = Qwen3GuardService()
    return _guardrails_service_instance
