# Provenance Guard — Planning Spec

A backend system for creative-sharing platforms that classifies submitted text as human- or AI-authored, scores confidence honestly, surfaces a transparency label, and gives creators an appeal path.

Design principle driving every decision below: **a false positive (calling a human's work AI) is worse than a false negative.** The system is deliberately hard to convince that something is AI-generated, keeps a wide "uncertain" band, and always offers an appeal path on non-human verdicts.

---

## 1. Detection Signals

### Signal 1 — LLM classification (Groq, llama-3.3-70b-versatile)
- **Measures:** holistic semantic and stylistic coherence — hedging patterns ("it is important to note"), generic rhetorical structure, uniform "essay voice" that LLMs converge on.
- **Why it differs between human and AI writing:** LLM output reflects trained-in rhetorical patterns; human writing carries idiosyncratic voice, tangents, and specificity.
- **Output:** a float in [0, 1], where 1.0 = strongly reads as AI-generated. The prompt asks the model to return **only** a JSON object: `{"ai_likelihood": <float>, "reasoning": "<one sentence>"}`. The reasoning string is stored in the audit log, never shown to end users.
- **Blind spots:** misfires on formal, polished human writing (academic prose, trained non-native speakers) and on lightly humanized AI output. Scores are not perfectly reproducible across calls.

### Signal 2 — Stylometric heuristics (pure Python)
- **Measures:** statistical "burstiness" of the text via three metrics:
  1. **Sentence length variance** (std dev of sentence lengths in words) — AI text is uniform, humans are irregular.
  2. **Type-token ratio** (unique words / total words) — proxies vocabulary diversity.
  3. **Punctuation density** (punctuation chars / total chars) — human informal writing uses more varied punctuation (dashes, ellipses, exclamations).
- **Combination into one signal:** each metric is normalized to [0, 1] where 1.0 = "AI-like" (low variance, low TTR, low punctuation density), then averaged. Normalization ranges were recalibrated against sample inputs after initial testing: real AI text is not perfectly uniform (sentence stdev ~4–5, not 0), and TTR only carries signal at realistic submission lengths.
- **Output:** a float in [0, 1], 1.0 = strongly AI-like, plus the raw metric values (logged for debugging).
- **Blind spots:** knows nothing about meaning. Genres with deliberately uniform structure (poetry with repetition, legal/technical writing, minimalist prose) look AI-like statistically. Breaks on short texts — variance over 3 sentences is noise.
- **Short-text guard:** if the text has < 5 sentences or < 60 words, the stylometric score is pulled halfway toward 0.5 and the record is flagged `short_text: true`, widening effective uncertainty.

**Why these two:** genuinely independent — Signal 1 reads what the text *says*; Signal 2 measures its *shape* without reading it at all. Disagreement between them is itself information (see scoring).

## 2. Uncertainty Representation

### Combining the signals
```
base       = 0.6 * llm_score + 0.4 * style_score
disagree   = abs(llm_score - style_score)
penalty    = max(0, disagree - 0.3)                 # only penalize real conflict
pull       = min(1.0, penalty * 2)                  # 0..1 strength
confidence = base + (0.5 - base) * pull * 0.8       # pull toward 0.5 (uncertain)
```
- LLM weighted 60/40 over stylometrics because it generalizes across genres better; stylometrics is the cheap independent check.
- **Disagreement penalty:** when the two signals conflict by more than 0.3, the combined score is pulled toward 0.5. Rationale: if the semantic and structural signals disagree, the honest answer is "we don't know," not the average. Example: `llm=0.9, style=0.2` → base 0.62, but disagreement 0.7 pulls it to ≈0.52 → **uncertain**, not "likely AI."

### What the score means
The confidence score is the system's **degree of belief that the text is AI-generated**, calibrated to label bands:

| Score | Attribution | Meaning |
|---|---|---|
| ≥ 0.70 | `likely_ai` | Both signals agree strongly; system is willing to assert AI involvement |
| 0.40 – 0.70 | `uncertain` | Signals are weak, mixed, or conflicting; system refuses to assert |
| ≤ 0.40 | `likely_human` | Signals point to human authorship |

- **A 0.60 means:** signals lean AI but not nearly enough to say so publicly → the user sees the *uncertain* label, not a softer AI accusation.
- **Deliberately asymmetric:** the AI band starts at 0.70 while the human band starts at 0.40, so it takes much stronger evidence to accuse a creator of using AI than to affirm them as human. This encodes the false-positive asymmetry directly into the label mapping.
- **Amendment (post-M4 calibration):** originally 0.75. Calibration testing showed the stylometric signal realistically maxes near 0.6, making 0.75 unreachable for even blatant AI text under the 60/40 weighting. Lowered to 0.70; the asymmetry (0.70 to accuse vs 0.40 to affirm) is preserved.
- **Validation plan:** test with ≥4 inputs spanning the range (clearly AI, clearly human, formal-human borderline, edited-AI borderline) and confirm (a) clearly-AI and clearly-human scores differ by ≥0.3, and (b) both borderline cases land in the uncertain band. Print both signal scores separately when a case misbehaves.

## 3. Transparency Label Design

Tone: creator-friendly and hedged. Non-human verdicts always mention the appeal path. Exact text of the three variants:

| Variant | Trigger | Exact label text |
|---|---|---|
| High-confidence AI | confidence ≥ 0.70 | "Likely AI-generated. Our automated analysis found strong indications that this piece was created with substantial AI assistance. Automated detection is not perfect — if you're the creator and believe this is wrong, you can appeal and a human will review the decision." |
| High-confidence human | confidence ≤ 0.40 | "Likely human-written. Our automated analysis indicates this piece was written by a person. This label reflects our best assessment, not a certification." |
| Uncertain | 0.40 < confidence < 0.70 | "Origin unclear. Our automated analysis could not confidently determine whether this piece was human-written or AI-assisted, so we're not labeling it either way. Please don't draw conclusions from this. If you're the creator, you can appeal to add context for human review." |

## 4. Appeals Workflow

- **Who can appeal:** the creator of the content (the `creator_id` attached to the original submission). The endpoint validates that the `content_id` exists; unknown IDs return 404.
- **What they provide:** `POST /appeal` with `{content_id, creator_reasoning}` — free-text reasoning is required and must be non-empty.
- **What the system does on receipt:**
  1. Looks up the original classification record in SQLite.
  2. Updates that content's `status` from `classified` → `under_review`.
  3. Logs the appeal **alongside the original decision**: appeal timestamp and `appeal_reasoning` are written to the same content record, so the original scores and label are never separated from the contest.
  4. Returns a confirmation: `{content_id, status: "under_review", message}`.
- **What a human reviewer would see** when opening the appeal queue: the submitted text, both individual signal scores, the combined confidence, the label that was shown, the original timestamp, and the creator's reasoning — everything needed to judge the appeal without re-running detection.
- Automated re-classification is out of scope (per spec).

## 5. Anticipated Edge Cases

1. **Poem with heavy repetition and simple vocabulary** (e.g., a villanelle or children's verse): low sentence-length variance and low type-token ratio make stylometrics score it AI-like even when the LLM signal reads it as human. Mitigation: the disagreement penalty pulls it into the uncertain band rather than "likely AI."
2. **Formal essay by a non-native English speaker:** careful, uniform, hedged prose can push *both* signals moderately AI-ward (e.g., 0.55–0.65 combined). Mitigation: the AI threshold at 0.70 keeps this out of the accusation band; it lands as *uncertain* with an appeal path — the exact scenario the appeal test uses.
3. **Very short submissions (< 60 words):** stylometric metrics are statistically meaningless. Mitigation: short-text guard pulls the stylometric signal toward 0.5 and flags the record.
4. **Lightly edited AI output:** human punctuation and irregularity pasted over AI structure. The signals will likely conflict → uncertain, which is the honest verdict; the system does not pretend it can catch this case.

---

## Architecture

Submission flow: a request hits the rate limiter first, then `/submit` fans the raw text out to both signals, the confidence scorer combines them (with the disagreement penalty), the label generator maps the score to one of three fixed variants, the audit logger writes the full record to SQLite, and the response returns `content_id`, attribution, confidence, and label. Appeal flow: `/appeal` validates the `content_id`, flips the record's status to `under_review`, logs the creator's reasoning next to the original decision, and confirms.

```
SUBMISSION FLOW
                        raw text + creator_id
  Client ── POST /submit ──► [Rate Limiter] ──► [Flask /submit handler]
                                  │ 429 if over limit      │ raw text
                                  ▼                        ├──────────────┐
                               reject                      ▼              ▼
                                              [Signal 1: Groq LLM]  [Signal 2: Stylometrics]
                                                      │ llm_score (0–1)   │ style_score (0–1)
                                                      └───────┬───────────┘
                                                              ▼
                                                   [Confidence Scorer]
                                                              │ combined score (0–1)
                                                              ▼
                                                    [Label Generator]
                                                              │ label text (1 of 3 variants)
                                                              ▼
                                                      [Audit Logger] ──► SQLite
                                                              │ full record
                                                              ▼
                                          JSON response: content_id, attribution,
                                          confidence, label, signal scores

APPEAL FLOW
  Client ── POST /appeal ──► [Flask /appeal handler]
              content_id +          │ look up original decision
              creator_reasoning     ▼
                              [SQLite: status → "under_review",
                               append appeal_reasoning to record]
                                    │
                                    ▼
                        JSON response: confirmation + status
```

### API surface
| Endpoint | Accepts | Returns |
|---|---|---|
| `POST /submit` | `{text, creator_id}` | `{content_id, attribution, confidence, label, signals: {llm, stylometric}}` |
| `POST /appeal` | `{content_id, creator_reasoning}` | `{content_id, status: "under_review", message}` |
| `GET /log` | — | `{entries: [...]}` most recent audit entries |

### Storage (SQLite, single table `audit_log`)
Columns: `content_id` (PK), `creator_id`, `timestamp`, `text`, `llm_score`, `style_score`, `confidence`, `attribution`, `label`, `status` (`classified` / `under_review`), `short_text` (bool), `appeal_reasoning` (nullable), `appeal_timestamp` (nullable).

---

## AI Tool Plan

**M3 — submission endpoint + first signal**
- *Spec sections provided to the AI tool:* 1 Detection Signals (Signal 1) + Architecture diagram + API surface.
- *Ask it to generate:* the Flask app skeleton with `POST /submit` and `GET /log` route stubs, SQLite setup with the `audit_log` table above, and the Groq classification function returning `{"ai_likelihood": float, "reasoning": str}`.
- *Verification:* call the signal function directly with 2–3 test inputs before wiring it in; confirm the route returns `content_id`, attribution, placeholder confidence, placeholder label; confirm each submission writes a structured SQLite row visible via `GET /log`.

**M4 — second signal + confidence scoring**
- *Spec sections provided:* 1 (Signal 2) + 2 Uncertainty Representation + diagram.
- *Ask it to generate:* the stylometric function (three metrics → one score, with the short-text guard) and the scoring function implementing the exact formula and thresholds in 2.
- *Verification:* check the generated code against the formula and thresholds line-by-line (AI tools drift here); run the 4-input test set and confirm clearly-AI vs clearly-human scores differ meaningfully and both borderline cases land uncertain; confirm the log now stores both individual scores.

**M5 — production layer**
- *Spec sections provided:* 3 Transparency Label Design + 4 Appeals Workflow + diagram.
- *Ask it to generate:* the label generation function mapping confidence → the exact variant text, the `POST /appeal` endpoint, and Flask-Limiter wiring (`10 per minute; 100 per day`, in-memory storage).
- *Verification:* produce all three label variants with real submissions and confirm the text matches 3 verbatim; submit an appeal against a real `content_id` and confirm `GET /log` shows `status: under_review` with `appeal_reasoning` populated; fire 12 rapid requests and confirm 429s after the 10th.