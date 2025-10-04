import re
import json
import os
import time
import base64
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image
import pytesseract  # OCR engine

# ---------------- Load Environment Variables ----------------
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={API_KEY}"

app = Flask(__name__)


# ---------------- Helper Functions ----------------
def llm_call_with_backoff(payload, max_retries=3):
    headers = {'Content-Type': 'application/json'}
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            candidate = result.get('candidates', [{}])[0]

            if candidate and 'text' in candidate.get('content', {}).get('parts', [{}])[0]:
                json_text = candidate['content']['parts'][0]['text']
                # remove ```json ... ``` wrappers if Gemini adds them
                if json_text.startswith('```json'):
                    json_text = json_text.strip().replace('```json\n', '').replace('\n```', '')
                return json.loads(json_text)
            return None

        except Exception as e:
            print(f"LLM call error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
    return None


def extract_provenance(text, raw_token):
    safe_token = re.escape(raw_token)
    match = re.search(f"(.{{0,20}}?{safe_token}.{{0,20}}?)", text, re.IGNORECASE)
    if match:
        return f"text: '{match.group(1).strip()}'"
    return f"token: '{raw_token}'"


# ---------------- Pipeline Steps ----------------
def step1_ocr_text_extraction(input_text):
    raw_tokens = []
    matches = re.findall(r'(\d+|[a-zA-Z]{1,3}\s*\d+|\d+\s*[a-zA-Z]{1,3})', input_text.replace('%', ''))
    currency_matches = re.findall(r'(INR|Rs|\$|USD|EUR|GBP)', input_text, re.IGNORECASE)
    currency_hint = currency_matches[0].upper() if currency_matches else None

    for m in matches:
        token = re.sub(r'[a-zA-Z\s]+', '', m).strip()
        if token and len(token) > 1:
            raw_tokens.append(token)

    if not raw_tokens:
        return {"status": "no_amounts_found", "reason": "document too noisy or no numeric tokens found"}

    return {
        "raw_tokens": raw_tokens,
        "currency_hint": currency_hint,
    }


def step2_normalization(raw_tokens):
    normalized_amounts = []
    for token in raw_tokens:
        corrected_token = token.replace('l', '1').replace('I', '1').replace('O', '0')
        try:
            normalized_amounts.append(int(corrected_token))
        except ValueError:
            pass
    return {"normalized_amounts": normalized_amounts}


def step3_classification_by_context(raw_text, raw_tokens, normalized_amounts):
    if not API_KEY:
        return {"amounts": [], "confidence": 0.0, "error": "API Key Missing"}

    classification_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "type": {"type": "STRING"},
                "value": {"type": "NUMBER"},
                "raw_token": {"type": "STRING"}
            },
            "required": ["type", "value", "raw_token"]
        }
    }

    amount_mapping = [{"raw_token": raw, "value": norm} for raw, norm in zip(raw_tokens, normalized_amounts)]

    user_query = f"""
    Analyze the following document text:
    ---
    {raw_text}
    ---
    The detected and normalized amounts are: {json.dumps(amount_mapping)}.
    Classify each amount as: total_bill, paid, due, tax, discount, item_cost, or other_fee.
    """

    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": "You are a financial document classifier."}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": classification_schema
        }
    }

    classified_data = llm_call_with_backoff(payload)
    return {"amounts": classified_data if classified_data else [], "confidence": 0.90 if classified_data else 0.0}


# ---------------- Flask Endpoint ----------------
@app.route('/detect-amounts', methods=['POST'])
def detect_amounts_endpoint():
    """
    Accepts either:
    1. Raw text (JSON key: document_text)
    2. Base64 image (JSON key: image_base64)
    3. Uploaded file (form-data key: file)
    """
    document_text = None

    # --- Case 1: JSON input (text or base64 image)
    if request.is_json:
        data = request.get_json()
        document_text = data.get("document_text")
        image_base64 = data.get("image_base64")

        if image_base64:
            try:
                image_data = base64.b64decode(image_base64)
                image = Image.open(BytesIO(image_data))
                document_text = pytesseract.image_to_string(image)
            except Exception as e:
                return jsonify({"status": "error", "reason": f"Image decode failed: {str(e)}"}), 400

    # --- Case 2: Multipart form upload (file)
    elif "file" in request.files:
        try:
            file = request.files["file"]
            image = Image.open(file.stream)
            document_text = pytesseract.image_to_string(image)
        except Exception as e:
            return jsonify({"status": "error", "reason": f"File upload failed: {str(e)}"}), 400

    # If still no text found
    if not document_text or len(document_text.strip()) < 5:
        return jsonify({"status": "error", "reason": "No valid document_text or image provided"}), 400

    # Step 1: Extraction
    step1_result = step1_ocr_text_extraction(document_text)
    if step1_result.get("status") == "no_amounts_found":
        return jsonify(step1_result), 200

    raw_tokens = step1_result["raw_tokens"]
    currency_hint = step1_result["currency_hint"]

    # Step 2: Normalization
    step2_result = step2_normalization(raw_tokens)
    normalized_amounts = step2_result["normalized_amounts"]

    if not normalized_amounts:
        return jsonify({"status": "no_amounts_found", "reason": "Tokens found but not valid numbers"}), 200

    # Step 3: Classification (LLM)
    step3_result = step3_classification_by_context(document_text, raw_tokens, normalized_amounts)
    if step3_result.get("error") == "API Key Missing":
        return jsonify({"status": "error", "reason": "Missing GEMINI_API_KEY"}), 500

    classified_amounts = step3_result["amounts"]
    if not classified_amounts:
        return jsonify({"status": "no_amounts_found", "reason": "LLM classification failed"}), 200

    # Step 4: Final Response
    final_currency = currency_hint if currency_hint else "USD"
    final_amounts = []
    for item in classified_amounts:
        if item.get("value") is None:
            continue
        source = extract_provenance(document_text, str(item.get("raw_token")))
        final_amounts.append({"type": item["type"], "value": item["value"], "source": source})

    return jsonify({
        "currency": final_currency,
        "amounts": final_amounts,
        "status": "ok",
        "model_confidence": step3_result["confidence"],
        "raw_text": document_text.strip()
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)


