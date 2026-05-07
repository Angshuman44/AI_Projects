def final_decision_engine(checks, diagnosis_procedure_results, PED_check_results):
    decision = "APPROVE"
    reasons = []
    risk_flags = []

    # ---------------- HARD REJECT ----------------
    if not checks.get("policy_active", {}).get("active", False):
        return {
            "final_decision": "REJECT",
            "decision_reason": ["Policy not active"],
            "risk_flags": ["POLICY_INACTIVE"]
        }

    if checks.get("hospital_excluded", False):
        return {
            "final_decision": "REJECT",
            "decision_reason": ["Hospital is in exclusion list"],
            "risk_flags": ["EXCLUDED_PROVIDER"]
        }

    if not diagnosis_procedure_results.get("procedure_justified", False):
        return {
            "final_decision": "REJECT",
            "decision_reason": ["Procedure not medically justified"],
            "risk_flags": ["INVALID_PROCEDURE"]
        }

    if not diagnosis_procedure_results.get("medical_necessity", False):
        return {
            "final_decision": "REJECT",
            "decision_reason": ["Treatment not medically necessary"],
            "risk_flags": ["NOT_MEDICALLY_NECESSARY"]
        }

    if diagnosis_procedure_results.get("exclusion_applicable", False):
        return {
            "final_decision": "REJECT",
            "decision_reason": ["Policy exclusion applicable"],
            "risk_flags": ["POLICY_EXCLUSION"]
        }

    # ---------------- REVIEW FLAGS ----------------

    if not checks.get("bill_within_30_days", True):
        decision = "REVIEW"
        reasons.append("Bill submitted outside allowed time window")
        risk_flags.append("DELAYED_SUBMISSION")

    if checks.get("negation_check", {}).get("flagged", False):
        decision = "REVIEW"
        reasons.append("Substance abuse / risk history detected")
        risk_flags.append("RISK_HISTORY")

    # PED logic
    ped = PED_check_results.get("causality_result", {})
    if ped.get("causal_link", False) and ped.get("confidence", 0) < 0.80:
        decision = "REVIEW"
        reasons.append("Possible PED linkage with low confidence")
        risk_flags.append("PED_RISK")

    # ---------------- CONDITIONAL APPROVAL ----------------
    room = checks.get("room_rent", {})
    si = checks.get("sum_insured", {})

    if not room.get("allowed", True):
        decision = "APPROVE_WITH_DEDUCTIONS"
        reasons.append("Room rent exceeds policy limit")
        risk_flags.append("ROOM_LIMIT_BREACH")

    if not si.get("covered", True):
        decision = "APPROVE_WITH_DEDUCTIONS"
        reasons.append("Bill exceeds sum insured")
        risk_flags.append("SI_LIMIT_BREACH")

    # ---------------- CLEAN APPROVAL ----------------
    if decision == "APPROVE" and not reasons:
        reasons.append("All checks passed")

    return {
        "final_decision": decision,
        "decision_reason": reasons,
        "risk_flags": risk_flags,
        "clinical_status": "VALID" if diagnosis_procedure_results.get("procedure_justified") else "INVALID",
        "confidence": ped.get("confidence", 1)
    }

def calculate_claim_amount(
    bill_data,
    pre_auth_data,
    discharge_data,
    check_results
):
    try:
        total_bill = float(bill_data.get("total_bill", 0))
        total_room_rent = float(bill_data.get("room_rental_charges", 0))

        stay_days = float(discharge_data.get("stay_duration", 1))
        room_per_day = float(pre_auth_data.get("room_charges_per_day", 0))

        room_limit = float(check_results.get("room_rent", {}).get("limit", 0))
        sum_insured = float(check_results.get("sum_insured", {}).get("limit", 0))

        # -------------------------------
        # Step 1: Room Rent Cap
        # -------------------------------
        allowed_per_day = min(room_per_day, room_limit)
        allowed_room_total = allowed_per_day * stay_days

        # cannot exceed actual charged
        allowed_room_total = min(allowed_room_total, total_room_rent)

        room_excess = max(0, total_room_rent - allowed_room_total)

        # -------------------------------
        # Step 2: Non-room untouched
        # -------------------------------
        non_room_bill = total_bill - total_room_rent

        adjusted_bill = allowed_room_total + non_room_bill

        # -------------------------------
        # Step 3: Sum Insured Cap
        # -------------------------------
        final_payable = min(adjusted_bill, sum_insured)
        policy_excess = max(0, adjusted_bill - sum_insured)

        return {
            "total_bill": total_bill,

            "room": {
                "actual": total_room_rent,
                "allowed": round(allowed_room_total, 2),
                "excess": round(room_excess, 2)
            },

            "non_room_bill": round(non_room_bill, 2),

            "adjusted_bill": round(adjusted_bill, 2),

            "sum_insured_limit": sum_insured,
            "final_payable": round(final_payable, 2),

            "policy_excess": round(policy_excess, 2),

            "total_deduction": round(total_bill - final_payable, 2)
        }

    except Exception as e:
        return {"error": str(e)}