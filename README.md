# AI Document Amount Extractor

A Python Flask app that extracts and classifies monetary amounts from text documents and images using OCR and AI (Gemini API).

---

## Features

- Accepts raw text or images (Base64 or uploaded file)
- Extracts numeric tokens and corrects OCR errors
- Classifies amounts: `total_bill`, `paid`, `due`, `tax`, `discount`, `item_cost`, `other_fee`
- Returns structured JSON with values, types, currency, and text source

---

## Architecture

The system architecture consists of three main components:

- **User Input:** Raw text or image uploaded via the API
- **Flask API:** Handles requests and responses
- **OCR Module:** Converts image text into machine-readable text
- **Amount Extraction & Classification:** AI model processes text to detect numeric values and classify them
- **JSON Output:** Structured output including value, type, currency, and source text

---

## Installation

```bash
git clone <repo-url>
cd <repo-folder>

python -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows

pip install -r requirements.txt

---

### Input
![Input Document](images/input.png)

### Output
![Output Part](images/output.png)

### YAML Representation
```yaml
input:
  image: "images/input.png"

output:
  image: "images/output.png"

Output Image:

![Extracted Amounts](images/output.png)
