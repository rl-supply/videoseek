import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from config import general_config, init_config, prompts_config
from .agent import DEFAULT_TASK_PROMPT, VideoSeekAgent
from .core import DetectionReport, parse_detections
from .utils import (
    TraceRecorder,
    compute_run_id,
    set_trace_recorder,
    sha256_file,
)

URL_PATTERN = re.compile(r"^https?://")


def build_agent_config(args: argparse.Namespace) -> dict:
    config = {}
    config.update(general_config)
    config.update(prompts_config)
    config = init_config(config, args)
    return config


def resolve_video(video_path: str, media_dir: Path) -> str:
    """Download remote videos (YouTube et al. via yt-dlp) into media_dir.

    Local paths are returned unchanged.
    """
    if not URL_PATTERN.match(video_path):
        return video_path
    import yt_dlp

    media_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(media_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": out_tmpl,
        "format": "best[height<=720]/best",
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_path, download=True)
        return ydl.prepare_filename(info)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cheatbench",
        description="Video-forensics agent harness: detects interview-integrity "
        "breaches in a recorded session (tool-guided seeking agent).",
    )
    p.add_argument(
        "--video_path",
        required=True,
        help="Video URL (downloaded via yt-dlp) or local path.",
    )
    p.add_argument(
        "--task",
        default=None,
        help="Override the default breach-detection task prompt.",
    )
    p.add_argument(
        "--session_id",
        default=None,
        help="Session identifier used for output filenames (default: video stem).",
    )
    p.add_argument(
        "--transcript_path",
        default=None,
        help="Pre-baked transcript JSON (skips Deepgram).",
    )
    p.add_argument(
        "--dictionary_path",
        default=str(Path(__file__).resolve().parent.parent / "config" / "dictionary.md"),
        help="Breach dictionary file (content-hashed into run_id).",
    )
    p.add_argument(
        "--manifest_path",
        default=None,
        help="Bench manifest file (content-hashed into run_id).",
    )
    p.add_argument(
        "--media_dir",
        default="./media/",
        help="Directory for downloaded media and transcript cache.",
    )
    p.add_argument(
        "--output_dir",
        default="./output/",
        help="Directory to write outputs (default: ./output/).",
    )
    p.add_argument("--verbose", action="store_true", help="Print agent step logs.")

    # Allow overriding general.yaml keys (optional)
    p.add_argument("--model_name", default=general_config["model_name"], help="Model name.")
    p.add_argument("--api_base", default=general_config["api_base"], help="API base.")
    p.add_argument("--api_key", default=general_config["api_key"], help="API key.")
    p.add_argument("--api_version", default=general_config["api_version"], help="API version.")
    p.add_argument("--reasoning_effort", default=general_config["reasoning_effort"], help="Reasoning effort of the LLM.")
    p.add_argument("--seed", type=int, default=general_config["seed"], help="Seed.")
    p.add_argument("--temperature", type=float, default=general_config["temperature"], help="Temperature.")
    p.add_argument("--max_tokens", type=int, default=general_config["max_tokens"], help="Max output tokens of the LLM.")
    p.add_argument("--max_steps", type=int, default=general_config["max_steps"], help="Max steps of the agent.")
    p.add_argument("--deepgram_model", default=general_config.get("deepgram_model", "nova-3"), help="Deepgram model.")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    media_dir = Path(args.media_dir).expanduser().resolve()
    media_dir.mkdir(parents=True, exist_ok=True)

    config = build_agent_config(args)

    # Resolve remote video; compute session_id from the local file.
    local_video = resolve_video(args.video_path, media_dir)
    session_id = args.session_id or Path(local_video).stem

    run_id = f"{session_id}_{int(time.time())}"
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Trace is a first-class output: every model call + tool invocation.
    trace_path = output_dir / f"{session_id}.trace.jsonl"
    recorder = TraceRecorder(trace_path)
    set_trace_recorder(recorder)

    # Breach dictionary (content-hashed into run_id).
    dictionary_text = Path(args.dictionary_path).read_text(encoding="utf-8")
    config["breach_dictionary"] = dictionary_text
    config["deepgram_api_key"] = os.getenv("DEEPGRAM_API_KEY")
    config["deepgram_model"] = args.deepgram_model

    run_id_hash = compute_run_id(
        image_digest=os.getenv("CHEATBENCH_IMAGE_DIGEST", "dev"),
        manifest_sha256=(
            sha256_file(args.manifest_path) if args.manifest_path else ""
        ),
        media_sha256=sha256_file(local_video),
        dictionary_sha256=sha256_file(args.dictionary_path),
        model_id=config["model_name"],
        decode_params={
            "temperature": config["temperature"],
            "seed": config["seed"],
            "max_tokens": config["max_tokens"],
            "reasoning_effort": config["reasoning_effort"],
        },
    )

    try:
        agent = VideoSeekAgent(
            config=config,
            video_path=local_video,
            output_dir=str(output_dir),
            tools=config["tools"],
            transcript_path=args.transcript_path,
            transcript_cache_dir=str(media_dir),
            verbose=args.verbose,
        )
        task = args.task or DEFAULT_TASK_PROMPT
        traj = agent.run(task)
        traj_dict = traj.to_dict()

        # Parse the detection contract; an invalid payload fails loudly.
        status, error = "ok", None
        try:
            detections = parse_detections(traj.final_answer or "")
        except Exception as e:
            detections, status, error = [], "failed", str(e)[:500]

        report = DetectionReport(
            session_id=session_id,
            duration_sec=agent.duration,
            model_id=config["model_name"],
            run_id=run_id_hash,
            detections=detections,
            status=status,
            error=error,
        )
        report_dict = report.to_dict()

        print(f"Session: {session_id}")
        print(f"Detections: {len(detections)} (status={status})")

        (output_dir / f"{session_id}.detections.json").write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "trajectory.json").write_text(
            json.dumps(traj_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        set_trace_recorder(None)
        recorder.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
