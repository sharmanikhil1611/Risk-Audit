"""
Unified LLM client. Switches between Groq, Google Gemini, and Anthropic
Claude based on the LLM_PROVIDER env var, so the rest of the codebase
(risk_agent.py, manager_agent.py) never has to know or care which
provider is behind it.

Save as: risk/services/llm_client.py

Setup - pick ONE:

    Groq (RECOMMENDED - free, no credit card, 1000 requests/day):
        pip install groq
        Get a free key at https://console.groq.com/keys
        .env:
            LLM_PROVIDER=groq
            GROQ_API_KEY=gsk_xxxxx
            GROQ_MODEL=openai/gpt-oss-20b          # optional override

    Gemini (free, but only 20 requests/day on gemini-3.6-flash):
        pip install google-genai
        .env:
            LLM_PROVIDER=gemini
            GEMINI_API_KEY=xxxxx
            GEMINI_MODEL=gemini-3.6-flash          # optional override

    Anthropic (paid):
        pip install anthropic
        .env:
            LLM_PROVIDER=anthropic
            ANTHROPIC_API_KEY=sk-ant-xxxxx
            ANTHROPIC_MODEL=claude-haiku-4-5-20251001   # optional override

Usage from risk_agent.py / manager_agent.py:

    from risk.services.llm_client import call_llm

    raw_text = call_llm(system_prompt=SYSTEM_PROMPT, user_content=case_context, max_tokens=500)
"""

import os
import re
import time

PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()

# Conservative delay between calls, per provider, to stay under free-tier limits.
_MIN_INTERVAL_SECONDS = {
    "groq": 2.5,      # ~24/min, well under Groq's 30 RPM free limit
    "gemini": 13.0,    # Gemini free tier: 5 RPM on gemini-3.6-flash
    "anthropic": 0.3,  # paid tier, minimal courtesy delay
}
MAX_RETRIES = 4
_last_call_time = 0.0


def _throttle():
    global _last_call_time
    interval = _MIN_INTERVAL_SECONDS.get(PROVIDER, 2.0)
    elapsed = time.time() - _last_call_time
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_call_time = time.time()


def call_llm(system_prompt: str, user_content: str, max_tokens: int = 500) -> str:
    """
    Sends a system prompt + user content to whichever provider is configured,
    and returns the raw text response (expected to be a JSON string, per our
    agents' system prompts). Markdown code fences are stripped defensively.
    Throttles and retries automatically on rate-limit errors.
    """
    for attempt in range(MAX_RETRIES):
        _throttle()
        try:
            if PROVIDER == "groq":
                raw_text = _call_groq(system_prompt, user_content, max_tokens)
            elif PROVIDER == "gemini":
                raw_text = _call_gemini(system_prompt, user_content)
            elif PROVIDER == "anthropic":
                raw_text = _call_anthropic(system_prompt, user_content, max_tokens)
            else:
                raise ValueError(
                    f"Unknown LLM_PROVIDER '{PROVIDER}'. Use 'groq', 'gemini', or 'anthropic' in your .env."
                )
            return raw_text.strip().replace("```json", "").replace("```", "").strip()

        except Exception as e:
            error_str = str(e)
            is_rate_limit = (
                "429" in error_str
                or "RESOURCE_EXHAUSTED" in error_str
                or "rate_limit" in error_str.lower()
            )
            is_daily_quota = "PerDay" in error_str or "daily" in error_str.lower()

            if is_daily_quota:
                # No point retrying within the same run - the quota won't reset for hours.
                raise RuntimeError(
                    f"Daily quota exhausted for provider '{PROVIDER}'. "
                    f"Switch LLM_PROVIDER in .env (e.g. to 'groq') or wait for reset. "
                    f"Original error: {error_str}"
                )

            if is_rate_limit and attempt < MAX_RETRIES - 1:
                match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)", error_str)
                wait = int(match.group(1)) + 3 if match else 20
                print(f"  Rate limited, waiting {wait}s before retrying...")
                time.sleep(wait)
                continue
            raise

    raise RuntimeError("call_llm: exhausted retries without success.")


def _call_groq(system_prompt: str, user_content: str, max_tokens: int) -> str:
    from groq import Groq  # local import so this dependency is optional

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    kwargs = dict(
        model=model,
        # gpt-oss models spend some of this budget on hidden reasoning before
        # writing the JSON, so give real headroom above the caller's ask.
        max_tokens=max(max_tokens * 3, 800),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    # Keep hidden reasoning short so more of the token budget goes to the JSON itself.
    if "gpt-oss" in model:
        kwargs["reasoning_effort"] = "low"

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content


def _call_gemini(system_prompt: str, user_content: str) -> str:
    from google import genai  # local import so this dependency is optional

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    response = client.models.generate_content(
        model=model,
        contents=user_content,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
        },
    )
    return response.text


def _call_anthropic(system_prompt: str, user_content: str, max_tokens: int) -> str:
    import anthropic  # local import so this dependency is optional

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text