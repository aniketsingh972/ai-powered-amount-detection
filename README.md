# AI Document Amount Extractor

A Python Flask app that extracts and classifies monetary amounts from text documents and images using OCR and AI (Gemini API).

---

## Features

- Accepts raw text or images (Base64 or uploaded file)
- Extracts numeric tokens and corrects OCR errors
- Classifies amounts: `total_bill`, `paid`, `due`, `tax`, `discount`, `item_cost`, `other_fee`
- Returns structured JSON with values, types, currency, and text source

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
## Example: Input and Output Images
 
##Example
Input Image:

![Input Document](images/input.png)

Output Image:

![Extracted Amounts](images/output.png)
