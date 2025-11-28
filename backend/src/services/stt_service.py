"""
Speech-to-Text (STT) Service - Routes to GPU service
Provides audio transcription with caching for Vietnamese Medical RAG system
"""

import hashlib
import os
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from ..core.cache import get_redis_client

# Cache configuration
STT_CACHE_TTL = 3600  # 1 hour cache for transcripts

# GPU service configuration
QWEN3_MODELS_ENABLED = os.getenv("QWEN3_MODELS_ENABLED", "true").lower() == "true"
QWEN3_SERVICE_URL = os.getenv("QWEN3_SERVICE_URL", "http://extra_models:8002")


class SttService:
    """
    STT service that routes to GPU service or uses local fallback
    Automatically routes to GPU service if available
    """

    def __init__(
        self,
        model_name: str = "turbo",
        device: str = "cuda",
        compute_type: str = "float16",
    ):
        """
        Initialize STT service

        Args:
            model_name: Whisper model (ignored if using GPU service)
            device: Device for inference (ignored if using GPU service)
            compute_type: Computation type (ignored if using GPU service)
        """
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.use_gpu_service = QWEN3_MODELS_ENABLED
        self.redis_client = get_redis_client()

        if self.use_gpu_service:
            logger.info(f"STT service: Using GPU service at {QWEN3_SERVICE_URL}")
        else:
            logger.info(
                f"STT service: GPU service disabled, would use local model={model_name}"
            )

    def load_model(self):
        """Load model - no-op if using GPU service"""
        if self.use_gpu_service:
            logger.info("STT: GPU service handles model loading")
            return

        logger.warning(
            "STT: GPU service disabled. Local STT not implemented in this version."
        )
        logger.warning("STT: Enable QWEN3_MODELS_ENABLED to use GPU STT service.")

    def _get_audio_hash(self, audio_path: str) -> str:
        """
        Generate hash of audio file for caching

        Args:
            audio_path: Path to audio file

        Returns:
            SHA256 hash of audio file content
        """
        try:
            with open(audio_path, "rb") as f:
                audio_data = f.read()
                return hashlib.sha256(audio_data).hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash audio file: {e}")
            return ""

    def _get_cached_transcript(self, audio_hash: str) -> Optional[str]:
        """
        Get cached transcript from Redis

        Args:
            audio_hash: Hash of audio file

        Returns:
            Cached transcript or None
        """
        if not self.redis_client or not audio_hash:
            return None

        try:
            cache_key = f"stt:transcript:{audio_hash}"
            cached = self.redis_client.get(cache_key)
            if cached:
                logger.info(f"STT cache hit: {audio_hash[:16]}...")
                return cached.decode("utf-8")
            return None
        except Exception as e:
            logger.error(f"Failed to get cached transcript: {e}")
            return None

    def _cache_transcript(self, audio_hash: str, transcript: str):
        """
        Cache transcript to Redis

        Args:
            audio_hash: Hash of audio file
            transcript: Transcribed text
        """
        if not self.redis_client or not audio_hash:
            return

        try:
            cache_key = f"stt:transcript:{audio_hash}"
            self.redis_client.setex(
                cache_key, STT_CACHE_TTL, transcript.encode("utf-8")
            )
            logger.info(f"STT transcript cached: {audio_hash[:16]}...")
        except Exception as e:
            logger.error(f"Failed to cache transcript: {e}")

    def transcribe_audio(
        self,
        audio_path: str,
        language: str = "vi",
        beam_size: int = 5,
        vad_filter: bool = True,
        batch_size: int = 16,
    ) -> dict:
        """
        Transcribe audio file to text
        Routes to GPU service if enabled, otherwise raises error

        Args:
            audio_path: Path to audio file (WAV, MP3, OGG, etc.)
            language: Language code (default: "vi" for Vietnamese)
            beam_size: Beam size for decoding (ignored for GPU service)
            vad_filter: Enable voice activity detection (ignored for GPU service)
            batch_size: Batch size for GPU inference (default: 16)

        Returns:
            dict with keys:
                - text: Transcribed text
                - language: Detected/specified language
                - duration: Audio duration in seconds
                - segments: List of segments with timestamps (optional)
                - cached: Whether result from cache
        """
        if not self.use_gpu_service:
            raise RuntimeError(
                "STT GPU service not enabled. Set QWEN3_MODELS_ENABLED=true"
            )

        # Check if audio file exists
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Check cache first (backend cache, GPU service has its own cache too)
        audio_hash = self._get_audio_hash(audio_path)
        cached_transcript = self._get_cached_transcript(audio_hash)
        if cached_transcript:
            return {
                "text": cached_transcript,
                "language": language,
                "duration": 0.0,
                "cached": True,
            }

        try:
            logger.info(f"Calling GPU STT service: {audio_path}, language={language}")

            # Call GPU service
            with httpx.Client(timeout=60.0) as client:
                with open(audio_path, "rb") as f:
                    files = {"file": (audio_file.name, f, "audio/mpeg")}
                    data = {
                        "language": language,
                        "batch_size": batch_size,
                    }

                    response = client.post(
                        f"{QWEN3_SERVICE_URL}/v1/models/stt",
                        files=files,
                        data=data,
                    )
                    response.raise_for_status()

            result = response.json()
            full_text = result["text"]

            logger.info(
                f"STT GPU service complete: length={len(full_text)}, cached={result.get('cached', False)}"
            )

            # Cache the transcript in backend Redis
            if audio_hash and not result.get("cached", False):
                self._cache_transcript(audio_hash, full_text)

            return {
                "text": full_text,
                "language": result["language"],
                "duration": result["duration"],
                "segments": result.get("segments", []),
                "cached": result.get("cached", False),
            }

        except httpx.RemoteProtocolError as e:
            logger.error(f"GPU STT service connection error: {e}")
            logger.error(
                "Possible causes: GPU service restarting, crashed, or overloaded"
            )
            raise Exception(
                "STT service không khả dụng. Vui lòng thử lại sau vài giây. "
                "(GPU service might be restarting or loading models)"
            )
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to GPU STT service: {e}")
            raise Exception(
                "Không thể kết nối STT service. Vui lòng kiểm tra GPU service đã khởi động chưa."
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"GPU STT service HTTP error: {e.response.status_code}")
            error_detail = e.response.json() if e.response.content else str(e)
            raise Exception(
                f"STT service error: {e.response.status_code} - {error_detail}"
            )
        except httpx.TimeoutException as e:
            logger.error(f"STT request timeout: {e}")
            raise Exception(
                "STT xử lý quá lâu. Vui lòng thử lại với file audio ngắn hơn."
            )
        except Exception as e:
            logger.error(f"STT transcription failed: {e}", exc_info=True)
            raise


# Global STT service instance
_stt_service: Optional[SttService] = None


def get_stt_service() -> SttService:
    """Get or create global STT service instance"""
    global _stt_service
    if _stt_service is None:
        # Configuration will be loaded from models.yaml
        _stt_service = SttService()
    return _stt_service


def initialize_stt_service(
    model_name: str = "turbo",
    device: str = "cuda",
    compute_type: str = "float16",
):
    """
    Initialize STT service with custom configuration

    Args:
        model_name: Whisper model
        device: Device for inference
        compute_type: Computation type
    """
    global _stt_service
    _stt_service = SttService(
        model_name=model_name, device=device, compute_type=compute_type
    )
    _stt_service.load_model()
    logger.info("STT service initialized")
