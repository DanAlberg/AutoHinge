import json
import time
from typing import Any, Dict

from llm_client import get_default_model, get_llm_client, resolve_model, LLMError
from prompts import LLM3_LONG, LLM3_SHORT, LLM4_LONG, LLM4_SHORT, LLM5_SAFETY
from ai_trace import _ai_trace_log, _ai_trace_log_response, _ai_trace_prompt_lines
from runtime import _log

def run_llm3_long(extracted: Dict[str, Any], model: str | None = None) -> Dict[str, Any]:
    prompt = LLM3_LONG(extracted)
    requested_model = model or get_default_model()
    resolved_model = resolve_model(requested_model)
    trace_lines = [
        f"AI_CALL call_id=llm3_long model={resolved_model} response_format=json_object"
    ]
    trace_lines.extend(_ai_trace_prompt_lines(prompt))
    _ai_trace_log(trace_lines)
    
    t0 = time.perf_counter()
    try:
        resp = get_llm_client().chat.completions.create(
            model=resolved_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        _ai_trace_log_response(
            "llm3_long",
            resolved_model,
            raw="",
            parsed=None,
            duration_ms=dt_ms,
            error=f"call_error: {e}",
        )
        raise LLMError(
            call_id="llm3_long",
            model=resolved_model,
            error_type="call_error",
            error_message=str(e),
            prompt=prompt,
            raw_response="",
            duration_ms=dt_ms,
        )
    
    dt_ms = int((time.perf_counter() - t0) * 1000)
    raw = resp.choices[0].message.content or ""
    
    try:
        parsed = json.loads(raw or "{}")
    except Exception as e:
        _ai_trace_log_response(
            "llm3_long",
            resolved_model,
            raw,
            parsed=None,
            duration_ms=dt_ms,
            error=f"json_parse_error: {e}",
        )
        raise LLMError(
            call_id="llm3_long",
            model=resolved_model,
            error_type="json_parse_error",
            error_message=str(e),
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    if not isinstance(parsed, dict):
        _ai_trace_log_response(
            "llm3_long",
            resolved_model,
            raw,
            parsed=None,
            duration_ms=dt_ms,
            error="parsed_not_dict",
        )
        raise LLMError(
            call_id="llm3_long",
            model=resolved_model,
            error_type="format_error",
            error_message="Response is not a dictionary",
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    parsed["model_used"] = resolved_model
    _ai_trace_log_response(
        "llm3_long",
        resolved_model,
        raw,
        parsed=parsed,
        duration_ms=dt_ms,
    )
    return parsed


def run_llm3_short(extracted: Dict[str, Any], model: str | None = None) -> Dict[str, Any]:
    prompt = LLM3_SHORT(extracted)
    requested_model = model or get_default_model()
    resolved_model = resolve_model(requested_model)
    trace_lines = [
        f"AI_CALL call_id=llm3_short model={resolved_model} response_format=json_object"
    ]
    trace_lines.extend(_ai_trace_prompt_lines(prompt))
    _ai_trace_log(trace_lines)
    
    t0 = time.perf_counter()
    try:
        resp = get_llm_client().chat.completions.create(
            model=resolved_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        _ai_trace_log_response(
            "llm3_short",
            resolved_model,
            raw="",
            parsed=None,
            duration_ms=dt_ms,
            error=f"call_error: {e}",
        )
        raise LLMError(
            call_id="llm3_short",
            model=resolved_model,
            error_type="call_error",
            error_message=str(e),
            prompt=prompt,
            raw_response="",
            duration_ms=dt_ms,
        )
    
    dt_ms = int((time.perf_counter() - t0) * 1000)
    raw = resp.choices[0].message.content or ""
    
    try:
        parsed = json.loads(raw or "{}")
    except Exception as e:
        _ai_trace_log_response(
            "llm3_short",
            resolved_model,
            raw,
            parsed=None,
            duration_ms=dt_ms,
            error=f"json_parse_error: {e}",
        )
        raise LLMError(
            call_id="llm3_short",
            model=resolved_model,
            error_type="json_parse_error",
            error_message=str(e),
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    if not isinstance(parsed, dict):
        _ai_trace_log_response(
            "llm3_short",
            resolved_model,
            raw,
            parsed=None,
            duration_ms=dt_ms,
            error="parsed_not_dict",
        )
        raise LLMError(
            call_id="llm3_short",
            model=resolved_model,
            error_type="format_error",
            error_message="Response is not a dictionary",
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    parsed["model_used"] = resolved_model
    _ai_trace_log_response(
        "llm3_short",
        resolved_model,
        raw,
        parsed=parsed,
        duration_ms=dt_ms,
    )
    return parsed


def _run_llm4_prompt(prompt: str, model: str | None = None) -> Dict[str, Any]:
    requested_model = model or get_default_model()
    resolved_model = resolve_model(requested_model)
    trace_lines = [
        f"AI_CALL call_id=llm4 model={resolved_model} response_format=json_object"
    ]
    trace_lines.extend(_ai_trace_prompt_lines(prompt))
    _ai_trace_log(trace_lines)
    
    t0 = time.perf_counter()
    try:
        resp = get_llm_client().chat.completions.create(
            model=resolved_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        _ai_trace_log_response(
            "llm4",
            resolved_model,
            raw="",
            parsed=None,
            duration_ms=dt_ms,
            error=f"call_error: {e}",
        )
        raise LLMError(
            call_id="llm4",
            model=resolved_model,
            error_type="call_error",
            error_message=str(e),
            prompt=prompt,
            raw_response="",
            duration_ms=dt_ms,
        )
    
    dt_ms = int((time.perf_counter() - t0) * 1000)
    raw = resp.choices[0].message.content or ""
    
    try:
        parsed = json.loads(raw or "{}")
    except Exception as e:
        _ai_trace_log_response(
            "llm4",
            resolved_model,
            raw,
            parsed=None,
            duration_ms=dt_ms,
            error=f"json_parse_error: {e}",
        )
        raise LLMError(
            call_id="llm4",
            model=resolved_model,
            error_type="json_parse_error",
            error_message=str(e),
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    _ai_trace_log_response(
        "llm4",
        resolved_model,
        raw,
        parsed=parsed,
        duration_ms=dt_ms,
    )
    
    if not isinstance(parsed, dict):
        raise LLMError(
            call_id="llm4",
            model=resolved_model,
            error_type="format_error",
            error_message="Response is not a dictionary",
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    parsed["model_used"] = resolved_model
    return parsed


def run_llm4_long(openers_json: Dict[str, Any], model: str | None = None) -> Dict[str, Any]:
    prompt = LLM4_LONG(openers_json)
    return _run_llm4_prompt(prompt, model=model)


def run_llm4_short(openers_json: Dict[str, Any], model: str | None = None) -> Dict[str, Any]:
    prompt = LLM4_SHORT(openers_json)
    return _run_llm4_prompt(prompt, model=model)


def run_llm4(openers_json: Dict[str, Any], model: str | None = None) -> Dict[str, Any]:
    prompt = LLM4_LONG(openers_json)
    return _run_llm4_prompt(prompt, model=model)


def run_llm5_safety(
    extracted: Dict[str, Any],
    decision: str,
    chosen_text: str,
    score_table: str,
    model: str | None = None
) -> Dict[str, Any]:
    prompt = LLM5_SAFETY(extracted, decision, chosen_text, score_table)
    requested_model = model or get_default_model()
    resolved_model = resolve_model(requested_model)
    trace_lines = [
        f"AI_CALL call_id=llm5_safety model={resolved_model} response_format=json_object"
    ]
    trace_lines.extend(_ai_trace_prompt_lines(prompt))
    _ai_trace_log(trace_lines)
    
    t0 = time.perf_counter()
    try:
        resp = get_llm_client().chat.completions.create(
            model=resolved_model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        _ai_trace_log_response(
            "llm5_safety",
            resolved_model,
            raw="",
            parsed=None,
            duration_ms=dt_ms,
            error=f"call_error: {e}",
        )
        raise LLMError(
            call_id="llm5_safety",
            model=resolved_model,
            error_type="call_error",
            error_message=str(e),
            prompt=prompt,
            raw_response="",
            duration_ms=dt_ms,
        )
    
    dt_ms = int((time.perf_counter() - t0) * 1000)
    raw = resp.choices[0].message.content or ""
    
    try:
        parsed = json.loads(raw or "{}")
    except Exception as e:
        _ai_trace_log_response(
            "llm5_safety",
            resolved_model,
            raw,
            parsed=None,
            duration_ms=dt_ms,
            error=f"json_parse_error: {e}",
        )
        raise LLMError(
            call_id="llm5_safety",
            model=resolved_model,
            error_type="json_parse_error",
            error_message=str(e),
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    if not isinstance(parsed, dict):
        _ai_trace_log_response(
            "llm5_safety",
            resolved_model,
            raw,
            parsed=None,
            duration_ms=dt_ms,
            error="parsed_not_dict",
        )
        raise LLMError(
            call_id="llm5_safety",
            model=resolved_model,
            error_type="format_error",
            error_message="Response is not a dictionary",
            prompt=prompt,
            raw_response=raw,
            duration_ms=dt_ms,
        )
    
    _ai_trace_log_response("llm5_safety", resolved_model, raw, parsed=parsed, duration_ms=dt_ms)
    parsed["model_used"] = resolved_model
    return parsed
