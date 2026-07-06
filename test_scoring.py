"""Milestone 4: test confidence scoring with the four assignment inputs.

Run:  python test_scoring.py   (server does NOT need to be running)

Prints both individual signal scores plus the combined confidence and
attribution for each case, so a misbehaving signal is immediately visible.
Save this output -- it's the evidence for the README's confidence-scoring
section (two examples with noticeably different scores).
"""

from dotenv import load_dotenv

load_dotenv()

import llm_signal
import scoring
import stylometrics

SAMPLES = {
    "clearly_ai": (
        "Artificial intelligence represents a transformative paradigm shift in "
        "modern society. It is important to note that while the benefits of AI "
        "are numerous, it is equally essential to consider the ethical "
        "implications. Furthermore, stakeholders across various sectors must "
        "collaborate to ensure responsible deployment."
    ),
    "clearly_human": (
        "ok so i finally tried that new ramen place downtown and honestly? "
        "underwhelming. the broth was fine but they put WAY too much sodium in "
        "it and i was thirsty for like three hours after. my friend got the "
        "spicy version and said it was better. probably won't go back unless "
        "someone drags me there"
    ),
    "borderline_formal_human": (
        "The relationship between monetary policy and asset price inflation has "
        "been extensively studied in the literature. Central banks face a "
        "fundamental tension between their mandate for price stability and the "
        "unintended consequences of prolonged low interest rates on equity and "
        "real estate valuations."
    ),
    "borderline_edited_ai": (
        "I've been thinking a lot about remote work lately. There are genuine "
        "tradeoffs — flexibility and no commute on one side, isolation and "
        "blurred work-life boundaries on the other. Studies show productivity "
        "varies widely by individual and role type."
    ),
}

if __name__ == "__main__":
    print(f"{'case':25s} {'llm':>5s} {'style':>6s} {'conf':>6s}  attribution")
    print("-" * 62)
    for name, text in SAMPLES.items():
        llm = llm_signal.classify_text(text)["ai_likelihood"]
        style = stylometrics.analyze(text)["style_score"]
        conf = scoring.combine(llm, style)
        print(f"{name:25s} {llm:5.2f} {style:6.3f} {conf:6.3f}  {scoring.attribution(conf)}")