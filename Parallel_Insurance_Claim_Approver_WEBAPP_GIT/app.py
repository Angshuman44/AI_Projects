import asyncio
import json
import tempfile
import traceback
from html import escape
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context
from werkzeug.utils import secure_filename

from mainInsuranceClaimParallel import (
    DEFAULT_BILL_PATH,
    DEFAULT_DISCHARGE_SUMMARY_PATH,
    DEFAULT_EXCLUSIONS_PATH,
    DEFAULT_HISTORY_CLAIMS_PATH,
    DEFAULT_INSURANCE_PATH,
    DEFAULT_MEDICAL_HISTORY_PATH,
    DEFAULT_PRE_AUTH_FORM_PATH,
    API_KEY,
    calculate_claim_amount,
    final_decision_engine,
    generate_final_claim_summary,
    process_documents,
    run_claim_pipeline,
    run_full_claim_pipeline,
)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_EXTENSIONS = {".pdf"}


def json_ready(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {key: json_ready(item) for key, item in value.items()}
        if isinstance(value, list):
            return [json_ready(item) for item in value]
        return str(value)


def money(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"INR {amount:,.2f}"


def result_page(payload):
    decision = payload.get("decision") or {}
    claim_amount = payload.get("claim_amount") or {}
    risk_flags = decision.get("risk_flags") or []
    summary = payload.get("summary") or json.dumps(json_ready(payload), indent=2)
    final_decision = str(decision.get("final_decision") or "-")
    decision_lower = final_decision.lower()
    if "approve" in decision_lower:
        decision_class = "approved"
        decision_label = "Approved"
    elif "reject" in decision_lower or "deny" in decision_lower:
        decision_class = "rejected"
        decision_label = "Rejected"
    else:
        decision_class = "review"
        decision_label = "Needs Review"
    flags_text = ", ".join(map(str, risk_flags)) or "None"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Claim Result</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #050914;
      --panel: rgba(255,255,255,0.08);
      --panel-strong: rgba(255,255,255,0.13);
      --line: rgba(255,255,255,0.16);
      --text: #edf6ff;
      --muted: #a9b8cc;
      --mint: #76f7cb;
      --blue: #7ab7ff;
      --gold: #ffd27a;
      --rose: #ff8fa3;
      font-family: "Segoe UI", Inter, Arial, sans-serif;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      min-height: 100vh;
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at 10% 16%, rgba(122, 183, 255, 0.25), transparent 28rem),
        radial-gradient(circle at 84% 18%, rgba(118, 247, 203, 0.18), transparent 25rem),
        radial-gradient(circle at 50% 92%, rgba(255, 210, 122, 0.13), transparent 28rem),
        linear-gradient(135deg, #050914 0%, #0e192b 52%, #07101d 100%);
    }}

    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,0.032) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.028) 1px, transparent 1px);
      background-size: 54px 54px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,0.75), transparent 82%);
    }}

    main {{
      width: min(1160px, calc(100% - 36px));
      margin: 0 auto;
      padding: 30px 0 58px;
      position: relative;
    }}

    .nav {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: center;
      margin-bottom: 42px;
    }}

    .brand {{
      display: flex;
      gap: 12px;
      align-items: center;
      font-weight: 850;
      letter-spacing: 0.02em;
    }}

    .mark {{
      width: 42px;
      height: 42px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      color: #06121f;
      background: linear-gradient(135deg, var(--mint), var(--blue));
      box-shadow: 0 18px 45px rgba(118, 247, 203, 0.18);
      font-weight: 900;
    }}

    a {{
      color: inherit;
    }}

    .back-link {{
      text-decoration: none;
      color: #06121f;
      background: linear-gradient(135deg, var(--gold), var(--mint), var(--blue));
      border-radius: 999px;
      padding: 12px 18px;
      font-weight: 900;
      box-shadow: 0 16px 38px rgba(118, 247, 203, 0.16);
    }}

    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 0.95fr) minmax(340px, 1.05fr);
      gap: 24px;
      align-items: stretch;
    }}

    .decision-card,
    .summary-card,
    .metric-card {{
      border: 1px solid var(--line);
      background: var(--panel);
      backdrop-filter: blur(18px);
      box-shadow: 0 28px 90px rgba(0, 0, 0, 0.28);
    }}

    .decision-card {{
      position: relative;
      border-radius: 34px;
      padding: 34px;
      overflow: hidden;
      background:
        linear-gradient(145deg, rgba(255,255,255,0.14), rgba(255,255,255,0.045)),
        rgba(8, 17, 31, 0.72);
    }}

    .decision-card::before {{
      content: "";
      position: absolute;
      width: 240px;
      height: 240px;
      right: -90px;
      top: -100px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(118,247,203,0.34), transparent 68%);
    }}

    .eyebrow {{
      position: relative;
      display: inline-flex;
      gap: 10px;
      align-items: center;
      width: fit-content;
      padding: 9px 14px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: #dceaff;
      background: rgba(255, 255, 255, 0.06);
      font-size: 0.74rem;
      font-weight: 850;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}

    .eyebrow::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--mint);
      box-shadow: 0 0 18px var(--mint);
    }}

    h1 {{
      position: relative;
      margin: 24px 0 22px;
      font-size: clamp(3.2rem, 8vw, 6.8rem);
      line-height: 0.9;
      letter-spacing: -0.06em;
    }}

    .status-badge {{
      position: relative;
      display: inline-flex;
      align-items: center;
      gap: 12px;
      border-radius: 22px;
      padding: 14px 16px;
      font-weight: 900;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.07);
    }}

    .status-badge::before {{
      content: "";
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--gold);
      box-shadow: 0 0 22px var(--gold);
    }}

    .status-badge.approved::before {{
      background: var(--mint);
      box-shadow: 0 0 22px var(--mint);
    }}

    .status-badge.rejected::before {{
      background: var(--rose);
      box-shadow: 0 0 22px var(--rose);
    }}

    .status-badge.review::before {{
      background: var(--gold);
      box-shadow: 0 0 22px var(--gold);
    }}

    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 14px;
    }}

    .metric-card {{
      min-height: 156px;
      border-radius: 28px;
      padding: 24px;
    }}

    .metric-card span {{
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 18px;
    }}

    .metric-card strong {{
      display: block;
      color: var(--text);
      font-size: clamp(1.35rem, 3vw, 2.1rem);
      line-height: 1.08;
      overflow-wrap: anywhere;
    }}

    .metric-card.wide {{
      grid-column: 1 / -1;
    }}

    .summary-card {{
      margin-top: 24px;
      border-radius: 32px;
      padding: 30px;
    }}

    h2 {{
      margin: 0 0 18px;
      font-size: clamp(1.6rem, 3vw, 2.35rem);
      letter-spacing: -0.04em;
    }}

    pre {{
      margin: 0;
      color: #d9e7f7;
      background: rgba(3, 9, 20, 0.52);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 22px;
      padding: 22px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.65;
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.95rem;
    }}

    .footer-note {{
      color: rgba(217, 231, 247, 0.62);
      text-align: center;
      margin-top: 34px;
      line-height: 1.6;
    }}

    @media (max-width: 900px) {{
      .hero {{
        grid-template-columns: 1fr;
      }}
    }}

    @media (max-width: 620px) {{
      main {{
        width: min(100% - 24px, 1160px);
        padding-top: 20px;
      }}

      .nav {{
        align-items: flex-start;
        flex-direction: column;
      }}

      .metric-grid {{
        grid-template-columns: 1fr;
      }}

      .decision-card,
      .summary-card,
      .metric-card {{
        border-radius: 24px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <nav class="nav" aria-label="Result page">
      <div class="brand">
        <div class="mark">IC</div>
        <div>Insurance Claim Approver</div>
      </div>
      <a class="back-link" href="/">Run Another Claim</a>
    </nav>

    <section class="hero">
      <article class="decision-card">
        <div class="eyebrow">Pipeline Complete</div>
        <h1>Claim result is ready.</h1>
        <div class="status-badge {decision_class}">{escape(decision_label)}</div>
      </article>

      <section class="metric-grid" aria-label="Decision metrics">
        <div class="metric-card">
          <span>Raw Status</span>
          <strong>{escape(final_decision)}</strong>
        </div>
        <div class="metric-card">
          <span>Final Payable</span>
          <strong>{escape(money(claim_amount.get("final_payable")))}</strong>
        </div>
        <div class="metric-card">
          <span>Total Deduction</span>
          <strong>{escape(money(claim_amount.get("total_deduction")))}</strong>
        </div>
        <div class="metric-card">
          <span>Risk Flags</span>
          <strong>{escape(flags_text)}</strong>
        </div>
      </section>
    </section>

    <section class="summary-card">
      <h2>Claim Summary</h2>
      <pre>{escape(str(summary))}</pre>
    </section>

    <p class="footer-note">This page is rendered by Flask after the claim pipeline completes.</p>
  </main>
</body>
</html>"""


def error_page(message):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Claim Error</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: "Segoe UI", Inter, Arial, sans-serif;
    }}

    body {{
      min-height: 100vh;
      margin: 0;
      display: grid;
      place-items: center;
      color: #edf6ff;
      background:
        radial-gradient(circle at 24% 20%, rgba(255,143,163,0.28), transparent 24rem),
        linear-gradient(135deg, #050914, #101b2d);
    }}

    main {{
      width: min(680px, calc(100% - 32px));
      border: 1px solid rgba(255,255,255,0.16);
      border-radius: 32px;
      padding: 34px;
      background: rgba(255,255,255,0.08);
      box-shadow: 0 28px 90px rgba(0,0,0,0.3);
    }}

    h1 {{
      margin: 0 0 14px;
      font-size: clamp(2.2rem, 6vw, 4rem);
      letter-spacing: -0.06em;
    }}

    p {{
      color: #a9b8cc;
      line-height: 1.7;
    }}

    a {{
      display: inline-block;
      margin-top: 14px;
      color: #06121f;
      text-decoration: none;
      border-radius: 999px;
      padding: 12px 18px;
      font-weight: 900;
      background: linear-gradient(135deg, #ffd27a, #76f7cb, #7ab7ff);
    }}
  </style>
</head>
<body>
  <main>
    <h1>Claim Error</h1>
    <p>{escape(str(message))}</p>
    <p><a href="/">Back to claim form</a></p>
  </main>
</body>
</html>"""


def progress_page_start():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Processing Claim</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050914;
      --panel: rgba(255,255,255,0.08);
      --line: rgba(255,255,255,0.16);
      --text: #edf6ff;
      --muted: #a9b8cc;
      --mint: #76f7cb;
      --blue: #7ab7ff;
      --gold: #ffd27a;
      font-family: "Segoe UI", Inter, Arial, sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      min-height: 100vh;
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 18%, rgba(122,183,255,0.24), transparent 28rem),
        radial-gradient(circle at 88% 12%, rgba(118,247,203,0.18), transparent 26rem),
        linear-gradient(135deg, #050914 0%, #0e192b 52%, #07101d 100%);
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,0.032) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.028) 1px, transparent 1px);
      background-size: 54px 54px;
      mask-image: linear-gradient(to bottom, rgba(0,0,0,0.75), transparent 82%);
    }

    main {
      width: min(1060px, calc(100% - 36px));
      margin: 0 auto;
      padding: 30px 0 58px;
      position: relative;
    }

    .nav {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: center;
      margin-bottom: 36px;
    }

    .brand {
      display: flex;
      gap: 12px;
      align-items: center;
      font-weight: 850;
      letter-spacing: 0.02em;
    }

    .mark {
      width: 42px;
      height: 42px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      color: #06121f;
      background: linear-gradient(135deg, var(--mint), var(--blue));
      font-weight: 900;
    }

    .hero {
      border: 1px solid var(--line);
      border-radius: 34px;
      padding: 34px;
      background:
        linear-gradient(145deg, rgba(255,255,255,0.14), rgba(255,255,255,0.045)),
        rgba(8, 17, 31, 0.72);
      box-shadow: 0 30px 100px rgba(0,0,0,0.32);
      backdrop-filter: blur(18px);
    }

    .eyebrow {
      display: inline-flex;
      gap: 10px;
      align-items: center;
      width: fit-content;
      padding: 9px 14px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: #dceaff;
      background: rgba(255,255,255,0.06);
      font-size: 0.74rem;
      font-weight: 850;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    .eyebrow::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--mint);
      box-shadow: 0 0 18px var(--mint);
    }

    h1 {
      margin: 22px 0 12px;
      font-size: clamp(3rem, 7vw, 6.4rem);
      line-height: 0.92;
      letter-spacing: -0.06em;
    }

    .hero p {
      max-width: 720px;
      margin: 0;
      color: var(--muted);
      font-size: 1.05rem;
      line-height: 1.75;
    }

    .timeline {
      display: grid;
      gap: 14px;
      margin-top: 24px;
    }

    .stage {
      display: grid;
      grid-template-columns: 52px 1fr auto;
      gap: 16px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      background: var(--panel);
      backdrop-filter: blur(18px);
    }

    .stage strong {
      display: block;
      margin-bottom: 5px;
      font-size: 1.02rem;
    }

    .stage span {
      color: var(--muted);
      line-height: 1.55;
      font-size: 0.92rem;
    }

    .badge {
      width: 42px;
      height: 42px;
      border-radius: 16px;
      display: grid;
      place-items: center;
      background: rgba(255,255,255,0.08);
      border: 1px solid var(--line);
      color: var(--muted);
      font-weight: 900;
    }

    .running .badge {
      border-color: rgba(255,210,122,0.42);
      color: var(--gold);
    }

    .done .badge {
      color: #06121f;
      background: linear-gradient(135deg, var(--mint), var(--blue));
    }

    .done-check,
    .done-text {
      display: none;
    }

    .state {
      padding: 8px 12px;
      border-radius: 999px;
      color: var(--muted);
      border: 1px solid var(--line);
      font-size: 0.74rem;
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      white-space: nowrap;
    }

    .running .state {
      color: var(--gold);
      border-color: rgba(255,210,122,0.42);
    }

    .done .state {
      color: var(--mint);
      border-color: rgba(118,247,203,0.38);
    }

    .spinner {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 3px solid rgba(255,210,122,0.22);
      border-top-color: var(--gold);
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .result-shell {
      margin-top: 24px;
      border: 1px solid var(--line);
      border-radius: 34px;
      padding: 30px;
      background: rgba(255,255,255,0.08);
      backdrop-filter: blur(18px);
      box-shadow: 0 28px 90px rgba(0,0,0,0.28);
    }

    .result-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 22px;
    }

    .metric {
      min-height: 138px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      background: rgba(3,9,20,0.36);
    }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 0.74rem;
      font-weight: 850;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 14px;
    }

    .metric strong {
      display: block;
      font-size: clamp(1.1rem, 2vw, 1.6rem);
      line-height: 1.2;
      overflow-wrap: anywhere;
    }

    pre {
      margin: 0;
      color: #d9e7f7;
      background: rgba(3, 9, 20, 0.52);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 22px;
      padding: 22px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.65;
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.95rem;
    }

    .back-link {
      display: inline-block;
      margin-top: 22px;
      text-decoration: none;
      color: #06121f;
      background: linear-gradient(135deg, var(--gold), var(--mint), var(--blue));
      border-radius: 999px;
      padding: 12px 18px;
      font-weight: 900;
    }

    @media (max-width: 900px) {
      .result-grid {
        grid-template-columns: repeat(2, 1fr);
      }
    }

    @media (max-width: 620px) {
      main {
        width: min(100% - 24px, 1060px);
      }

      .stage {
        grid-template-columns: 44px 1fr;
      }

      .state {
        grid-column: 2;
        width: fit-content;
      }

      .result-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main>
    <nav class="nav" aria-label="Processing page">
      <div class="brand">
        <div class="mark">IC</div>
        <div>Insurance Claim Approver</div>
      </div>
    </nav>

    <section class="hero">
      <div class="eyebrow">Live Pipeline</div>
      <h1>Review in progress.</h1>
      <p>The claim is moving through each stage. Completed steps will appear here as the backend finishes them.</p>
    </section>

    <section class="timeline" aria-label="Claim processing stages">
"""


def progress_stage(stage_number, title, description):
    return f"""      <article class="stage running" id="stage-{stage_number}">
        <div class="badge">
          <div class="spinner" aria-hidden="true"></div>
          <span class="done-check">✓</span>
        </div>
        <div>
          <strong>{escape(title)}</strong>
          <span>{escape(description)}</span>
        </div>
        <div class="state">
          <span class="running-text">Stage {stage_number}: Running</span>
          <span class="done-text">Stage {stage_number}: Done</span>
        </div>
      </article>
"""


def progress_stage_done(stage_number):
    return f"""      <style>
        #stage-{stage_number} {{
          border-color: rgba(118,247,203,0.38);
        }}
        #stage-{stage_number} .spinner,
        #stage-{stage_number} .running-text {{
          display: none;
        }}
        #stage-{stage_number} .done-check {{
          display: inline;
        }}
        #stage-{stage_number} .done-text {{
          display: inline;
        }}
        #stage-{stage_number} .badge {{
          color: #06121f;
          background: linear-gradient(135deg, var(--mint), var(--blue));
        }}
        #stage-{stage_number} .state {{
          color: var(--mint);
          border-color: rgba(118,247,203,0.38);
        }}
      </style>
"""


def progress_stage_legacy(stage_number, title, description, state):
    state_label = "Running" if state == "running" else "Done"
    badge = '<div class="spinner" aria-hidden="true"></div>' if state == "running" else "✓"
    return f"""      <article class="stage {state}">
        <div class="badge">{badge}</div>
        <div>
          <strong>{escape(title)}</strong>
          <span>{escape(description)}</span>
        </div>
        <div class="state">Stage {stage_number}: {state_label}</div>
      </article>
"""


def progress_result_section(payload):
    decision = payload.get("decision") or {}
    claim_amount = payload.get("claim_amount") or {}
    risk_flags = decision.get("risk_flags") or []
    summary = payload.get("summary") or json.dumps(json_ready(payload), indent=2)
    final_decision = str(decision.get("final_decision") or "-")
    flags_text = ", ".join(map(str, risk_flags)) or "None"

    return f"""    </section>

    <section class="result-shell">
      <div class="eyebrow">Pipeline Complete</div>
      <h1>Claim result is ready.</h1>
      <div class="result-grid">
        <div class="metric">
          <span>Status</span>
          <strong>{escape(final_decision)}</strong>
        </div>
        <div class="metric">
          <span>Final Payable</span>
          <strong>{escape(money(claim_amount.get("final_payable")))}</strong>
        </div>
        <div class="metric">
          <span>Total Deduction</span>
          <strong>{escape(money(claim_amount.get("total_deduction")))}</strong>
        </div>
        <div class="metric">
          <span>Risk Flags</span>
          <strong>{escape(flags_text)}</strong>
        </div>
      </div>
      <h2>Claim Summary</h2>
      <pre>{escape(str(summary))}</pre>
      <a class="back-link" href="/">Run Another Claim</a>
    </section>
"""


def progress_error_section(message):
    return f"""    </section>
    <section class="result-shell">
      <div class="eyebrow">Pipeline Stopped</div>
      <h1>Claim error.</h1>
      <pre>{escape(str(message))}</pre>
      <a class="back-link" href="/">Back to Claim Form</a>
    </section>
"""


def progress_page_end():
    return """  </main>
</body>
</html>
"""


def run_full_claim_pipeline_with_progress(temp_dir):
    yield progress_page_start()

    try:
        bill_path = save_upload(temp_dir, "bill", DEFAULT_BILL_PATH)
        pre_auth_path = save_upload(temp_dir, "pre_auth", DEFAULT_PRE_AUTH_FORM_PATH)
        discharge_path = save_upload(temp_dir, "discharge_summary", DEFAULT_DISCHARGE_SUMMARY_PATH)

        yield progress_stage(
            1,
            "Extracting claim documents",
            "Reading the hospital bill, pre-auth form, and discharge summary in parallel.",
        )
        structured_bill_output_data, structured_PreAuthForm_output_data, structured_DischargeSummary_output_data = asyncio.run(
            process_documents(
                bill_path,
                pre_auth_path,
                discharge_path,
                API_KEY,
            )
        )
        yield progress_stage_done(1)

        insurance_path = str(BASE_DIR / DEFAULT_INSURANCE_PATH)
        excusionspath = str(BASE_DIR / DEFAULT_EXCLUSIONS_PATH)
        medical_history_path = str(BASE_DIR / DEFAULT_MEDICAL_HISTORY_PATH)
        history_claims_path = str(BASE_DIR / DEFAULT_HISTORY_CLAIMS_PATH)

        yield progress_stage(
            2,
            "Running policy and medical checks",
            "Checking coverage rules, exclusions, diagnosis sanity, PED, and claim history.",
        )
        claimChecks, diagnosis_procedure_results, PED_check_results = asyncio.run(
            run_claim_pipeline(
                structured_bill_output_data,
                structured_PreAuthForm_output_data,
                structured_DischargeSummary_output_data,
                insurance_path,
                excusionspath,
                medical_history_path,
                history_claims_path,
                API_KEY,
            )
        )
        yield progress_stage_done(2)

        yield progress_stage(
            3,
            "Calculating amount and decision",
            "Computing payable amount, deductions, and the final approval decision.",
        )
        claim_amount = calculate_claim_amount(
            structured_bill_output_data,
            structured_PreAuthForm_output_data,
            structured_DischargeSummary_output_data,
            claimChecks,
        )
        final_output = final_decision_engine(
            claimChecks,
            diagnosis_procedure_results,
            PED_check_results,
        )
        yield progress_stage_done(3)

        yield progress_stage(
            4,
            "Generating final summary",
            "Writing the human-readable explanation for the claim outcome.",
        )
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
            final_output,
        )
        yield progress_stage_done(4)

        yield progress_result_section(
            json_ready(
                {
                    "bill": structured_bill_output_data,
                    "pre_auth": structured_PreAuthForm_output_data,
                    "discharge_summary": structured_DischargeSummary_output_data,
                    "checks": claimChecks,
                    "diagnosis_procedure": diagnosis_procedure_results,
                    "ped": PED_check_results,
                    "claim_amount": claim_amount,
                    "decision": final_output,
                    "summary": summary,
                }
            )
        )
    except Exception as exc:
        traceback.print_exc()
        yield progress_error_section(exc)

    yield progress_page_end()


def is_allowed_pdf(file_storage):
    suffix = Path(file_storage.filename or "").suffix.lower()
    return suffix in ALLOWED_EXTENSIONS


def save_upload(temp_dir, field_name, fallback_path):
    file_storage = request.files.get(field_name)
    if not file_storage or not file_storage.filename:
        return str(BASE_DIR / fallback_path)

    if not is_allowed_pdf(file_storage):
        raise ValueError(f"{field_name} must be a PDF file")

    filename = secure_filename(file_storage.filename)
    destination = Path(temp_dir) / filename
    file_storage.save(destination)
    return str(destination)


async def process_request(temp_dir):
    bill_path = save_upload(temp_dir, "bill", DEFAULT_BILL_PATH)
    pre_auth_path = save_upload(temp_dir, "pre_auth", DEFAULT_PRE_AUTH_FORM_PATH)
    discharge_path = save_upload(temp_dir, "discharge_summary", DEFAULT_DISCHARGE_SUMMARY_PATH)

    return await run_full_claim_pipeline(
        bill_path=bill_path,
        pre_auth_form_path=pre_auth_path,
        discharge_summary_path=discharge_path,
        insurance_path=str(BASE_DIR / DEFAULT_INSURANCE_PATH),
        excusionspath=str(BASE_DIR / DEFAULT_EXCLUSIONS_PATH),
        medical_history_path=str(BASE_DIR / DEFAULT_MEDICAL_HISTORY_PATH),
        history_claims_path=str(BASE_DIR / DEFAULT_HISTORY_CLAIMS_PATH),
    )


@app.get("/")
def index():
    return Response((BASE_DIR / "webPage.index").read_text(encoding="utf-8"), mimetype="text/html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/claims")
def create_claim_page():
    def generate():
        with tempfile.TemporaryDirectory() as temp_dir:
            yield from run_full_claim_pipeline_with_progress(temp_dir)

    return Response(stream_with_context(generate()), mimetype="text/html")


@app.post("/api/claims")
def create_claim():
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = asyncio.run(process_request(temp_dir))
        return jsonify(json_ready(result))
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)


