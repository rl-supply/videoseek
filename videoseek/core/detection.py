import json
from typing import Any, Dict, List, Optional

BREACH_TYPES = (
    "looking_off_screen",
    "unauthorized_device",
    "multiple_participants",
    "candidate_left_frame",
    "candidate_swap",
)

SEVERITIES = ("high", "medium", "low")


class Detection:
    """One breach detection emitted by the agent.

    Contract (benchmark deck): breach (enum), start_sec, end_sec,
    confidence (0-1), evidence (free-text citation of what was seen),
    severity (high|medium|low — taxonomy tier the detection was flagged at).
    """

    def __init__(
        self,
        breach: str,
        start_sec: float,
        end_sec: float,
        confidence: float,
        evidence: str,
        severity: str = None,
    ):
        self.breach = breach
        self.start_sec = float(start_sec)
        self.end_sec = float(end_sec)
        self.confidence = float(confidence)
        self.evidence = evidence
        self.severity = severity

    def validate(self) -> List[str]:
        errors = []
        if self.breach not in BREACH_TYPES:
            errors.append(f"invalid breach type: {self.breach!r}")
        if self.start_sec < 0:
            errors.append("start_sec must be >= 0")
        if self.end_sec <= self.start_sec:
            errors.append("end_sec must be greater than start_sec")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be in [0, 1]")
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            errors.append("evidence must be a non-empty string")
        if self.severity is not None and self.severity not in SEVERITIES:
            errors.append(f"invalid severity: {self.severity!r}")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "breach": self.breach,
            "start_sec": round(self.start_sec, 2),
            "end_sec": round(self.end_sec, 2),
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
        }
        if self.severity is not None:
            d["severity"] = self.severity
        return d


class DetectionReport:
    """Final output of a cheat-detection run for one session."""

    def __init__(
        self,
        session_id: str,
        duration_sec: float,
        model_id: str,
        run_id: str,
        detections: List[Detection],
        status: str = "ok",
        error: Optional[str] = None,
    ):
        self.session_id = session_id
        self.duration_sec = duration_sec
        self.model_id = model_id
        self.run_id = run_id
        self.detections = detections
        self.status = status
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        report = {
            "session_id": self.session_id,
            "duration_sec": self.duration_sec,
            "model_id": self.model_id,
            "run_id": self.run_id,
            "status": self.status,
            "detections": [d.to_dict() for d in self.detections],
        }
        if self.error:
            report["error"] = self.error
        return report


def parse_detections(raw: str) -> List[Detection]:
    """Parse the answer tool's JSON output into validated Detections.

    Raises ValueError on malformed JSON or invalid entries — the caller
    turns that into a loud run failure rather than a silent zero score.
    """
    data = json.loads(raw)
    items = data.get("detections", None)
    if not isinstance(items, list):
        raise ValueError("answer payload must contain a 'detections' array")

    detections: List[Detection] = []
    problems: List[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f"detection[{idx}] is not an object")
            continue
        try:
            det = Detection(
                breach=str(item["breach"]),
                start_sec=float(item["start_sec"]),
                end_sec=float(item["end_sec"]),
                confidence=float(item["confidence"]),
                evidence=str(item.get("evidence", "")),
                severity=(str(item["severity"]).lower() if item.get("severity") is not None else None),
            )
        except (KeyError, TypeError, ValueError) as e:
            problems.append(f"detection[{idx}] malformed: {e}")
            continue
        errors = det.validate()
        if errors:
            problems.append(f"detection[{idx}] invalid: {'; '.join(errors)}")
            continue
        detections.append(det)

    if problems:
        raise ValueError("invalid detection payload: " + " | ".join(problems))
    return detections
