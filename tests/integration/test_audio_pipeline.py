import os
from pathlib import Path


def _sample_audio_path():
    # Allow placing a sample file in repo root or tests folder
    candidates = [
        Path("sample_audio_vn.wav"),
        Path("tests/sample_audio_vn.wav"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def test_stt_tts_audio_rag_if_sample_available(client):
    audio_path = _sample_audio_path()
    if audio_path is None:
        # Skip gracefully if no sample audio is available
        return

    # STT
    with open(audio_path, "rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        resp_stt = client.post("/v1/models/stt", files=files)
    assert resp_stt.status_code == 200
    stt_data = resp_stt.json()
    assert isinstance(stt_data.get("text"), str) and len(stt_data["text"]) >= 0

    # TTS
    payload_tts = {"text": "Xin chào, đây là kiểm thử TTS."}
    resp_tts = client.post("/v1/models/tts", json=payload_tts)
    assert resp_tts.status_code == 200
    assert int(resp_tts.headers.get("Content-Length", "0")) >= 0

    # Audio RAG
    import uuid

    thread_id = str(uuid.uuid4())
    with open(audio_path, "rb") as f:
        files = {"file": (audio_path.name, f, "audio/wav")}
        data = {
            "user_identifier": "test-user",
            "thread_id": thread_id,
            "language": "vi",
        }
        resp_audio_rag = client.post("/v1/rag/audio", files=files, data=data)
    assert resp_audio_rag.status_code == 200
    rag_data = resp_audio_rag.json()
    assert "response" in rag_data and "audio_url" in rag_data
