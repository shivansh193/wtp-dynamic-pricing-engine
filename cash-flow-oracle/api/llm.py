"""
LLM (Google Gemini) working-capital recommendation for the Cash Flow Oracle.

`generate_recommendation()` builds a merchant-specific prompt, calls Gemini
(generativelanguage REST API, no SDK dependency), caches the result in
Postgres/SQLite for 6 hours, and falls back to a deterministic template
sentence if the API key is missing or the call fails. The route always gets a
usable string plus a `source` of "llm" | "template".
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

from .. import config as C
from ..db import store

SYSTEM_PROMPT = (
    "You are a CFO advisor for Indian ecommerce merchants. You have access to a "
    "merchant's settlement forecast, peer benchmarks, seasonal patterns, and "
    "credit cost analysis. Write a specific, actionable cash flow recommendation "
    "in plain English. Reference specific numbers, dates, and the merchant's "
    "category context. Never use generic advice. Sound like a trusted advisor, "
    "not a report generator."
)


def _inr(x) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if abs(x) >= 1e7:
        return f"Rs {x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"Rs {x / 1e5:.2f} L"
    return f"Rs {x:,.0f}"


def _context_hash(payload: dict) -> str:
    keys = ("merchant_id", "regime", "anomaly_flag", "credit_apply_by_date")
    slim = {k: payload.get(k) for k in keys}
    fc = payload.get("forecast") or {}
    slim["stress"] = [(s.get("start"), s.get("days")) for s in
                      (fc.get("cash_stress_periods") or [])]
    slim["cash"] = round(float(fc.get("current_cash_position") or 0) / 1e5)
    cc = payload.get("carry_cost_analysis") or {}
    slim["net_benefit"] = round(float(cc.get("net_benefit_inr") or 0) / 1e3)
    return hashlib.sha256(json.dumps(slim, sort_keys=True, default=str).encode()).hexdigest()[:32]


def build_prompt(payload: dict) -> str:
    m = payload.get("merchant", {})
    fc = payload.get("forecast", {})
    peer = payload.get("peer_comparison", {})
    cc = payload.get("carry_cost_analysis", {})
    stress = fc.get("cash_stress_periods") or []
    lines = [
        f"Merchant: {m.get('display_name')} ({m.get('archetype')} category, "
        f"Tier {m.get('city_tier')} city).",
        f"Average daily settlement: {_inr(m.get('avg_daily_settlement'))}. "
        f"Operating threshold (min safe cash): {_inr(m.get('operating_threshold'))}.",
        f"Current cash position: {_inr(fc.get('current_cash_position'))}. "
        f"Trailing 7-day net: {_inr(fc.get('trailing_7d_net_inr'))}.",
        f"Current regime: {payload.get('regime')} "
        f"(confidence {payload.get('regime_confidence')}).",
        f"60-day forecast total: {_inr(fc.get('forecast_total_inr'))}.",
    ]
    if stress:
        s = stress[0]
        lines.append(
            f"Projected cash stress: {s.get('start')} to {s.get('end')} "
            f"({s.get('days')} days), trough around "
            f"{_inr(s.get('trough_balance') or s.get('min_lower_inr'))}"
            + (f", shortfall {_inr(s.get('shortfall_at_trough'))}."
               if s.get('shortfall_at_trough') else ".")
        )
    else:
        lines.append("No cash stress period projected in the next 60 days.")
    if payload.get("anomaly_flag"):
        lines.append(f"Anomaly: {payload.get('anomaly_explanation')}")
    if peer:
        v = peer.get("volatility", {})
        lines.append(
            f"Peer benchmark ({peer.get('peer_group')}): settlement volatility "
            f"{v.get('percentile')}th percentile vs peers; "
            f"{peer.get('avg_daily_settlement', {}).get('plain', '')}"
        )
    if cc:
        lines.append(
            f"Credit cost analysis: borrowing ~{_inr(cc.get('shortfall_inr'))} "
            f"about {cc.get('days_early')} days early costs "
            f"{_inr(cc.get('carry_cost_inr'))} in carry vs "
            f"{_inr(cc.get('late_payment_penalty_avoided_inr'))} in penalties "
            f"avoided (net {_inr(cc.get('net_benefit_inr'))}). "
            f"Apply-by date: {payload.get('credit_apply_by_date')}."
        )
    lines.append(
        "\nWrite 3-4 sentences of specific cash flow advice for this merchant. "
        "Reference the numbers and dates above. No preamble."
    )
    return "\n".join(lines)


def template_recommendation(payload: dict) -> str:
    m = payload.get("merchant", {})
    fc = payload.get("forecast", {})
    cc = payload.get("carry_cost_analysis", {})
    stress = fc.get("cash_stress_periods") or []
    cat = m.get("archetype", "your")
    if stress:
        s = stress[0]
        apply_by = payload.get("credit_apply_by_date")
        base = (
            f"{m.get('display_name', 'This merchant')} is heading into a "
            f"{s.get('days')}-day cash squeeze from {s.get('start')}, with the "
            f"balance troughing near {_inr(s.get('trough_balance') or s.get('min_lower_inr'))} "
            f"- below the {_inr(m.get('operating_threshold'))} operating threshold."
        )
        if cc and cc.get("recommendation") == "borrow_early":
            base += (
                f" Apply for Razorpay Capital by {apply_by} to draw "
                f"~{_inr(cc.get('shortfall_inr'))}; the {_inr(cc.get('carry_cost_inr'))} "
                f"carry cost is far below the {_inr(cc.get('late_payment_penalty_avoided_inr'))} "
                f"in late-payment penalties it avoids."
            )
        else:
            base += (" Tighten payables timing and hold discretionary spend until "
                     "settlements recover; a small Capital draw is optional.")
        return base
    return (
        f"{m.get('display_name', 'This merchant')}'s {cat} settlements look stable "
        f"for the next 60 days (forecast {_inr(fc.get('forecast_total_inr'))} vs "
        f"{_inr(fc.get('current_cash_position'))} on hand). No borrowing is needed - "
        f"keep a {_inr((m.get('avg_daily_settlement') or 0) * 7)} operating buffer "
        f"and deploy the surplus into inventory or growth."
    )


_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _gen_config(with_thinking_off: bool) -> dict:
    cfg = {"maxOutputTokens": 800, "temperature": 0.6}
    if with_thinking_off:
        # 2.5-flash is a reasoning model; without this it can spend the whole
        # token budget on thoughts and return an empty `parts`. Some API
        # surfaces reject the field, so we retry without it.
        cfg["thinkingConfig"] = {"thinkingBudget": 0}
    return cfg


async def _call_gemini(prompt: str) -> str | None:
    key = (C.GEMINI_API_KEY or "").strip()
    if not key:
        return None
    try:
        import httpx  # already a dependency; no LLM SDK needed

        base = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        url = _GEMINI_URL.format(model=C.LLM_MODEL)

        def _oneline(s: str) -> str:
            return " ".join(s.split())[:300]

        headers = {"x-goog-api-key": key}
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                url, headers=headers, json={**base, "generationConfig": _gen_config(True)})
            if resp.status_code == 400:
                # some API surfaces reject thinkingConfig - retry once without it
                print(f"[cfo.llm] Gemini 400: {_oneline(resp.text)}")
                resp = await client.post(
                    url, headers=headers,
                    json={**base, "generationConfig": _gen_config(False)})

        resp.raise_for_status()
        data = resp.json()
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = " ".join(p.get("text", "").strip() for p in parts).strip()
        if not text:
            print(f"[cfo.llm] Gemini returned no text (finishReason="
                  f"{cand.get('finishReason')!r}) -> template fallback")
        return text or None
    except Exception as exc:  # noqa: BLE001
        print(f"[cfo.llm] Gemini call failed ({exc!r}) -> template fallback")
        return None


async def generate_recommendation(payload: dict) -> dict:
    merchant_id = payload.get("merchant_id") or payload.get("merchant", {}).get("merchant_id")
    ctx_hash = _context_hash(payload)

    try:
        cached = await store.get_llm_cache(merchant_id, ctx_hash, C.LLM_CACHE_TTL_HOURS)
    except Exception:  # noqa: BLE001
        cached = None
    if cached:
        return {
            "recommendation": cached["recommendation"],
            "source": cached.get("source", "llm"),
            "model": cached.get("model", C.LLM_MODEL),
            "cached": True,
            "generated_on": str(cached.get("created_at") or date.today()),
        }

    prompt = build_prompt(payload)
    text = await _call_gemini(prompt)
    source = "llm" if text else "template"
    model = C.LLM_MODEL if text else "template"
    if not text:
        text = template_recommendation(payload)

    try:
        await store.save_llm_cache(merchant_id, ctx_hash, text, model, source)
    except Exception:  # noqa: BLE001
        pass
    return {"recommendation": text, "source": source, "model": model,
            "cached": False, "generated_on": str(date.today())}
