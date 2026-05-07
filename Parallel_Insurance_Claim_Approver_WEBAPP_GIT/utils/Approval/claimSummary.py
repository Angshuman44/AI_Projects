from openai import OpenAI
import json
import pandas as pd


def generate_final_claim_summary(
    api_key,
    bill_data,
    preauth_data,
    discharge_data,
    checks,
    procedure_results,
    ped_results,
    claim_amount_result,
    insurance_path,
    final_output
):
    client = OpenAI(api_key=api_key)

    # ---------------- PATIENT LOOKUP ----------------
    policy_number = str(preauth_data.get("policy_number"))
    govt_id = str(preauth_data.get("govt_id"))

    insurance_df=pd.read_csv(insurance_path)
    match = insurance_df[
        (insurance_df["Policy Number"].astype(str) == policy_number) |
        (insurance_df["Govt_ID"].astype(str) == govt_id)
    ]

    patient = match.iloc[0].to_dict() if not match.empty else {}


    prompt = f"""
You are a senior insurance claims auditor.

Generate a PROFESSIONAL 1-PAGE CLAIM SUMMARY.

Include:
1. Patient & Policy Details
2. Pre-Authorization Summary
3. Discharge Summary (clinical findings + treatment)
4. Key Validation Checks
5. PED / Causality Analysis
6. Financial Summary
7. Final Decision (STRICTLY USE PROVIDED DECISION)
8. Clear justification

IMPORTANT:
- DO NOT re-evaluate or change the decision
- USE the provided final decision, reasons, and risk flags exactly
- Only explain and present them professionally

---

FINAL DECISION INPUT (SOURCE OF TRUTH):
Decision: {final_output.get("final_decision")}
Reasons: {json.dumps(final_output.get("decision_reason"), indent=2)}
Risk Flags: {json.dumps(final_output.get("risk_flags"), indent=2)}
Clinical Status: {final_output.get("clinical_status")}
Confidence: {final_output.get("confidence")}

---

PATIENT DETAILS:
Name: {preauth_data.get("patient_name")}
Govt ID: {govt_id}
Policy Number: {policy_number}

POLICY DETAILS:
{json.dumps(patient, indent=2)}

---

PRE-AUTH DATA:
{json.dumps(preauth_data, indent=2)}

---

DISCHARGE SUMMARY:
{discharge_data.get("discharge_summary")}

DIAGNOSIS:
{discharge_data.get("diagnosis_text")}

PROCEDURES:
{discharge_data.get("procedures")}

---

CHECK RESULTS:
{json.dumps(checks, indent=2)}

---

PROCEDURE VALIDATION:
{json.dumps(procedure_results, indent=2)}

---

PED / CAUSALITY:
{json.dumps(ped_results, indent=2)}

---

FINANCIALS:
{json.dumps(claim_amount_result, indent=2)}

---

Return clean structured text (NOT JSON).
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a professional insurance auditor."},
            {"role": "user", "content": prompt}
        ],
        temperature=0, top_p=1
    )

    return response.choices[0].message.content