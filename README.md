AI-Powered Amount Detection Service (Problem Statement 8)
Overview
This project implements a backend microservice to extract, normalize, and contextually classify financial amounts from noisy text data (simulated OCR output from medical bills/receipts). The core is a four-step pipeline that leverages Python's deterministic logic (Regex, Normalization) and the Gemini API for high-value contextual classification.


1. Architecture and Pipeline
The service follows a strict, sequential pipeline:

Ingestion & Tokenization (Python/Regex): Extracts raw, noisy numeric strings and identifies currency hints (Rs, INR, etc.).

Numeric Normalization (Python Logic): Cleans up common OCR errors (e.g., l → 1, O → 0) and maps tokens to reliable integer values.

Context Classification (Gemini API): The model assigns a logical type (total_bill, paid, due, etc.) to each normalized amount based on the surrounding text. This is enforced by a strict JSON schema.

Finalization & Provenance (Python): Compiles the final response, ensuring currency is present and adding the exact source text fragment for auditing (provenance).

2. Setup and Installation
Prerequisites
Python 3.8+

A Gemini API Key (Obtained from Google AI Studio)

Installation Steps
Clone the repository (or navigate to your plum directory):

cd plum

Create and Activate Virtual Environment:

python3 -m venv venv 
source venv/bin/activate

Install Dependencies:
(Requires Flask and requests from requirements.txt)

pip install -r requirements.txt

Set Environment Variable (Crucial for API Authentication):
Replace the placeholder with your actual key. This command must be run every time you open a new terminal or restart your server.

export GEMINI_API_KEY="YOUR_ACTUAL_API_KEY_STRING_HERE"

Run the Flask Application:
The server runs on port 5001.

python app.py

(The server should output: * Running on http://127.0.0.1:5001)

3. API Usage Examples and Testing
The service exposes a single POST endpoint. All requests must be sent with the Content-Type: application/json header.

Endpoint: POST /detect-amounts (running on http://127.0.0.1:5001 or your public ngrok URL)

Example 1: Standard Noisy Text Input (Core Functionality Test)
This test validates OCR error correction, normalization, and the core AI classification.

# REQUEST (cURL)
curl -X POST [http://127.0.0.1:5001/detect-amounts](http://127.0.0.1:5001/detect-amounts) \
-H "Content-Type: application/json" \
-d '{
    "document_text": "T0tal: Rs l200 | Pald: 1000 | Due: 200 | Discount: l0% (Includes tax 50)"
}'

Expected Structured Response:
The type and source fields demonstrate successful context classification and provenance tracking.

{
  "currency": "RS",
  "amounts": [
    { "type": "total_bill", "value": 1200, "source": "text: 'T0tal: Rs l200'" },
    { "type": "paid", "value": 1000, "source": "text: 'Pald: 1000'" },
    { "type": "due", "value": 200, "source": "text: 'Due: 200'" },
    { "type": "tax", "value": 50, "source": "text: '(Includes tax 50)'" }
  ],
  "status": "ok",
  "model_confidence": 0.9
}

Example 2: Guardrail Test (No Amounts Found)
This test validates the robustness and error handling.

# REQUEST (cURL)
curl -X POST [http://127.0.0.1:5001/detect-amounts](http://127.0.0.1:5001/detect-amounts) \
-H "Content-Type: application/json" \
-d '{"document_text": "Patient records updated. No charges or financial data listed here."}'

Expected Guardrail Response:
The system correctly fails early and returns the defined failure structure.

{
  "status": "no_amounts_found",
  "reason": "document too noisy or no numeric tokens found"
}

Example 3: Image Input Simulation (Architecture Test)
This test validates the architectural path for image inputs.

# REQUEST (cURL)
curl -X POST [http://127.0.0.1:5001/detect-amounts](http://127.0.0.1:5001/detect-amounts) \
-H "Content-Type: application/json" \
-d '{
    "image_base64": "iVBORw0KGgoAAAANSUhEUgAAA",
    "document_text": ""
}'
