transcript_tool = {
    "type": "function",
    "function": {
        "name": "transcript",
        "description": (
            "To learn who is speaking and what is said, fetch the transcript "
            "(speaker turns and text) for a time range (start_time - end_time). "
            "Use it to locate answer windows and to tell answering from listening."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "start_time": {
                    "type": "number",
                    "description": "The start time of the transcript range in seconds.",
                },
                "end_time": {
                    "type": "number",
                    "description": "The end time of the transcript range in seconds.",
                },
            },
            "required": ["start_time", "end_time"],
            "additionalProperties": False,
        },
    },
}


def execute_transcript(config: dict, parameters: dict) -> str:
    """Return speaker turns overlapping [start_time, end_time]."""
    start_time = parameters["start_time"]
    end_time = parameters["end_time"]
    store = parameters["transcript_store"]
    segments = store.slice(start_time, end_time)
    if not segments:
        return f"No transcript content in {start_time:.1f}s - {end_time:.1f}s."
    lines = [
        f"[{s['start']:.1f}s - {s['end']:.1f}s] Speaker {s['speaker']}: {s['transcript']}"
        for s in segments
    ]
    return "\n".join(lines)
