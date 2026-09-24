#!/usr/bin/env python3
"""Bench prep step — runs WITH network access.

Per-session preparation for the isolated agent run:
  1. resolve/download the video (yt-dlp for URLs);
  2. extract audio and transcribe with Deepgram (cached transcript JSON);
  3. emit a manifest.jsonl row.

After this step the agent run itself needs only one egress: the LLM
endpoint — so the sandboxed phase can sit behind an allowlist proxy.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from videoseek.cli import resolve_video
from videoseek.transcript import TranscriptStore


def main() -> int:
    p = argparse.ArgumentParser(prog="prepare_session")
    p.add_argument("--video_path", required=True, help="Video URL or local path.")
    p.add_argument("--session_id", default=None)
    p.add_argument("--media_dir", default="./media/")
    p.add_argument("--manifest", default="./bench/manifest.jsonl")
    p.add_argument("--deepgram_model", default="nova-3")
    args = p.parse_args()

    media_dir = Path(args.media_dir).expanduser().resolve()
    media_dir.mkdir(parents=True, exist_ok=True)

    local_video = resolve_video(args.video_path, media_dir)
    session_id = args.session_id or Path(local_video).stem

    store = TranscriptStore(
        video_path=local_video,
        cache_dir=str(media_dir),
        deepgram_model=args.deepgram_model,
    )
    segments = store.ensure()
    print(f"Transcript: {len(segments)} utterances -> {store.cache_path}")

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "session_id": session_id,
        "media_path": str(local_video),
        "transcript_path": str(store.cache_path),
        "split": "dev",
    }
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(f"Manifest row appended -> {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
