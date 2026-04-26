from flask import Flask, request, jsonify, render_template
import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

API_URL = os.getenv(
    "HF_API_URL",
    "https://router.huggingface.co/hf-inference/models/prithivMLmods/Deep-Fake-Detector-v2-Model",
)
LEGACY_API_URL = "https://api-inference.huggingface.co/models/prithivMLmods/Deep-Fake-Detector-v2-Model"
API_KEY = os.getenv("HF_API_KEY") or os.getenv("HF_API")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_MODEL_FALLBACKS = [
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-pro-latest",
]

headers = {
    "Authorization": f"Bearer {API_KEY}"
}


def normalize_confidence(score):
    numeric_score = float(score or 0)
    return numeric_score / 100 if numeric_score > 1 else numeric_score


def build_detection_summary(detections):
    if not isinstance(detections, list) or not detections:
        return {
            "top_label": "unknown",
            "top_score": 0,
            "real_confidence": 0,
        }

    top = sorted(detections, key=lambda item: item.get("score", 0), reverse=True)[0]
    label = str(top.get("label", "unknown"))
    confidence = normalize_confidence(top.get("score", 0))
    is_fake_class = any(token in label.lower() for token in ("deepfake", "fake", "ai"))
    real_confidence = 1 - confidence if is_fake_class else confidence

    return {
        "top_label": label,
        "top_score": round(confidence, 4),
        "real_confidence": round(real_confidence, 4),
    }


def parse_gemini_json(text):
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    return json.loads(cleaned)


def generate_user_guidance(detections):
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set"

    summary = build_detection_summary(detections)
    prompt = (
        "You are an AI safety assistant for image authenticity checks. "
        "Write plain-language, non-technical guidance for end users based on classifier output.\n\n"
        f"Top label: {summary['top_label']}\n"
        f"Top confidence: {summary['top_score']}\n"
        f"Estimated real-image confidence: {summary['real_confidence']}\n\n"
        "Return valid JSON only with this schema:\n"
        "{\n"
        "  \"explanation\": \"short user-friendly summary in 1-2 sentences\",\n"
        "  \"safety_recommendations\": [\"3 to 5 concrete action items\"]\n"
        "}\n"
        "Rules: Keep tone calm and practical. Do not mention model names or internal scores."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt,
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }

    model_candidates = [GEMINI_MODEL] + [m for m in GEMINI_MODEL_FALLBACKS if m != GEMINI_MODEL]
    last_error = None

    for model_name in model_candidates:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            f"?key={GEMINI_API_KEY}"
        )

        try:
            response = requests.post(endpoint, json=payload, timeout=20)

            # If model alias is unavailable for this key/project, try next candidate.
            if response.status_code == 404:
                last_error = f"Model not found or unsupported: {model_name}"
                continue

            response.raise_for_status()
            data = response.json()
            raw_text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            parsed = parse_gemini_json(raw_text)
            explanation = str(parsed.get("explanation", "")).strip()
            recommendations = [
                str(item).strip()
                for item in parsed.get("safety_recommendations", [])
                if str(item).strip()
            ]

            if not explanation or not recommendations:
                last_error = f"Gemini returned incomplete JSON guidance from {model_name}"
                continue

            return {
                "explanation": explanation,
                "safety_recommendations": recommendations[:5],
            }, None
        except requests.RequestException as exc:
            last_error = f"Gemini request failed for {model_name}: {exc}"
        except (ValueError, KeyError, IndexError, TypeError):
            last_error = f"Failed to parse Gemini response from {model_name}"

    return None, last_error or "Gemini guidance unavailable"

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/analyze', methods=['POST'])
def analyze():
    if not API_KEY:
        return jsonify({"error": "HF_API_KEY not set"}), 500

    file = request.files.get('image')
    if not file:
        return jsonify({"error": "No image file uploaded"}), 400

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "Uploaded image is empty"}), 400

    candidate_urls = []
    for url in (API_URL, LEGACY_API_URL):
        if url and url not in candidate_urls:
            candidate_urls.append(url)

    response = None
    last_exception = None
    for url in candidate_urls:
        try:
            response = requests.post(
                url,
                headers={**headers, "Content-Type": "application/octet-stream"},
                data=image_bytes,
                timeout=30,
            )
        except requests.RequestException as exc:
            last_exception = exc
            continue

        # Some HF hosts return an HTML "Cannot POST /models/..." page on unsupported routes.
        # If that happens, try the next candidate URL.
        if "Cannot POST /models/" in response.text:
            response = None
            continue

        break

    if response is None:
        detail = str(last_exception) if last_exception else "No valid response from inference API"
        return jsonify({"error": "Failed to reach inference API", "detail": detail}), 502

    if response.status_code != 200:
        return jsonify({
            "error": "Inference API returned an error",
            "status": response.status_code,
            "detail": response.text,
        }), response.status_code

    try:
        result = response.json()
    except ValueError:
        return jsonify({"error": "Invalid JSON response from inference API", "detail": response.text}), 502

    guidance, guidance_error = generate_user_guidance(result)

    payload = {
        "detections": result,
        "guidance": guidance,
    }

    if guidance_error:
        payload["guidance_error"] = guidance_error

    return jsonify(payload)

if __name__ == '__main__':
    app.run(debug=True)