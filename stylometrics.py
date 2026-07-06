"""Signal 2: stylometric heuristics (pure Python, per planning.md §1).

Three metrics, each normalized to [0, 1] where 1.0 = "AI-like":
  1. Sentence length variance -- AI text is uniform; humans are bursty.
  2. Type-token ratio         -- vocabulary diversity.
  3. Punctuation density      -- human informal writing punctuates more variedly.

Short-text guard (per spec): < 5 sentences or < 60 words -> the final
score is pulled halfway toward 0.5 and the result is flagged short_text.

Output contract: {"style_score": float, "metrics": {...}, "short_text": bool}

Calibration note: the normalization caps below (STDEV_CAP etc.) are
heuristic reference points tuned against the project's four sample
inputs; they are design decisions, not derived constants, and are the
first thing to revisit if scores look miscalibrated on new genres.
"""

import re
import statistics

# Normalization reference points (see calibration note above).
# Recalibrated after testing against sample inputs: real AI text is not
# perfectly uniform (stdev ~4-5, not 0), and TTR only carries signal at
# realistic submission lengths, so the ranges below map observed values
# rather than theoretical extremes.
STDEV_LO, STDEV_HI = 1.5, 7.5    # sentence-length stdev (words): <=LO fully AI-like, >=HI fully human
TTR_LOW, TTR_HIGH = 0.65, 0.88   # type-token ratio range mapped to [AI ... human]
PUNCT_CAP = 0.04       # punctuation chars per char; >= this reads fully human

_SENTENCE_SPLIT = re.compile(r"[.!?]+(?:\s+|$)")
_WORD = re.compile(r"[A-Za-z']+")
_PUNCT = set(".,;:!?—–-…\"'()")


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def analyze(text: str) -> dict:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    words = [w.lower() for w in _WORD.findall(text)]
    n_words = len(words)

    # Metric 1: sentence length variance (stdev of words per sentence)
    lengths = [len(_WORD.findall(s)) for s in sentences]
    stdev = statistics.stdev(lengths) if len(lengths) >= 2 else 0.0
    uniformity = _clamp(1.0 - (stdev - STDEV_LO) / (STDEV_HI - STDEV_LO))  # 1.0 = uniform = AI-like

    # Metric 2: type-token ratio (unique words / total words)
    ttr = (len(set(words)) / n_words) if n_words else 0.0
    ttr_ai_like = _clamp(1.0 - (ttr - TTR_LOW) / (TTR_HIGH - TTR_LOW))

    # Metric 3: punctuation density
    density = (sum(1 for ch in text if ch in _PUNCT) / len(text)) if text else 0.0
    punct_ai_like = _clamp(1.0 - density / PUNCT_CAP)

    style_score = (uniformity + ttr_ai_like + punct_ai_like) / 3.0

    # Short-text guard: variance over a handful of sentences is noise
    short_text = len(sentences) < 5 or n_words < 60
    if short_text:
        style_score = style_score + (0.5 - style_score) * 0.5

    return {
        "style_score": round(style_score, 3),
        "metrics": {
            "sentence_count": len(sentences),
            "word_count": n_words,
            "sentence_len_stdev": round(stdev, 2),
            "type_token_ratio": round(ttr, 3),
            "punct_density": round(density, 4),
        },
        "short_text": short_text,
    }