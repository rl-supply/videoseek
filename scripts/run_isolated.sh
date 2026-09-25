#!/usr/bin/env bash
# Isolated bench run: prep (network) -> agent run (proxy-egress only).
# Usage: scripts/run_isolated.sh <video_url_or_path> [session_id]
set -euo pipefail

VIDEO_PATH="${1:?usage: run_isolated.sh <video_url_or_path> [session_id]}"
SESSION_ID="${2:-}"

echo "==> building image"
docker build -t cheatbench:local .

echo "==> prep step (unrestricted network): download media + Deepgram transcript"
# Runs on the host network — downloads the video and pre-bakes the transcript
# so the agent phase only needs LLM egress.
ARGS=(--video_path "$VIDEO_PATH" --media_dir ./media/)
if [[ -n "$SESSION_ID" ]]; then ARGS+=(--session_id "$SESSION_ID"); fi
python scripts/prepare_session.py "${ARGS[@]}"

# Resolve the downloaded file for the isolated run
LOCAL_FILE=$(ls -t ./media/ | grep -v '.transcript.json$' | head -1)
SID="${SESSION_ID:-${LOCAL_FILE%.*}}"

echo "==> isolated agent run (egress via allowlist proxy only)"
docker compose run --rm --profile run agent \
    --video_path "/app/media/$LOCAL_FILE" \
    --session_id "$SID" \
    --transcript_path "/app/media/${LOCAL_FILE%.*}.transcript.json" \
    --verbose

echo "==> outputs in ./output/"
ls -la ./output/"$SID".* 2>/dev/null || true
