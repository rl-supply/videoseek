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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from videoseek.cli import resolve_video
from videoseek.transcript import TranscriptStore


def normalize_media(video_path: str, media_dir: Path) -> str:
    """Re-encode to h264/yuv420p faststart, capped at 854px wide.

    Bench recordings come from merge pipelines whose containers can stall
    decord's random-access decode; a clean normalized file is also what
    gets hashed into run_id, keeping the media pin reproducible.
    """
    src = Path(video_path)
    out = media_dir / f"{src.stem}.norm.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", "scale='min(854,iw)':-2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg normalize failed: {proc.stderr[-500:]}")
    return str(out)


def main() -> int:
    p = argparse.ArgumentParser(prog="prepare_session")
    p.add_argument("--video_path", required=True, help="Video URL or local path.")
    p.add_argument("--session_id", default=None)
    p.add_argument("--media_dir", default="./media/")
    p.add_argument("--manifest", default="./bench/manifest.jsonl")
    p.add_argument("--deepgram_model", default="nova-3")
    p.add_argument("--no_normalize", action="store_true",
                   help="Skip ffmpeg normalization (use input as-is).")
    args = p.parse_args()

    media_dir = Path(args.media_dir).expanduser().resolve()
    media_dir.mkdir(parents=True, exist_ok=True)

    local_video = resolve_video(args.video_path, media_dir)
    if not args.no_normalize:
        local_video = normalize_media(local_video, media_dir)
    session_id = args.session_id or Path(local_video).stem.replace(".norm", "")

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
