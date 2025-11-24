"""
Text-to-Speech (TTS) Service
Supports ElevenLabs API for high-quality voice synthesis
"""

import hashlib
import os
from typing import Optional

import httpx
from loguru import logger

from ..core.cache import get_redis_client

# Cache configuration
TTS_CACHE_TTL = 86400  # 24 hours cache for generated audio

# ElevenLabs API configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "1rqNHUqUbBGpY3OyzPMI")


class TtsService:
    """
    TTS service using ElevenLabs API
    Provides high-quality voice synthesis with caching
    """

    def __init__(
        self,
        api_key: str = ELEVENLABS_API_KEY,
        voice_id: str = DEFAULT_VOICE_ID,
    ):
        """
        Initialize TTS service

        Args:
            api_key: ElevenLabs API key
            voice_id: Default voice ID to use
        """
        self.api_key = api_key
        self.voice_id = voice_id
        self.redis_client = get_redis_client()

        if not self.api_key:
            logger.warning("ElevenLabs API key not configured")

        logger.info(f"Initializing TTS service: voice_id={voice_id}")

    def _get_text_hash(self, text: str, voice_id: str) -> str:
        """
        Generate hash of text + voice_id for caching

        Args:
            text: Text to synthesize
            voice_id: Voice identifier

        Returns:
            SHA256 hash of text + voice_id
        """
        content = f"{text}:{voice_id}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _get_cached_audio(self, text_hash: str) -> Optional[bytes]:
        """
        Get cached audio from Redis

        Args:
            text_hash: Hash of text + voice_id

        Returns:
            Cached audio data or None
        """
        if not self.redis_client or not text_hash:
            return None

        try:
            cache_key = f"tts:audio:{text_hash}"
            cached = self.redis_client.get(cache_key)
            if cached:
                logger.info(f"TTS cache hit: {text_hash[:16]}...")
                return cached
            return None
        except Exception as e:
            logger.error(f"Failed to get cached audio: {e}")
            return None

    def _cache_audio(self, text_hash: str, audio_data: bytes):
        """
        Cache audio to Redis

        Args:
            text_hash: Hash of text + voice_id
            audio_data: Generated audio bytes
        """
        if not self.redis_client or not text_hash:
            return

        try:
            cache_key = f"tts:audio:{text_hash}"
            self.redis_client.setex(cache_key, TTS_CACHE_TTL, audio_data)
            logger.info(
                f"TTS audio cached: {text_hash[:16]}..., size={len(audio_data)}"
            )
        except Exception as e:
            logger.error(f"Failed to cache audio: {e}")

    async def synthesize_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        speed: float = 1.0,
    ) -> bytes:
        """
        Synthesize speech from text using ElevenLabs API

        Args:
            text: Text to convert to speech
            voice_id: Voice identifier (uses default if None)
            model_id: ElevenLabs model ID
            stability: Voice stability (0.0-1.0)
            similarity_boost: Clarity/similarity boost (0.0-1.0)
            speed: Speech speed multiplier (0.5-2.0)

        Returns:
            bytes: Audio data in MP3 format

        Raises:
            Exception: If API call fails or API key not configured
        """
        if not self.api_key:
            raise Exception("ElevenLabs API key not configured")

        # Use default voice if not specified
        voice_id = voice_id or self.voice_id

        # Check cache first
        text_hash = self._get_text_hash(text, voice_id)
        cached_audio = self._get_cached_audio(text_hash)
        if cached_audio:
            return cached_audio

        try:
            logger.info(
                f"Synthesizing speech: text_length={len(text)}, voice_id={voice_id}"
            )

            # Prepare API request
            url = f"{ELEVENLABS_API_URL}/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key,
            }
            payload = {
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "speed": speed,
                },
            }

            # Call ElevenLabs API
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                audio_data = response.content
                logger.info(
                    f"TTS synthesis complete: audio_size={len(audio_data)} bytes"
                )

                # Cache the audio
                if text_hash:
                    self._cache_audio(text_hash, audio_data)

                return audio_data

        except httpx.HTTPStatusError as e:
            logger.error(
                f"ElevenLabs API error: {e.response.status_code} - {e.response.text}"
            )
            raise Exception(f"TTS API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise


# Global TTS service instance
_tts_service: Optional[TtsService] = None


def get_tts_service() -> TtsService:
    """Get or create global TTS service instance"""
    global _tts_service
    if _tts_service is None:
        _tts_service = TtsService()
    return _tts_service


def initialize_tts_service(api_key: str = None, voice_id: str = None):
    """
    Initialize TTS service with custom configuration

    Args:
        api_key: ElevenLabs API key
        voice_id: Default voice ID
    """
    global _tts_service
    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key
    if voice_id:
        kwargs["voice_id"] = voice_id

    _tts_service = TtsService(**kwargs)
    logger.info("TTS service initialized")
