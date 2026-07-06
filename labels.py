"""Transparency label generation (planning.md §3).

Maps a confidence score to the exact label text a reader would see on
the platform. The three variants below are copied VERBATIM from the
spec's label table -- if the spec text changes, this module must change
with it. Thresholds come from scoring.py so labels and attribution can
never drift apart.
"""

import scoring

LABEL_AI = (
    "Likely AI-generated. Our automated analysis found strong indications "
    "that this piece was created with substantial AI assistance. Automated "
    "detection is not perfect — if you're the creator and believe this is "
    "wrong, you can appeal and a human will review the decision."
)

LABEL_HUMAN = (
    "Likely human-written. Our automated analysis indicates this piece was "
    "written by a person. This label reflects our best assessment, not a "
    "certification."
)

LABEL_UNCERTAIN = (
    "Origin unclear. Our automated analysis could not confidently determine "
    "whether this piece was human-written or AI-assisted, so we're not "
    "labeling it either way. Please don't draw conclusions from this. If "
    "you're the creator, you can appeal to add context for human review."
)


def label_for(confidence: float) -> str:
    """Return the exact transparency label text for a confidence score."""
    if confidence >= scoring.AI_THRESHOLD:
        return LABEL_AI
    if confidence <= scoring.HUMAN_THRESHOLD:
        return LABEL_HUMAN
    return LABEL_UNCERTAIN