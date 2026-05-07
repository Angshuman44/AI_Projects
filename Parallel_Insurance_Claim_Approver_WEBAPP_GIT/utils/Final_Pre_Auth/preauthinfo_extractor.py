from PyPDF2 import PdfReader
from openai import OpenAI
import json
import os
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import re

CONFIG_PATH = r"config.yaml"



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


def get_PreAuth_data(fpath):
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



# -------------------------------
# Step 2: Initialize OpenAI
# -------------------------------
def get_llm():
    return 


# -------------------------------
# Step 3: Extract structured medical info
# -------------------------------
def extract_medical_PreAuth_info(text,API_KEY):
    print("🛠️  LLM Processing Text...")
    client = OpenAI(api_key=API_KEY)
    prompt = f"""
You are an expert health insurance claims data extraction analyst.

Analyze the provided Cashless Claim Form / Pre-Authorization Form text.

Extract all relevant fields accurately and return ONLY valid JSON.

Rules:

1. Use exact values from the document.
2. Preserve names, diagnosis, procedures, dates exactly where possible.
3. Correct minor OCR errors when obvious.
4. If any field missing return "".
5. Return JSON only. No markdown or explanation.
6. Generate a short professional summary in "general_summary".
7. Costs should contain numbers only where possible.
8. admission_date MUST be in DD/MM/YYYY format (e.g., 19/09/2019), If the date appears in another format (e.g., 19-09-2019, 19-Sep-2019, 2019-09-19), convert it to DD/MM/YYYY

JSON FORMAT:

{{
  "patient_name": "",
  "age": "",
  "gender": "",
  "policy_number": "",
  "govt_id": "",

  "hospital_name": "",
  "hospital_code": "",
  "doctor_name": "",
  "admission_date": "",

  "diagnosis": "",
  "secondary_diagnosis": "",
  "icd10_code": "",
  "procedure": "",

  "general_summary": "",

  "room_charges_per_day": "",
  "investigation_charges": "",
  "doctor_fees": "",
  "approximate_bill_total": "",

  "history": {{
      "diabetes": "",
      "hypertension": "",
      "heart_disease": "",
      "hyperlipidemia": "",
      "osteoarthritis": "",
      "asthma_copd_bronchitis": "",
      "cancer": "",
      "alcohol_drug_abuse": "",
      "hiv_std": "",

      "other_conditions": {{
          "condition_name_1": "",
          "condition_name_2": "",
          "condition_name_3": ""
      }}
  }}
}}

History Rules:

- If explicitly mentioned = "Yes"
- If absent = "No Mention"
- If implied = "Suspected"

Other Conditions Rules:

1. Any past illness, neurological disease, surgery, chronic issue, implant, tube, tracheostomy, gastrostomy, stroke, seizure disorder, encephalopathy, renal disease etc. not listed above must go inside:

"other_conditions"

2. Use condition name as KEY and value as:
"Yes"

Example:

"other_conditions": {{
   "acute meningoencephalitis with sequelae": "Yes",
   "previous tracheostomy": "Yes",
   "previous gastrostomy": "Yes"
}}

3. If none found:

"other_conditions": {{}}

DOCUMENT TEXT:

{text}
"""
   

    response = client.responses.create(
        model="gpt-4o-mini",            #Replace with O3 finally
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_text", "text": f"DOCUMENT:\n{text}"}
                ]
            }
        ]
    )

    raw_output = response.output_text

    # -------------------------------
    # Step 4: Safe JSON parsing
    # -------------------------------
    try:
        # structured_data = json.loads(raw_output)
        structured_data_PreAuth = safe_json_load(raw_output)
    except:
        print("⚠️ JSON parsing failed. Raw output:")
        print(raw_output)
        structured_data_PreAuth = {}

    return structured_data_PreAuth


def runPreAuth(form_path,API_KEY):

    if not os.path.exists(form_path):
        print(f"{form_path} does not exist.")
    else:
        
        text_data = get_PreAuth_data(form_path)


        if len(text_data.strip()) > 100:
            print("\n✅ Form Data Extracted Successfully\n")

        structured_PreAuthForm_output = extract_medical_PreAuth_info(text_data,API_KEY)
        
        # print("\n✅ Structured Pre Authorization Form Details Ready:\n")
        # print(json.dumps(structured_PreAuthForm_output, indent=2))
    
    return structured_PreAuthForm_output