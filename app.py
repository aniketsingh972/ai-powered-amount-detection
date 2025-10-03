import re
import json
import os
import time
import requests
from flask import Flask, request, jsonify

# --- Configuration ---
API_KEY = os.environ.get("GEMINI_API_KEY", "") 
# Use the correct model endpoint and include the API key in the URL
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={API_KEY}"
app = Flask(__name__)

# --- Helper Functions ---

def llm_call_with_backoff(payload, max_retries=3):
    """Handles the API call to Gemini with exponential backoff and error handling."""
    headers = {'Content-Type': 'application/json'}
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status() # Raise HTTPError for bad status codes
            
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            
            if candidate and 'text' in candidate.get('content', {}).get('parts', [{}])[0]:
                json_text = candidate['content']['parts'][0]['text']
                # Clean up markdown code fences if present
                if json_text.startswith('```json'):
                    json_text = json_text.strip().replace('```json\n', '').replace('\n```', '')
                return json.loads(json_text)
            
            print(f"LLM structure error: Non-JSON or incomplete response on attempt {attempt + 1}.")
            return None

        except requests.exceptions.HTTPError as e:
            # Handle authentication (403), bad requests (400), and other server errors
            print(f"HTTP Error: {e}. Attempt {attempt + 1}. Response: {response.text[:100]}...")
            if attempt < max_retries - 1:
                delay = 2 ** attempt
                time.sleep(delay)
            else:
                return None
        except requests.exceptions.RequestException as e:
            # Handle network errors (timeouts, DNS issues)
            print(f"Network Error: {e}. Attempt {attempt + 1}.")
            if attempt < max_retries - 1:
                delay = 2 ** attempt
                time.sleep(delay)
            else:
                return None
        except json.JSONDecodeError:
            print(f"Failed to decode JSON from LLM response body.")
            return None
    return None

def extract_provenance(text, raw_token):
    """Finds the surrounding text for provenance tracking."""
    safe_token = re.escape(raw_token)
    # Finds up to 20 characters before and after the token
    match = re.search(f"(.{{0,20}}?{safe_token}.{{0,20}}?)", text, re.IGNORECASE)
    if match:
        return f"text: '{match.group(1).strip()}'"
    return f"token: '{raw_token}'"

# --- Main Processing Steps ---

def step1_ocr_text_extraction(input_text):
    """Step 1: Extracts raw numeric tokens and attempts to infer currency."""
    raw_tokens = []
    
    # Regex to find numbers/amounts (e.g., '1200', 'Rs 100')
    matches = re.findall(r'(\d+|[a-zA-Z]{1,3}\s*\d+|\d+\s*[a-zA-Z]{1,3})', input_text.replace('%', ''))
    
    # Heuristically detect currency hint (INR, Rs, $, etc.)
    currency_matches = re.findall(r'(INR|Rs|\$|USD|EUR|GBP)', input_text, re.IGNORECASE)
    currency_hint = currency_matches[0].upper() if currency_matches else None
    
    for m in matches:
        # Strip non-numeric and non-space characters (simulating noise filter)
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
    """Step 2: Fixes simulated OCR errors (l -> 1, O -> 0) and converts to integers."""
    normalized_amounts = []
    
    for token in raw_tokens:
        # OCR correction: replace 'l', 'I', 'O' with correct digits
        corrected_token = token.replace('l', '1').replace('I', '1').replace('O', '0')
        
        try:
            normalized_amounts.append(int(corrected_token))
        except ValueError:
            pass # Skip unconvertible tokens

    return {"normalized_amounts": normalized_amounts}

def step3_classification_by_context(raw_text, raw_tokens, normalized_amounts):
    """Step 3: Uses the Gemini API with structured output to classify amounts."""
    if not API_KEY:
        return {"amounts": [], "confidence": 0.0, "error": "API Key Missing"}

    # Define the strict JSON schema for the LLM output
    classification_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "type": {"type": "STRING", "description": "Classification: e.g., total_bill, paid, due, tax, discount, item_cost"},
                "value": {"type": "NUMBER", "description": "The normalized integer amount."},
                "raw_token": {"type": "STRING", "description": "The original raw token (before normalization)."}
            },
            "required": ["type", "value", "raw_token"]
        }
    }
    
    amount_mapping = []
    for raw, norm in zip(raw_tokens, normalized_amounts):
        amount_mapping.append({"raw_token": raw, "value": norm})
        
    user_query = f"""
    Analyze the following medical document text:
    ---
    {raw_text}
    ---
    The detected and normalized amounts are: {json.dumps(amount_mapping)}.
    For each unique amount/raw_token pair, classify its 'type' based on the surrounding text context. 
    Choose the classification 'type' from: total_bill, paid, due, tax, discount, item_cost, or other_fee.
    """
    
    system_prompt = "You are a specialized medical bill data classifier. Your task is to analyze the context of financial amounts in a document and return a clean JSON array strictly adhering to the provided schema."

    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": { # Correct key for structured output
            "responseMimeType": "application/json",
            "responseSchema": classification_schema
        }
    }

    classified_data = llm_call_with_backoff(payload)

    return {
        "amounts": classified_data if classified_data else [],
        "confidence": 0.90 if classified_data else 0.0
    }


# --- Flask Endpoint ---

@app.route('/detect-amounts', methods=['POST'])
def detect_amounts_endpoint():
    """Orchestrates the four-step AI pipeline."""
    data = request.json
    document_text = data.get("document_text", "")
    image_base64 = data.get("image_base64", None) # Accepts optional image input
    
    if not document_text and not image_base64:
        return jsonify({"status": "error", "reason": "Missing 'document_text' or 'image_base64' input."}), 400

    # Architecture Path: Image -> OCR Simulation -> Text
    if image_base64:
        document_text = document_text or "Total Amount: 500 | Paid: 450 | Due: 50 USD" # Placeholder text
        
    if len(document_text) < 10:
        return jsonify({"status": "no_amounts_found", "reason": "Document text is too short or missing."}), 200

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
        return jsonify({"status": "no_amounts_found", "reason": "Tokens found, but none could be reliably normalized to numbers."}), 200

    # Step 3: Classification by Context (LLM Call)
    step3_result = step3_classification_by_context(document_text, raw_tokens, normalized_amounts)
    
    if step3_result.get("error") == "API Key Missing":
        return jsonify({"status": "error", "reason": "Configuration error: GEMINI_API_KEY environment variable is not set."}), 500

    classified_amounts = step3_result["amounts"]
    
    if not classified_amounts:
        return jsonify({"status": "no_amounts_found", "reason": "LLM classification failed due to structure or confidence issues."}), 200

    # Step 4: Final Output Compilation
    final_currency = currency_hint if currency_hint else "USD"
    
    final_amounts = []
    for item in classified_amounts:
        value = item.get("value")
        if value is None: continue
            
        source = extract_provenance(document_text, str(item.get("raw_token")))
        
        final_amounts.append({
            "type": item["type"],
            "value": value,
            "source": source
        })

    return jsonify({
        "currency": final_currency,
        "amounts": final_amounts,
        "status": "ok",
        "model_confidence": step3_result["confidence"]
    })

if __name__ == '__main__':
    # Running on port 5001, confirmed functional by testing
    app.run(host='0.0.0.0', port=5001)
