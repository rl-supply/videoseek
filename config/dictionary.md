# Breach Dictionary v0.1

Reportable breach types for video-only interview-integrity review. A breach
counts only when it is VISIBLE in the interview recording and matches the
definition below — including its floor and non-examples.

## looking_off_screen
Definition. The candidate's gaze is directed off-camera while producing an
answer — reading from a second screen, notes, or a prompt outside the frame.
Pattern of repeated, sustained off-axis glances during answers.
Floor. Not reportable below ~3 s of sustained off-screen gaze, and single
momentary glances are not reportable.
Not this breach:
  - glancing away while a question is being read out
  - looking up or aside while thinking between sentences
  - a gaze fixed on the primary screen that holds the interview window

## unauthorized_device
Definition. A phone, tablet, second screen, or written notes visible in
frame during the interview — whether held in hand, lying face-down on the
desk, or simply present — counts as a breach. A device does NOT need to be
seen in active use: its visible presence during the interview is itself
the violation.
Floor. Not reportable below ~3 s of continuous visibility.
Not this breach:
  - the laptop/screen the interview itself runs on
  - notes or a device the posting explicitly permits
  - looking down with nothing resolvable in frame
  - a device visible only in the background of a bystander

## multiple_participants
Definition. A second person visibly present and participating — in frame
beside the candidate, leaning in, prompting, or answering for them — while
an answer is produced.
Floor. Not reportable below ~3 s of visible presence.
Not this breach:
  - a passer-by crossing the background without interacting
  - a poster, photo, or screen image of a face
  - a voice without a visible second person (audio-only evidence does not
    count — this benchmark is vision-only)

## candidate_left_frame
Definition. The candidate's face is not visible in frame for a sustained
stretch while the interview is in progress — they left their seat or moved
fully out of view.
Floor. Not reportable below ~10 s of absence; brief leans or reaches
partially out of frame do not count.
Not this breach:
  - the camera feed dropping or freezing (a technical artifact, not a breach)
  - partial framing where the face is still identifiable
  - absence before the interview starts or after it ends

## candidate_swap
Definition. The person answering is not the same person seen at session
start / enrollment — a visibly different face takes over mid-session.
Session-level verdict: flag the change point and interval once.
Not this breach:
  - the same person under changed lighting, pose, glasses, or camera angle
  - image-quality degradation that only makes identity uncertain
