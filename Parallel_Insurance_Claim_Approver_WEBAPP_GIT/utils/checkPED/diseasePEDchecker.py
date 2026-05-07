from openai import OpenAI
import pandas as pd
import json



def build_patient_history_context(govt_id, policy_number, history_df, claims_df):
    history = history_df[
        (history_df["Govt_ID"] == govt_id) |
        (history_df["Policy_Number"] == policy_number)
    ]

    claims = claims_df[
        (claims_df["Govt_ID"] == govt_id) |
        (claims_df["Policy_Number"] == policy_number)
    ]

    return {
        "medical_history": history.to_dict(orient="records"),
        "historical_claims": claims.to_dict(orient="records")
    }

def llm_causality_check(
    api_key,
    discharge_summary,
    diagnosis,
    procedure,
    patient_context,
    threshold=0.80
):
    client = OpenAI(api_key=api_key)

    prompt = f"""
You are a senior insurance medical auditor.

Your task:

1. Analyze if CURRENT PRIMARY DIAGNOSIS is causally linked to:
   - Past medical history
   - Previous claims

2. Determine if this is likely a progression or complication of past disease.

3. Estimate confidence (0 to 1)

---

DISCHARGE SUMMARY:
{discharge_summary}

CURRENT DIAGNOSIS:
{diagnosis}

PROCEDURE:
{procedure}

---

PATIENT MEDICAL HISTORY:
{patient_context["medical_history"]}

PAST CLAIMS:
{patient_context["historical_claims"]}

---

Return STRICT JSON:

{{
  "causal_link": true/false,
  "reason": "clinical reasoning",
  "confidence": 0-1
}}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a strict insurance medical auditor."},
            {"role": "user", "content": prompt}
        ],
        temperature=0, top_p=1
    )

    # Parse safely
    try:
        result = json.loads(response.choices[0].message.content)
    except Exception:
        return {
            "causal_link": False,
            "confidence": 0,
            "decision": "REVIEW",
            "reason": "LLM parsing failed"
        }

    # Final decision logic (your requirement)
    confidence = result.get("confidence", 0)
    causal = result.get("causal_link", False)

    if causal and confidence >= threshold:
        decision = "PASS"
    elif causal:
        decision = "REVIEW"
    else:
        decision = "PASS"  # no causal link → safe

    return {
        "causal_link": causal,
        "confidence": confidence,
        "decision": decision,
        "reason": result.get("reason", "")
    }



def run_causality_pipeline(
    medical_history_path,
    history_claims_path,
    pre_auth_data,
    discharge_data,
    api_key
):
    # Load datasets
    medical_history_df = pd.read_csv(medical_history_path)
    historical_claims_df = pd.read_csv(history_claims_path)

    # Build patient context
    patient_context = build_patient_history_context(
        govt_id=pre_auth_data.get("govt_id"),
        policy_number=pre_auth_data.get("policy_number"),
        history_df=medical_history_df,
        claims_df=historical_claims_df
    )

    # Run LLM causality check
    result = llm_causality_check(
        api_key=api_key,
        discharge_summary=discharge_data.get("discharge_summary"),
        diagnosis=discharge_data.get("diagnosis_text")[0],
        procedure=discharge_data.get("procedures")[0],
        patient_context=patient_context
    )

    return {
        "patient_context": patient_context,
        "causality_result": result
    }