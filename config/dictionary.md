# Breach Taxonomy v0.2 — vision-only subset of the V2 cheat taxonomy

Each breach lists: Definition, when to flag HIGH / MEDIUM / LOW, and when to
DISCARD (never emit). Confidence should track severity: high ≈ 0.85–1.0,
medium ≈ 0.55–0.85, low ≈ 0.3–0.55. Anything you'd discard must NOT appear
in `detections` at all.

## looking_off_screen  (v2: offscreen_reference_pattern)
Definition. The candidate's gaze is held off-camera while producing an
answer — reading a second screen, notes, a hidden overlay, or looking
down/elsewhere to get clues. Judge against the candidate's OWN baseline
gaze direction — camera angles differ per setup.
Flag HIGH:
  - the candidate appears to read from an off-camera source AND at least
    one other supporting signal exists in the timeline (e.g. a visible
    device, suspicious pause-then-answer pattern); or
  - the eyes scan in straight horizontal left-to-right reading lines,
    ignoring the camera, during the answer.
Flag LOW:
  - the off-camera gaze is sustained but its purpose is unclear.
DISCARD:
  - brief or single momentary glances (< ~3 s sustained)
  - glancing away while a question is being read out
  - looking up or aside while thinking between sentences
  - a gaze fixed on the primary screen that holds the interview window

## unauthorized_device  (v2: unauthorized_aid_object_present)
Definition. An unauthorized aid object — phone, tablet, extra laptop,
smartwatch, second monitor, paper notes — is visible in frame during the
interview. The device the session itself runs on is not an aid.
Flag HIGH:
  - active use is evident: reading from, typing on, or repeatedly glancing
    at the object while answering; or the object is used to answer on the
    candidate's behalf; or eyes scan it in straight horizontal lines.
Flag MEDIUM:
  - the object is present and plausibly consulted, but active use can't
    be confirmed (e.g. held in hand with gaze mostly on it).
Flag LOW:
  - the object is merely visible (e.g. a phone lying face-down on the
    desk) — presence alone is still reportable.
DISCARD:
  - the laptop/screen the interview itself runs on
  - notes or a device the posting explicitly permits
  - a device visible only in the background of a bystander
  - anything under ~3 s of continuous visibility

## multiple_participants  (v2: multiple_people_presence)
Definition. A second person is visibly present and participating while an
answer is produced — in frame beside the candidate, leaning in, prompting,
or answering for them.
Flag HIGH:
  - the second person appears to assist the candidate.
Flag MEDIUM:
  - a second person is genuinely present in frame but their role cannot
    be confirmed.
DISCARD:
  - not clearly a second person: reflection, poster, photo, screen image
  - a passer-by crossing the background without interacting
  - a voice without a visible second person (vision-only benchmark)
  - anything under ~3 s of visible presence

## candidate_left_frame  (v2: candidate_absence_or_unverifiable_presence)
Definition. The candidate's face is not visible for a sustained stretch
while the interview is in progress — left their seat or moved out of view.
Flag HIGH:
  - prolonged, total absence (≥ ~5 s).
Flag MEDIUM:
  - presence is partial or merely hard to verify for a sustained period.
DISCARD:
  - brief leans or reaches partially out of frame (< ~5 s)
  - the camera feed dropping or freezing — a technical artifact
  - face still identifiable at partial framing
  - absence before the interview starts or after it ends

## candidate_swap  (v2: identity_authenticity_risk)
Definition. The person answering is not the same person seen at session
start — a visibly different face takes over mid-session.
Flag HIGH:
  - an abrupt, clear identity change — different person answers a
    question. Flag the change point and the interval once.
Flag MEDIUM:
  - a different face is probable but occlusions/lighting keep certainty
    short of clear.
DISCARD:
  - the same person under changed lighting, pose, glasses, camera angle
  - image-quality degradation that only makes identity uncertain
  - brief occlusions where the candidate reappears unchanged
