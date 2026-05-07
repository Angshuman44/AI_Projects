import os
import yaml
import itertools
import sys
import time
from utils.Bills.bill_extractor import *
from utils.Final_Pre_Auth.preauthinfo_extractor import *
from utils.Discharge_Summaries.discharge_summary_extractor import *
from utils.PolicyProcedure.rule_checks import *
from utils.PolicyProcedure.runProcedureValidity import *
from utils.checkPED.diseasePEDchecker import *
from utils.Approval.approvalRun import *
from utils.Approval.claimSummary import *
import asyncio




CONFIG_PATH = r"config.yaml"

DEFAULT_BILL_PATH = "utils/Bills/PSG_Hospital_Bill_One_Page.pdf"
DEFAULT_PRE_AUTH_FORM_PATH = "utils/Final_Pre_Auth/DharneshPreAu.pdf"
DEFAULT_DISCHARGE_SUMMARY_PATH = "utils/Discharge_Summaries/pdfcoffee.com_discharge-summary-3-pdf-free.pdf"
DEFAULT_INSURANCE_PATH = "utils/PolicyProcedure/Insurance_Customers_DataBase.csv"
DEFAULT_EXCLUSIONS_PATH = "utils/PolicyProcedure/ExcludedHospitalsFinal.csv"
DEFAULT_MEDICAL_HISTORY_PATH = "utils/checkPED/Medical_History_Final.csv"
DEFAULT_HISTORY_CLAIMS_PATH = "utils/checkPED/Historical_Claims_Final.csv"

import sys
import time
import threading
import itertools

def start_loader(message="Processing"):
    stop_event = threading.Event()

    def spin():
        spinner = itertools.cycle(["|", "/", "-", "\\"])
        while not stop_event.is_set():
            sys.stdout.write(f"\r{message}... {next(spinner)}")
            sys.stdout.flush()
            time.sleep(0.1)
    thread = threading.Thread(target=spin)
    thread.start()

    return stop_event, thread


def stop_loader(stop_event, thread):
    stop_event.set()
    thread.join()

def load_api_key(config_path=CONFIG_PATH):
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return api_key

    with open(config_path) as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        return data["OPENAI_API_KEY"]


# Load API key
API_KEY = load_api_key()


async def process_documents(bill_path, pre_auth_form_path, discharge_summary_path, api_key):
    start = time.time()

    # Run blocking functions in parallel threads
    bill_task = asyncio.to_thread(runBill, bill_path, api_key)
    preauth_task = asyncio.to_thread(runPreAuth, pre_auth_form_path, api_key)
    discharge_task = asyncio.to_thread(runDischarge, discharge_summary_path, api_key)

    bill_data, preauth_data, discharge_data = await asyncio.gather(
        bill_task,
        preauth_task,
        discharge_task
    )

    print(f"Time taken: {time.time() - start:.2f} sec")

    return bill_data, preauth_data, discharge_data



async def run_claim_pipeline(
    structured_bill_output_data,
    structured_PreAuthForm_output_data,
    structured_DischargeSummary_output_data,
    insurance_path,
    excusionspath,
    medical_history_path,
    history_claims_path,
    api_key
):
    start = time.time()

    # Task 1: Claim checks
    claim_task = asyncio.to_thread(
        run_claim_checks,
        structured_bill_output_data,
        structured_PreAuthForm_output_data,
        structured_DischargeSummary_output_data,
        insurance_path,
        excusionspath
    )

    # Task 2: Diagnosis & procedural sanity check
    diagnosis_task = asyncio.to_thread(
        evaluate_claim_with_exclusions,
        structured_DischargeSummary_output_data["discharge_summary"],
        structured_DischargeSummary_output_data["diagnosis_text"][0],
        structured_DischargeSummary_output_data["procedures"][0],
        structured_DischargeSummary_output_data["negations"],
        api_key
    )

    # Task 3: PED / causality pipeline
    ped_task = asyncio.to_thread(
        run_causality_pipeline,
        medical_history_path,
        history_claims_path,
        structured_PreAuthForm_output_data,
        structured_DischargeSummary_output_data,
        api_key
    )

    # Run all in parallel
    claimChecks, diagnosis_procedure_results, PED_check_results = await asyncio.gather(
        claim_task,
        diagnosis_task,
        ped_task
    )

    print(f"Claim pipeline time: {time.time() - start:.2f} sec")

    return claimChecks, diagnosis_procedure_results, PED_check_results


async def run_full_claim_pipeline(
    bill_path=DEFAULT_BILL_PATH,
    pre_auth_form_path=DEFAULT_PRE_AUTH_FORM_PATH,
    discharge_summary_path=DEFAULT_DISCHARGE_SUMMARY_PATH,
    insurance_path=DEFAULT_INSURANCE_PATH,
    excusionspath=DEFAULT_EXCLUSIONS_PATH,
    medical_history_path=DEFAULT_MEDICAL_HISTORY_PATH,
    history_claims_path=DEFAULT_HISTORY_CLAIMS_PATH,
    api_key=API_KEY
):
    structured_bill_output_data, structured_PreAuthForm_output_data, structured_DischargeSummary_output_data = await process_documents(
        bill_path,
        pre_auth_form_path,
        discharge_summary_path,
        api_key
    )

    claimChecks, diagnosis_procedure_results, PED_check_results = await run_claim_pipeline(
        structured_bill_output_data,
        structured_PreAuthForm_output_data,
        structured_DischargeSummary_output_data,
        insurance_path,
        excusionspath,
        medical_history_path,
        history_claims_path,
        api_key
    )

    claim_amount = calculate_claim_amount(
        structured_bill_output_data,
        structured_PreAuthForm_output_data,
        structured_DischargeSummary_output_data,
        claimChecks
    )

    final_output = final_decision_engine(
        claimChecks,
        diagnosis_procedure_results,
        PED_check_results
    )

    summary = generate_final_claim_summary(
        api_key,
        structured_bill_output_data,
        structured_PreAuthForm_output_data,
        structured_DischargeSummary_output_data,
        claimChecks,
        diagnosis_procedure_results,
        PED_check_results,
        claim_amount,
        insurance_path,
        final_output
    )

    return {
        "bill": structured_bill_output_data,
        "pre_auth": structured_PreAuthForm_output_data,
        "discharge_summary": structured_DischargeSummary_output_data,
        "checks": claimChecks,
        "diagnosis_procedure": diagnosis_procedure_results,
        "ped": PED_check_results,
        "claim_amount": claim_amount,
        "decision": final_output,
        "summary": summary
    }



if __name__ == "__main__":
    start=time.time()

    stop, t = start_loader("Extracting Bill,Pre Approval forms and Discharge summary...")

    bill_path = DEFAULT_BILL_PATH
    pre_auth_form_path = DEFAULT_PRE_AUTH_FORM_PATH
    discharge_summary_path = DEFAULT_DISCHARGE_SUMMARY_PATH

    structured_bill_output_data, structured_PreAuthForm_output_data, structured_DischargeSummary_output_data = asyncio.run(
        process_documents(
            bill_path,
            pre_auth_form_path,
            discharge_summary_path,
            API_KEY
        )
    )
    stop_loader(stop, t)


    stop, t = start_loader("Running claim checks, PED, diagnosis sanity...")

    insurance_path= DEFAULT_INSURANCE_PATH
    excusionspath= DEFAULT_EXCLUSIONS_PATH
    medical_history_path= DEFAULT_MEDICAL_HISTORY_PATH
    history_claims_path= DEFAULT_HISTORY_CLAIMS_PATH
    

    claimChecks, diagnosis_procedure_results, PED_check_results = asyncio.run(
        run_claim_pipeline(
            structured_bill_output_data,
            structured_PreAuthForm_output_data,
            structured_DischargeSummary_output_data,
            insurance_path,
            excusionspath,
            medical_history_path,
            history_claims_path,
            API_KEY
        )
    )
    stop_loader(stop, t)


    stop, t = start_loader("Generating claim decision plus calculating claim amount...")
    #Claim Ammount
    claim_amount = calculate_claim_amount(
    structured_bill_output_data,
    structured_PreAuthForm_output_data,
    structured_DischargeSummary_output_data,
    claimChecks)

    # print("\n Claim Amount Calculation:\n")
    # print(json.dumps(claim_amount, indent=2))
    #Final decision engine
    final_output = final_decision_engine(
    claimChecks,
    diagnosis_procedure_results,
    PED_check_results)
    stop_loader(stop, t)

    # print("\n🚀 FINAL CLAIM DECISION:\n")
    # print(json.dumps(final_output, indent=2))
    #Claim Summary
    stop, t = start_loader("Generating final Claim Summary...")

    summary = generate_final_claim_summary(
        API_KEY,
        structured_bill_output_data,
        structured_PreAuthForm_output_data,
        structured_DischargeSummary_output_data,
        claimChecks,
        diagnosis_procedure_results,
        PED_check_results,
        claim_amount,
        insurance_path,
        final_output
    )
    stop_loader(stop, t)

    print("\n FINAL CLAIM SUMMARY:\n")
    print(summary)

    end=time.time()

    print("Runtime:", end - start, "seconds")

