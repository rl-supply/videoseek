import json

from videoseek.utils import call_llm_api
from videoseek.core import BREACH_TYPES


answer_tool = {
    "type": "function",
    "function": {
        "name": "answer",
        "description": (
            "Emit the final breach detections collected from the trajectory. "
            "Call this when evidence gathering is complete — including when the "
            "conclusion is that no breach occurred."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}


RECONCILE_INSTRUCTION = (
    "Before emitting detections, list EVERY candidate moment your earlier "
    "observations flagged (a device visible in frame, sustained downward gaze "
    "at it, a second person, leaving frame, a different person appearing...). "
    "For each one give an explicit verdict on its own line:\n"
    "  BREACH: <breach type> <start>-<end>s — <why it matches the dictionary>\n"
    "  DROPPED: <moment> — <dictionary-grounded reason>\n"
    "Remember: a device visible in frame during the interview is "
    "unauthorized_device even if you did not see it being actively used."
)

DETECTION_INSTRUCTION = (
    "Based on the trajectory and your reconciliation above, emit the final "
    "detections for this interview session.\n"
    "Return ONLY valid JSON with this exact schema:\n"
    '{"detections": [{"breach": "<one of: '
    + ", ".join(BREACH_TYPES)
    + '>", "start_sec": <float>, "end_sec": <float>, '
    '"confidence": <float 0-1>, "evidence": "<what was seen, with frame/timestamp citations>"}]}\n'
    "Rules:\n"
    "- Only report breaches from the enum above; never invent breach names.\n"
    "- Every detection needs visible evidence you actually observed — cite timestamps.\n"
    "- start_sec/end_sec bound when the breach was VISIBLE in the interview video.\n"
    "- confidence is your calibrated probability that this is a real breach (0-1).\n"
    "- Every moment you marked BREACH above MUST appear here as a detection; "
    "do not silently re-drop it.\n"
    "- If no breach is supported by evidence, return an empty detections array."
)


def _request_detections(
    config: dict, messages: list, json_mode: bool = True, call_site: str = "tool:answer"
) -> str:
    response = call_llm_api(
        messages=messages,
        model_name=config["model_name"],
        api_base=config["api_base"],
        api_key=config["api_key"],
        api_version=config["api_version"],
        max_tokens=config["max_tokens"],
        reasoning_effort=config["reasoning_effort"],
        seed=config["seed"],
        temperature=config["temperature"],
        return_json=json_mode,
        call_site=call_site,
    )
    if response is None:
        return None
    return response.choices[0].message.content


def execute_answer(config: dict, parameters: dict) -> str:
    """Emit the detection contract from the accumulated trajectory."""
    question = parameters["question"]
    messages = parameters["messages"]
    # Reconcile first: force an explicit verdict per flagged candidate moment
    # in free text (landed in the trace), so a bare {"detections": []} would
    # contradict the model's own stated verdicts.
    messages.append(
        {
            "role": "user",
            "content": f"Task:\n{question}\n\n{RECONCILE_INSTRUCTION}",
        }
    )
    reconcile = _request_detections(
        config, messages, json_mode=False, call_site="tool:answer:reconcile"
    )
    if reconcile:
        messages.append({"role": "assistant", "content": reconcile})

    messages.append(
        {
            "role": "user",
            "content": DETECTION_INSTRUCTION,
        }
    )
    raw = _request_detections(config, messages)
    if raw is None:
        return json.dumps({"detections": [], "error": "llm_call_failed"})

    # One corrective retry if the model did not return valid detections JSON.
    try:
        json.loads(raw)["detections"]
    except Exception:
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous response was not valid detections JSON. "
                    "Return ONLY the JSON object now, same schema."
                ),
            }
        )
        retry_raw = _request_detections(config, messages)
        if retry_raw is not None:
            raw = retry_raw

    return raw
