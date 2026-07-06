"""Milestone 3: test Signal 1 standalone, BEFORE trusting it in the endpoint.

Run:  python test_llm_signal.py
Expected: an AI-ish text scoring clearly higher than a human-ish text.
"""

from dotenv import load_dotenv

load_dotenv()

import llm_signal

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
}

if __name__ == "__main__":
    for name, text in SAMPLES.items():
        result = llm_signal.classify_text(text)
        print(f"{name:15s} ai_likelihood={result['ai_likelihood']:.2f}  "
              f"reasoning: {result['reasoning']}")