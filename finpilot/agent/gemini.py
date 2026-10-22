"""
The same orchestrating agent, driven by Google Gemini instead of Claude (Gemini API, REST via httpx).

Everything around the model is shared with orchestrator.run_ai: the approved tools and their argument
validation, the independent re-checks of every tool result, live progress events, draft actions the owner
confirms, the step limit, and figure-by-figure verification of the answer with one repair turn.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from finpilot.agent.tools import ToolContext, anthropic_tool_specs

BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-flash-latest"  # only a fallback name; the key check picks a model this key can really use
_ALLOWED = {"type", "description", "enum", "items", "properties", "required", "minimum", "maximum", "minItems", "maxItems", "format", "nullable"}


# ---------------------------------------------------------------- errors (named like the Anthropic SDK's, so the plain-language reasons are shared)


class GeminiError(Exception):
    pass


class AuthenticationError(GeminiError):
    pass


class PermissionDeniedError(GeminiError):
    pass


class RateLimitError(GeminiError):
    pass


class NotFoundError(GeminiError):
    pass


class APIConnectionError(GeminiError):
    pass


class OverloadedError(GeminiError):
    pass


def _raise_for(status: int, body: dict) -> None:
    err = body.get("error", {}) if isinstance(body, dict) else {}
    msg = str(err.get("message", ""))[:300]
    reasons = json.dumps(err.get("details", []))
    if status == 400 and ("API_KEY_INVALID" in reasons or "API key not valid" in msg):
        raise AuthenticationError(msg)
    if status in (401,):
        raise AuthenticationError(msg)
    if status == 403:
        raise PermissionDeniedError(msg)
    if status == 404:
        raise NotFoundError(msg)
    if status == 429:
        raise RateLimitError(msg)
    if status in (500, 502, 503, 504):
        raise OverloadedError(msg)
    raise GeminiError(f"HTTP {status}: {msg}")


def http_post(path: str, body: dict, api_key: str, timeout: float = 120) -> dict:
    import httpx

    for attempt in range(2):
        try:
            r = httpx.post(f"{BASE}/{path}", json=body, headers={"x-goog-api-key": api_key}, timeout=timeout)
        except httpx.HTTPError as e:
            raise APIConnectionError(type(e).__name__) from e
        if r.status_code in (500, 502, 503, 504) and attempt == 0:  # Gemini is sometimes briefly overloaded: one retry
            time.sleep(1.5)
            continue
        data = r.json() if r.content else {}
        if r.status_code >= 400:
            _raise_for(r.status_code, data)
        return data
    return {}


def http_get(path: str, api_key: str, timeout: float = 30) -> dict:
    import httpx

    try:
        r = httpx.get(f"{BASE}/{path}", headers={"x-goog-api-key": api_key}, timeout=timeout)
    except httpx.HTTPError as e:
        raise APIConnectionError(type(e).__name__) from e
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        _raise_for(r.status_code, data)
    return data


# ---------------------------------------------------------------- tool declarations


def _schema(s: dict) -> dict | None:
    """JSON Schema → the OpenAPI subset Gemini's functionDeclarations accept."""
    out: dict[str, Any] = {}
    for k, v in s.items():
        if k not in _ALLOWED:
            continue
        if k == "type":
            out[k] = str(v).upper()
        elif k == "properties":
            props = {name: c for name, c in ((n, _schema(p)) for n, p in v.items()) if c is not None}
            out[k] = props
        elif k == "items":
            out[k] = _schema(v) or {"type": "STRING"}
        else:
            out[k] = v
    if out.get("type") == "OBJECT" and not out.get("properties"):
        return None  # free-form or empty objects aren't accepted; such arguments are optional
    if "required" in out:
        out["required"] = [r for r in out["required"] if r in out.get("properties", {})]
    return out


def function_declarations() -> list[dict]:
    decls = []
    for t in anthropic_tool_specs():
        d = {"name": t["name"], "description": t["description"]}
        params = _schema(t["input_schema"])
        if params:
            d["parameters"] = params
        decls.append(d)
    return decls


# ---------------------------------------------------------------- key check and model choice


def candidates(models: list[dict], preferred: str | None = None) -> list[str]:
    """Models to try, best first: the one already chosen (if this key lists it), then stable 'flash' models newest first,
    then Google's 'gemini-flash-latest' alias. Listing a model doesn't mean it answers: Google retires models for new
    keys while still listing them, so check_key tries each one."""
    names = [m["name"].split("/", 1)[-1] for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]

    def ver(n: str) -> tuple:
        m = re.match(r"gemini-(\d+)(?:\.(\d+))?-flash$", n)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (-1, -1)

    out = [preferred] if preferred and preferred in names else []
    out += [n for n in sorted((n for n in names if ver(n)[0] >= 0), key=ver, reverse=True) if n not in out]
    if "gemini-flash-latest" in names and "gemini-flash-latest" not in out:
        out.append("gemini-flash-latest")
    return out


def pick_model(models: list[dict], preferred: str | None = None) -> str | None:
    """The first candidate (no network call)."""
    c = candidates(models, preferred)
    return c[0] if c else None


PROBE = {"contents": [{"role": "user", "parts": [{"text": "Reply with OK."}]}], "generationConfig": {"maxOutputTokens": 8}}


def check_key(api_key: str, preferred: str | None = None, get: Callable | None = None, post: Callable | None = None) -> str:
    """Raises a GeminiError if the key doesn't work; returns a model that really answers. Lists the models, then sends a
    one-line 'Reply with OK.' to each candidate until one answers — nothing about the business is sent."""
    get, post = get or http_get, post or http_post
    models, token = [], None
    for _ in range(5):
        data = get("models?pageSize=200" + (f"&pageToken={token}" if token else ""), api_key)
        models += data.get("models", [])
        token = data.get("nextPageToken")
        if not token:
            break
    busy = None
    for name in candidates(models, preferred)[:6]:
        try:
            post(f"models/{name}:generateContent", PROBE, api_key)
            return name
        except NotFoundError:  # listed but retired for this key
            continue
        except (OverloadedError, RateLimitError):  # it exists; it's just busy right now
            busy = busy or name
    if busy:
        return busy
    raise NotFoundError("No Gemini text model is available for this key.")


# ---------------------------------------------------------------- the agent loop


def run_gemini(
    question: str,
    ctx: ToolContext,
    api_key: str,
    model: str,
    business: str,
    history: list | None = None,
    prior_results: list | None = None,
    max_steps: int = 8,
    lang: str = "en",
    on_event=None,
    preface: str = "",
    post: Callable | None = None,
):
    from finpilot.agent import orchestrator as o  # shared helpers (imported here to avoid a cycle)

    post = post or http_post
    run = o.AgentRun(question=question, mode="ai", on_event=on_event)
    contents = list(history or []) + [{"role": "user", "parts": [{"text": (preface + "\n\n" + question) if preface else question}]}]
    prior_results = prior_results or []
    decls = function_declarations()
    system = o.system_prompt(ctx, business, lang)
    tool_rounds, repairs_left, force_answer = 0, 1, False

    while True:
        body: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": decls}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192},
        }
        if force_answer:
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        data = post(f"models/{model}:generateContent", body, api_key)
        cands = data.get("candidates") or []
        if not cands:
            run.answer = "Gemini declined to answer this question. Try rephrasing it as a question about the business's records."
            run.warnings.append("The model declined this request" + (f" ({data['promptFeedback'].get('blockReason')})." if data.get("promptFeedback") else "."))
            break
        cand = cands[0]
        parts = (cand.get("content") or {}).get("parts") or []
        contents.append({"role": "model", "parts": parts})  # kept verbatim: thought signatures must round-trip
        calls = [p["functionCall"] for p in parts if isinstance(p, dict) and "functionCall" in p]
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p and not p.get("thought")).strip()
        finish = cand.get("finishReason", "")

        if calls and not force_answer:
            tool_rounds += 1
            if text:
                run.notes.append(text)
                run.emit("note", text=text)
            responses = []
            for c in calls:
                ok, result = o._execute(ctx, run, c.get("name", ""), c.get("args") or {})
                responses.append({"functionResponse": {"name": c.get("name", ""), "response": json.loads(json.dumps(result, default=str))}})
            if tool_rounds >= max_steps:
                force_answer = True
                responses.append({"text": f"Step limit of {max_steps} tool rounds reached. Answer now from the results you have, and say what you could not check."})
                run.warnings.append(f"Stopped after {max_steps} rounds of tool calls.")
            contents.append({"role": "user", "parts": responses})
            continue

        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION") and not text:
            run.answer = "Gemini declined to answer this question. Try rephrasing it as a question about the business's records."
            run.warnings.append("The model declined this request.")
            break
        if finish == "MAX_TOKENS":
            run.answer = text
            run.warnings.append("The answer was cut off at the length limit.")
            break

        report = o._verify(run, ctx, text, prior_results)
        if report.ok or repairs_left == 0:
            run.answer, run.verification = text, report
            if not report.ok:
                run.warnings.extend(report.answer_issues)
            break
        repairs_left -= 1
        run.repaired = True
        force_answer = False
        run.emit("repair", issues=report.answer_issues)
        contents.append({"role": "user", "parts": [{"text": "[Automatic verification — not from the user] Your answer contains "
                                                           + "; ".join(report.answer_issues)
                                                           + ". Every figure, date and record id must appear in a tool result. Call tools if you need the figure, or remove it. Reply with the full corrected answer only."}]})

    if run.verification is None and run.answer:
        run.verification = o._verify(run, ctx, run.answer, prior_results)
        if not run.verification.ok:
            run.warnings.extend(run.verification.answer_issues)
    run.messages = contents
    return run
