# Plan: Speech-to-Speech Integration for Vietnamese Medical RAG

Thêm tính năng voice input/output vào hệ thống RAG hiện tại. User nói → STT (faster-whisper local) → RAG pipeline → TTS (ElevenLabs hoặc open-source) → voice response. Transcript và response text vẫn hiển thị trên UI. Tối ưu latency bằng cách streaming, caching, và xử lý song song.

## Steps

1. **Enable Chainlit audio và tạo audio handlers trong `frontend/main.py`**
   - Bật `features.audio.enabled = true` trong `frontend/.chainlit/config.toml`
   - Thêm `@cl.on_audio_chunk` hoặc `@cl.on_audio_end` handler để nhận audio input từ user
   - Gửi audio file tới backend endpoint `POST /v1/models/stt` qua `helpers.py`
   - Hiển thị transcript (STT output) trong `cl.Message` khi nhận được
   - Nhận audio response từ backend và render bằng `cl.Audio` element

2. **Tạo STT service với faster-whisper trong `backend/src/services/stt_service.py`**
   - Implement `SttService` class với `faster_whisper.WhisperModel` (model="medium", device="auto")
   - Method `transcribe_audio(audio_path: str) -> str` để convert audio → text
   - Thêm caching layer (Redis) cho audio transcripts (key: audio file hash, TTL: 1h)
   - Add config vào `backend/config/models.yaml` (section `stt: {active: "medium", device: "auto"}`)
   - Load model on startup via `backend/src/core/model_loader.py`

3. **Tạo TTS service trong `backend/src/services/tts_service.py`**
   - Implement `TtsService` class với 2 options: ElevenLabs API hoặc open-source (e.g., Coqui TTS, piper-tts)
   - Method `synthesize_speech(text: str, voice_id: str) -> bytes` để convert text → audio
   - Thêm caching layer (Redis) cho generated audio (key: text hash + voice_id, TTL: 24h)
   - Add config vào `backend/config/models.yaml` (section `tts: {provider: "elevenlabs", voice_id: "...", fallback: "coqui"}`)
   - Async processing để không block RAG pipeline

4. **Thêm audio endpoints vào `backend/src/main.py`**
   - `POST /v1/models/stt`: Upload audio file → return transcript JSON `{text: str, duration: float}`
   - `POST /v1/models/tts`: Send text → return audio file (streaming response with `StreamingResponse`)
   - `POST /v1/rag/audio`: Combined endpoint nhận audio → STT → RAG → TTS → return audio + transcript + sources
   - Add schemas vào `backend/src/schemas/schema.py`: `SttRequest`, `SttResponse`, `TtsRequest`, `AudioRagRequest`, `AudioRagResponse`

5. **Optimize audio processing pipeline cho low latency**
   - **Parallel processing**: STT → RAG → TTS chạy sequential, nhưng chunking audio input để xử lý streaming (nếu dùng WebSocket)
   - **Streaming RAG response**: Modify `bot_route_answer_message` để stream tokens via SSE hoặc WebSocket thay vì return full text (requires refactoring Celery task → async function)
   - **Pre-warm models**: Load STT/TTS models on startup để tránh cold start latency
   - **Audio format optimization**: Use Opus codec (compress tốt hơn) thay vì WAV để giảm upload/download time
   - **Batch TTS**: Nếu response dài, chia thành chunks và synthesize song song (nếu TTS service hỗ trợ batch)

6. **Add Docker container cho STT service trong `backend/docker-compose.yml`**
   - Service `stt_whisper`: Image với faster-whisper + whisper-medium model
   - Mount shared volume `/data/audio` để frontend/backend share audio files
   - GPU support: `deploy.resources.reservations.devices` nếu có GPU available
   - Environment variables: `WHISPER_MODEL=medium`, `DEVICE=cuda` hoặc `cpu`

## Further Considerations

1. **Streaming vs Batch Processing**: Option A: Full audio upload → process → return audio (simpler, latency ~5-10s). Option B: WebSocket streaming (audio chunks → real-time transcript → stream response) (phức tạp hơn, latency thấp hơn ~2-3s). Hiện tại hãy implement **Option A** cho MVP trước.

2. **TTS Provider Choice**: Option A: **ElevenLabs API** (voice quality tốt nhất, cost ~$0.30/1K chars, latency ~1-2s).

3. **Audio Format & Compression**: Input audio nên accept multiple formats (WAV, MP3, OGG, Opus). Output audio recommend **Opus codec** (compression ratio tốt, latency thấp). Chainlit `sample_rate = 24000` phù hợp với Whisper (16kHz native) và TTS models (22-24kHz).

4. **Celery Task Timeout**: Current soft limit 180s có thể không đủ cho audio pipeline (STT ~2s + RAG ~5s + TTS ~3s = ~10s, nhưng worst-case có thể 30-60s). Recommend tăng soft limit lên 240s hoặc tách audio processing ra khỏi Celery (dùng FastAPI background tasks).

5. **Caching Strategy**: STT transcripts cache by audio file hash (avoid re-transcribing same audio). TTS audio cache by text content hash (avoid re-synthesizing same response). Embeddings cache đã có sẵn trong `backend/src/core/cache.py` (no changes needed).

6. **Security & Validation**: Add file size limit cho audio upload (e.g., max 10MB = ~10 minutes audio). Validate audio format trước khi process (avoid malicious files). Add rate limiting cho audio endpoints (prevent abuse).
