"""Transcript acquisition via Deepgram.

The transcript is extracted once per video (audio pulled out with ffmpeg,
sent to Deepgram's prerecorded endpoint with diarization + utterances),
normalized to utterance segments, and cached beside the media so the
agent run itself can stay offline: the `transcript` tool only ever
slices this store for a requested time range.
"""

import json
import os
import subprocess
from pathlib import Path

import requests

from .utils import load_transcript_json

DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"


def extract_audio_wav(video_path: str, out_path: str) -> str:
    """Extract mono 16 kHz audio from a video file with ffmpeg."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        out_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError(f"ffmpeg audio extraction failed: {proc.stderr[-500:]}")
    return out_path


def transcribe_deepgram(
    audio_path: str,
    api_key: str,
    model: str = "nova-3",
    timeout: int = 900,
) -> list[dict]:
    """Send audio to Deepgram and return normalized utterance segments.

    Returns [{"start","end","speaker","transcript","confidence"}, ...]
    sorted by start time.
    """
    params = {
        "model": model,
        "diarize": "true",
        "utterances": "true",
        "smart_format": "true",
        "punctuate": "true",
    }
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav",
    }
    with open(audio_path, "rb") as f:
        resp = requests.post(
            DEEPGRAM_LISTEN_URL,
            params=params,
            headers=headers,
            data=f,
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Deepgram transcription failed ({resp.status_code}): {resp.text[:500]}"
        )
    data = resp.json()
    utterances = (data.get("results") or {}).get("utterances") or []
    segments = []
    for u in utterances:
        text = (u.get("transcript") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": round(float(u.get("start", 0.0)), 2),
                "end": round(float(u.get("end", 0.0)), 2),
                "speaker": int(u.get("speaker", 0)),
                "transcript": text,
                "confidence": float(u.get("confidence", 1.0)),
            }
        )
    segments.sort(key=lambda s: s["start"])
    return segments


class TranscriptStore:
    """Holds the session transcript; lazily produces it on first need.

    Resolution order:
      1. an explicit transcript JSON path (pre-baked by the bench prep step);
      2. a cached <video>.transcript.json next to the video (or in cache_dir);
      3. live generation: ffmpeg extract → Deepgram → cache write.
    """

    def __init__(
        self,
        video_path: str,
        transcript_path: str | None = None,
        cache_dir: str | None = None,
        deepgram_api_key: str | None = None,
        deepgram_model: str = "nova-3",
    ):
        self.video_path = video_path
        self.explicit_path = transcript_path
        video_stem = Path(video_path).stem
        base = Path(cache_dir) if cache_dir else Path(video_path).parent
        self.cache_path = Path(base) / f"{video_stem}.transcript.json"
        self.api_key = deepgram_api_key or os.getenv("DEEPGRAM_API_KEY")
        self.model = deepgram_model
        self._segments: list[dict] | None = None

    def ensure(self) -> list[dict]:
        """Return the transcript segments, generating them if needed."""
        if self._segments is not None:
            return self._segments

        if self.explicit_path and os.path.exists(self.explicit_path):
            self._segments = load_transcript_json(self.explicit_path)
            return self._segments

        if self.cache_path.exists():
            self._segments = load_transcript_json(str(self.cache_path))
            return self._segments

        if not self.api_key:
            raise RuntimeError(
                "No transcript available and DEEPGRAM_API_KEY is not set; "
                "pre-bake a transcript with scripts/prepare_session.py or "
                "pass --transcript_path."
            )

        audio_path = self.cache_path.with_suffix(".audio.wav")
        try:
            extract_audio_wav(self.video_path, str(audio_path))
            self._segments = transcribe_deepgram(
                str(audio_path), self.api_key, model=self.model
            )
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

        self.cache_path.write_text(
            json.dumps({"utterances": self._segments}, indent=2),
            encoding="utf-8",
        )
        return self._segments

    @property
    def segments(self) -> list[dict]:
        return self._segments or []

    def slice(self, start_time: float, end_time: float) -> list[dict]:
        """Utterances overlapping [start_time, end_time]."""
        return [
            s
            for s in self.segments
            if s["end"] >= start_time and s["start"] <= end_time
        ]
