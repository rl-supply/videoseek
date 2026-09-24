import hashlib
import json
import os
import random
import re
import threading
import time
from pathlib import Path
from litellm import completion, completion_cost


def retry_with_exponential_backoff(
    func,
    initial_delay: float = 1,
    exponential_base: float = 2,
    jitter: bool = True,
    max_retries: int = 8,
):
    """Retry a function with exponential backoff."""

    def wrapper(*args, **kwargs):
        # Initialize variables
        num_retries = 0
        delay = initial_delay

        # Loop until a successful response or max_retries is hit or an exception is raised
        while True:
            try:
                return func(*args, **kwargs)
            # Raise exceptions for any errors not specified
            except Exception as e:
                if (
                    "rate limit" in str(e).lower()
                    or "timed out" in str(e)
                    or "Too Many Requests" in str(e)
                    or "Forbidden for url" in str(e)
                    or "the maximum usage" in str(e).lower()
                    or "server had an error" in str(e).lower()
                    or "has no attribute 'upper'" in str(e).lower()
                    or "internal" in str(e).lower()
                ):
                    # Increment retries
                    num_retries += 1

                    # Check if max retries has been reached
                    if num_retries > max_retries:
                        print("Max retries reached. Exiting.")
                        return None

                    # Increment the delay
                    delay *= exponential_base * (1 + jitter * random.random())
                    print(f"Retrying in {delay} seconds for {str(e)}...")
                    # Sleep for the delay
                    time.sleep(delay)
                else:
                    print(str(e))
                    return None

    return wrapper


class TraceRecorder:
    """Append-only JSONL trace of every model call and tool invocation.

    The trace is a first-class benchmark output: it separates
    "never looked there" from "looked and misjudged" and carries the
    per-session token/latency/cost numbers reported beside the score.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = open(self.path, "a", encoding="utf-8")

    def record(self, event: dict) -> None:
        event = {"ts": round(time.time(), 3), **event}
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def record_llm_call(
        self,
        *,
        call_site: str,
        model_name: str,
        latency_ms: float,
        response=None,
        error: str | None = None,
    ) -> None:
        event: dict = {
            "type": "llm_call",
            "call_site": call_site,
            "model": model_name,
            "latency_ms": round(latency_ms, 1),
        }
        if response is not None:
            usage = getattr(response, "usage", None)
            if usage is not None:
                event["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
                event["completion_tokens"] = getattr(usage, "completion_tokens", None)
                event["total_tokens"] = getattr(usage, "total_tokens", None)
            try:
                event["cost_usd"] = completion_cost(completion_response=response)
            except Exception:
                event["cost_usd"] = None
        if error is not None:
            event["error"] = error
        self.record(event)

    def record_tool_call(
        self,
        *,
        tool: str,
        parameters: dict,
        latency_ms: float,
        outcome_chars: int,
    ) -> None:
        self.record(
            {
                "type": "tool_call",
                "tool": tool,
                "parameters": parameters,
                "latency_ms": round(latency_ms, 1),
                "outcome_chars": outcome_chars,
            }
        )

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass


_current_recorder: TraceRecorder | None = None


def set_trace_recorder(recorder: TraceRecorder | None) -> None:
    global _current_recorder
    _current_recorder = recorder


def get_trace_recorder() -> TraceRecorder | None:
    return _current_recorder


@retry_with_exponential_backoff
def call_llm_api(
    model_name: str,
    messages: list,
    api_base: str,
    api_key: str = None,
    api_version: str = None,
    max_tokens: int = 32768,
    reasoning_effort: str = "medium",
    seed: int = 42,
    temperature: float = 1.0,
    tools: list = None,
    tool_choice: str = None,
    return_json: bool = False,
    call_site: str = "unknown",
) -> dict:
    start = time.monotonic()
    try:
        response = completion(
            model=model_name,
            messages=messages,
            api_base=api_base,
            api_key=api_key,
            api_version=api_version,
            max_completion_tokens=max_tokens,
            seed=seed,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tools=tools,
            tool_choice=tool_choice,
            response_format={"type": "json_object"} if return_json else None,
            timeout=900,
        )
    except Exception as e:
        recorder = get_trace_recorder()
        if recorder is not None:
            recorder.record_llm_call(
                call_site=call_site,
                model_name=model_name,
                latency_ms=(time.monotonic() - start) * 1000,
                error=str(e)[:500],
            )
        raise
    recorder = get_trace_recorder()
    if recorder is not None:
        recorder.record_llm_call(
            call_site=call_site,
            model_name=model_name,
            latency_ms=(time.monotonic() - start) * 1000,
            response=response,
        )
    return response


def load_subtitles(subtitle_path: str):
    """Parse SRT file and return list of {start_time, end_time, subtitle} dicts."""
    if subtitle_path is None or not os.path.exists(subtitle_path):
        return []
    with open(subtitle_path, "r", encoding="utf-8") as f:
        content = f.read()

    result = []
    # SRT format: index, HH:MM:SS,mmm --> HH:MM:SS,mmm, then text lines
    pattern = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
    )
    blocks = re.split(r"\n\n+", content.strip())

    def to_seconds(h, m, s, ms):
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    for block in blocks:
        match = pattern.search(block)
        if match:
            start = to_seconds(*match.groups()[:4])
            end = to_seconds(*match.groups()[4:8])
            text = block[match.end() :].strip().replace("\n", " ")
            result.append(
                {
                    "start_time": round(start, 1),
                    "end_time": round(end, 1),
                    "subtitle": text,
                }
            )
    return result


def load_transcript_json(transcript_path: str):
    """Load a normalized transcript JSON file.

    Expected shape: [{"start": float, "end": float, "speaker": int,
    "transcript": str, "confidence": float}, ...]
    """
    if transcript_path is None or not os.path.exists(transcript_path):
        return []
    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("utterances", [])
    segments = []
    for u in data:
        try:
            segments.append(
                {
                    "start": round(float(u["start"]), 2),
                    "end": round(float(u["end"]), 2),
                    "speaker": int(u.get("speaker", 0)),
                    "transcript": str(u.get("transcript", "")).strip(),
                    "confidence": float(u.get("confidence", 1.0)),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    segments.sort(key=lambda s: s["start"])
    return segments


def transcript_to_subtitle_segments(utterances: list[dict]) -> list[dict]:
    """Adapt Deepgram-style utterances to the subtitles shape used by the
    vision tools: {start_time, end_time, subtitle}."""
    segments = []
    for u in utterances:
        speaker = u.get("speaker", 0)
        segments.append(
            {
                "start_time": u["start"],
                "end_time": u["end"],
                "subtitle": f"Speaker {speaker}: {u['transcript']}",
            }
        )
    return segments


def convert_to_free_form_text_representation(
    history: list[dict], content_type: str = "caption"
) -> str:
    """
    This function will form the textual representation for the entire video to be used for QA.
    It gives a good structured representation of the entire video.
    JSON types of representations are good for outputs, but free-form/ semi-structured should be better for input.
    """
    free_form_text_representation = ""
    if len(history) == 0:
        return f"No {content_type} found."
    for i in history:
        if i[content_type] is None:
            continue
        x = ""
        start_time, end_time = i["start_time"], i["end_time"]
        x += f"**Timestamp**: {start_time}s - {end_time}s\n"
        x += f"**{content_type.capitalize()}**: {i[content_type]}\n"

        free_form_text_representation += f"{x}\n"

    return free_form_text_representation


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_run_id(
    *,
    image_digest: str = "dev",
    manifest_sha256: str = "",
    media_sha256: str = "",
    dictionary_sha256: str = "",
    model_id: str = "",
    decode_params: dict | None = None,
) -> str:
    """run_id = sha256(image_digest ‖ manifest ‖ media_tree ‖ dictionary
    ‖ model_id ‖ decode_params)[:16]

    Any change to a pinned input is a new run, which is what makes two
    scores comparable.
    """
    decode_str = json.dumps(decode_params or {}, sort_keys=True)
    material = "|".join(
        [
            image_digest,
            manifest_sha256,
            media_sha256,
            dictionary_sha256,
            model_id,
            hashlib.sha256(decode_str.encode()).hexdigest(),
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]
