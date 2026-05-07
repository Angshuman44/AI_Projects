from PyPDF2 import PdfReader
from openai import OpenAI
import json
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import re
import os

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




def get_discharge_data(fpath):
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
def extract_medical_info_discharge_summary(text,API_KEY):
    print("🛠️  LLM Processing Text...")
    client = OpenAI(api_key=API_KEY)
    prompt = '''You are a Senior Medical Professional/Doctor and Clinical Information Extraction Specialist.

Extract structured clinical information from the given discharge summary.

Your task is to accurately identify ONLY clinically valid and explicitly supported information from the document.

RULES:

1. DIAGNOSES
- Include only confirmed diagnoses explicitly stated in assessment, impression, diagnosis, final diagnosis, discharge diagnosis, or clinician summary sections.
- Do NOT infer diagnoses from medications alone.
- Do NOT include ruled-out, suspected, query, possible, or negated conditions.

2. NEGATIONS
- STRICTLY FOLLOW: Capture all explicitly denied symptoms, denied diseases, and negative history statements.
- STRICTLY FOLLOW: If a condition is followed by "No", "Nil", "Absent", "Negative", "Denied", treat it as NEGATION
Examples:
  - "No fever"
  - "No seizures"
  - "History of Diabetes: No"
  - "No CAD"
  - "No alcohol use"


3. PROCEDURES
- Include surgeries, interventions, operations, procedures, implants, ventilation, tracheostomy, gastrostomy, cesarean section, decompression, grafting, etc.

4. COMPLICATIONS
- Include complications explicitly documented during admission, surgery, or recovery.

5. HISTORY CONDITIONS
- STRICTLY FOLLOW: If a condition is followed by "No", "Nil", "Absent", "Negative", "Denied", treat it as DONOT INCLUDE IN history conditions.
- STRICTLY FOLLOW: First read the entire text and then decide on the history, sometimes there is mention of a disease and there is another field marked as Yes/No
- Include only past medical history or chronic comorbidities that are explicitly PRESENT.

6. NORMALIZATION
- Normalize terminology where clear:
  - increased liquor → polyhydramnios
  - DM → diabetes mellitus
  - HTN → hypertension
  - CAD → coronary artery disease
  - AVN → avascular necrosis
- Preserve clinical meaning exactly.

7. PATIENT FIELDS
- Extract patient_name exactly as written.
- Extract discharge_date exactly as written.
- discharge_date MUST be in DD/MM/YYYY format (e.g., 19/09/2019), If the date appears in another format (e.g., 19-09-2019, 19-Sep-2019, 2019-09-19), convert it to DD/MM/YYYY


8. NUMBER OF DAYS
- Extract the total number of days the patient stayed at the hospital ie from admission date to discharge date and return as "stay_duration"

9. IGNORE
- Billing, insurance, payment, phone numbers, addresses, IDs unless part of patient identity.

10. Procedure description
- Carefully read the entire discharge doccument and generate a professional summary of the procedure used for the disease.
  example:
        For diagnosis A a procedure of B was followed as per the doctor.
- return the summary as "procedure_summary"
        
11. Discharge Summary
- As a Senior Medical Doctor prepare a professional summary of the patent's entire case excluding personal details and bill details.
- return this as "discharge_summary"

12. ICD Code
- As a Senior Medical Doctor return the latest ICD10 code for the primary diagnosis as "diagnosis_ICD10_code"

13. OUTPUT
- If field missing use "" or [].
- Return ONLY valid JSON.
- No markdown.
- No explanation.

Return STRICT JSON in this format:

{
  "patient_name": "",
  "discharge_date": "",
  "stay_duration": "",
  "diagnosis_text": [],
  "diagnosis_ICD10_code": "",
  "history_conditions": [],
  "procedures": [],
  "procedure_summary": "",
  "complications": [],
  "negations": [],
  "discharge_summary": ""
}'''
   

    response = client.responses.create(
        model="o3",            #Replace with O3 finally
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
        structured_data_discharge = safe_json_load(raw_output)
    except:
        print("⚠️ JSON parsing failed. Raw output:")
        print(raw_output)
        structured_data_discharge = {}

    return structured_data_discharge


def runDischarge(discharge_summary_path,API_KEY):

    if not os.path.exists(discharge_summary_path):
        print(f"{discharge_summary_path} does not exist.")
    else:

        text_data = get_discharge_data(discharge_summary_path)


        if len(text_data.strip()) > 100:
            print("\n✅ Discharge Summary Data Extracted Successfully\n")

        structured_discharge_summary_output = extract_medical_info_discharge_summary(text_data,API_KEY)

        # print("\n✅ Structured Discharge Summary Details Ready:\n")
        # print(json.dumps(structured_discharge_summary_output, indent=2))
    
    return structured_discharge_summary_output