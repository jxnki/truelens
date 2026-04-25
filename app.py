from flask import Flask, request, jsonify, render_template
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

API_URL = os.getenv(
    "HF_API_URL",
    "https://router.huggingface.co/hf-inference/models/prithivMLmods/Deep-Fake-Detector-v2-Model",
)
LEGACY_API_URL = "https://api-inference.huggingface.co/models/prithivMLmods/Deep-Fake-Detector-v2-Model"
API_KEY = os.getenv("HF_API_KEY") or os.getenv("HF_API")

headers = {
    "Authorization": f"Bearer {API_KEY}"
}

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

    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)