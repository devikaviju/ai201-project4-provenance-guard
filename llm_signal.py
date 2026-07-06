"""Signal 1: LLM-based classification via Groq.

Sends the text to llama-3.3-70b-versatile and asks for a structured
assessment of how strongly it reads as AI-generated.

Output contract (per planning.md §1):
    {"ai_likelihood": float in [0, 1], "reasoning": str}
1.0 = strongly reads as AI-generated. The reasoning string is stored in
the audit log for reviewers; it is never shown to end users.
"""

import json
import os

from groq import Groq

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a text-attribution analyst for a creative writing platform.
Assess how strongly the given text reads as AI-generated rather than human-written.

Consider: generic rhetorical structure, hedging boilerplate (e.g. "it is
important to note"), uniform 'essay voice', lack of specific lived detail,
and overly balanced framing. Remember that formal or polished writing is
NOT automatically AI-generated -- humans write formally too.

Respond with ONLY a JSON object, no markdown fences, no extra text:
{"ai_likelihood": <float between 0.0 and 1.0>, "reasoning": "<one sentence>"}

where 1.0 means almost certainly AI-generated and 0.0 means almost
certainly human-written."""


def classify_text(text: str) -> dict:
    """Return {"ai_likelihood": float, "reasoning": str} for the given text."""
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.0,  # keep scores as reproducible as the model allows
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    )
    raw = response.choices[0].message.content.strip()

    # Defensive parsing: strip markdown fences if the model adds them anyway.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)
    score = float(parsed["ai_likelihood"])
    score = max(0.0, min(1.0, score))  # clamp to [0, 1]
    return {"ai_likelihood": score, "reasoning": str(parsed.get("reasoning", ""))}