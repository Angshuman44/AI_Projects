from PyPDF2 import PdfReader
from openai import OpenAI
import json
import os
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import re

def safe_json_load(raw_output):
    try:
        return json.loads(raw_output)
    except:
        # extract JSON block
        match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return {}

def get_bill_data(fpath):
    text = ""

    # -------------------------------
    # Step 1: Try PyPDF (fast)
    # -------------------------------
    try:
        pdf = PdfReader(fpath)
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except:
        pass

    # -------------------------------
    # Step 2: Check if text is usable
    # -------------------------------
    if len(text.strip()) > 100:   # threshold
        print("✅ PyPDF SUCCESS...")
        return text

    print("⚠️ PyPDF FAILED, using OCR based Tesseract...")

    # -------------------------------
    # Step 3: OCR fallback
    # -------------------------------
    text = ""
    images = convert_from_path(fpath)

    for i, img in enumerate(images):
        page_text = pytesseract.image_to_string(img)
        text += page_text + "\n"
    print("✅ Tesseract SUCCESS...")
    return text



def extract_medical_bill_info(text,API_KEY):
    print("🛠️  LLM Processing Text...")
    client = OpenAI(api_key=API_KEY)

    prompt = """
You are a Senior Medical Billing Auditor and Hospital Claims Specialist.

Your job is to carefully review hospital bills, discharge summaries, and invoice text, then accurately extract billing information.

Instructions:

* Read the document carefully.
* Extract only values explicitly mentioned in the text.
* If multiple values exist, prefer the final billed amount.
* Standardize currency values as plain numbers without commas or symbols.
* If a field is missing, return an empty string.
* Ignore unrelated clinical notes unless needed for patient name.
* Normalize all extracted dates.

Extract the following:

1. patient_name
2. total_bill
3. room_rental_charges
4. bill_date

Return ONLY valid JSON in this exact format:

{
"patient_name": "",
"total_bill": "",
"room_rental_charges": "",
"bill_date": ""
}

Rules:

* bill_date MUST be in DD/MM/YYYY format (e.g., 19/09/2019)
* If the date appears in another format (e.g., 19-09-2019, 19-Sep-2019, 2019-09-19), convert it to DD/MM/YYYY
* Do NOT include any text outside the JSON
"""

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_text", "text": f"DOCUMENT:\n{text}"}
                ]
            }
        ],
        temperature=0
    )

    raw_output = response.output_text

    # -------------------------------
    # Safe JSON parsing
    # -------------------------------
    try:
        structured_bill_data = safe_json_load(raw_output)
    except:
        print("⚠️ JSON parsing failed. Raw output:")
        print(raw_output)

        structured_bill_data = {
            "patient_name": "",
            "total_bill": "",
            "room_rental_charges": "",
            "bill_date": ""
        }

    return structured_bill_data

def runBill(bill_path,API_KEY):

    if not os.path.exists(bill_path):
        print(f"{bill_path} does not exist.")
    else:

        text_data = get_bill_data(bill_path)

        if len(text_data.strip()) > 100:
            print("\n✅ Bill Data Extracted Successfully\n")

        structured_bill_output = extract_medical_bill_info(text_data,API_KEY)

        # print("\n✅ Structured Bill Details Ready:\n")
        # print(json.dumps(structured_bill_output, indent=2))
    
    return structured_bill_output