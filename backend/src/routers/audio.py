"""Audio/Speech Endpoints (STT, TTS, Audio RAG)"""

import hashlib
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger
from sqlalchemy.orm import Session

from ..schemas.schema import SttResponse, TtsRequest, AudioRagResponse
from ..services.stt_service import SttService
from ..services.tts_service import TtsService
from ..services.rag_service import handle_speech_rag_query
from ..database import get_db_session
from ..configs.setup import get_backend_settings

settings = get_backend_settings()

router = APIRouter(prefix="/v1", tags=["Audio & Speech"])

# Import metrics from centralized module
from ..core.metrics import (
    model_inference_duration_seconds,
    voice_request_duration_seconds,
    audio_rag_stage_duration_seconds,
    voice_request_errors_total,
)

# Audio storage directory
AUDIO_DIR = Path("/tmp/audio")
AUDIO_DIR.mkdir(exist_ok=True)


@router.post("/models/stt", response_model=SttResponse)
async def speech_to_text(
    file: UploadFile = File(...),
    language: str = Form("vi"),
):
    """
    Speech-to-Text endpoint: Transcribe audio to text

    Routes to GPU service (Whisper-turbo with batch inference)

    Accepts audio files in various formats (WAV, MP3, OGG, Opus, etc.)
    Returns transcribed text with metadata
    """
    start_time = time.time()
    try:
        # Save uploaded file
        audio_path = (
            AUDIO_DIR
            / f"{hashlib.md5(os.urandom(16)).hexdigest()}.{file.filename.split('.')[-1]}"
        )
        with open(audio_path, "wb") as f:
            f.write(await file.read())

        logger.info(
            f"Received audio file: {file.filename} ({audio_path.stat().st_size} bytes)"
        )

        # Transcribe using STT service (routes to GPU service)
        stt_service = SttService()
        result_dict = stt_service.transcribe_audio(str(audio_path), language=language)

        duration = time.time() - start_time
        model_inference_duration_seconds.labels(
            model_type="stt", model_name="whisper-turbo"
        ).observe(duration)

        # Cleanup
        audio_path.unlink(missing_ok=True)

        # Convert dict to SttResponse
        result = SttResponse(
            text=result_dict["text"],
            language=result_dict["language"],
            duration=result_dict["duration"],
            cached=result_dict.get("cached", False),
        )

        logger.info(f"✅ Transcribed audio in {duration:.3f}s: '{result.text[:50]}...'")

        return result

    except Exception as e:
        logger.error(f"STT failed: {e}")
        voice_request_errors_total.labels(
            endpoint="stt",
            error_type=type(e).__name__
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        voice_request_duration_seconds.labels(endpoint="stt").observe(
            time.time() - start_time
        )


@router.post("/models/tts")
async def text_to_speech(request: TtsRequest):
    """
    Text-to-Speech endpoint: Synthesize speech from text

    Uses ElevenLabs API for high-quality multilingual TTS

    Returns audio file in MP3 format
    """
    start_time = time.time()
    try:
        # Synthesize using TTS service (ElevenLabs API)
        tts_service = TtsService()
        audio_bytes = await tts_service.synthesize_speech(
            text=request.text,
            voice_id=request.voice_id or settings.elevenlabs_voice_id,
            model_id=request.model_id or settings.elevenlabs_model_id,
            stability=(
                request.stability
                if request.stability is not None
                else settings.elevenlabs_stability
            ),
            similarity_boost=(
                request.similarity_boost
                if request.similarity_boost is not None
                else settings.elevenlabs_similarity_boost
            ),
            speed=(
                request.speed
                if request.speed is not None
                else settings.elevenlabs_speed
            ),
        )

        duration = time.time() - start_time
        model_inference_duration_seconds.labels(
            model_type="tts", model_name="elevenlabs"
        ).observe(duration)

        logger.info(
            f"✅ Synthesized speech in {duration:.3f}s: '{request.text[:50]}...'"
        )

        return StreamingResponse(
            iter([audio_bytes]),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "attachment; filename=speech.mp3",
                "Content-Length": str(len(audio_bytes)),
            },
        )

    except Exception as e:
        logger.error(f"TTS failed: {e}")
        voice_request_errors_total.labels(
            endpoint="tts",
            error_type=type(e).__name__
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        voice_request_duration_seconds.labels(endpoint="tts").observe(
            time.time() - start_time
        )


@router.post("/rag/audio", response_model=AudioRagResponse)
def audio_rag_query(
    file: UploadFile = File(...),
    user_identifier: str = Form(...),
    thread_id: str = Form(...),
    language: str = Form("vi"),
    voice_id: Optional[str] = Form(None),
    db: Session = Depends(get_db_session),
):
    """
    Combined Speech-to-Speech RAG endpoint

    Pipeline: Audio input → STT → RAG → TTS → Audio output
    Returns both text response and audio file URL
    """
    request_start = time.time()

    try:
        # Step 1: Speech-to-Text
        logger.info("Step 1/3: Transcribing audio...")
        stt_start = time.time()

        # Save uploaded file
        audio_path = (
            AUDIO_DIR
            / f"{hashlib.md5(os.urandom(16)).hexdigest()}.{file.filename.split('.')[-1]}"
        )
        with open(audio_path, "wb") as f:
            f.write(file.file.read())  # Sync read for sync endpoint

        # Transcribe
        stt_service = SttService()
        stt_result_dict = stt_service.transcribe_audio(
            str(audio_path), language=language
        )
        transcript = stt_result_dict["text"]  # Access dict properly

        stt_duration = time.time() - stt_start
        audio_rag_stage_duration_seconds.labels(stage="stt").observe(stt_duration)
        logger.info(f"✅ STT completed in {stt_duration:.3f}s: '{transcript[:50]}...'")

        # Cleanup audio
        audio_path.unlink(missing_ok=True)

        # Step 2: RAG Query (using Speech-optimized prompt)
        logger.info("Step 2/3: Processing Speech RAG query...")
        rag_start = time.time()

        # Call Speech RAG service with DB session (uses SPEECH_RAG_SYSTEM_PROMPT)
        response_text, sources = handle_speech_rag_query(
            db=db,
            user_identifier=user_identifier,
            thread_id=thread_id,
            query=transcript,
        )

        rag_duration = time.time() - rag_start
        audio_rag_stage_duration_seconds.labels(stage="rag").observe(rag_duration)
        logger.info(f"✅ Speech RAG completed in {rag_duration:.3f}s")

        # Step 3: Text-to-Speech
        logger.info("Step 3/3: Synthesizing speech...")
        tts_start = time.time()

        tts_service = TtsService()
        # TTS service synthesize_speech is async - we need to handle it properly
        import asyncio

        audio_bytes = asyncio.run(
            tts_service.synthesize_speech(
                text=response_text,
                voice_id=voice_id or settings.elevenlabs_voice_id,
                model_id=settings.elevenlabs_model_id,
                stability=settings.elevenlabs_stability,
                similarity_boost=settings.elevenlabs_similarity_boost,
                speed=settings.elevenlabs_speed,
            )
        )

        # Save audio file
        output_audio_path = (
            AUDIO_DIR / f"response_{hashlib.md5(os.urandom(16)).hexdigest()}.mp3"
        )
        with open(output_audio_path, "wb") as f:
            f.write(audio_bytes)

        tts_duration = time.time() - tts_start
        audio_rag_stage_duration_seconds.labels(stage="tts").observe(tts_duration)
        logger.info(f"✅ TTS completed in {tts_duration:.3f}s")

        total_duration = time.time() - request_start

        return AudioRagResponse(
            thread_id=thread_id,  # ✅ Added missing field
            transcript=transcript,
            response=response_text,
            audio_url=f"/v1/audio/{output_audio_path.name}",  # ✅ Fixed: Added /v1 prefix
            sources=sources,
            metadata={
                "stt_duration": stt_duration,
                "rag_duration": rag_duration,
                "tts_duration": tts_duration,
                "total_duration": total_duration,
                "stt_cached": stt_result_dict.get("cached", False),
                "language": language,
            },
        )

    except Exception as e:
        logger.error(f"Audio RAG failed: {e}")
        voice_request_errors_total.labels(
            endpoint="audio_rag",
            error_type=type(e).__name__
        ).inc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        voice_request_duration_seconds.labels(endpoint="audio_rag").observe(
            time.time() - request_start
        )


@router.get("/audio/{filename}")
async def get_audio_file(filename: str):
    """
    Serve generated audio files

    Returns audio file from temporary storage
    """
    audio_path = AUDIO_DIR / filename

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        filename=filename,
    )
