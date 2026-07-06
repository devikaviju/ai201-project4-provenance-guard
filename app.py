"""Provenance Guard -- Flask app.

Complete system (Milestone 5): POST /submit runs both detection signals,
combines them into a calibrated confidence score, maps the score to one
of three transparency label variants, and writes a structured audit-log
entry. POST /appeal lets a creator contest a classification. Flask-Limiter
rate-limits submissions. GET /log surfaces the audit trail.
"""

import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()  # loads GROQ_API_KEY from .env -- must run before importing llm_signal use

import audit_log
import labels
import llm_signal
import scoring
import stylometrics

app = Flask(__name__)
audit_log.init_db()

# Rate limiting (planning.md AI Tool Plan / README rationale):
# 10/minute -- a real writer submitting their own work never needs more
# than a handful of checks per minute; sustained faster traffic from one
# address is a script, not a person.
# 100/day -- generous for an individual creator (most submit a few pieces
# a day at most) while capping the daily cost an abuser can impose on the
# Groq-backed pipeline. In-memory storage is appropriate for a single-
# process dev deployment; production would use Redis.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    creator_id = body.get("creator_id")
    if not text or not isinstance(text, str) or not text.strip():
        return jsonify({"error": "'text' is required and must be a non-empty string"}), 400
    if not creator_id:
        return jsonify({"error": "'creator_id' is required"}), 400

    content_id = str(uuid.uuid4())

    # Signal 1: semantic (Groq LLM); Signal 2: structural (stylometrics)
    signal1 = llm_signal.classify_text(text)
    llm_score = signal1["ai_likelihood"]
    signal2 = stylometrics.analyze(text)
    style_score = signal2["style_score"]

    confidence = scoring.combine(llm_score, style_score)
    label = labels.label_for(confidence)

    record = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "llm_score": llm_score,
        "llm_reasoning": signal1["reasoning"],
        "style_score": style_score,
        "confidence": confidence,
        "attribution": scoring.attribution(confidence),
        "label": label,
        "status": "classified",
        "short_text": 1 if signal2["short_text"] else 0,
    }
    audit_log.log_classification(record)

    return jsonify(
        {
            "content_id": content_id,
            "attribution": record["attribution"],
            "confidence": confidence,
            "label": label,
            "signals": {"llm": llm_score, "stylometric": style_score},
        }
    )


@app.route("/appeal", methods=["POST"])
def appeal():
    body = request.get_json(silent=True) or {}
    content_id = body.get("content_id")
    reasoning = body.get("creator_reasoning")
    if not content_id:
        return jsonify({"error": "'content_id' is required"}), 400
    if not reasoning or not isinstance(reasoning, str) or not reasoning.strip():
        return jsonify({"error": "'creator_reasoning' is required and must be non-empty"}), 400

    record = audit_log.get_record(content_id)
    if record is None:
        return jsonify({"error": f"no classification found for content_id '{content_id}'"}), 404

    audit_log.record_appeal(
        content_id, reasoning.strip(), datetime.now(timezone.utc).isoformat()
    )
    return jsonify(
        {
            "content_id": content_id,
            "status": "under_review",
            "message": "Appeal received. The original classification and your "
                       "reasoning have been logged for human review.",
        }
    )


@app.route("/log", methods=["GET"])
def log():
    # In a real deployment this endpoint would sit behind auth; here it
    # exists for grading visibility per the project spec.
    return jsonify({"entries": audit_log.get_log()})


if __name__ == "__main__":
    app.run(debug=True)