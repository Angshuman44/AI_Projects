
import json
from openai import OpenAI
import json



def evaluate_claim_with_exclusions(
    discharge_summary,
    diagnosis,
    procedure,
    negations,
    API_KEY
):
    EXCLUSION_DISEASES = [
    "pancreatitis",
    "biliary stones",
    "urinary stones",
    "cataract",
    "glaucoma",
    "retinal detachment",
    "prostate hyperplasia",
    "hydrocele",
    "spermatocele",
    "uterine prolapse",
    "cervix prolapse",
    "endometriosis",
    "fibroids",
    "polycystic ovarian disease",
    "pcod",
    "hysterectomy",
    "hemorrhoids",
    "fissure",
    "fistula",
    "anal abscess",
    "rectal abscess",
    "hernia",
    "osteoarthritis",
    "joint replacement",
    "osteoporosis",
    "connective tissue disorder",
    "rheumatoid arthritis",
    "gout",
    "intervertebral disc disorder",
    "ligament repair",
    "arthroscopy",
    "varicose veins",
    "benign tumor",
    "neoplasm",
    "cyst",
    "sinus",
    "polyps",
    "nodules",
    "mass",
    "lump",
    "ulcer",
    "gastrointestinal erosion",
    "varices",
    "middle ear disease",
    "otitis media",
    "cholesteatoma",
    "tympanic membrane perforation",
    "tonsils",
    "adenoids",
    "nasal septum",
    "sinusitis"
]

    client = OpenAI(api_key=API_KEY)
    prompt = f"""
You are a senior medical auditor in an insurance TPA system.

Your tasks:

1. Diagnosis Validation
- Is the diagnosis supported by the discharge summary?

2. Procedure Justification
- Is the procedure medically appropriate for the diagnosis?

3. Exclusion Evaluation
Check if the case falls under ANY exclusions from the provided list.

4. Advanced Clinical Reasoning (VERY IMPORTANT)
Evaluate the following:

- Medical Necessity:
  Is the treatment necessary and standard of care?

- Investigation-only Admission:
  Was the admission only for diagnostics without treatment?

- Rest Cure / Non-treatment Admission:
  Was the admission mainly for rest, rehab, or non-active treatment?

- Cosmetic Nature:
  Is the procedure cosmetic or aesthetic rather than medically required?

- Substance Abuse:
  Is there any indication of alcohol/drug/substance abuse?
  IMPORTANT: Respect negations like "No alcohol use"

- Unproven Treatment:
  Is the procedure experimental or lacking medical evidence?

---

Return STRICT JSON only:

{{
  "diagnosis_supported": true/false,
  "procedure_justified": true/false,

  "exclusion_applicable": true/false,
  "matched_exclusions": [],

  "medical_necessity": true/false,
  "investigation_only": true/false,
  "rest_cure": true/false,
  "cosmetic": true/false,
  "substance_abuse": true/false,
  "unproven_treatment": true/false,

  "confidence": 0.0-1.0,

  "reason": "clear structured clinical and policy reasoning"
}}

---

EXCLUSION LIST:
{EXCLUSION_DISEASES}

---

DISCHARGE SUMMARY:
{discharge_summary}

---

NEGATIONS:
{negations}

---

DIAGNOSIS:
{diagnosis}

---

PROCEDURE:
{procedure}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a strict, conservative, and highly accurate medical insurance auditor."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,top_p=1
    )

    content= response.choices[0].message.content

    try:
        return json.loads(content)  
    except:
        return {"error": "LLM parsing failed", "raw": content}


