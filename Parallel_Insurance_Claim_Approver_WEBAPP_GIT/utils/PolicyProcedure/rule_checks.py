
from datetime import datetime
import pandas as pd
import re
from dateutil.relativedelta import relativedelta

# ---------------- FUNCTIONS ----------------

def lookup_patient(df, govt_id=None, policy_number=None):
    if govt_id:
        match = df[df["Govt_ID"].astype(str) == str(govt_id)]
        if not match.empty:
            return match.iloc[0].to_dict()

    if policy_number:
        match = df[df["Policy Number"].astype(str) == str(policy_number)]
        if not match.empty:
            return match.iloc[0].to_dict()

    return None

def parse_date(date_str):
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
    raise ValueError(f"Unknown date format: {date_str}")


def check_policy_active(patient, admission_date):
    try:
        admission = parse_date(admission_date)
        purchase = parse_date(patient["Policy_Purchase_Date"])

        # Clean waiting period
        waiting_raw = str(patient.get("Waiting_Period", "")).strip().lower()
        
        if not waiting_raw or waiting_raw in ["nan", "none"]:
            waiting_years = 0
        else:
            waiting_years = int(re.findall(r"\d+", waiting_raw)[0])

        eligible_date = purchase + relativedelta(years=waiting_years)

        return {
            "active": admission >= eligible_date,
            "admission_date": admission.strftime("%d/%m/%Y"),
            "policy_purchase_date": purchase.strftime("%d/%m/%Y"),
            "waiting_period_years": waiting_years,
            "eligible_after": eligible_date.strftime("%d/%m/%Y")
        }

    except Exception as e:
        return {
            "active": False,
            "error": str(e), 
            "admission_date": admission_date,
            "policy_purchase_date": patient.get("Policy_Purchase_Date"),
            "waiting_period_years": None,
            "eligible_after": None
        }

def compare_room_rent(patient, actual_rent):
    try:
        actual = float(actual_rent)
        limit = float(patient["Room_Rent_Per_Day_Covered"])
        return {
            "allowed": actual <= limit,
            "limit": limit,
            "excess": max(0, actual - limit)
        }
    except:
        return {"allowed": False, "limit": None, "excess": None}


def is_bill_within_30_days(bill_date, discharge_date):
    try:
        bill = datetime.strptime(bill_date, "%d/%m/%Y")
        discharge = datetime.strptime(discharge_date, "%d/%m/%Y")
        return 0 <= (bill - discharge).days <= 30
    except:
        return False


def validate_icd_fuzzy(pre_auth_icd, discharge_icd):
    try:
        return pre_auth_icd.split(".")[0] == discharge_icd.split(".")[0]
    except:
        return False


def check_sum_insured(policy, bill):
    try:
        total_bill = float(bill["total_bill"])
        sum_insured = float(policy["Fixed_Coverage_Amount"])
        return {
            "covered": total_bill <= sum_insured,
            "limit": sum_insured,
            "excess": max(0, total_bill - sum_insured)
        }
    except:
        return {"covered": False, "limit": None, "excess": None}


def check_negation_exclusions(negations, keywords):
    negations = [str(x).lower() for x in negations]
    present, negated = [], []

    for kw in keywords:
        kw = kw.lower()

        if any(kw in s and ("no" in s or "nil" in s) for s in negations):
            negated.append(kw)
        elif any(kw in s for s in negations):
            present.append(kw)

    return {
        "flagged": len(present) > 0,
        "present": present,
        "negated": negated
    }


def check_hospital_exclusion(hospital_code, exclusion_df):
    try:
        excluded = exclusion_df["Hospital Code"].astype(str).str.strip().values
        return hospital_code in excluded
    except:
        return False
# ---------------- MASTER PIPELINE ----------------

def run_claim_checks(
    bill_data,
    pre_auth_data,
    discharge_data,
    insurance_path,
    exclusionHospitalpath
):

    insurance_df=pd.read_csv(insurance_path)
    exclusion_hospitals_df=pd.read_csv(exclusionHospitalpath)
    patient = lookup_patient(
        insurance_df,
        govt_id=pre_auth_data.get("govt_id"),
        policy_number=pre_auth_data.get("policy_number")
    )

    if not patient:
        return {"error": "Patient not found"}

    checks_result = {}
    # Policy
    checks_result["policy_active"] = check_policy_active(
        patient, pre_auth_data.get("admission_date")
    )

    # Room rent
    checks_result["room_rent"] = compare_room_rent(
        patient, pre_auth_data.get("room_charges_per_day")
    )

    # Bill timing
    checks_result["bill_within_30_days"] = is_bill_within_30_days(
        bill_data.get("bill_date"),
        discharge_data.get("discharge_date")
    )

    # ICD
    checks_result["icd_match"] = validate_icd_fuzzy(
        pre_auth_data.get("icd10_code"),
        discharge_data.get("diagnosis_ICD10_code")
    )

    # Sum insured
    checks_result["sum_insured"] = check_sum_insured(
        patient, bill_data
    )

    # Hospital exclusion
    checks_result["hospital_excluded"] = check_hospital_exclusion(
        pre_auth_data.get("hospital_code"),
        exclusion_hospitals_df
    )

    # Negation exclusions
    checks_result["negation_check"] = check_negation_exclusions(
        discharge_data.get("negations", []),
        ["alcohol", "smoking", "drug", "substance"]
    )
    return checks_result
