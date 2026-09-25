# CheatBench — Video Cheat-Detection Harness

An interview-integrity benchmark harness built on the
[VideoSeek](https://arxiv.org/abs/2603.20185) tool-guided seeking agent.
The agent reviews a recorded interview and reports **visible integrity
breaches** as a structured detection artifact — plus a complete
model/tool call trace for auditability and cost analysis.

## Reportable breaches (dictionary v0.1)

| breach | meaning |
|---|---|
| `looking_off_screen` | candidate reading off a second screen/notes while answering |
| `unauthorized_device` | phone / extra screen / notes visible in frame during the interview (even untouched) |
| `multiple_participants` | a second person visibly participating while an answer is produced |
| `candidate_left_frame` | candidate's face absent from frame ≥ ~10 s mid-interview |
| `candidate_swap` | a different person answers than the one at session start |

Definitions, floors, and non-examples live in `config/dictionary.md` —
the agent only reports what's in the dictionary (its *floor* is what
keeps a candidate reading the question, a passer-by in the background,
or a momentary glance from becoming a detection). Deepfake and
second-voice are deliberately out of scope (vision-only benchmark).

## How it works

Think → Act → Observe loop over three perception tools plus `answer`.
The Deepgram diarized transcript is not a tool — it is injected with
the task input (and also feeds the vision tools' subtitles channel):

- `overview` — coarse whole-video scan (16-frame summary)
- `skim` — fast scan of a long segment to localize candidates
- `focus` — dense 1-fps inspection of a short clip to confirm/bound
- `answer` — emits the final detections JSON

Intended workflow: **Orient** (overview + provided transcript) → **Hunt**
(skim answer windows) → **Confirm** (focus candidate moments) →
**Emit** (`answer`).

## Install

```bash
pip install -e .          # needs ffmpeg on PATH for audio extraction
```

Secrets/config via env vars:

| env var | purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM key (models routed via OpenRouter) |
| `OPENROUTER_API_BASE` | default `https://openrouter.ai/api/v1` |
| `OPENROUTER_API_VERSION` | optional |
| `DEEPGRAM_API_KEY` | transcript generation (optional — see below) |

Default model: `openrouter/google/gemini-3.7-flash` (change via
`--model_name` or `config/general.yaml`).

## Usage

```bash
# local file
cheatbench-cli --video_path ./media/session01.mp4 --session_id s001 --verbose

# remote video — downloaded via yt-dlp first
cheatbench-cli --video_path "https://youtube.com/watch?v=..." --session_id s001

# offline transcription: pre-bake the transcript, no Deepgram needed
python scripts/prepare_session.py --video_path ./media/session01.mp4 --session_id s001
cheatbench-cli --video_path ./media/session01.mp4 --session_id s001 \
    --transcript_path ./media/session01.transcript.json
```

`--task` overrides the default analysis task; `--max_steps`,
`--reasoning_effort`, `--temperature`, `--seed`, `--max_tokens` tune the
agent loop. Run `cheatbench-cli -h` for the full list.

### Transcript resolution order

1. `--transcript_path` if given;
2. `<video_stem>.transcript.json` next to the video / in `--media_dir`;
3. live generation: ffmpeg audio → Deepgram (`nova-3`, diarize +
   utterances) → cache written beside the video.

Without a transcript the agent runs video-only (a warning is printed).

## Outputs (bench contract)

Written to `--output_dir` (default `./output/`):

- `<session_id>.detections.json` — the score artifact:
  `{session_id, duration_sec, model_id, run_id, status, detections: [{breach, start_sec, end_sec, confidence, evidence}]}`
- `<session_id>.trace.jsonl` — every LLM call (`call_site`, tokens,
  latency, cost) and every tool call (parameters, latency)
- `<session_id>_<timestamp>/trajectory.json` — full agent trajectory

`run_id = sha256(image_digest ‖ manifest.sha256 ‖ media.sha256 ‖
dictionary.sha256 ‖ model_id ‖ decode_params.sha256)[:16]` — any change
to a pinned input is a new run, which is what makes scores comparable.
`image_digest` comes from `CHEATBENCH_IMAGE_DIGEST` (default `dev`).

Invalid model output fails loudly: unparsable/invalid detections land in
`status: "failed"` with the error, never silently coerced.

## Isolated bench runs

The agent phase is sandboxed behind an allowlist egress proxy: video
download and Deepgram happen in a prep step *with* network; the agent
container only reaches the destinations in `docker/squid.conf`
(OpenRouter, Deepgram, YouTube/video CDN hosts) — all other egress is
denied.

```bash
export OPENROUTER_API_KEY=... DEEPGRAM_API_KEY=...
scripts/run_isolated.sh "https://youtube.com/watch?v=..." s001
```

To tighten further, remove unneeded `dstdomain` lines from
`docker/squid.conf` (e.g. for fully offline media, drop the video hosts
and pre-bake transcripts so only `api.openrouter.ai` remains).

## Repo layout

- `videoseek/agent.py` — think→act→observe loop
- `videoseek/tools/` — `overview`, `skim`, `focus`, `answer`
- `videoseek/transcript.py` — ffmpeg → Deepgram → cached TranscriptStore
- `videoseek/core/detection.py` — detection contract + validation
- `videoseek/utils.py` — LLM wrapper + TraceRecorder + run_id
- `config/prompts.yaml` — forensic-analyst system prompt
- `config/dictionary.md` — breach dictionary (edit to change policy)
- `scripts/prepare_session.py`, `scripts/run_isolated.sh` — bench flow
- `Dockerfile`, `docker-compose.yml`, `docker/squid.conf` — isolation

*Forked from [jylins/videoseek](https://github.com/jylins/videoseek)
(VideoSeek: Long-Horizon Video Agent with Tool-Guided Seeking).*
