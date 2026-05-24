"""
STT endpoint using faster-whisper.
Faster, better Hindi accuracy, no dependency issues vs openai-whisper.

Preloads Whisper at startup to avoid 8-second delay on first request.
/api/stt/ready allows the frontend to wait until the model is loaded
before showing the mic button.

Default: Whisper is used for all branches (NOT Web Speech API).
Reason: Web Speech API sends audio to Google's servers when online,
which is a compliance violation for banking data.
"""

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()

_model = None
_executor = ThreadPoolExecutor(max_workers=1)

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB


def preload_whisper() -> None:
    """Call from main.py startup. Blocking — run via run_in_executor."""
    global _model
    print(f"[STT] Loading faster-whisper {WHISPER_MODEL_SIZE}...")
    _model = WhisperModel(
        WHISPER_MODEL_SIZE,
        device="cpu",
        compute_type="int8",   # int8 is fastest on CPU, good quality
    )
    print(f"[STT] faster-whisper {WHISPER_MODEL_SIZE} ready")


@router.get("/api/stt/ready")
def stt_ready():
    return {"ready": _model is not None, "model": WHISPER_MODEL_SIZE}


@router.post("/api/stt")
async def transcribe(audio: UploadFile = File(...)):
    if _model is None:
        raise HTTPException(503, "STT model loading. Please wait.")

    contents = await audio.read()
    if len(contents) > MAX_AUDIO_SIZE:
        raise HTTPException(413, "Audio too large (max 10MB)")
    if len(contents) < 500:
        raise HTTPException(400, "Audio too short")

    # Determine extension
    ext = ".wav"
    ct = audio.content_type or ""
    if "webm" in ct:
        ext = ".webm"
    elif "ogg" in ct:
        ext = ".ogg"

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(contents)
        tmp_path = f.name

    try:
        loop = asyncio.get_event_loop()

        def _transcribe():
            # faster-whisper returns a generator of segments
            segments, info = _model.transcribe(
                tmp_path,
                language="hi",       # Hindi hint
                beam_size=5,
                vad_filter=True,     # filter silence automatically
            )
            text = " ".join(seg.text for seg in segments).strip()
            return text, info.language

        text, lang = await loop.run_in_executor(_executor, _transcribe)

        if not text:
            raise HTTPException(422, "Could not transcribe — please speak clearly")

        return {"transcript": text, "language": lang}

    finally:
        os.unlink(tmp_path)