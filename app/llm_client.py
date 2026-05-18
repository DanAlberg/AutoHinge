import os
from typing import Any, Dict, List, Optional, Tuple
from types import SimpleNamespace

try:
    from google import genai
except Exception:
    genai = None

class LLMError(Exception):
    """Exception raised when an LLM call fails. Captures all relevant context for debugging."""
    
    def __init__(
        self,
        call_id: str,
        model: str,
        error_type: str,
        error_message: str,
        prompt: str = "",
        raw_response: str = "",
        duration_ms: Optional[int] = None,
    ):
        self.call_id = call_id
        self.model = model
        self.error_type = error_type
        self.error_message = error_message
        self.prompt = prompt
        self.raw_response = raw_response
        self.duration_ms = duration_ms
        super().__init__(f"[{call_id}] {error_type}: {error_message}")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "model": self.model,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "prompt": self.prompt,
            "raw_response": self.raw_response if self.raw_response else None,
            "duration_ms": self.duration_ms,
        }

_CLIENT_CACHE: Dict[Tuple[Any, ...], Any] = {}

def get_large_model() -> str:
    return (os.getenv("GEMINI_LARGE_MODEL") or "gemini-3.1-pro-preview").strip()

def get_small_model() -> str:
    return (os.getenv("GEMINI_SMALL_MODEL") or "gemini-3-flash-preview").strip()

def get_gemini_client() -> Any:
    if genai is None:
        raise RuntimeError("google-genai is required.")
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required.")
    
    cache_key = ("gemini", api_key)
    if cache_key in _CLIENT_CACHE:
        return _CLIENT_CACHE[cache_key]

    client = genai.Client(api_key=api_key)
    _CLIENT_CACHE[cache_key] = client
    return client

def _split_data_url(url: str) -> Optional[Tuple[str, str]]:
    if not url.startswith("data:"):
        return None
    try:
        header, data = url.split(",", 1)
    except ValueError:
        return None
    mime = header[5:].split(";")[0].strip() if header.startswith("data:") else ""
    mime = mime or "application/octet-stream"
    return mime, data

def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)
        return "\n".join([t for t in texts if t]).strip()
    return ""

def _content_parts(content: Any) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    if isinstance(content, str):
        parts.append({"text": content})
        return parts
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append({"text": text})
            elif ptype == "image_url":
                image = part.get("image_url") or {}
                url = image.get("url") if isinstance(image, dict) else ""
                if not isinstance(url, str):
                    continue
                split = _split_data_url(url)
                if split:
                    mime, data = split
                    parts.append({"inline_data": {"mime_type": mime, "data": data}})
                elif url:
                    parts.append({"file_data": {"mime_type": "image/png", "file_uri": url}})
    return parts or [{"text": ""}]

def _openai_messages_to_gemini(messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    contents: List[Dict[str, Any]] = []
    system_chunks: List[str] = []

    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or "user").strip().lower()
        content = msg.get("content", "")
        if role == "system":
            text = _content_text(content)
            if text:
                system_chunks.append(text)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        parts = _content_parts(content)
        contents.append({"role": gemini_role, "parts": parts})

    system_instruction = "\n".join(system_chunks).strip()
    return contents, system_instruction

def _gemini_text_from_response(resp: Any) -> str:
    try:
        parts_out: List[str] = []
        candidates = getattr(resp, "candidates", []) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", []) if content is not None else []
            for part in parts or []:
                if isinstance(part, dict):
                    text = part.get("text")
                else:
                    text = getattr(part, "text", None)
                if isinstance(text, str):
                    parts_out.append(text)
        return "".join(parts_out)
    except Exception:
        return ""

def calculate_cost(model_name: str, usage_metadata: Any) -> float:
    if not usage_metadata:
        return 0.0
    try:
        prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
        candidate_tokens = getattr(usage_metadata, "candidates_token_count", 0) or 0
    except Exception:
        return 0.0
    
    cost = 0.0
    if "pro" in model_name.lower():
        cost += (prompt_tokens / 1_000_000) * 2.00
        cost += (candidate_tokens / 1_000_000) * 12.00
    elif "flash" in model_name.lower():
        cost += (prompt_tokens / 1_000_000) * 0.50
        cost += (candidate_tokens / 1_000_000) * 3.00
        
    return round(cost, 6)

class LLMResponse:
    def __init__(self, content: str, model_name: str, usage_metadata: Any = None):
        self.content = content
        self.model_name = model_name
        self.usage_metadata = usage_metadata
        self.cost_usd = calculate_cost(model_name, usage_metadata)

def generate_completion(
    model_type: str,
    messages: List[Dict[str, Any]],
    response_format: Optional[Dict[str, Any]] = None,
    **kwargs
) -> LLMResponse:
    model = get_large_model() if model_type == "large" else get_small_model()
    client = get_gemini_client()
    contents, system_instruction = _openai_messages_to_gemini(messages)
    
    config: Dict[str, Any] = {}
    if system_instruction:
        config["system_instruction"] = system_instruction
    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
        config["response_mime_type"] = "application/json"
    
    for k in ("temperature", "top_p", "max_output_tokens"):
        if k in kwargs:
            config[k] = kwargs[k]

    if config:
        resp = client.models.generate_content(model=model, contents=contents, config=config)
    else:
        resp = client.models.generate_content(model=model, contents=contents)
        
    text = _gemini_text_from_response(resp)
    
    # Optional usage info
    usage = getattr(resp, "usage_metadata", None)
    
    return LLMResponse(content=text, model_name=model, usage_metadata=usage)
