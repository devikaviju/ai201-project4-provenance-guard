# ai201-project4-provenance-guard
# Provenance Guard

A backend system for creative-sharing platforms that classifies submitted text as human- or AI-authored, scores its confidence honestly, surfaces a plain-language transparency label, and gives creators a path to appeal. Built with Flask, Groq (llama-3.3-70b-versatile), pure-Python stylometrics, Flask-Limiter, and SQLite.

Design principle driving the whole system: **a false positive (labeling a human's work as AI) is worse than a false negative.** Every layer reflects that asymmetry — the scoring thresholds, the label wording, and the appeal path.

## Architecture overview

A creator POSTs text and a `creator_id` to `/submit`. The rate limiter checks first (429 if over limit). The app then generates a `content_id` and fans the raw text out to two independent detection signals: the **Groq LLM classifier** (semantic) and the **stylometric analyzer** (structural). The **confidence scorer** combines both into a single calibrated score, applying a disagreement penalty when the signals conflict. The **label generator** maps the score to one of three fixed transparency labels. The **audit logger** writes the full record — both signal scores, combined confidence, attribution, label, status — to SQLite. The response returns `content_id`, attribution, confidence, and the label text.

Appeal flow: a creator POSTs `content_id` + `creator_reasoning` to `/appeal`. The system validates the ID, flips the record's status to `under_review`, and logs the reasoning alongside the original decision — the contest is never separated from the scores that triggered it. `GET /log` surfaces the audit trail. (Full diagram in [planning.md](planning.md).)

| Endpoint | Accepts | Returns |
|---|---|---|
| `POST /submit` | `{text, creator_id}` | `{content_id, attribution, confidence, label, signals}` |
| `POST /appeal` | `{content_id, creator_reasoning}` | `{content_id, status: "under_review", message}` |
| `GET /log` | — | recent audit-log entries |

## Detection signals

**Signal 1 — LLM classification (Groq).** Measures holistic semantic and stylistic coherence: hedging boilerplate ("it is important to note"), generic rhetorical structure, the uniform "essay voice" LLMs converge on. Chosen because it generalizes across genres and reads *meaning*, which no cheap heuristic can. What it misses: it misfires on formal, polished human writing (academic prose, trained non-native speakers) and can itself be fooled by lightly humanized AI output — both failure modes appeared in testing (see limitations). Its scores are also not perfectly reproducible across calls.

**Signal 2 — Stylometric heuristics (pure Python).** Measures statistical "burstiness" through three metrics: sentence-length variance (AI text is uniform, humans are irregular), type-token ratio (vocabulary diversity), and punctuation density. Chosen because it is genuinely independent of Signal 1 — it measures the text's *shape* without reading it — so agreement between the two signals means more than either alone. What it misses: everything semantic. Genres with deliberately uniform structure (poetry with repetition, legal writing) look AI-like statistically, and its metrics are meaningless on short texts — so submissions under 5 sentences or 60 words trigger a short-text guard that pulls the stylometric score halfway toward neutral and flags the record.

Normalization ranges were recalibrated against sample inputs after initial testing: real AI text is not perfectly uniform (sentence stdev ~4–5, not 0), and type-token ratio only carries signal at realistic submission lengths.

## Confidence scoring

Both signals output a score in [0, 1] where 1.0 = AI-like. They combine as:

```
base       = 0.6 * llm_score + 0.4 * style_score
penalty    = max(0, |llm_score - style_score| - 0.3)
confidence = base + (0.5 - base) * min(1, penalty * 2) * 0.8
```

The LLM is weighted 60/40 because it generalizes better across genres; stylometrics is the independent structural check. The **disagreement penalty** pulls the combined score toward 0.5 when the signals conflict by more than 0.3 — if the semantic and structural signals disagree, the honest answer is "uncertain," not their average.

The score maps to labels **asymmetrically**: `likely_ai` requires ≥ 0.70, `likely_human` requires ≤ 0.40, and everything between is `uncertain`. It deliberately takes far stronger evidence to accuse a creator of using AI than to affirm them as human.

**Validation:** tested with four inputs spanning the range (plus longer texts). Two real examples showing the scores vary meaningfully:

High-confidence case — formulaic AI-style essay (long):
```json
{"attribution": "likely_ai", "confidence": 0.725,
 "signals": {"llm": 0.9, "stylometric": 0.532}}
```

Low-confidence (human) case — casual restaurant review:
```json
{"attribution": "likely_human", "confidence": 0.206,
 "signals": {"llm": 0.1, "stylometric": 0.365}}
```

A third case demonstrates the false-positive protection working: formal academic-register human prose scored **llm = 0.8** — the LLM alone would have accused — but the combined score of **0.619** kept it in the uncertain band, and the reader saw "Origin unclear," not an accusation.

## Transparency label

Three variants, chosen by confidence band. Exact text displayed:

| Variant | Trigger | Exact label text |
|---|---|---|
| High-confidence AI | confidence ≥ 0.70 | "Likely AI-generated. Our automated analysis found strong indications that this piece was created with substantial AI assistance. Automated detection is not perfect — if you're the creator and believe this is wrong, you can appeal and a human will review the decision." |
| High-confidence human | confidence ≤ 0.40 | "Likely human-written. Our automated analysis indicates this piece was written by a person. This label reflects our best assessment, not a certification." |
| Uncertain | 0.40 < confidence < 0.70 | "Origin unclear. Our automated analysis could not confidently determine whether this piece was human-written or AI-assisted, so we're not labeling it either way. Please don't draw conclusions from this. If you're the creator, you can appeal to add context for human review." |

Design choices: hedged, creator-friendly wording; the AI and uncertain variants always mention the appeal path; the human variant explicitly disclaims being a certification. The label text lives in `labels.py`, which imports its thresholds from `scoring.py` so labels and attribution can never drift apart.

All three variants were verified reachable with real submissions (the three responses above).

## Appeals workflow

`POST /appeal` accepts a `content_id` and a required non-empty `creator_reasoning`. On receipt the system validates the ID (404 if unknown), updates the content's status to `under_review`, and logs the appeal alongside the original classification — same record, so a reviewer sees the text, both signal scores, the combined confidence, the label shown, and the creator's reasoning together. Automated re-classification is out of scope per the project spec.

Verified end-to-end:
```json
{"content_id": "...", "status": "under_review",
 "message": "Appeal received. The original classification and your reasoning have been logged for human review."}
```
{
    "content_id": "2a7b65dc-b7a8-430b-9eed-7c359d98e25b",
    "creator_id": "test-user-1",
    "attribution": "uncertain",
    "confidence": 0.619,
    "llm_score": 0.8,
    "style_score": 0.403,
    "label": "Origin unclear. Our automated analysis could not confidently determine whether this piece was human-written or AI-assisted, so we're not labeling it either way. Please don't draw conclusions from this. If you're the creator, you can appeal to add context for human review.",
    "status": "under_review",
    "appeal_reasoning": "I wrote this myself. I have an economics background and my professional writing style is formal, but this analysis is my own work.",
    "appeal_timestamp": "2026-07-06T06:26:00.879827+00:00",
    "timestamp": "2026-07-06T06:06:10.894732+00:00"
}

## Rate limiting

`POST /submit` is limited to **10 per minute and 100 per day** per IP (Flask-Limiter, in-memory storage).

Reasoning: a real writer checking their own work submits at most a handful of pieces in a sitting — sustained traffic above 10/minute from one address is a script, not a person. The 100/day cap bounds the daily cost an abuser can impose on the Groq-backed pipeline while staying generous for any individual creator. In-memory storage suits a single-process deployment; production would move to Redis so limits survive restarts and apply across workers.

Verified — 12 rapid requests:
```
200 200 200 200 200 200 200 429 429 429 429 429
```
Only 7 requests succeeded before the 429s because three label-demonstration submissions minutes earlier counted against the same per-IP window — the limiter tracks the address, not the test script.

## Audit log

Every attribution decision writes a structured row to SQLite: timestamp, content ID, creator ID, both individual signal scores, the LLM's one-line reasoning, combined confidence, attribution, label, status, short-text flag, and any appeal (reasoning + timestamp). `GET /log` returns recent entries; sample entries covering all three attribution bands plus an appeal are visible in the repo's evidence above and via the endpoint.

The log is the system's source of truth: the appeal record keeps its original scores and label forever, so a reviewer can always reconstruct exactly what the system decided and why.

## Known limitations

**Lightly edited AI output is affirmed as human.** In testing, an AI-drafted paragraph with human-style punctuation and casual phrasing scored `llm = 0.20` — the LLM signal itself was fooled — producing `confidence = 0.255` and a `likely_human` label. The spec predicted the two signals would *conflict* on this content and land it in the uncertain band; in reality Signal 1 was simply deceived, so there was no conflict for the penalty to catch. This is a false negative, which the design explicitly tolerates (the system is tuned so its failures are missed AI, not falsely accused humans), but it means the "Likely human-written" label cannot be read as proof of human authorship — which is exactly why that label disclaims being a certification.

Also: stylometric metrics carry little information on very short submissions (mitigated by the short-text guard, not solved), and repetitive poetic forms would score AI-like structurally (mitigated by the disagreement penalty).

## Spec reflection

**How the spec helped:** the label table in planning.md 3 specified the exact text of all three variants before any label code existed, so implementation was transcription rather than invention — the generated `labels.py` could be verified against the spec verbatim, and the three live responses matched it word for word.

**How implementation diverged:** the spec originally set the `likely_ai` threshold at 0.75. Calibration testing during Milestone 4 showed the stylometric signal realistically maxes near 0.6, which under the 60/40 weighting made 0.75 unreachable even for blatant AI text — the label would have existed in the spec but never appeared in reality. The threshold was lowered to 0.70 (preserving the accuse-vs-affirm asymmetry against 0.40), and the spec was amended with the rationale rather than silently rewritten.

## AI usage

1. **Spec-driven code generation with independent verification (M3).** I made the core design decisions (signal pairing, asymmetric thresholds, disagreement-penalty scoring, label tone), then directed Claude to generate the Flask skeleton, SQLite layer, and Groq signal function from my planning.md sections. Before wiring the signal into the endpoint, I verified it standalone with test inputs (`test_llm_signal.py`) — it scored a clearly-AI sample 0.80 and a clearly-human sample 0.10.

2. **Overriding the spec when calibration contradicted it (M4).** I directed Claude to implement my spec's exact scoring formula; its calibration testing revealed my 0.75 AI threshold was unreachable with realistic signal ranges. Claude presented three options; I evaluated the tradeoffs and chose lowering the threshold to 0.70, then amended planning.md with the rationale.

3. **Verifying generated label logic against the spec (M5).** I directed Claude to generate the label function and `/appeal` endpoint from my §3–§4 spec sections, then verified all three label variants were reachable with real submissions and that an appeal updated the record's status and preserved the original scores.