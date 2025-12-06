# Load Testing

This directory contains Locust scenarios to measure backend performance for text and audio RAG endpoints.

## Prerequisites

- Backend running at `http://localhost:8000`
- Optional: a small Vietnamese WAV file at `testing/sample_audio_vn.wav`

## Quick Start (Windows PowerShell)

```powershell
Push-Location "testing"; locust; Pop-Location
```

Open Locust UI at `http://localhost:8089`, set users/spawn rate, and start the test.

## Scenarios

- `RagUser`: sends POST `/v1/rag` requests with realistic Vietnamese medical queries; includes health checks.
- `AudioUser`: sends POST `/v1/rag/audio` with an audio file if available; falls back to `/v1/models/stt` to validate error handling if file is missing.

## Observability

- Inspect Grafana dashboards for latency percentiles, request rates, and GPU VRAM usage.
- Review Prometheus metrics exposed by backend and GPU services.

## Notes

- Adjust Locust user counts to avoid overwhelming GPU or external APIs.
- For deterministic runs, mock TTS and external calls during load.
