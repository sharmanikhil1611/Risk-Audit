"""
Manager Agent: takes a RiskVerdict and decides what to actually do about
the return — approve, flag for human review, or deny. This is the audit
trail entry the buildathon judges will want to see.

Provider (Gemini/Anthropic) is decided by llm_client.py via .env - this
file never touches provider-specific code.

Save as: risk/services/manager_agent.py
"""

import json

from risk.models import RiskVerdict, ManagerDecision
from risk.services.llm_client import call_llm

# Returns scoring below this are approved deterministically, without an LLM
# call - there's no ambiguity worth spending a model call on. The LLM is
# reserved for the genuinely uncertain middle and high-risk cases, where its
# judgment (weighing refund amount against confidence) actually adds value.
AUTO_APPROVE_THRESHOLD = 0.45

SYSTEM_PROMPT = """You are the Manager Agent for an e-commerce return/refund system.

You receive a risk assessment from the Risk Agent and must decide what
action to take. You are STRICTLY DEFENSIVE — your only job is to protect
the merchant from loss while being fair to genuine customers. You never
suggest ways to exploit or evade this process.

Decision rules:
- If the risk score is comfortably below 0.80 (this system's risk threshold), and
  nothing else in the reasoning stands out as an unusually strong red flag,
  lean toward "approve". Most genuine returns should pass through smoothly —
  do not treat "medium" as automatically suspicious.
- "flag_for_review": risk score at or above 0.80, OR a borderline score (roughly
  0.6-0.79) combined with a refund amount large enough that a human should
  confirm before denying (protects genuine customers from an automated wrong
  call on big-ticket items).
- "deny": risk score at or above 0.80 AND the refund amount is small/moderate,
  where the cost of a wrong denial is low relative to the fraud risk avoided.

Always err toward "flag_for_review" over "deny" when you are not confident,
since a wrongful denial damages customer trust. But do not be afraid to
"approve" outright when the risk score is genuinely low — flagging every
return for review defeats the purpose of having a risk score at all.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{
  "decision": "approve" | "flag_for_review" | "deny",
  "reasoning": "<1-3 sentence explanation of why, referencing the risk score and amount>"
}

IMPORTANT: Never use quotation marks (" or ') inside the "reasoning" string —
they will break JSON parsing. Refer to field values in plain text without
quoting them.
"""


def decide(risk_verdict: RiskVerdict) -> ManagerDecision:
    return_request = risk_verdict.return_request

    # Deterministic fast path: clearly low-risk returns don't need an LLM call.
    if risk_verdict.risk_score < AUTO_APPROVE_THRESHOLD:
        decision_obj, _ = ManagerDecision.objects.update_or_create(
            risk_verdict=risk_verdict,
            defaults={
                "decision": "approve",
                "reasoning": (
                    f"Risk score {risk_verdict.risk_score:.2f} is well below the "
                    f"auto-approve threshold ({AUTO_APPROVE_THRESHOLD}); no signals "
                    f"strong enough to warrant review. Approved automatically."
                ),
            },
        )
        return decision_obj

    case_context = f"""Risk Agent assessment:
- Risk score: {risk_verdict.risk_score:.2f} (this system's risk threshold is 0.80 — scores below that are NOT predicted risky)
- Risk level label: {risk_verdict.risk_level} (a rough qualitative tag - trust the numeric score above more)
- Risk reasoning: {risk_verdict.reasoning}

Refund amount at stake: ₹{return_request.refund_amount / 100:.2f}
"""

    raw_text = call_llm(system_prompt=SYSTEM_PROMPT, user_content=case_context, max_tokens=300)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        raise ValueError(f"Manager agent returned non-JSON output: {raw_text!r}")

    decision_obj, _ = ManagerDecision.objects.update_or_create(
        risk_verdict=risk_verdict,
        defaults={
            "decision": parsed["decision"],
            "reasoning": parsed["reasoning"],
        },
    )
    return decision_obj